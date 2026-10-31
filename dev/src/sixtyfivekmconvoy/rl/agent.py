"""Inference wrapper: MaskedActorCritic ↔ game / PettingZoo agents."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import torch

from sixtyfivekmconvoy.env.spaces import MAX_LEGAL, flatten_observation
from sixtyfivekmconvoy.rl.policy import MaskedActorCritic


class RLAgent:
    """
    Bot that picks a legal-action *index* (PettingZoo) or the underlying
    choice vector (engine ``choose``).
    """

    def __init__(
        self,
        policy: MaskedActorCritic,
        *,
        deterministic: bool = False,
        device: str | torch.device = "cpu",
        seed: int | None = None,
    ):
        self.policy = policy.to(device)
        self.policy.eval()
        self.deterministic = deterministic
        self.device = torch.device(device)
        self.rng = np.random.default_rng(seed)

    @classmethod
    def from_checkpoint(
        cls,
        path: str | Path,
        *,
        deterministic: bool = False,
        device: str | torch.device = "cpu",
        seed: int | None = None,
    ) -> RLAgent:
        data = torch.load(path, map_location=device, weights_only=False)
        policy = MaskedActorCritic.from_checkpoint(
            data["policy"] if "policy" in data else data,
            map_location=device,
        )
        return cls(
            policy, deterministic=deterministic, device=device, seed=seed
        )

    def act(
        self,
        observation: np.ndarray | dict[str, Any],
        legal_actions: list[list[int]],
        *,
        agent_index: int | None = None,
        num_players: int | None = None,
        action_mask: np.ndarray | None = None,
    ) -> int:
        """Return index into ``legal_actions`` / action_mask."""
        obs_vec = self._obs_vector(
            observation, agent_index=agent_index, num_players=num_players
        )
        mask = action_mask
        if mask is None:
            mask = np.zeros(MAX_LEGAL, dtype=np.float32)
            for i in range(min(len(legal_actions), MAX_LEGAL)):
                mask[i] = 1.0
        if not legal_actions or mask.sum() <= 0:
            return 0
        action, _, _ = self.policy.act(
            obs_vec, mask, deterministic=self.deterministic
        )
        if action < 0 or action >= len(legal_actions):
            # Safety: fall back to first legal.
            return 0
        return int(action)

    def choose(
        self,
        legal_actions: list[list[int]],
        *,
        observation: np.ndarray | dict[str, Any] | None = None,
        agent_index: int = 0,
        num_players: int = 3,
        action_mask: np.ndarray | None = None,
    ) -> list[int]:
        """Engine-style: return the chosen legal action vector."""
        if not legal_actions:
            return []
        if observation is None:
            # No obs — uniform among legal (should be rare for RL bots).
            idx = int(self.rng.integers(0, len(legal_actions)))
            return list(legal_actions[idx])
        idx = self.act(
            observation,
            legal_actions,
            agent_index=agent_index,
            num_players=num_players,
            action_mask=action_mask,
        )
        return list(legal_actions[idx])

    @staticmethod
    def _obs_vector(
        observation: np.ndarray | dict[str, Any],
        *,
        agent_index: int | None,
        num_players: int | None,
    ) -> np.ndarray:
        if isinstance(observation, np.ndarray):
            return observation.astype(np.float32, copy=False)
        if agent_index is None or num_players is None:
            raise ValueError(
                "dict observations require agent_index and num_players"
            )
        return flatten_observation(observation, agent_index, num_players)
