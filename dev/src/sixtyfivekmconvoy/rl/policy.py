"""Masked actor-critic policy for discrete legal-action indices."""

from __future__ import annotations

from typing import Any

import numpy as np
import torch
import torch.nn as nn
from torch.distributions import Categorical

from sixtyfivekmconvoy.env.spaces import MAX_LEGAL, observation_size


def _masked_probs(logits: torch.Tensor, mask: torch.Tensor) -> torch.Tensor:
    """Softmax over legal actions only; illegal logits → -inf."""
    very_neg = torch.finfo(logits.dtype).min
    masked = torch.where(mask > 0, logits, very_neg)
    # If a row is all-illegal (shouldn't happen), fall back to uniform over slots.
    all_bad = mask.sum(dim=-1, keepdim=True) <= 0
    if all_bad.any():
        masked = torch.where(all_bad, logits, masked)
    return torch.softmax(masked, dim=-1)


class MaskedActorCritic(nn.Module):
    """Shared MLP trunk → policy logits (MAX_LEGAL) + scalar value."""

    def __init__(
        self,
        obs_dim: int | None = None,
        hidden: int = 256,
        n_layers: int = 2,
        num_players: int = 3,
    ):
        super().__init__()
        if obs_dim is None:
            obs_dim = observation_size(num_players)
        self.obs_dim = int(obs_dim)
        self.hidden = int(hidden)
        self.n_layers = max(1, int(n_layers))
        self.n_actions = MAX_LEGAL
        layers: list[nn.Module] = []
        in_dim = self.obs_dim
        for _ in range(self.n_layers):
            layers.extend([nn.Linear(in_dim, self.hidden), nn.Tanh()])
            in_dim = self.hidden
        self.trunk = nn.Sequential(*layers)
        self.policy_head = nn.Linear(self.hidden, self.n_actions)
        self.value_head = nn.Linear(self.hidden, 1)
        self.apply(self._init_weights)

    @staticmethod
    def _init_weights(module: nn.Module) -> None:
        if isinstance(module, nn.Linear):
            nn.init.orthogonal_(module.weight, gain=np.sqrt(2))
            nn.init.zeros_(module.bias)

    def forward(
        self, obs: torch.Tensor, mask: torch.Tensor
    ) -> tuple[Categorical, torch.Tensor]:
        h = self.trunk(obs)
        logits = self.policy_head(h)
        probs = _masked_probs(logits, mask)
        dist = Categorical(probs=probs)
        value = self.value_head(h).squeeze(-1)
        return dist, value

    def act(
        self,
        obs: np.ndarray | torch.Tensor,
        mask: np.ndarray | torch.Tensor,
        *,
        deterministic: bool = False,
    ) -> tuple[int, float, float]:
        """Return (action_index, log_prob, value)."""
        device = next(self.parameters()).device
        if not torch.is_tensor(obs):
            obs_t = torch.as_tensor(obs, dtype=torch.float32, device=device)
        else:
            obs_t = obs.to(device=device, dtype=torch.float32)
        if not torch.is_tensor(mask):
            mask_t = torch.as_tensor(mask, dtype=torch.float32, device=device)
        else:
            mask_t = mask.to(device=device, dtype=torch.float32)
        if obs_t.dim() == 1:
            obs_t = obs_t.unsqueeze(0)
            mask_t = mask_t.unsqueeze(0)
            squeeze = True
        else:
            squeeze = False
        with torch.no_grad():
            dist, value = self.forward(obs_t, mask_t)
            action = dist.probs.argmax(dim=-1) if deterministic else dist.sample()
            logp = dist.log_prob(action)
        if squeeze:
            return int(action.item()), float(logp.item()), float(value.item())
        return action, logp, value  # type: ignore[return-value]

    def evaluate_actions(
        self,
        obs: torch.Tensor,
        mask: torch.Tensor,
        actions: torch.Tensor,
    ) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        dist, value = self.forward(obs, mask)
        logp = dist.log_prob(actions)
        entropy = dist.entropy()
        return logp, entropy, value

    def checkpoint_dict(self) -> dict[str, Any]:
        return {
            "state_dict": self.state_dict(),
            "obs_dim": self.obs_dim,
            "n_actions": self.n_actions,
            "hidden": self.hidden,
            "n_layers": self.n_layers,
        }

    @classmethod
    def from_checkpoint(
        cls, data: dict[str, Any], *, map_location: str | torch.device = "cpu"
    ) -> MaskedActorCritic:
        hidden = int(data.get("hidden", 256))
        obs_dim = int(data.get("obs_dim", observation_size()))
        n_layers = int(data.get("n_layers", 2))
        model = cls(obs_dim=obs_dim, hidden=hidden, n_layers=n_layers)
        model.load_state_dict(data["state_dict"])
        model.to(map_location)
        model.eval()
        return model
