"""Transformer actor-critic with autoregressive multi-slot choices.

History is the event window already stored in the observation. There is no
recurrent state between decisions. The GRU only picks the slots of one choice.
"""

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
from sixtyfivekmconvoy.rl.events import EVENT_FIELDS, EVENT_WINDOW


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
    Encoder MLP → transformer over board token + event rows → value and picks.

    Up to ``num_choices`` picks are decoded over option embeddings carved from
    the observation. Flat ``MAX_LEGAL`` logits are the fallback when a row has
    no options.
    """

    def __init__(
        self,
        obs_dim: int | None = None,
        hidden: int = 256,
        n_layers: int = 2,
        width: int | None = None,
        num_players: int = 3,
        max_options: int = MAX_OPTIONS,
        max_picks: int = MAX_PICKS,
        *,
        d_model: int = 128,
        nhead: int = 4,
        dim_feedforward: int = 256,
        tf_layers: int = 2,
        lstm_hidden: int | None = None,
        lstm_layers: int | None = None,
        sequence: str | None = None,
    ):
        super().__init__()
        del lstm_layers, sequence
        if obs_dim is None:
            obs_dim = observation_size(num_players)
        if width is None:
            width = 128 if lstm_hidden is None else int(lstm_hidden)
        self.obs_dim = int(obs_dim)
        self.hidden = int(hidden)
        self.n_layers = max(1, int(n_layers))
        self.width = int(width)
        self.d_model = int(d_model)
        self.nhead = int(nhead)
        self.dim_feedforward = int(dim_feedforward)
        self.tf_layers = max(1, int(tf_layers))
        if self.d_model % self.nhead != 0:
            raise ValueError(
                f"d_model ({self.d_model}) must be divisible by nhead ({self.nhead})"
            )
        # Alias so older call sites that read the decision width still work.
        self.lstm_hidden = self.width
        self.n_actions = MAX_LEGAL
        self.max_options = int(max_options)
        self.max_picks = int(max_picks)
        self.sequence = "transformer"
        self.recurrent = False

        layers: list[nn.Module] = []
        in_dim = self.obs_dim
        for _ in range(self.n_layers):
            layers.extend([nn.Linear(in_dim, self.hidden), nn.Tanh()])
            in_dim = self.hidden
        self.encoder = nn.Sequential(*layers)
        self.tf_board = nn.Linear(self.hidden, self.d_model)
        self.tf_event = nn.Linear(EVENT_FIELDS, self.d_model)
        tf_layer = nn.TransformerEncoderLayer(
            d_model=self.d_model,
            nhead=self.nhead,
            dim_feedforward=self.dim_feedforward,
            dropout=0.0,
            batch_first=True,
            activation="gelu",
        )
        self.transformer = nn.TransformerEncoder(tf_layer, num_layers=self.tf_layers)
        self.tf_out = nn.Linear(self.d_model, self.width)
        self.value_head = nn.Linear(self.width, 1)
        self.flat_policy_head = nn.Linear(self.width, self.n_actions)
        self.option_proj = nn.Linear(OPTION_FEAT_DIM, self.width)
        self.query_proj = nn.Linear(self.width, self.width)
        self.pick_gru = nn.GRUCell(self.width, self.width)

        fs, fe, ms, me = option_block_slices(self.obs_dim)
        self._opt_feat_slice = (fs, fe)
        self._opt_mask_slice = (ms, me)
        self.apply(self._init_weights)

    @staticmethod
    def _init_weights(module: nn.Module) -> None:
        if isinstance(module, nn.Linear):
            nn.init.orthogonal_(module.weight, gain=np.sqrt(2))
            nn.init.zeros_(module.bias)
        elif isinstance(module, nn.GRUCell):
            for name, param in module.named_parameters():
                if "weight" in name:
                    nn.init.orthogonal_(param)
                elif "bias" in name:
                    nn.init.zeros_(param)

    def _encode(self, obs: torch.Tensor) -> torch.Tensor:
        """obs [B, D] → decision features [B, width]."""
        if obs.dim() == 1:
            obs = obs.unsqueeze(0)
        enc = self.encoder(obs)
        return self._transformer_step(obs, enc)

    def _transformer_step(self, obs: torch.Tensor, enc: torch.Tensor) -> torch.Tensor:
        """obs [B, D], enc [B, hidden] → [B, width] from board + event tokens."""
        b = obs.shape[0]
        tail = EVENT_WINDOW * EVENT_FIELDS
        ev = obs[:, -tail:].reshape(b, EVENT_WINDOW, EVENT_FIELDS)
        valid = ev[:, :, 0] > 1e-6
        board = self.tf_board(enc).unsqueeze(1)
        tokens = torch.cat([board, self.tf_event(ev)], dim=1)
        pad = torch.cat(
            [
                torch.zeros(b, 1, dtype=torch.bool, device=obs.device),
                ~valid,
            ],
            dim=1,
        )
        hidden = self.transformer(tokens, src_key_padding_mask=pad)
        return self.tf_out(hidden[:, 0])

    def _option_tensors_from_obs(
        self, obs: torch.Tensor
    ) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor, torch.Tensor]:
        """Extract option feats/mask/num_picks/ordered from flat obs. Batched [B,...]."""
        fs, fe = self._opt_feat_slice
        ms, me = self._opt_mask_slice
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
        ``ordered`` is accepted so callers share one signature; reuse is banned
        for both ordered and unordered picks.
        """
        del ordered
        b = h.shape[0]
        device = h.device
        opt_emb = torch.tanh(self.option_proj(opt_feats))
        pick_h = h
        picks = torch.zeros(b, self.max_picks, dtype=torch.long, device=device)
        logps = torch.zeros(b, device=device)
        ents = torch.zeros(b, device=device)
        used = torch.zeros(b, self.max_options, device=device)

        max_k = int(num_picks.max().item()) if b > 0 else 0
        for t in range(max(max_k, 1)):
            active = (num_picks > t).float()
            query = torch.tanh(self.query_proj(pick_h)).unsqueeze(1)
            logits = (query * opt_emb).sum(dim=-1)
            step_mask = opt_mask * (1.0 - used)
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
                1, a.view(b, 1, 1).expand(-1, 1, self.width)
            ).squeeze(1)
            nxt = self.pick_gru(chosen_emb, pick_h)
            pick_h = active.unsqueeze(-1) * nxt + (1.0 - active.unsqueeze(-1)) * pick_h
        return picks, logps, ents

    def forward(
        self,
        obs: torch.Tensor,
        mask: torch.Tensor,
    ) -> tuple[Categorical, torch.Tensor]:
        """Flat categorical + value for a batch of observations."""
        h = self._encode(obs)
        logits = _masked_logits(self.flat_policy_head(h), mask)
        value = self.value_head(h).reshape(-1)
        return Categorical(logits=logits), value

    def act(
        self,
        obs: np.ndarray | torch.Tensor,
        mask: np.ndarray | torch.Tensor,
        *,
        deterministic: bool = False,
        options: list[Any] | None = None,
        ordered: bool | None = None,
        num_choices: int | None = None,
        hx: Any = None,
    ) -> tuple[int, float, float, list[int], list[int]]:
        """
        Return (flat_index_or_-1, log_prob, value, option_picks, choice_vector).

        ``hx`` is ignored. Prefer ``choice_vector`` for env.step when non-empty.
        """
        del hx
        rows = self.act_batch(
            obs,
            mask,
            deterministic=deterministic,
            options=[options],
            ordered=[ordered],
            num_choices=[num_choices],
        )
        return rows[0]

    def act_batch(
        self,
        obs: np.ndarray | torch.Tensor,
        mask: np.ndarray | torch.Tensor,
        *,
        deterministic: bool = False,
        options: list[list[Any] | None] | None = None,
        ordered: list[bool | None] | None = None,
        num_choices: list[int | None] | None = None,
    ) -> list[tuple[int, float, float, list[int], list[int]]]:
        """Batched ``act``. One result per row: flat index, logp, value, picks, choice."""
        device = next(self.parameters()).device
        if not torch.is_tensor(obs):
            obs_t = torch.as_tensor(np.asarray(obs), dtype=torch.float32, device=device)
        else:
            obs_t = obs.to(device=device, dtype=torch.float32)
        if not torch.is_tensor(mask):
            mask_t = torch.as_tensor(np.asarray(mask), dtype=torch.float32, device=device)
        else:
            mask_t = mask.to(device=device, dtype=torch.float32)
        if obs_t.dim() == 1:
            obs_t = obs_t.unsqueeze(0)
            mask_t = mask_t.unsqueeze(0)
        b = int(obs_t.shape[0])
        if options is None:
            options = [None] * b
        if ordered is None:
            ordered = [None] * b
        if num_choices is None:
            num_choices = [None] * b

        with torch.no_grad():
            h = self._encode(obs_t)
            value = self.value_head(h).reshape(-1)
            opt_feats, opt_mask, num_picks, ord_t = self._option_tensors_from_obs(obs_t)
            for i, n in enumerate(num_choices):
                if n is not None:
                    num_picks[i] = int(n)
            for i, flag in enumerate(ordered):
                if flag is not None:
                    ord_t[i] = float(bool(flag))
            use_ar = (num_picks > 0) & (opt_mask.sum(dim=-1) > 0)
            logp = torch.zeros(b, device=device)
            picks_t = torch.zeros(b, self.max_picks, dtype=torch.long, device=device)
            if bool(use_ar.any()):
                ar_picks, ar_logp, _ = self._ar_logprobs(
                    h,
                    opt_feats,
                    opt_mask,
                    num_picks,
                    ord_t,
                    deterministic=deterministic,
                )
                picks_t = torch.where(use_ar.unsqueeze(-1), ar_picks, picks_t)
                logp = torch.where(use_ar, ar_logp, logp)
            flat = ~use_ar
            if bool(flat.any()):
                dist = Categorical(
                    logits=_masked_logits(self.flat_policy_head(h), mask_t)
                )
                action = dist.probs.argmax(dim=-1) if deterministic else dist.sample()
                picks_t[:, 0] = torch.where(flat, action, picks_t[:, 0])
                logp = torch.where(flat, dist.log_prob(action), logp)

        out: list[tuple[int, float, float, list[int], list[int]]] = []
        num_list = num_picks.tolist()
        use_list = use_ar.tolist()
        ord_list = ord_t.tolist()
        logp_list = logp.tolist()
        value_list = value.tolist()
        picks_cpu = picks_t.tolist()
        for i in range(b):
            n = int(num_list[i]) if use_list[i] else 0
            row_picks = [int(x) for x in picks_cpu[i][:n]] if n else []
            if use_list[i] and options[i] is not None:
                choice_vec = picks_to_vector(
                    list(options[i]),
                    row_picks,
                    ordered=float(ord_list[i]) > 0.5,
                )
                flat_idx = -1
            else:
                choice_vec = []
                flat_idx = int(picks_cpu[i][0])
                row_picks = [flat_idx]
            out.append(
                (
                    flat_idx,
                    float(logp_list[i]),
                    float(value_list[i]),
                    row_picks,
                    choice_vec,
                )
            )
        return out

    def evaluate_actions(
        self,
        obs: torch.Tensor,
        mask: torch.Tensor,
        actions: torch.Tensor,
        *,
        picks: torch.Tensor | None = None,
        num_picks: torch.Tensor | None = None,
    ) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        """
        Log-prob, entropy, and value for a batch of independent decisions.

        ``picks`` is [B, MAX_PICKS] option indices when a row uses the
        autoregressive head; otherwise ``actions`` is the flat index.
        """
        if obs.dim() == 1:
            obs = obs.unsqueeze(0)
            mask = mask.unsqueeze(0)
            actions = actions.unsqueeze(0)
            if picks is not None:
                picks = picks.unsqueeze(0)
            if num_picks is not None:
                num_picks = num_picks.unsqueeze(0)
        h = self._encode(obs)
        value = self.value_head(h).reshape(-1)
        opt_feats, opt_mask, auto_n, ord_t = self._option_tensors_from_obs(obs)
        if num_picks is None:
            num_picks = auto_n
        use_ar = (num_picks > 0) & (opt_mask.sum(dim=-1) > 0)
        logp = torch.zeros(obs.shape[0], device=obs.device)
        entropy = torch.zeros(obs.shape[0], device=obs.device)

        if bool(use_ar.any()) and picks is not None:
            _ar_picks, ar_logp, ar_ent = self._ar_logprobs(
                h, opt_feats, opt_mask, num_picks, ord_t, actions=picks
            )
            logp = torch.where(use_ar, ar_logp, logp)
            entropy = torch.where(use_ar, ar_ent, entropy)

        flat = ~use_ar
        if bool(flat.any()):
            logits = _masked_logits(self.flat_policy_head(h), mask)
            dist = Categorical(logits=logits)
            a = actions.long()
            logp = torch.where(flat, dist.log_prob(a), logp)
            entropy = torch.where(flat, dist.entropy(), entropy)
        return logp, entropy, value

    def checkpoint_dict(self) -> dict[str, Any]:
        return {
            "state_dict": self.state_dict(),
            "obs_dim": self.obs_dim,
            "n_actions": self.n_actions,
            "hidden": self.hidden,
            "n_layers": self.n_layers,
            "width": self.width,
            "d_model": self.d_model,
            "nhead": self.nhead,
            "dim_feedforward": self.dim_feedforward,
            "tf_layers": self.tf_layers,
            "lstm_hidden": self.width,
            "max_options": self.max_options,
            "max_picks": self.max_picks,
            "recurrent": False,
            "sequence": "transformer",
            "arch": "transformer_ar",
        }

    @classmethod
    def from_checkpoint(
        cls, data: dict[str, Any], *, map_location: str | torch.device = "cpu"
    ) -> MaskedActorCritic:
        hidden = int(data.get("hidden", 256))
        obs_dim = int(data.get("obs_dim", observation_size()))
        n_layers = int(data.get("n_layers", 2))
        width = int(data.get("width", data.get("lstm_hidden", 128)))
        model = cls(
            obs_dim=obs_dim,
            hidden=hidden,
            n_layers=n_layers,
            width=width,
            max_options=int(data.get("max_options", MAX_OPTIONS)),
            max_picks=int(data.get("max_picks", MAX_PICKS)),
            d_model=int(data.get("d_model", 128)),
            nhead=int(data.get("nhead", 4)),
            dim_feedforward=int(data.get("dim_feedforward", 256)),
            tf_layers=int(data.get("tf_layers", 2)),
        )
        state = data["state_dict"]
        model_state = model.state_dict()
        filtered = {
            k: v
            for k, v in state.items()
            if k in model_state and v.shape == model_state[k].shape
        }
        model_state.update(filtered)
        model.load_state_dict(model_state)
        model.to(map_location)
        model.eval()
        return model
