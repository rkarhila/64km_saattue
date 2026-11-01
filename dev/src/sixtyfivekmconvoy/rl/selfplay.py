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
    width: int = 128
    num_envs: int = 8
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
                width=self.config.width,
                num_players=self.config.num_players,
            )
        self.policy = policy.to(self.device)
        self.policy.eval()
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

        if not self.league.list():
            entry = self.league.add(
                self.policy,
                name=f"{learner_name}-init",
                parent_id=parent_id,
                tags=["init", self.config.league_name, "transformer"],
                config={
                    "num_players": self.config.num_players,
                    "hidden": self.config.hidden,
                    "width": self.config.width,
                    "num_envs": self.config.num_envs,
                    "reward_mode": self.config.reward_mode,
                    "arch": "transformer_ar",
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

    def _new_slot(self) -> dict[str, Any]:
        slot: dict[str, Any] = {"env": self._make_env()}
        self._reset_slot(slot)
        return slot

    def _reset_slot(self, slot: dict[str, Any]) -> None:
        cfg = self.config
        seed = int(self.rng.integers(0, 2**31 - 1))
        env: ConvoyEnv = slot["env"]
        env.reset(seed=seed)
        learner_seat = int(self.rng.integers(0, cfg.num_players))
        seat_agents = self._assign_opponents(learner_seat)
        for bot in seat_agents.values():
            if bot is not None:
                bot.reset_memory()
        slot["learner_id"] = f"player_{learner_seat}"
        slot["seat_agents"] = seat_agents
        slot["pending"] = None
        slot["pending_reward"] = 0.0
        slot["traj"] = []
        slot["ep_len"] = 0
        slot["finished"] = False

    def _episode_over(self, slot: dict[str, Any]) -> bool:
        env: ConvoyEnv = slot["env"]
        if slot["ep_len"] > 50_000:
            return True
        if not env.agents:
            return True
        if all(env.terminations.values()) or all(env.truncations.values()):
            return True
        return False

    def _close_slot(
        self,
        slot: dict[str, Any],
        ep_returns: list[float],
        ep_lens: list[int],
    ) -> None:
        if slot["pending"] is not None:
            step = dict(slot["pending"])
            step["reward"] = float(slot["pending_reward"])
            step["done"] = True
            slot["traj"].append(step)
            slot["pending"] = None
            slot["pending_reward"] = 0.0
        if len(self.buffer) < self.config.rollout_steps and slot["traj"]:
            self.buffer.extend_episode(slot["traj"])
        env: ConvoyEnv = slot["env"]
        learner_id = slot["learner_id"]
        ep_returns.append(float(env._cumulative_rewards.get(learner_id, 0.0)))
        ep_lens.append(int(slot["ep_len"]))
        self.episodes += 1
        slot["traj"] = []
        slot["finished"] = True

    def _mask_for(self, info: dict[str, Any], legal: list) -> np.ndarray:
        mask = info.get("action_mask")
        if mask is None:
            mask = np.zeros(MAX_LEGAL, dtype=np.float32)
            for i in range(min(len(legal), MAX_LEGAL)):
                mask[i] = 1.0
        return np.asarray(mask, dtype=np.float32)

    def _decision(self, slot: dict[str, Any]) -> dict[str, Any] | None:
        if slot["finished"] or self._episode_over(slot):
            return None
        env: ConvoyEnv = slot["env"]
        agent = env.agent_selection
        info = env.infos[agent]
        legal = list(info.get("legal_actions") or [])
        if not legal:
            return {"kind": "empty", "slot": slot}
        seat = int(agent.split("_")[1])
        obs = np.asarray(env.observe(agent), dtype=np.float32)
        mask = self._mask_for(info, legal)
        spec = info.get("choice_spec") or {}
        raw = info.get("raw") or {}
        choice = raw.get("choice") if isinstance(raw, dict) else None
        item = {
            "slot": slot,
            "agent": agent,
            "seat": seat,
            "obs": obs,
            "mask": mask,
            "legal": legal,
            "spec": spec,
            "choice": choice,
        }
        if agent == slot["learner_id"]:
            item["kind"] = "live"
            item["is_learner"] = True
            return item
        bot = slot["seat_agents"].get(seat)
        if bot is None:
            item["kind"] = "live"
            item["is_learner"] = False
            return item
        item["kind"] = "frozen"
        item["bot"] = bot
        return item

    def _commit_pending(self, slot: dict[str, Any]) -> None:
        if slot["pending"] is None:
            return
        step = dict(slot["pending"])
        step["reward"] = float(slot["pending_reward"])
        step["done"] = False
        slot["traj"].append(step)
        slot["pending"] = None
        slot["pending_reward"] = 0.0

    def _apply_env_step(self, slot: dict[str, Any], action: int | list[int]) -> None:
        env: ConvoyEnv = slot["env"]
        env.step(action)
        slot["ep_len"] += 1
        self.global_step += 1
        if slot["pending"] is not None:
            slot["pending_reward"] += float(
                env.rewards.get(slot["learner_id"], 0.0)
            )

    def _spec_fields(
        self, item: dict[str, Any]
    ) -> tuple[list[Any] | None, bool | None, int | None]:
        spec = item.get("spec") or {}
        choice = item.get("choice") or {}
        options = spec.get("options")
        if options is None and isinstance(choice, dict):
            options = choice.get("options")
        options_l = list(options) if options is not None else None
        if "ordered" in spec:
            ordered: bool | None = bool(spec.get("ordered"))
        else:
            ordered = None
        if spec.get("num_choices") is not None:
            num_choices: int | None = int(spec.get("num_choices") or 0)
        elif isinstance(choice, dict) and choice.get("num_choice") is not None:
            num_choices = int(choice.get("num_choice") or 0)
        else:
            num_choices = None
        return options_l, ordered, num_choices

    def _action_from_result(
        self,
        result: tuple[int, float, float, list[int], list[int]],
        legal: list,
    ) -> int | list[int]:
        flat_idx, _logp, _value, _picks, choice_vec = result
        if choice_vec:
            if choice_vec in legal:
                return list(choice_vec)
            target = sorted(choice_vec)
            for vec in legal:
                if sorted(vec) == target:
                    return list(vec)
        if 0 <= flat_idx < len(legal):
            return flat_idx
        return 0

    def _step_live_batch(self, items: list[dict[str, Any]]) -> None:
        if not items:
            return
        obs = np.stack([it["obs"] for it in items])
        mask = np.stack([it["mask"] for it in items])
        options: list[list[Any] | None] = []
        ordered: list[bool | None] = []
        num_choices: list[int | None] = []
        for it in items:
            opt, ord_flag, n = self._spec_fields(it)
            options.append(opt)
            ordered.append(ord_flag)
            num_choices.append(n)
        results = self.policy.act_batch(
            obs,
            mask,
            deterministic=False,
            options=options,
            ordered=ordered,
            num_choices=num_choices,
        )
        for it, result in zip(items, results):
            slot = it["slot"]
            if it["is_learner"]:
                self._commit_pending(slot)
                flat_idx, logp, value, picks, choice_vec = result
                slot["pending"] = {
                    "obs": it["obs"].copy(),
                    "mask": it["mask"].copy(),
                    "action_idx": int(flat_idx) if flat_idx >= 0 else 0,
                    "logprob": float(logp),
                    "value": float(value),
                    "picks": list(picks),
                    "num_picks": len(picks) if choice_vec else 0,
                }
                slot["pending_reward"] = 0.0
            self._apply_env_step(slot, self._action_from_result(result, it["legal"]))

    def _step_frozen_batch(self, items: list[dict[str, Any]]) -> None:
        if not items:
            return
        bot: RLAgent = items[0]["bot"]
        obs = np.stack([it["obs"] for it in items])
        mask = np.stack([it["mask"] for it in items])
        options = []
        ordered = []
        num_choices = []
        for it in items:
            opt, ord_flag, n = self._spec_fields(it)
            if opt is None and isinstance(it.get("choice"), dict):
                opt = list(it["choice"].get("options") or [])
            options.append(opt)
            ordered.append(ord_flag)
            num_choices.append(n)
        results = bot.policy.act_batch(
            obs,
            mask,
            deterministic=bot.deterministic,
            options=options,
            ordered=ordered,
            num_choices=num_choices,
        )
        for it, result in zip(items, results):
            self._apply_env_step(
                it["slot"], self._action_from_result(result, it["legal"])
            )

    def collect_rollout(self) -> dict[str, float]:
        """Play ``num_envs`` games in flight and batch their decisions."""
        cfg = self.config
        n_env = max(1, int(cfg.num_envs))
        self.buffer.clear()
        self.policy.eval()
        slots = [self._new_slot() for _ in range(n_env)]
        ep_returns: list[float] = []
        ep_lens: list[int] = []
        guard = 0
        limit = cfg.rollout_steps * 40 + n_env * 100

        while len(self.buffer) < cfg.rollout_steps and guard < limit:
            guard += 1
            for slot in slots:
                if not slot["finished"] and self._episode_over(slot):
                    self._close_slot(slot, ep_returns, ep_lens)
            if len(self.buffer) >= cfg.rollout_steps:
                break
            for slot in slots:
                if slot["finished"]:
                    if len(self.buffer) >= cfg.rollout_steps:
                        break
                    self._reset_slot(slot)

            live: list[dict[str, Any]] = []
            frozen: dict[int, list[dict[str, Any]]] = {}
            for slot in slots:
                if slot["finished"]:
                    continue
                item = self._decision(slot)
                if item is None:
                    continue
                if item["kind"] == "empty":
                    self._apply_env_step(slot, 0)
                    continue
                if item["kind"] == "live":
                    live.append(item)
                else:
                    frozen.setdefault(id(item["bot"]), []).append(item)
            if live:
                self._step_live_batch(live)
            for group in frozen.values():
                self._step_frozen_batch(group)
            if not live and not frozen and all(s["finished"] for s in slots):
                break

        return {
            "ep_return_mean": float(np.mean(ep_returns)) if ep_returns else 0.0,
            "ep_len_mean": float(np.mean(ep_lens)) if ep_lens else 0.0,
            "episodes": float(len(ep_returns)),
            "buffer_size": float(len(self.buffer)),
            "num_envs": float(n_env),
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
            tags=[self.config.league_name, "transformer"] + ([tag] if tag else []),
            config={
                "hidden": self.config.hidden,
                "width": self.config.width,
                "num_envs": self.config.num_envs,
                "num_players": self.config.num_players,
                "arch": "transformer_ar",
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
            f"self-play transformer start players={cfg.num_players} "
            f"timesteps={cfg.total_timesteps} "
            f"max_seconds={cfg.max_seconds} device={cfg.device} "
            f"width={cfg.width} envs={cfg.num_envs} "
            f"minibatch={cfg.ppo.minibatch_size} "
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
