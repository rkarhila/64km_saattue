"""Self-play training loop with a league of frozen / branched opponents."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

import numpy as np
import torch

from sixtyfivekmconvoy.env.convoy_env import ConvoyEnv
from sixtyfivekmconvoy.env.spaces import MAX_LEGAL, observation_size
from sixtyfivekmconvoy.rl.agent import RLAgent
from sixtyfivekmconvoy.rl.buffer import RolloutBuffer
from sixtyfivekmconvoy.rl.league import League
from sixtyfivekmconvoy.rl.policy import MaskedActorCritic
from sixtyfivekmconvoy.rl.ppo import PPOConfig, PPOTrainer


@dataclass
class SelfPlayConfig:
    num_players: int = 3
    seed: int = 0
    total_timesteps: int = 100_000
    rollout_steps: int = 2048
    checkpoint_every_steps: int = 10_000
    eval_every_steps: int = 10_000
    eval_episodes: int = 8
    opponent_latest_weight: float = 0.35
    include_self_mirror: float = 0.25  # chance all seats use live learner
    hidden: int = 256
    n_layers: int = 2
    device: str = "cpu"
    reward_mode: str = "rank"
    league_name: str = "main"
    ppo: PPOConfig = field(default_factory=PPOConfig)


class SelfPlayTrainer:
    """
    Train one learning policy against a mix of:

    - its own live weights (mirror self-play),
    - frozen league checkpoints (past selves / branches).

    Only the learning seat contributes transitions to the PPO buffer.
    """

    def __init__(
        self,
        league: League,
        config: SelfPlayConfig | None = None,
        *,
        policy: MaskedActorCritic | None = None,
        learner_name: str = "learner",
        parent_id: str | None = None,
        log_fn: Callable[[str], None] | None = None,
    ):
        self.config = config or SelfPlayConfig()
        self.league = league
        self.log = log_fn or (lambda msg: print(msg, flush=True))
        self.device = torch.device(self.config.device)
        self.rng = np.random.default_rng(self.config.seed)

        obs_dim = observation_size(self.config.num_players)
        if policy is None:
            policy = MaskedActorCritic(
                obs_dim=obs_dim,
                hidden=self.config.hidden,
                n_layers=self.config.n_layers,
                num_players=self.config.num_players,
            )
        self.policy = policy.to(self.device)
        self.trainer = PPOTrainer(
            self.policy, self.config.ppo, device=self.device
        )
        self.buffer = RolloutBuffer(
            obs_dim=obs_dim,
            n_actions=MAX_LEGAL,
            capacity=self.config.rollout_steps,
            gamma=self.config.ppo.gamma,
            gae_lambda=self.config.ppo.gae_lambda,
        )
        self.learner_name = learner_name
        self.parent_id = parent_id
        self.global_step = 0
        self.episodes = 0
        self._frozen_cache: dict[str, RLAgent] = {}

        # Ensure the league has at least one seed checkpoint.
        if not self.league.list():
            entry = self.league.add(
                self.policy,
                name=f"{learner_name}-init",
                parent_id=parent_id,
                tags=["init", self.config.league_name],
                config={
                    "num_players": self.config.num_players,
                    "hidden": self.config.hidden,
                    "reward_mode": self.config.reward_mode,
                },
            )
            self.parent_id = entry.id
            self.log(f"league seed checkpoint {entry.id} ({entry.name})")

    # ------------------------------------------------------------------
    # Opponent sampling
    # ------------------------------------------------------------------

    def _load_frozen(self, entry_id: str) -> RLAgent:
        if entry_id not in self._frozen_cache:
            model = self.league.load_model(entry_id, map_location=self.device)
            self._frozen_cache[entry_id] = RLAgent(
                model, deterministic=False, device=self.device
            )
        return self._frozen_cache[entry_id]

    def _assign_opponents(self, learner_seat: int) -> dict[int, RLAgent | None]:
        """
        Map seat → agent. ``None`` means the live learning policy.
        """
        n = self.config.num_players
        seats = {i: None for i in range(n)}  # default: live learner
        seats[learner_seat] = None

        if self.rng.random() < self.config.include_self_mirror:
            return seats

        need = n - 1
        ids = self.league.sample_opponent_ids(
            self.rng,
            k=need,
            exclude=(),
            include_latest_weight=self.config.opponent_latest_weight,
        )
        others = [i for i in range(n) if i != learner_seat]
        for seat, oid in zip(others, ids):
            if oid:
                seats[seat] = self._load_frozen(oid)
        return seats

    # ------------------------------------------------------------------
    # Rollouts
    # ------------------------------------------------------------------

    def _act_live(
        self, obs: np.ndarray, mask: np.ndarray
    ) -> tuple[int, float, float]:
        return self.policy.act(obs, mask, deterministic=False)

    def collect_rollout(self) -> dict[str, float]:
        cfg = self.config
        env = ConvoyEnv(
            num_players=cfg.num_players,
            seed=None,
            reward_mode=cfg.reward_mode,
            max_cycles=50_000,
        )
        self.buffer.clear()
        ep_returns: list[float] = []
        ep_lens: list[int] = []

        while len(self.buffer) < cfg.rollout_steps:
            seed = int(self.rng.integers(0, 2**31 - 1))
            env.reset(seed=seed)
            learner_seat = int(self.rng.integers(0, cfg.num_players))
            seat_agents = self._assign_opponents(learner_seat)
            learner_id = f"player_{learner_seat}"

            ep_reward = 0.0
            ep_len = 0
            last_learner_transition: dict[str, Any] | None = None

            while env.agents and not all(env.terminations.values()):
                agent = env.agent_selection
                info = env.infos[agent]
                legal = info.get("legal_actions") or []
                mask = info.get("action_mask")
                if mask is None:
                    mask = np.zeros(MAX_LEGAL, dtype=np.float32)
                    for i in range(min(len(legal), MAX_LEGAL)):
                        mask[i] = 1.0
                obs = env.observe(agent)
                seat = int(agent.split("_")[1])

                if agent == learner_id and legal:
                    # Finalize previous learner step with reward observed now.
                    if last_learner_transition is not None:
                        self.buffer.add(
                            last_learner_transition["obs"],
                            last_learner_transition["mask"],
                            last_learner_transition["action"],
                            float(env.rewards.get(learner_id, 0.0)),
                            False,
                            last_learner_transition["logprob"],
                            last_learner_transition["value"],
                        )
                        if len(self.buffer) >= cfg.rollout_steps:
                            last_learner_transition = None
                            break
                    action, logp, value = self._act_live(obs, mask)
                    last_learner_transition = {
                        "obs": obs.copy(),
                        "mask": np.asarray(mask, dtype=np.float32).copy(),
                        "action": int(action),
                        "logprob": float(logp),
                        "value": float(value),
                    }
                else:
                    bot = seat_agents.get(seat)
                    if bot is None:
                        # Mirror: live policy, no buffer write.
                        action, _, _ = self._act_live(obs, mask)
                    else:
                        action = bot.act(obs, legal, action_mask=mask)

                env.step(action if legal else 0)
                ep_len += 1
                self.global_step += 1

                if env.terminations.get(agent, False) or all(
                    env.terminations.get(a, False) for a in env.possible_agents
                ):
                    break
                if ep_len > 50_000:
                    break

            # Episode end — credit terminal reward to last learner transition.
            term_r = float(env.rewards.get(learner_id, 0.0))
            # Prefer cumulative if available after terminal broadcast.
            if env.terminations.get(learner_id, False):
                # Re-read terminal rewards from env (set for all agents).
                term_r = float(env.rewards.get(learner_id, term_r))
            ep_reward = float(env._cumulative_rewards.get(learner_id, term_r))
            if last_learner_transition is not None and len(self.buffer) < cfg.rollout_steps:
                self.buffer.add(
                    last_learner_transition["obs"],
                    last_learner_transition["mask"],
                    last_learner_transition["action"],
                    term_r,
                    True,
                    last_learner_transition["logprob"],
                    last_learner_transition["value"],
                )
            self.episodes += 1
            ep_returns.append(ep_reward)
            ep_lens.append(ep_len)

        # Bootstrap value for truncated rollout (not necessarily terminal).
        last_done = True
        last_value = 0.0
        self.buffer.compute_returns_and_advantages(last_value, last_done)
        return {
            "ep_return_mean": float(np.mean(ep_returns)) if ep_returns else 0.0,
            "ep_len_mean": float(np.mean(ep_lens)) if ep_lens else 0.0,
            "episodes": float(len(ep_returns)),
            "buffer_size": float(len(self.buffer)),
        }

    # ------------------------------------------------------------------
    # Eval / checkpoint
    # ------------------------------------------------------------------

    def evaluate(self, n_episodes: int | None = None) -> dict[str, float]:
        n_episodes = n_episodes or self.config.eval_episodes
        env = ConvoyEnv(
            num_players=self.config.num_players,
            reward_mode=self.config.reward_mode,
            max_cycles=50_000,
        )
        live = RLAgent(self.policy, deterministic=True, device=self.device)
        wins = 0
        returns: list[float] = []
        for ep in range(n_episodes):
            seed = int(self.rng.integers(0, 2**31 - 1))
            env.reset(seed=seed)
            learner_seat = ep % self.config.num_players
            learner_id = f"player_{learner_seat}"
            seat_agents = self._assign_opponents(learner_seat)
            steps = 0
            while env.agents and not all(env.terminations.values()):
                agent = env.agent_selection
                info = env.infos[agent]
                legal = info.get("legal_actions") or []
                mask = info.get("action_mask")
                obs = env.observe(agent)
                seat = int(agent.split("_")[1])
                if agent == learner_id:
                    action = live.act(obs, legal, action_mask=mask)
                else:
                    bot = seat_agents.get(seat)
                    if bot is None:
                        action = live.act(obs, legal, action_mask=mask)
                    else:
                        action = bot.act(obs, legal, action_mask=mask)
                env.step(action if legal else 0)
                steps += 1
                if steps > 50_000:
                    break
            ret = float(env._cumulative_rewards.get(learner_id, 0.0))
            returns.append(ret)
            ranking = env.engine.winner_ranking() or []
            if ranking and f"player_{ranking[0]['number']}" == learner_id:
                wins += 1
        return {
            "eval_return_mean": float(np.mean(returns)) if returns else 0.0,
            "eval_win_rate": wins / max(1, n_episodes),
            "eval_episodes": float(n_episodes),
        }

    def checkpoint(self, *, tag: str | None = None, metrics: dict[str, float] | None = None) -> str:
        name = f"{self.learner_name}-step{self.global_step}"
        entry = self.league.add(
            self.policy,
            name=name,
            parent_id=self.parent_id,
            step=self.global_step,
            episodes=self.episodes,
            metrics=metrics or {},
            tags=[self.config.league_name] + ([tag] if tag else []),
            config={"hidden": self.config.hidden, "num_players": self.config.num_players},
        )
        self.parent_id = entry.id
        # Drop frozen cache so new weights can be sampled next.
        self._frozen_cache.clear()
        self.log(
            f"checkpoint {entry.id} {entry.name} "
            f"step={self.global_step} episodes={self.episodes}"
        )
        return entry.id

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------

    def train(self) -> dict[str, Any]:
        cfg = self.config
        t0 = time.time()
        last_ckpt = 0
        last_eval = 0
        history: list[dict[str, float]] = []

        self.log(
            f"self-play start players={cfg.num_players} "
            f"timesteps={cfg.total_timesteps} device={cfg.device}"
        )
        while self.global_step < cfg.total_timesteps:
            roll = self.collect_rollout()
            update = self.trainer.update(self.buffer)
            row = {
                "step": float(self.global_step),
                "episodes": float(self.episodes),
                **roll,
                **update,
            }
            if (
                self.global_step - last_eval >= cfg.eval_every_steps
                or self.global_step >= cfg.total_timesteps
            ):
                ev = self.evaluate()
                row.update(ev)
                last_eval = self.global_step
            history.append(row)
            self.log(
                " | ".join(
                    f"{k}={v:.3f}" if isinstance(v, float) else f"{k}={v}"
                    for k, v in row.items()
                    if k
                    in (
                        "step",
                        "ep_return_mean",
                        "policy_loss",
                        "entropy",
                        "eval_return_mean",
                        "eval_win_rate",
                    )
                )
            )
            if self.global_step - last_ckpt >= cfg.checkpoint_every_steps:
                self.checkpoint(metrics={k: float(row[k]) for k in row if k != "step"})
                last_ckpt = self.global_step

        final_id = self.checkpoint(
            tag="final",
            metrics=history[-1] if history else {},
        )
        elapsed = time.time() - t0
        self.log(f"done in {elapsed:.1f}s final={final_id}")
        return {
            "final_id": final_id,
            "steps": self.global_step,
            "episodes": self.episodes,
            "elapsed_sec": elapsed,
            "history": history,
        }
