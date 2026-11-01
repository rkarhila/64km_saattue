"""Self-play training loop with a league of frozen / branched opponents."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
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
    max_seconds: float | None = None  # wall-clock stop after current rollout
    rollout_steps: int = 2048
    checkpoint_every_steps: int = 10_000
    eval_every_steps: int = 10_000
    eval_episodes: int = 8
    opponent_latest_weight: float = 0.35
    include_self_mirror: float = 0.25  # chance all seats use live learner
    # Prefer these checkpoint ids as opponents (e.g. sibling fork).
    prefer_opponent_ids: list[str] = field(default_factory=list)
    prefer_opponent_weight: float = 0.7
    hidden: int = 256
    n_layers: int = 2
    lstm_hidden: int = 512
    lstm_layers: int = 2
    device: str = "cpu"
    reward_mode: str = "win"
    pp_reward: float = 0.25
    cash_reward: float = 0.05
    win_reward: float = 1.0
    lose_reward: float = 0.0
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
                lstm_hidden=self.config.lstm_hidden,
                lstm_layers=self.config.lstm_layers,
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
            lstm_hidden=self.policy.lstm_hidden,
            lstm_layers=self.policy.lstm_layers,
        )
        self.learner_name = learner_name
        self.parent_id = parent_id
        self.global_step = 0
        self.episodes = 0
        self._frozen_cache: dict[str, RLAgent] = {}

        if not self.league.list():
            entry = self.league.add(
                self.policy,
                name=f"{learner_name}-init",
                parent_id=parent_id,
                tags=["init", self.config.league_name, "rnn"],
                config={
                    "num_players": self.config.num_players,
                    "hidden": self.config.hidden,
                    "lstm_hidden": self.config.lstm_hidden,
                    "lstm_layers": self.config.lstm_layers,
                    "reward_mode": self.config.reward_mode,
                    "arch": "lstm_ar",
                },
            )
            self.parent_id = entry.id
            self.log(f"league seed checkpoint {entry.id} ({entry.name})")

    def _load_frozen(self, entry_id: str) -> RLAgent:
        if entry_id not in self._frozen_cache:
            model = self.league.load_model(entry_id, map_location=self.device)
            self._frozen_cache[entry_id] = RLAgent(
                model, deterministic=False, device=self.device
            )
        return self._frozen_cache[entry_id]

    def _make_env(self, *, seed: int | None = None) -> ConvoyEnv:
        cfg = self.config
        return ConvoyEnv(
            num_players=cfg.num_players,
            seed=seed,
            reward_mode=cfg.reward_mode,
            max_cycles=50_000,
            pp_reward=cfg.pp_reward,
            cash_reward=cfg.cash_reward,
            win_reward=cfg.win_reward,
            lose_reward=cfg.lose_reward,
        )

    def _assign_opponents(self, learner_seat: int) -> dict[int, RLAgent | None]:
        n = self.config.num_players
        seats: dict[int, RLAgent | None] = {i: None for i in range(n)}
        seats[learner_seat] = None

        if self.rng.random() < self.config.include_self_mirror:
            return seats

        need = n - 1
        ids = self.league.sample_opponent_ids(
            self.rng,
            k=need,
            exclude=(),
            include_latest_weight=self.config.opponent_latest_weight,
            prefer_ids=self.config.prefer_opponent_ids or None,
            prefer_id_weight=self.config.prefer_opponent_weight,
        )
        others = [i for i in range(n) if i != learner_seat]
        for seat, oid in zip(others, ids):
            if oid:
                seats[seat] = self._load_frozen(oid)
        return seats

    def _hx_numpy(
        self, hx: tuple[torch.Tensor, torch.Tensor] | None
    ) -> tuple[np.ndarray, np.ndarray]:
        size = self.policy.lstm_state_size
        if hx is None:
            z = np.zeros(size, dtype=np.float32)
            return z, z.copy()
        h, c = hx
        return (
            h.detach().cpu().numpy().reshape(-1)[:size],
            c.detach().cpu().numpy().reshape(-1)[:size],
        )

    def _act_live(
        self,
        obs: np.ndarray,
        mask: np.ndarray,
        *,
        hx: tuple[torch.Tensor, torch.Tensor] | None,
        choice_spec: dict[str, Any] | None,
    ) -> tuple[int | list[int], float, float, tuple[torch.Tensor, torch.Tensor], list[int], int]:
        options = None
        ordered = None
        num_choices = None
        if choice_spec:
            options = list(choice_spec.get("options") or [])
            ordered = bool(choice_spec.get("ordered"))
            num_choices = int(choice_spec.get("num_choices") or 0)
        flat_idx, logp, value, hx2, picks, choice_vec = self.policy.act(
            obs,
            mask,
            deterministic=False,
            hx=hx,
            options=options,
            ordered=ordered,
            num_choices=num_choices,
        )
        action: int | list[int]
        if choice_vec:
            action = choice_vec
        else:
            action = flat_idx if flat_idx >= 0 else 0
        return action, logp, value, hx2, picks, num_choices or len(picks)

    def collect_rollout(self) -> dict[str, float]:
        cfg = self.config
        env = self._make_env()
        self.buffer.clear()
        ep_returns: list[float] = []
        ep_lens: list[int] = []

        while len(self.buffer) < cfg.rollout_steps:
            seed = int(self.rng.integers(0, 2**31 - 1))
            env.reset(seed=seed)
            learner_seat = int(self.rng.integers(0, cfg.num_players))
            seat_agents = self._assign_opponents(learner_seat)
            for bot in seat_agents.values():
                if bot is not None:
                    bot.reset_memory()
            learner_id = f"player_{learner_seat}"
            live_hx: dict[int, tuple[torch.Tensor, torch.Tensor] | None] = {
                i: None for i in range(cfg.num_players)
            }

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
                choice_spec = info.get("choice_spec")

                if agent == learner_id and legal:
                    if last_learner_transition is not None:
                        self.buffer.add(
                            last_learner_transition["obs"],
                            last_learner_transition["mask"],
                            last_learner_transition["action_idx"],
                            float(env.rewards.get(learner_id, 0.0)),
                            False,
                            last_learner_transition["logprob"],
                            last_learner_transition["value"],
                            picks=last_learner_transition["picks"],
                            num_picks=last_learner_transition["num_picks"],
                            h0=last_learner_transition["h0"],
                            c0=last_learner_transition["c0"],
                        )
                        if len(self.buffer) >= cfg.rollout_steps:
                            last_learner_transition = None
                            break
                    h0, c0 = self._hx_numpy(live_hx[seat])
                    action, logp, value, hx2, picks, n_picks = self._act_live(
                        obs, mask, hx=live_hx[seat], choice_spec=choice_spec
                    )
                    live_hx[seat] = hx2
                    action_idx = action if isinstance(action, int) else -1
                    last_learner_transition = {
                        "obs": obs.copy(),
                        "mask": np.asarray(mask, dtype=np.float32).copy(),
                        "action": action,
                        "action_idx": int(action_idx) if action_idx >= 0 else 0,
                        "logprob": float(logp),
                        "value": float(value),
                        "picks": list(picks),
                        "num_picks": int(n_picks),
                        "h0": h0,
                        "c0": c0,
                    }
                else:
                    bot = seat_agents.get(seat)
                    if bot is None:
                        action, _, _, hx2, _, _ = self._act_live(
                            obs, mask, hx=live_hx[seat], choice_spec=choice_spec
                        )
                        live_hx[seat] = hx2
                    else:
                        raw = info.get("raw") or {}
                        action = bot.act(
                            obs,
                            legal,
                            action_mask=mask,
                            raw_choice=raw.get("choice"),
                        )

                env.step(action if legal else 0)
                ep_len += 1
                self.global_step += 1

                if env.terminations.get(agent, False) or all(
                    env.terminations.get(a, False) for a in env.possible_agents
                ):
                    break
                if ep_len > 50_000:
                    break

            term_r = float(env.rewards.get(learner_id, 0.0))
            if env.terminations.get(learner_id, False):
                term_r = float(env.rewards.get(learner_id, term_r))
            ep_reward = float(env._cumulative_rewards.get(learner_id, term_r))
            if last_learner_transition is not None and len(self.buffer) < cfg.rollout_steps:
                self.buffer.add(
                    last_learner_transition["obs"],
                    last_learner_transition["mask"],
                    last_learner_transition["action_idx"],
                    term_r,
                    True,
                    last_learner_transition["logprob"],
                    last_learner_transition["value"],
                    picks=last_learner_transition["picks"],
                    num_picks=last_learner_transition["num_picks"],
                    h0=last_learner_transition["h0"],
                    c0=last_learner_transition["c0"],
                )
            self.episodes += 1
            ep_returns.append(ep_reward)
            ep_lens.append(ep_len)

        last_done = True
        last_value = 0.0
        self.buffer.compute_returns_and_advantages(last_value, last_done)
        return {
            "ep_return_mean": float(np.mean(ep_returns)) if ep_returns else 0.0,
            "ep_len_mean": float(np.mean(ep_lens)) if ep_lens else 0.0,
            "episodes": float(len(ep_returns)),
            "buffer_size": float(len(self.buffer)),
        }

    def evaluate(self, n_episodes: int | None = None) -> dict[str, float]:
        n_episodes = n_episodes or self.config.eval_episodes
        env = self._make_env()
        live = RLAgent(self.policy, deterministic=True, device=self.device)
        wins = 0
        returns: list[float] = []
        for ep in range(n_episodes):
            seed = int(self.rng.integers(0, 2**31 - 1))
            env.reset(seed=seed)
            learner_seat = ep % self.config.num_players
            learner_id = f"player_{learner_seat}"
            seat_agents = self._assign_opponents(learner_seat)
            live.reset_memory()
            for bot in seat_agents.values():
                if bot is not None:
                    bot.reset_memory()
            steps = 0
            while env.agents and not all(env.terminations.values()):
                agent = env.agent_selection
                info = env.infos[agent]
                legal = info.get("legal_actions") or []
                mask = info.get("action_mask")
                obs = env.observe(agent)
                seat = int(agent.split("_")[1])
                raw = info.get("raw") or {}
                if agent == learner_id:
                    action = live.act(
                        obs, legal, action_mask=mask, raw_choice=raw.get("choice")
                    )
                else:
                    bot = seat_agents.get(seat)
                    if bot is None:
                        action = live.act(
                            obs,
                            legal,
                            action_mask=mask,
                            raw_choice=raw.get("choice"),
                        )
                    else:
                        action = bot.act(
                            obs,
                            legal,
                            action_mask=mask,
                            raw_choice=raw.get("choice"),
                        )
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
            tags=[self.config.league_name, "rnn"] + ([tag] if tag else []),
            config={
                "hidden": self.config.hidden,
                "lstm_hidden": self.config.lstm_hidden,
                "lstm_layers": self.config.lstm_layers,
                "num_players": self.config.num_players,
                "arch": "lstm_ar",
            },
        )
        self.parent_id = entry.id
        self._frozen_cache.clear()
        self.log(
            f"checkpoint {entry.id} {entry.name} "
            f"step={self.global_step} episodes={self.episodes}"
        )
        return entry.id

    def train(self) -> dict[str, Any]:
        cfg = self.config
        t0 = time.time()
        start_step = self.global_step
        last_ckpt = self.global_step
        last_eval = self.global_step
        history: list[dict[str, float]] = []
        deadline = (
            t0 + float(cfg.max_seconds) if cfg.max_seconds is not None else None
        )

        self.log(
            f"self-play RNN start players={cfg.num_players} "
            f"timesteps={cfg.total_timesteps} "
            f"max_seconds={cfg.max_seconds} device={cfg.device} "
            f"lstm={cfg.lstm_hidden}x{cfg.lstm_layers} bptt={cfg.ppo.bptt_len} "
            f"pp={cfg.pp_reward} cash={cfg.cash_reward} ent={cfg.ppo.ent_coef}"
        )
        while self.global_step < cfg.total_timesteps:
            if deadline is not None and time.time() >= deadline:
                self.log(
                    f"wall-clock deadline reached "
                    f"({cfg.max_seconds:.0f}s) at step={self.global_step}"
                )
                break
            roll = self.collect_rollout()
            update = self.trainer.update(self.buffer)
            elapsed = max(1e-6, time.time() - t0)
            steps_delta = max(0, self.global_step - start_step)
            sps = steps_delta / elapsed
            row = {
                "step": float(self.global_step),
                "episodes": float(self.episodes),
                "elapsed_sec": float(elapsed),
                "steps_per_sec": float(sps),
                **roll,
                **update,
            }
            hit_step_cap = self.global_step >= cfg.total_timesteps
            hit_deadline = deadline is not None and time.time() >= deadline
            if (
                self.global_step - last_eval >= cfg.eval_every_steps
                or hit_step_cap
                or hit_deadline
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
                        "steps_per_sec",
                    )
                )
            )
            if self.global_step - last_ckpt >= cfg.checkpoint_every_steps:
                self.checkpoint(metrics={k: float(row[k]) for k in row if k != "step"})
                last_ckpt = self.global_step
            if hit_deadline:
                break

        final_id = self.checkpoint(
            tag="final",
            metrics=history[-1] if history else {},
        )
        elapsed = time.time() - t0
        sps = (self.global_step - start_step) / max(1e-6, elapsed)
        self.log(
            f"done in {elapsed:.1f}s final={final_id} "
            f"steps={self.global_step} sps={sps:.1f}"
        )
        return {
            "final_id": final_id,
            "steps": self.global_step,
            "episodes": self.episodes,
            "elapsed_sec": elapsed,
            "steps_per_sec": sps,
            "history": history,
        }
