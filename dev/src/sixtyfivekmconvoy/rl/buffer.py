"""On-policy rollout storage with GAE."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import torch


@dataclass
class RolloutBatch:
    obs: torch.Tensor
    masks: torch.Tensor
    actions: torch.Tensor
    logprobs: torch.Tensor
    advantages: torch.Tensor
    returns: torch.Tensor
    values: torch.Tensor


@dataclass
class RolloutBuffer:
    obs_dim: int
    n_actions: int
    capacity: int
    gamma: float = 0.99
    gae_lambda: float = 0.95

    obs: np.ndarray = field(init=False)
    masks: np.ndarray = field(init=False)
    actions: np.ndarray = field(init=False)
    rewards: np.ndarray = field(init=False)
    dones: np.ndarray = field(init=False)
    logprobs: np.ndarray = field(init=False)
    values: np.ndarray = field(init=False)
    pos: int = field(default=0, init=False)

    def __post_init__(self) -> None:
        self.obs = np.zeros((self.capacity, self.obs_dim), dtype=np.float32)
        self.masks = np.zeros((self.capacity, self.n_actions), dtype=np.float32)
        self.actions = np.zeros((self.capacity,), dtype=np.int64)
        self.rewards = np.zeros((self.capacity,), dtype=np.float32)
        self.dones = np.zeros((self.capacity,), dtype=np.float32)
        self.logprobs = np.zeros((self.capacity,), dtype=np.float32)
        self.values = np.zeros((self.capacity,), dtype=np.float32)
        self.pos = 0

    def __len__(self) -> int:
        return self.pos

    def clear(self) -> None:
        self.pos = 0

    def add(
        self,
        obs: np.ndarray,
        mask: np.ndarray,
        action: int,
        reward: float,
        done: bool,
        logprob: float,
        value: float,
    ) -> None:
        if self.pos >= self.capacity:
            raise RuntimeError("RolloutBuffer full — call clear() after update")
        i = self.pos
        self.obs[i] = obs
        self.masks[i] = mask
        self.actions[i] = action
        self.rewards[i] = reward
        self.dones[i] = float(done)
        self.logprobs[i] = logprob
        self.values[i] = value
        self.pos += 1

    def compute_returns_and_advantages(self, last_value: float, last_done: bool) -> None:
        n = self.pos
        advantages = np.zeros(n, dtype=np.float32)
        last_gae = 0.0
        next_value = last_value
        next_nonterminal = 1.0 - float(last_done)
        for t in reversed(range(n)):
            if t == n - 1:
                next_nonterminal = 1.0 - float(last_done)
                next_value = last_value
            else:
                next_nonterminal = 1.0 - self.dones[t + 1]
                next_value = self.values[t + 1]
            delta = (
                self.rewards[t]
                + self.gamma * next_value * next_nonterminal
                - self.values[t]
            )
            last_gae = delta + self.gamma * self.gae_lambda * next_nonterminal * last_gae
            advantages[t] = last_gae
        self._advantages = advantages
        self._returns = advantages + self.values[:n]

    def get(self, device: torch.device | str = "cpu") -> RolloutBatch:
        n = self.pos
        adv = self._advantages
        adv = (adv - adv.mean()) / (adv.std() + 1e-8)
        return RolloutBatch(
            obs=torch.as_tensor(self.obs[:n], device=device),
            masks=torch.as_tensor(self.masks[:n], device=device),
            actions=torch.as_tensor(self.actions[:n], device=device),
            logprobs=torch.as_tensor(self.logprobs[:n], device=device),
            advantages=torch.as_tensor(adv, device=device),
            returns=torch.as_tensor(self._returns, device=device),
            values=torch.as_tensor(self.values[:n], device=device),
        )
