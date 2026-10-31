"""Proximal Policy Optimization update for masked discrete actions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import torch
import torch.nn as nn

from sixtyfivekmconvoy.rl.buffer import RolloutBatch, RolloutBuffer
from sixtyfivekmconvoy.rl.policy import MaskedActorCritic


@dataclass
class PPOConfig:
    lr: float = 3e-4
    clip_range: float = 0.2
    ent_coef: float = 0.01
    vf_coef: float = 0.5
    max_grad_norm: float = 0.5
    epochs: int = 4
    minibatch_size: int = 256
    gamma: float = 0.99
    gae_lambda: float = 0.95


class PPOTrainer:
    def __init__(
        self,
        policy: MaskedActorCritic,
        config: PPOConfig | None = None,
        *,
        device: str | torch.device = "cpu",
    ):
        self.policy = policy.to(device)
        self.config = config or PPOConfig()
        self.device = torch.device(device)
        self.optimizer = torch.optim.Adam(
            self.policy.parameters(), lr=self.config.lr, eps=1e-5
        )

    def update(self, buffer: RolloutBuffer) -> dict[str, float]:
        batch = buffer.get(self.device)
        cfg = self.config
        n = batch.obs.shape[0]
        if n == 0:
            return {}

        mb = min(cfg.minibatch_size, n)
        idxs = torch.randperm(n, device=self.device)
        metrics: dict[str, list[float]] = {
            "policy_loss": [],
            "value_loss": [],
            "entropy": [],
            "approx_kl": [],
            "clipfrac": [],
        }

        for _ in range(cfg.epochs):
            for start in range(0, n, mb):
                mb_idx = idxs[start : start + mb]
                loss_info = self._minibatch_loss(batch, mb_idx)
                self.optimizer.zero_grad(set_to_none=True)
                loss_info["loss"].backward()
                nn.utils.clip_grad_norm_(
                    self.policy.parameters(), cfg.max_grad_norm
                )
                self.optimizer.step()
                for k, v in loss_info.items():
                    if k == "loss":
                        continue
                    metrics[k].append(float(v))

        return {k: float(sum(vs) / max(1, len(vs))) for k, vs in metrics.items()}

    def _minibatch_loss(
        self, batch: RolloutBatch, idx: torch.Tensor
    ) -> dict[str, Any]:
        cfg = self.config
        obs = batch.obs[idx]
        masks = batch.masks[idx]
        actions = batch.actions[idx]
        old_logp = batch.logprobs[idx]
        advantages = batch.advantages[idx]
        returns = batch.returns[idx]

        logp, entropy, values = self.policy.evaluate_actions(obs, masks, actions)
        ratio = torch.exp(logp - old_logp)
        unclipped = advantages * ratio
        clipped = advantages * torch.clamp(
            ratio, 1.0 - cfg.clip_range, 1.0 + cfg.clip_range
        )
        policy_loss = -torch.min(unclipped, clipped).mean()
        value_loss = 0.5 * (returns - values).pow(2).mean()
        entropy_loss = entropy.mean()
        loss = (
            policy_loss
            + cfg.vf_coef * value_loss
            - cfg.ent_coef * entropy_loss
        )
        with torch.no_grad():
            approx_kl = (old_logp - logp).mean().item()
            clipfrac = (
                ((ratio - 1.0).abs() > cfg.clip_range).float().mean().item()
            )
        return {
            "loss": loss,
            "policy_loss": policy_loss.item(),
            "value_loss": value_loss.item(),
            "entropy": entropy_loss.item(),
            "approx_kl": approx_kl,
            "clipfrac": clipfrac,
        }
