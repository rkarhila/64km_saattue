"""Inference wrapper: MaskedActorCritic ↔ game / PettingZoo agents."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import torch

from sixtyfivekmconvoy.env.spaces import (
    MAX_LEGAL,
    encode_choice_options,
    flatten_observation,
    picks_to_vector,
)
from sixtyfivekmconvoy.rl.policy import MaskedActorCritic


class RLAgent:
    """
    Bot that picks a legal-action *index* (PettingZoo) or the underlying
    choice vector (engine ``choose``). Maintains LSTM state across calls;
    call ``reset_memory()`` at episode boundaries.
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
        self._hx: tuple[torch.Tensor, torch.Tensor] | None = None

    def reset_memory(self) -> None:
        self._hx = None

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
        raw_choice: dict[str, Any] | None = None,
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

        options = None
        ordered = None
        num_choices = None
        if raw_choice is not None:
            options = list(raw_choice.get("options") or [])
            _, _, num_choices, ordered, _ = encode_choice_options(raw_choice)
        elif isinstance(observation, dict) and observation.get("choice"):
            raw_choice = observation["choice"]
            options = list(raw_choice.get("options") or [])
            _, _, num_choices, ordered, _ = encode_choice_options(raw_choice)

        flat_idx, _, _, self._hx, _picks, choice_vec = self.policy.act(
            obs_vec,
            mask,
            deterministic=self.deterministic,
            hx=self._hx,
            options=options,
            ordered=ordered,
            num_choices=num_choices,
        )
        if choice_vec and legal_actions:
            for i, vec in enumerate(legal_actions):
                if list(vec) == list(choice_vec):
                    return i
            # Unordered set match
            if ordered is False:
                target = sorted(choice_vec)
                for i, vec in enumerate(legal_actions):
                    if sorted(vec) == target:
                        return i
        if flat_idx < 0 or flat_idx >= len(legal_actions):
            return 0
        return int(flat_idx)

    def choose(
        self,
        legal_actions: list[list[int]],
        *,
        observation: np.ndarray | dict[str, Any] | None = None,
        agent_index: int = 0,
        num_players: int = 3,
        action_mask: np.ndarray | None = None,
        raw_choice: dict[str, Any] | None = None,
    ) -> list[int]:
        """Engine-style: return the chosen legal action vector."""
        if not legal_actions:
            return []
        if observation is None:
            idx = int(self.rng.integers(0, len(legal_actions)))
            return list(legal_actions[idx])

        options = None
        ordered = None
        num_choices = None
        choice = raw_choice
        if choice is None and isinstance(observation, dict):
            choice = observation.get("choice")
        if choice is not None:
            options = list(choice.get("options") or [])
            _, _, num_choices, ordered, _ = encode_choice_options(choice)

        obs_vec = self._obs_vector(
            observation, agent_index=agent_index, num_players=num_players
        )
        mask = action_mask
        if mask is None:
            mask = np.zeros(MAX_LEGAL, dtype=np.float32)
            for i in range(min(len(legal_actions), MAX_LEGAL)):
                mask[i] = 1.0

        flat_idx, _, _, self._hx, picks, choice_vec = self.policy.act(
            obs_vec,
            mask,
            deterministic=self.deterministic,
            hx=self._hx,
            options=options,
            ordered=ordered,
            num_choices=num_choices,
        )
        if choice_vec:
            if choice_vec in [list(v) for v in legal_actions]:
                return list(choice_vec)
            if ordered is False:
                target = sorted(choice_vec)
                for vec in legal_actions:
                    if sorted(vec) == target:
                        return list(vec)
            if options is not None and picks:
                rebuilt = picks_to_vector(
                    options, picks, ordered=bool(ordered)
                )
                if rebuilt:
                    return rebuilt
        # Do not call act() again — LSTM already advanced above.
        if 0 <= flat_idx < len(legal_actions):
            return list(legal_actions[flat_idx])
        return list(legal_actions[0])

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
