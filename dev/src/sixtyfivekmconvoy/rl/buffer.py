"""On-policy rollout storage. GAE is computed per episode, then concatenated."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import torch

from sixtyfivekmconvoy.env.spaces import MAX_PICKS


@dataclass
class RolloutBatch:
    obs: torch.Tensor
    masks: torch.Tensor
    actions: torch.Tensor
    picks: torch.Tensor
    num_picks: torch.Tensor
    logprobs: torch.Tensor
    advantages: torch.Tensor
    returns: torch.Tensor
    values: torch.Tensor
    dones: torch.Tensor


@dataclass
class RolloutBuffer:
    obs_dim: int
    n_actions: int
    capacity: int
    gamma: float = 0.99
    gae_lambda: float = 0.95
    max_picks: int = MAX_PICKS

    obs: np.ndarray = field(init=False)
    masks: np.ndarray = field(init=False)
    actions: np.ndarray = field(init=False)
    picks: np.ndarray = field(init=False)
    num_picks: np.ndarray = field(init=False)
    rewards: np.ndarray = field(init=False)
    dones: np.ndarray = field(init=False)
    logprobs: np.ndarray = field(init=False)
    values: np.ndarray = field(init=False)
    advantages: np.ndarray = field(init=False)
    returns: np.ndarray = field(init=False)
    pos: int = field(default=0, init=False)

    def __post_init__(self) -> None:
        self.obs = np.zeros((self.capacity, self.obs_dim), dtype=np.float32)
        self.masks = np.zeros((self.capacity, self.n_actions), dtype=np.float32)
        self.actions = np.zeros((self.capacity,), dtype=np.int64)
        self.picks = np.zeros((self.capacity, self.max_picks), dtype=np.int64)
        self.num_picks = np.zeros((self.capacity,), dtype=np.int64)
        self.rewards = np.zeros((self.capacity,), dtype=np.float32)
        self.dones = np.zeros((self.capacity,), dtype=np.float32)
        self.logprobs = np.zeros((self.capacity,), dtype=np.float32)
        self.values = np.zeros((self.capacity,), dtype=np.float32)
        self.advantages = np.zeros((self.capacity,), dtype=np.float32)
        self.returns = np.zeros((self.capacity,), dtype=np.float32)
        self.pos = 0

    def __len__(self) -> int:
        return self.pos

    def clear(self) -> None:
        self.pos = 0

    def _gae(
        self,
        rewards: np.ndarray,
        values: np.ndarray,
        dones: np.ndarray,
        *,
        bootstrap: float,
        terminated: bool,
    ) -> np.ndarray:
        """GAE over one episode. ``dones[t]`` means the episode ended at t."""
        n = len(rewards)
        adv = np.zeros(n, dtype=np.float32)
        last = 0.0
        for t in reversed(range(n)):
            if t == n - 1:
                if terminated:
                    next_v = 0.0
                    nonterminal = 0.0
                else:
                    next_v = float(bootstrap)
                    nonterminal = 1.0
            else:
                nonterminal = 1.0 - float(dones[t])
                next_v = float(values[t + 1]) if nonterminal else 0.0
            delta = rewards[t] + self.gamma * next_v * nonterminal - values[t]
            last = delta + self.gamma * self.gae_lambda * nonterminal * last
            adv[t] = last
        return adv

    def extend_episode(self, steps: list[dict[str, Any]]) -> int:
        """
        Append one episode and its advantages.

        The last step should have ``done=True``. If the buffer fills mid-episode,
        the kept prefix bootstraps from the next step's value. Returns how many
        steps were stored.
        """
        if not steps or self.pos >= self.capacity:
            return 0
        room = self.capacity - self.pos
        use = steps[:room]
        cut = len(use) < len(steps)
        n = len(use)
        rewards = np.asarray([float(s["reward"]) for s in use], dtype=np.float32)
        values = np.asarray([float(s["value"]) for s in use], dtype=np.float32)
        dones = np.asarray(
            [1.0 if s.get("done") else 0.0 for s in use], dtype=np.float32
        )
        if cut:
            adv = self._gae(
                rewards,
                values,
                dones,
                bootstrap=float(steps[n]["value"]),
                terminated=False,
            )
        else:
            terminated = bool(dones[-1] > 0.5)
            adv = self._gae(
                rewards, values, dones, bootstrap=0.0, terminated=terminated
            )
        i0 = self.pos
        for j, step in enumerate(use):
            i = i0 + j
            self.obs[i] = step["obs"]
            self.masks[i] = step["mask"]
            action = int(step.get("action_idx", 0))
            self.actions[i] = action if action >= 0 else 0
            row = np.zeros(self.max_picks, dtype=np.int64)
            picks = step.get("picks")
            num_picks = int(step.get("num_picks") or 0)
            if picks is not None:
                arr = np.asarray(list(picks)[: self.max_picks], dtype=np.int64)
                row[: len(arr)] = arr
                if num_picks <= 0 and step.get("choice"):
                    num_picks = len(arr)
            self.picks[i] = row
            self.num_picks[i] = num_picks
            self.rewards[i] = rewards[j]
            self.dones[i] = dones[j]
            self.logprobs[i] = float(step["logprob"])
            self.values[i] = values[j]
            self.advantages[i] = adv[j]
            self.returns[i] = adv[j] + values[j]
        self.pos += n
        return n

    def get(self, device: torch.device | str = "cpu") -> RolloutBatch:
        n = self.pos
        adv = self.advantages[:n].copy()
        if n > 1:
            adv = (adv - adv.mean()) / (adv.std() + 1e-8)
        return RolloutBatch(
            obs=torch.as_tensor(self.obs[:n], device=device),
            masks=torch.as_tensor(self.masks[:n], device=device),
            actions=torch.as_tensor(self.actions[:n], device=device),
            picks=torch.as_tensor(self.picks[:n], device=device),
            num_picks=torch.as_tensor(self.num_picks[:n], device=device),
            logprobs=torch.as_tensor(self.logprobs[:n], device=device),
            advantages=torch.as_tensor(adv, device=device),
            returns=torch.as_tensor(self.returns[:n], device=device),
            values=torch.as_tensor(self.values[:n], device=device),
            dones=torch.as_tensor(self.dones[:n], device=device),
        )
