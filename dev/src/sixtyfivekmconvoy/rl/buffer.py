"""On-policy rollout storage with GAE (supports recurrent BPTT fields)."""

from __future__ import annotations

from dataclasses import dataclass, field

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
    h0: torch.Tensor
    c0: torch.Tensor


@dataclass
class RolloutBuffer:
    obs_dim: int
    n_actions: int
    capacity: int
    gamma: float = 0.99
    gae_lambda: float = 0.95
    lstm_hidden: int = 512
    lstm_layers: int = 2
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
    h0: np.ndarray = field(init=False)
    c0: np.ndarray = field(init=False)
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
        state_size = self.lstm_layers * self.lstm_hidden
        self.h0 = np.zeros((self.capacity, state_size), dtype=np.float32)
        self.c0 = np.zeros((self.capacity, state_size), dtype=np.float32)
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
        *,
        picks: list[int] | np.ndarray | None = None,
        num_picks: int = 0,
        h0: np.ndarray | None = None,
        c0: np.ndarray | None = None,
    ) -> None:
        if self.pos >= self.capacity:
            raise RuntimeError("RolloutBuffer full — call clear() after update")
        i = self.pos
        self.obs[i] = obs
        self.masks[i] = mask
        self.actions[i] = action if action >= 0 else 0
        row = np.zeros(self.max_picks, dtype=np.int64)
        if picks is not None:
            arr = np.asarray(list(picks)[: self.max_picks], dtype=np.int64)
            row[: len(arr)] = arr
            if num_picks <= 0:
                num_picks = len(arr)
        self.picks[i] = row
        self.num_picks[i] = int(num_picks)
        self.rewards[i] = reward
        self.dones[i] = float(done)
        self.logprobs[i] = logprob
        self.values[i] = value
        state_size = self.lstm_layers * self.lstm_hidden
        if h0 is not None:
            flat = np.asarray(h0, dtype=np.float32).reshape(-1)
            self.h0[i, : min(state_size, flat.size)] = flat[:state_size]
        if c0 is not None:
            flat = np.asarray(c0, dtype=np.float32).reshape(-1)
            self.c0[i, : min(state_size, flat.size)] = flat[:state_size]
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
            picks=torch.as_tensor(self.picks[:n], device=device),
            num_picks=torch.as_tensor(self.num_picks[:n], device=device),
            logprobs=torch.as_tensor(self.logprobs[:n], device=device),
            advantages=torch.as_tensor(adv, device=device),
            returns=torch.as_tensor(self._returns, device=device),
            values=torch.as_tensor(self.values[:n], device=device),
            dones=torch.as_tensor(self.dones[:n], device=device),
            h0=torch.as_tensor(self.h0[:n], device=device),
            c0=torch.as_tensor(self.c0[:n], device=device),
        )
