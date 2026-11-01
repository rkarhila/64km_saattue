"""Recurrent masked actor-critic with autoregressive multi-slot choices."""

from __future__ import annotations

from typing import Any

import numpy as np
import torch
import torch.nn as nn
from torch.distributions import Categorical

from sixtyfivekmconvoy.env.spaces import (
    MAX_LEGAL,
    MAX_OPTIONS,
    MAX_PICKS,
    OPTION_FEAT_DIM,
    observation_size,
    option_block_slices,
    picks_to_vector,
)


def _masked_logits(logits: torch.Tensor, mask: torch.Tensor) -> torch.Tensor:
    """Illegal slots → very negative; all-illegal rows fall back to raw logits."""
    very_neg = torch.finfo(logits.dtype).min / 4
    masked = torch.where(mask > 0, logits, very_neg)
    all_bad = mask.sum(dim=-1, keepdim=True) <= 0
    if all_bad.any():
        masked = torch.where(all_bad, logits, masked)
    return masked


class MaskedActorCritic(nn.Module):
    """
    Encoder MLP → LSTM → value head + autoregressive option picks.

    Each env decision: LSTM advances once; then up to ``num_choices`` picks
    are decoded over option embeddings carved from the observation vector
    (or passed explicitly). Flat ``MAX_LEGAL`` logits remain as a fallback
    when no options are present.
    """

    def __init__(
        self,
        obs_dim: int | None = None,
        hidden: int = 256,
        n_layers: int = 2,
        lstm_hidden: int | None = None,
        lstm_layers: int = 2,
        num_players: int = 3,
        max_options: int = MAX_OPTIONS,
        max_picks: int = MAX_PICKS,
    ):
        super().__init__()
        if obs_dim is None:
            obs_dim = observation_size(num_players)
        self.obs_dim = int(obs_dim)
        self.hidden = int(hidden)
        self.n_layers = max(1, int(n_layers))
        self.lstm_hidden = int(lstm_hidden if lstm_hidden is not None else 512)
        self.lstm_layers = max(1, int(lstm_layers))
        self.n_actions = MAX_LEGAL
        self.max_options = int(max_options)
        self.max_picks = int(max_picks)
        self.recurrent = True

        layers: list[nn.Module] = []
        in_dim = self.obs_dim
        for _ in range(self.n_layers):
            layers.extend([nn.Linear(in_dim, self.hidden), nn.Tanh()])
            in_dim = self.hidden
        self.encoder = nn.Sequential(*layers)
        self.lstm = nn.LSTM(
            input_size=self.hidden,
            hidden_size=self.lstm_hidden,
            num_layers=self.lstm_layers,
            batch_first=True,
        )
        self.value_head = nn.Linear(self.lstm_hidden, 1)
        self.flat_policy_head = nn.Linear(self.lstm_hidden, self.n_actions)
        self.option_proj = nn.Linear(OPTION_FEAT_DIM, self.lstm_hidden)
        self.query_proj = nn.Linear(self.lstm_hidden, self.lstm_hidden)
        self.pick_gru = nn.GRUCell(self.lstm_hidden, self.lstm_hidden)

        fs, fe, ms, me = option_block_slices(self.obs_dim)
        self._opt_feat_slice = (fs, fe)
        self._opt_mask_slice = (ms, me)
        self.apply(self._init_weights)

    @staticmethod
    def _init_weights(module: nn.Module) -> None:
        if isinstance(module, nn.Linear):
            nn.init.orthogonal_(module.weight, gain=np.sqrt(2))
            nn.init.zeros_(module.bias)
        elif isinstance(module, nn.LSTM):
            for name, param in module.named_parameters():
                if "weight" in name:
                    nn.init.orthogonal_(param)
                elif "bias" in name:
                    nn.init.zeros_(param)

    @property
    def lstm_state_size(self) -> int:
        """Flattened (h or c) length: lstm_layers * lstm_hidden."""
        return self.lstm_layers * self.lstm_hidden

    def initial_state(
        self, batch_size: int = 1, *, device: torch.device | str | None = None
    ) -> tuple[torch.Tensor, torch.Tensor]:
        dev = device or next(self.parameters()).device
        h = torch.zeros(
            self.lstm_layers, batch_size, self.lstm_hidden, device=dev
        )
        c = torch.zeros(
            self.lstm_layers, batch_size, self.lstm_hidden, device=dev
        )
        return h, c

    def _encode(
        self,
        obs: torch.Tensor,
        hx: tuple[torch.Tensor, torch.Tensor] | None,
    ) -> tuple[torch.Tensor, tuple[torch.Tensor, torch.Tensor]]:
        """obs: [B, D] or [B, T, D] → features [B, H] or [B, T, H], new hx."""
        squeezed = False
        if obs.dim() == 2:
            obs = obs.unsqueeze(1)
            squeezed = True
        b, t, _ = obs.shape
        flat = obs.reshape(b * t, -1)
        enc = self.encoder(flat).reshape(b, t, -1)
        if hx is None:
            hx = self.initial_state(b, device=obs.device)
        out, hx2 = self.lstm(enc, hx)
        if squeezed:
            out = out.squeeze(1)
        return out, hx2

    def _option_tensors_from_obs(
        self, obs: torch.Tensor
    ) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor, torch.Tensor]:
        """Extract option feats/mask/num_picks/ordered from flat obs. Batched [B,...]."""
        fs, fe = self._opt_feat_slice
        ms, me = self._opt_mask_slice
        # Meta sits just before option feats: present, ctype, n_pick, ordered, n_opts
        # Layout end: ... present, ctype, n_pick/MAX, ordered, n_opts/MAX, feats..., mask...
        meta_start = fs - 5
        n_pick_norm = obs[:, meta_start + 2]
        ordered = obs[:, meta_start + 3]
        num_picks = torch.clamp(
            (n_pick_norm * MAX_PICKS).round().long(), min=0, max=self.max_picks
        )
        opt_feats = obs[:, fs:fe].reshape(-1, self.max_options, OPTION_FEAT_DIM)
        opt_mask = obs[:, ms:me]
        return opt_feats, opt_mask, num_picks, ordered

    def _ar_logprobs(
        self,
        h: torch.Tensor,
        opt_feats: torch.Tensor,
        opt_mask: torch.Tensor,
        num_picks: torch.Tensor,
        ordered: torch.Tensor,
        actions: torch.Tensor | None = None,
        *,
        deterministic: bool = False,
    ) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        """
        Autoregressive picks over options.

        Returns (picks [B, MAX_PICKS], logp [B], entropy [B]).
        If ``actions`` is given (option indices), evaluate those; else sample.
        """
        b = h.shape[0]
        device = h.device
        opt_emb = torch.tanh(self.option_proj(opt_feats))  # [B, O, H]
        pick_h = h
        picks = torch.zeros(b, self.max_picks, dtype=torch.long, device=device)
        logps = torch.zeros(b, device=device)
        ents = torch.zeros(b, device=device)
        used = torch.zeros(b, self.max_options, device=device)

        max_k = int(num_picks.max().item()) if b > 0 else 0
        for t in range(max(max_k, 1)):
            active = (num_picks > t).float()
            query = torch.tanh(self.query_proj(pick_h)).unsqueeze(1)  # [B,1,H]
            logits = (query * opt_emb).sum(dim=-1)  # [B, O]
            step_mask = opt_mask * (1.0 - used)
            # If unordered, forbid reusing; if ordered (perm), also no reuse.
            logits = _masked_logits(logits, step_mask)
            dist = Categorical(logits=logits)
            if actions is not None:
                a = actions[:, t].clamp(0, self.max_options - 1)
            elif deterministic:
                a = logits.argmax(dim=-1)
            else:
                a = dist.sample()
            picks[:, t] = a
            logps = logps + dist.log_prob(a) * active
            ents = ents + dist.entropy() * active
            used = used.scatter(1, a.unsqueeze(1), torch.ones(b, 1, device=device))
            chosen_emb = opt_emb.gather(
                1, a.view(b, 1, 1).expand(-1, 1, self.lstm_hidden)
            ).squeeze(1)
            pick_h = self.pick_gru(chosen_emb, pick_h)
            # Keep inactive rows' pick_h unchanged effectively via active mix
            pick_h = active.unsqueeze(-1) * pick_h + (1.0 - active.unsqueeze(-1)) * h

        # Zero-pick edge: single dummy flat? treat as logp 0
        no_pick = (num_picks <= 0).float()
        if no_pick.any():
            flat_logits = _masked_logits(
                self.flat_policy_head(h),
                torch.ones(b, self.n_actions, device=device),
            )
            flat_dist = Categorical(logits=flat_logits)
            if actions is not None:
                # actions may store flat index in picks[:,0] when no options
                a0 = actions[:, 0].clamp(0, self.n_actions - 1)
            elif deterministic:
                a0 = flat_logits.argmax(dim=-1)
            else:
                a0 = flat_dist.sample()
            picks[:, 0] = torch.where(num_picks <= 0, a0, picks[:, 0])
            logps = torch.where(
                num_picks <= 0, flat_dist.log_prob(a0), logps
            )
            ents = torch.where(num_picks <= 0, flat_dist.entropy(), ents)
        return picks, logps, ents

    def forward(
        self,
        obs: torch.Tensor,
        mask: torch.Tensor,
        hx: tuple[torch.Tensor, torch.Tensor] | None = None,
    ) -> tuple[Categorical, torch.Tensor, tuple[torch.Tensor, torch.Tensor]]:
        """Flat categorical (legacy) + value; advances LSTM."""
        h, hx2 = self._encode(obs, hx)
        logits = _masked_logits(self.flat_policy_head(h), mask)
        dist = Categorical(logits=logits)
        value = self.value_head(h).squeeze(-1)
        return dist, value, hx2

    def act(
        self,
        obs: np.ndarray | torch.Tensor,
        mask: np.ndarray | torch.Tensor,
        *,
        deterministic: bool = False,
        hx: tuple[torch.Tensor, torch.Tensor] | None = None,
        options: list[Any] | None = None,
        ordered: bool | None = None,
        num_choices: int | None = None,
    ) -> tuple[int, float, float, tuple[torch.Tensor, torch.Tensor], list[int], list[int]]:
        """
        Return (flat_index_or_-1, log_prob, value, new_hx, option_picks, choice_vector).

        Prefer ``choice_vector`` for env.step when non-empty.
        """
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

        with torch.no_grad():
            h, hx2 = self._encode(obs_t, hx)
            value = self.value_head(h).squeeze(-1)
            opt_feats, opt_mask, num_picks, ord_t = self._option_tensors_from_obs(obs_t)
            if num_choices is not None:
                num_picks = torch.full_like(num_picks, int(num_choices))
            if ordered is not None:
                ord_t = torch.full_like(ord_t, float(ordered))

            use_ar = bool((num_picks > 0).all().item() and (opt_mask.sum() > 0).item())
            if use_ar:
                picks_t, logp, _ = self._ar_logprobs(
                    h,
                    opt_feats,
                    opt_mask,
                    num_picks,
                    ord_t,
                    deterministic=deterministic,
                )
                picks = [int(x) for x in picks_t[0, : int(num_picks[0].item())].tolist()]
                is_ordered = bool(ord_t[0].item() > 0.5)
                if options is None:
                    # Reconstruct option ids from feat id_norm is lossy; caller
                    # should pass options. Fall back to flat index 0.
                    choice_vec: list[int] = []
                    flat_idx = 0
                else:
                    choice_vec = picks_to_vector(
                        options, picks, ordered=is_ordered
                    )
                    flat_idx = -1
                return (
                    flat_idx,
                    float(logp[0].item()),
                    float(value[0].item()),
                    hx2,
                    picks,
                    choice_vec,
                )

            dist = Categorical(logits=_masked_logits(self.flat_policy_head(h), mask_t))
            action = dist.probs.argmax(dim=-1) if deterministic else dist.sample()
            logp = dist.log_prob(action)
            return (
                int(action[0].item()),
                float(logp[0].item()),
                float(value[0].item()),
                hx2,
                [int(action[0].item())],
                [],
            )

    def evaluate_actions(
        self,
        obs: torch.Tensor,
        mask: torch.Tensor,
        actions: torch.Tensor,
        *,
        hx: tuple[torch.Tensor, torch.Tensor] | None = None,
        picks: torch.Tensor | None = None,
        num_picks: torch.Tensor | None = None,
        dones: torch.Tensor | None = None,
    ) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor, tuple[torch.Tensor, torch.Tensor]]:
        """
        Evaluate logp/entropy/value for a batch (single-step LSTM, no T dim).

        ``picks``: [B, MAX_PICKS] option indices when using AR; else ``actions``
        is the flat discrete index.
        """
        h, hx2 = self._encode(obs, hx)
        value = self.value_head(h).squeeze(-1)
        opt_feats, opt_mask, auto_n, ord_t = self._option_tensors_from_obs(obs)
        if num_picks is None:
            num_picks = auto_n
        use_ar = (num_picks > 0) & (opt_mask.sum(dim=-1) > 0)
        logp = torch.zeros(obs.shape[0], device=obs.device)
        entropy = torch.zeros(obs.shape[0], device=obs.device)

        if use_ar.any() and picks is not None:
            ar_picks, ar_logp, ar_ent = self._ar_logprobs(
                h, opt_feats, opt_mask, num_picks, ord_t, actions=picks
            )
            logp = torch.where(use_ar, ar_logp, logp)
            entropy = torch.where(use_ar, ar_ent, entropy)
            _ = ar_picks

        flat = ~use_ar
        if flat.any():
            logits = _masked_logits(self.flat_policy_head(h), mask)
            dist = Categorical(logits=logits)
            a = actions.long()
            logp = torch.where(flat, dist.log_prob(a), logp)
            entropy = torch.where(flat, dist.entropy(), entropy)

        if dones is not None:
            # Caller may reset hx externally; returned hx2 still useful.
            pass
        return logp, entropy, value, hx2

    def checkpoint_dict(self) -> dict[str, Any]:
        return {
            "state_dict": self.state_dict(),
            "obs_dim": self.obs_dim,
            "n_actions": self.n_actions,
            "hidden": self.hidden,
            "n_layers": self.n_layers,
            "lstm_hidden": self.lstm_hidden,
            "lstm_layers": self.lstm_layers,
            "max_options": self.max_options,
            "max_picks": self.max_picks,
            "recurrent": True,
            "arch": "lstm_ar",
        }

    @classmethod
    def from_checkpoint(
        cls, data: dict[str, Any], *, map_location: str | torch.device = "cpu"
    ) -> MaskedActorCritic:
        hidden = int(data.get("hidden", 256))
        obs_dim = int(data.get("obs_dim", observation_size()))
        n_layers = int(data.get("n_layers", 2))
        lstm_hidden = int(data.get("lstm_hidden", 512))
        lstm_layers = int(data.get("lstm_layers", 2))
        model = cls(
            obs_dim=obs_dim,
            hidden=hidden,
            n_layers=n_layers,
            lstm_hidden=lstm_hidden,
            lstm_layers=lstm_layers,
            max_options=int(data.get("max_options", MAX_OPTIONS)),
            max_picks=int(data.get("max_picks", MAX_PICKS)),
        )
        # Old MLP checkpoints lack LSTM keys — load what we can.
        state = data["state_dict"]
        model_state = model.state_dict()
        filtered = {k: v for k, v in state.items() if k in model_state and v.shape == model_state[k].shape}
        model_state.update(filtered)
        model.load_state_dict(model_state)
        model.to(map_location)
        model.eval()
        return model
