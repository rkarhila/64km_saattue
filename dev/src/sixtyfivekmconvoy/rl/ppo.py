"""Proximal Policy Optimization with truncated BPTT for LSTM policies."""

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
    bptt_len: int = 16
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

        metrics: dict[str, list[float]] = {
            "policy_loss": [],
            "value_loss": [],
            "entropy": [],
            "approx_kl": [],
            "clipfrac": [],
        }

        bptt = max(1, int(cfg.bptt_len))
        for _ in range(cfg.epochs):
            # Contiguous BPTT windows (preserve temporal order for LSTM).
            starts = list(range(0, n, bptt))
            # Shuffle window starts only.
            order = torch.randperm(len(starts), device=self.device).tolist()
            for oi in order:
                start = starts[oi]
                end = min(start + bptt, n)
                loss_info = self._sequence_loss(batch, start, end)
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

        return {
            k: float(sum(vs) / max(1, len(vs))) for k, vs in metrics.items()
        }

    def _sequence_loss(
        self, batch: RolloutBatch, start: int, end: int
    ) -> dict[str, Any]:
        cfg = self.config
        obs = batch.obs[start:end]
        masks = batch.masks[start:end]
        actions = batch.actions[start:end]
        picks = batch.picks[start:end]
        num_picks = batch.num_picks[start:end]
        old_logp = batch.logprobs[start:end]
        advantages = batch.advantages[start:end]
        returns = batch.returns[start:end]
        dones = batch.dones[start:end]

        # Seed LSTM from stored pre-step state of the first timestep.
        layers = self.policy.lstm_layers
        hidden = self.policy.lstm_hidden
        h = batch.h0[start].view(layers, 1, hidden)
        c = batch.c0[start].view(layers, 1, hidden)
        hx: tuple[torch.Tensor, torch.Tensor] | None = (h, c)

        logps: list[torch.Tensor] = []
        ents: list[torch.Tensor] = []
        vals: list[torch.Tensor] = []

        for t in range(obs.shape[0]):
            if t > 0 and float(dones[t - 1].item()) > 0.5:
                hx = self.policy.initial_state(1, device=self.device)
            logp, ent, value, hx = self.policy.evaluate_actions(
                obs[t : t + 1],
                masks[t : t + 1],
                actions[t : t + 1],
                hx=hx,
                picks=picks[t : t + 1],
                num_picks=num_picks[t : t + 1],
            )
            # Detach across BPTT window boundary only happens by windowing.
            logps.append(logp)
            ents.append(ent)
            vals.append(value)
            # Truncate BPTT graph for next step within window? Keep connected.
            assert hx is not None
            hx = (hx[0], hx[1])

        logp_t = torch.cat(logps, dim=0)
        ent_t = torch.cat(ents, dim=0)
        values = torch.cat(vals, dim=0)

        ratio = torch.exp(logp_t - old_logp)
        unclipped = advantages * ratio
        clipped = advantages * torch.clamp(
            ratio, 1.0 - cfg.clip_range, 1.0 + cfg.clip_range
        )
        policy_loss = -torch.min(unclipped, clipped).mean()
        value_loss = 0.5 * (returns - values).pow(2).mean()
        entropy_loss = ent_t.mean()
        loss = (
            policy_loss
            + cfg.vf_coef * value_loss
            - cfg.ent_coef * entropy_loss
        )
        with torch.no_grad():
            approx_kl = (old_logp - logp_t).mean().item()
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
