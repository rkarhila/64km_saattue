"""One game process per environment. The parent only sees float observations."""

from __future__ import annotations

import multiprocessing as mp
from typing import Any

import numpy as np

from sixtyfivekmconvoy.env.spaces import MAX_LEGAL


def _pack(env: Any) -> dict[str, Any]:
    rewards = {
        a: float(env.rewards.get(a, 0.0)) for a in env.possible_agents
    }
    cumulative = {
        a: float(env._cumulative_rewards.get(a, 0.0)) for a in env.possible_agents
    }
    over = (not env.agents) or all(env.terminations.values()) or all(
        env.truncations.values()
    )
    if over:
        return {
            "over": True,
            "agent": None,
            "rewards": rewards,
            "cumulative": cumulative,
        }
    agent = env.agent_selection
    info = env.infos.get(agent) or {}
    spec = info.get("choice_spec")
    if spec is not None:
        spec = {
            "options": list(spec.get("options") or []),
            "num_choices": int(spec.get("num_choices") or 0),
            "ordered": bool(spec.get("ordered")),
            "choicetype": int(spec.get("choicetype") if spec.get("choicetype") is not None else -1),
        }
    mask = info.get("action_mask")
    if mask is None:
        mask = np.zeros(MAX_LEGAL, dtype=np.float32)
    return {
        "over": False,
        "agent": agent,
        "obs": np.asarray(env.observe(agent), dtype=np.float32),
        "mask": np.asarray(mask, dtype=np.float32),
        "legal": list(info.get("legal_actions") or []),
        "spec": spec,
        "rewards": rewards,
        "cumulative": cumulative,
    }


def _worker(conn: Any, env_kwargs: dict[str, Any]) -> None:
    from sixtyfivekmconvoy.env.convoy_env import ConvoyEnv

    env = ConvoyEnv(**env_kwargs)
    try:
        while True:
            cmd, data = conn.recv()
            if cmd == "close":
                break
            try:
                if cmd == "reset":
                    env.reset(seed=data)
                elif cmd == "step":
                    env.step(data)
                else:
                    raise RuntimeError(f"unknown env command {cmd}")
                conn.send(_pack(env))
            except Exception as exc:  # noqa: BLE001 — report across the pipe
                conn.send({"error": f"{type(exc).__name__}: {exc}"})
    finally:
        conn.close()


class RemoteEnv:
    """Parent-side handle. ``begin_*`` then ``finish_*`` so several games overlap."""

    def __init__(self, conn: Any) -> None:
        self.conn = conn
        self.agents: list[str] = []
        self.terminations: dict[str, bool] = {}
        self.truncations: dict[str, bool] = {}
        self.rewards: dict[str, float] = {}
        self._cumulative_rewards: dict[str, float] = {}
        self.infos: dict[str, dict[str, Any]] = {}
        self.agent_selection: str | None = None
        self.possible_agents: list[str] = []

    def begin_reset(self, seed: int) -> None:
        self.conn.send(("reset", int(seed)))

    def finish_reset(self) -> None:
        self._apply(self.conn.recv())

    def begin_step(self, action: int | list[int]) -> None:
        self.conn.send(("step", action))

    def finish_step(self) -> None:
        self._apply(self.conn.recv())

    def observe(self, agent: str) -> np.ndarray:
        del agent
        info = self.infos.get(self.agent_selection or "") or {}
        obs = info.get("obs")
        if obs is None:
            raise RuntimeError("remote env has no observation")
        return obs

    def _apply(self, pack: dict[str, Any]) -> None:
        if pack.get("error"):
            raise RuntimeError(pack["error"])
        self.rewards = pack.get("rewards") or {}
        self._cumulative_rewards = pack.get("cumulative") or {}
        self.possible_agents = list(self.rewards)
        if pack.get("over"):
            self.agents = []
            self.terminations = {}
            self.truncations = {}
            self.infos = {}
            self.agent_selection = None
            return
        agent = pack["agent"]
        self.agents = [agent]
        self.terminations = {agent: False}
        self.truncations = {agent: False}
        self.agent_selection = agent
        self.infos = {
            agent: {
                "legal_actions": pack.get("legal") or [],
                "action_mask": pack.get("mask"),
                "choice_spec": pack.get("spec"),
                "obs": pack.get("obs"),
                "raw": None,
            }
        }


class GamePool:
    def __init__(self, n: int, env_kwargs: dict[str, Any]) -> None:
        self.n = int(n)
        ctx = mp.get_context("spawn")
        self.conns: list[Any] = []
        self.procs: list[mp.Process] = []
        self.envs: list[RemoteEnv] = []
        for _ in range(self.n):
            parent, child = ctx.Pipe(duplex=True)
            proc = ctx.Process(
                target=_worker,
                args=(child, env_kwargs),
                daemon=True,
            )
            proc.start()
            child.close()
            self.conns.append(parent)
            self.procs.append(proc)
            self.envs.append(RemoteEnv(parent))

    def close(self) -> None:
        for conn in self.conns:
            try:
                conn.send(("close", None))
            except (OSError, BrokenPipeError):
                pass
        for proc in self.procs:
            proc.join(timeout=2)
            if proc.is_alive():
                proc.terminate()
        self.conns.clear()
        self.procs.clear()
        self.envs.clear()
