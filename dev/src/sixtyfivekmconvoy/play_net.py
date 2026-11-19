"""Deterministic copy of the trained transformer, in NumPy.

The browser loads this instead of PyTorch. ``play`` matches
``MaskedActorCritic.act(..., deterministic=True)`` on the same observation.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from sixtyfivekmconvoy.env.spaces import (
    MAX_HAND,
    MAX_LEGAL,
    MAX_OPTIONS,
    MAX_PICKS,
    MAX_UNITS,
    encode_choice_options,
    flatten_observation,
    option_block_slices,
    picks_to_vector,
)
from sixtyfivekmconvoy.env.card_features import CARD_FEAT_DIM, N_CARD_SLOTS
from sixtyfivekmconvoy.env.table_features import (
    CARD_TOKEN_DIM,
    OFFICER_DIM,
    OFFICER_QUEUE_SLOTS,
    TUCK_DIM,
    UNIT_STACKS,
)
from sixtyfivekmconvoy.rl.events import EVENT_FIELDS, EVENT_WINDOW

BOT_ID = "63ca88c06d48"
BOT_NAME = "curriculum-step1840496"
BOT_STEP = 1840496


def _linear(x: np.ndarray, weight: np.ndarray, bias: np.ndarray) -> np.ndarray:
    return x @ weight.T + bias


def _erf(x: np.ndarray) -> np.ndarray:
    """Hastings approximation. Enough that the trained argmax stays put."""
    sign = np.sign(x)
    ax = np.abs(x)
    t = 1.0 / (1.0 + 0.3275911 * ax)
    poly = (((((1.061405429 * t - 1.453152027) * t) + 1.421413741) * t - 0.284496736) * t + 0.254829592) * t
    return sign * (1.0 - poly * np.exp(-ax * ax))


def _gelu(x: np.ndarray) -> np.ndarray:
    return 0.5 * x * (1.0 + _erf(x / np.sqrt(2.0)))


def _layer_norm(x: np.ndarray, weight: np.ndarray, bias: np.ndarray) -> np.ndarray:
    mean = x.mean(axis=-1, keepdims=True)
    var = x.var(axis=-1, keepdims=True)
    return (x - mean) / np.sqrt(var + 1e-5) * weight + bias


def _sigmoid(x: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-np.clip(x, -60.0, 60.0)))


def _gru_cell(
    x: np.ndarray,
    h: np.ndarray,
    weight_ih: np.ndarray,
    weight_hh: np.ndarray,
    bias_ih: np.ndarray,
    bias_hh: np.ndarray,
) -> np.ndarray:
    gi = _linear(x, weight_ih, bias_ih)
    gh = _linear(h, weight_hh, bias_hh)
    i_r, i_z, i_n = np.split(gi, 3, axis=-1)
    h_r, h_z, h_n = np.split(gh, 3, axis=-1)
    reset = _sigmoid(i_r + h_r)
    update = _sigmoid(i_z + h_z)
    new = np.tanh(i_n + reset * h_n)
    return (1.0 - update) * new + update * h


class NumpyPolicy:
    """One frozen checkpoint. Decisions are argmax, with no hidden state."""

    def __init__(self, weights: dict[str, np.ndarray]):
        self.w = {key: np.asarray(value, dtype=np.float32) for key, value in weights.items()}
        self.d_model = int(self.w["tf_out.weight"].shape[0])
        self.width = int(self.w["tf_out.weight"].shape[1])
        self.nhead = 4
        self.head_dim = self.d_model // self.nhead
        self.layers = sum(1 for key in self.w if key.endswith("self_attn.in_proj_weight") and key.startswith("transformer.layers."))
        self.board_dim = int(self.w["encoder.0.weight"].shape[1])
        self.obs_dim = self.board_dim  # replaced once slices are known
        # The board prefix ends where the option block begins. Recover obs
        # length from the flat head's legal mask living at the end of the vector
        # the checkpoint was trained on: encoder sees board_dim, and the saved
        # net's option block is addressed from the full observation. Callers
        # pass that full vector; the slices below match spaces.option_block_slices
        # for the live layout, which is the layout this checkpoint uses.
        from sixtyfivekmconvoy.env.spaces import observation_size

        self.obs_dim = observation_size()
        fs, fe, ms, me = option_block_slices(self.obs_dim)
        self._opt_feat = (fs, fe)
        self._opt_mask = (ms, me)
        self._tokens = None

    def reset_memory(self) -> None:
        return None

    def _tokens_of(self, obs: np.ndarray, start: int, count: int, dim: int) -> np.ndarray:
        return obs[start : start + count * dim].reshape(count, dim)

    def _layout(self) -> tuple[tuple[int, int], ...]:
        from sixtyfivekmconvoy.env.spaces import token_layout

        return token_layout(self.obs_dim)

    def _encode(self, obs: np.ndarray) -> np.ndarray:
        board = obs[: self.board_dim]
        hidden = np.tanh(_linear(board, self.w["encoder.0.weight"], self.w["encoder.0.bias"]))
        hidden = np.tanh(_linear(hidden, self.w["encoder.2.weight"], self.w["encoder.2.bias"]))
        card_span, officer_span, hand_span, stack_span, tuck_span, event_span = self._layout()
        cards = self._tokens_of(obs, card_span[0], N_CARD_SLOTS, CARD_FEAT_DIM)
        officers = self._tokens_of(obs, officer_span[0], OFFICER_QUEUE_SLOTS, OFFICER_DIM)
        hand = self._tokens_of(obs, hand_span[0], MAX_HAND, CARD_TOKEN_DIM)
        stacks = self._tokens_of(obs, stack_span[0], MAX_UNITS * UNIT_STACKS, CARD_TOKEN_DIM)
        tucks = self._tokens_of(obs, tuck_span[0], MAX_UNITS, TUCK_DIM)
        events = self._tokens_of(obs, event_span[0], EVENT_WINDOW, EVENT_FIELDS)
        pieces = [
            _linear(hidden, self.w["tf_board.weight"], self.w["tf_board.bias"])[None, :],
            _linear(cards, self.w["tf_card.weight"], self.w["tf_card.bias"]),
            _linear(officers, self.w["tf_officer.weight"], self.w["tf_officer.bias"]),
            _linear(hand, self.w["tf_action.weight"], self.w["tf_action.bias"]),
            _linear(stacks, self.w["tf_action.weight"], self.w["tf_action.bias"]),
            _linear(tucks, self.w["tf_tuck.weight"], self.w["tf_tuck.bias"]),
            _linear(events, self.w["tf_event.weight"], self.w["tf_event.bias"]) + self.w["event_pos.weight"],
        ]
        tokens = np.concatenate(pieces, axis=0)
        pad = np.concatenate(
            [
                np.zeros(1, dtype=bool),
                cards[:, 0] <= 0.5,
                officers[:, 0] <= 0.5,
                hand[:, 0] <= 0.5,
                stacks[:, 0] <= 0.5,
                (tucks[:, 0] <= 0.5) & (tucks[:, OFFICER_DIM] <= 0.5),
                events[:, 0] <= 1e-6,
            ]
        )
        hidden_tok = tokens
        for layer in range(self.layers):
            hidden_tok = self._encoder_layer(hidden_tok, pad, layer)
        return _linear(hidden_tok[0], self.w["tf_out.weight"], self.w["tf_out.bias"])

    def _encoder_layer(self, tokens: np.ndarray, pad: np.ndarray, layer: int) -> np.ndarray:
        prefix = f"transformer.layers.{layer}."
        attn = self._attention(tokens, pad, prefix)
        tokens = _layer_norm(tokens + attn, self.w[prefix + "norm1.weight"], self.w[prefix + "norm1.bias"])
        ff = _linear(tokens, self.w[prefix + "linear1.weight"], self.w[prefix + "linear1.bias"])
        ff = _gelu(ff)
        ff = _linear(ff, self.w[prefix + "linear2.weight"], self.w[prefix + "linear2.bias"])
        return _layer_norm(tokens + ff, self.w[prefix + "norm2.weight"], self.w[prefix + "norm2.bias"])

    def _attention(self, tokens: np.ndarray, pad: np.ndarray, prefix: str) -> np.ndarray:
        mixed = _linear(
            tokens,
            self.w[prefix + "self_attn.in_proj_weight"],
            self.w[prefix + "self_attn.in_proj_bias"],
        )
        q, k, v = np.split(mixed, 3, axis=-1)
        seq = tokens.shape[0]
        heads = self.nhead
        dim = self.head_dim
        q = q.reshape(seq, heads, dim).transpose(1, 0, 2)
        k = k.reshape(seq, heads, dim).transpose(1, 0, 2)
        v = v.reshape(seq, heads, dim).transpose(1, 0, 2)
        scores = np.matmul(q, np.swapaxes(k, -1, -2)) / np.sqrt(dim)
        scores[:, :, pad] = -1e30
        scores = scores - scores.max(axis=-1, keepdims=True)
        exp = np.exp(scores)
        attn = exp / exp.sum(axis=-1, keepdims=True)
        mixed = np.matmul(attn, v).transpose(1, 0, 2).reshape(seq, self.d_model)
        return _linear(
            mixed,
            self.w[prefix + "self_attn.out_proj.weight"],
            self.w[prefix + "self_attn.out_proj.bias"],
        )

    def play(self, obs: np.ndarray, mask: np.ndarray) -> tuple[list[int], int, bool, int]:
        """Return option picks, flat index, whether the option head was used, and pick count."""
        obs = np.asarray(obs, dtype=np.float32).reshape(-1)
        mask = np.asarray(mask, dtype=np.float32).reshape(-1)
        hidden = self._encode(obs)
        fs, fe = self._opt_feat
        ms, me = self._opt_mask
        meta = fs - 5
        num_picks = int(np.clip(np.round(obs[meta + 2] * MAX_PICKS), 0, MAX_PICKS))
        opt_feats = obs[fs:fe].reshape(MAX_OPTIONS, -1)
        opt_mask = obs[ms:me]
        use_ar = num_picks > 0 and float(opt_mask.sum()) > 0
        opt_emb = np.tanh(_linear(opt_feats, self.w["option_proj.weight"], self.w["option_proj.bias"]))
        pick_h = hidden
        used = np.zeros(MAX_OPTIONS, dtype=np.float32)
        picks: list[int] = []
        for _step in range(num_picks if use_ar else 0):
            query = np.tanh(_linear(pick_h, self.w["query_proj.weight"], self.w["query_proj.bias"]))
            logits = opt_emb @ query
            step_mask = opt_mask * (1.0 - used)
            logits = np.where(step_mask > 0, logits, -1e30)
            choice = int(np.argmax(logits))
            picks.append(choice)
            used[choice] = 1.0
            pick_h = _gru_cell(
                opt_emb[choice],
                pick_h,
                self.w["pick_gru.weight_ih"],
                self.w["pick_gru.weight_hh"],
                self.w["pick_gru.bias_ih"],
                self.w["pick_gru.bias_hh"],
            )
        flat_logits = _linear(hidden, self.w["flat_policy_head.weight"], self.w["flat_policy_head.bias"])
        flat_logits = np.where(mask > 0, flat_logits, -1e30)
        if not np.any(mask > 0):
            flat_logits = _linear(hidden, self.w["flat_policy_head.weight"], self.w["flat_policy_head.bias"])
        flat = int(np.argmax(flat_logits))
        return picks, flat, use_ar, num_picks

    def choose(
        self,
        legal_actions: list[list[int]],
        *,
        observation: np.ndarray | dict[str, Any] | None = None,
        agent_index: int = 0,
        num_players: int = 3,
        raw_choice: dict[str, Any] | None = None,
        **_ignored: Any,
    ) -> list[int]:
        if not legal_actions:
            return []
        if isinstance(observation, np.ndarray):
            obs = np.asarray(observation, dtype=np.float32)
        else:
            obs = flatten_observation(observation or {}, agent_index, num_players)
        choice = raw_choice
        if choice is None and isinstance(observation, dict):
            choice = observation.get("choice")
        mask = np.zeros(MAX_LEGAL, dtype=np.float32)
        for index in range(min(len(legal_actions), MAX_LEGAL)):
            mask[index] = 1.0
        picks, flat, use_ar, _count = self.play(obs, mask)
        if use_ar and choice is not None:
            options = list(choice.get("options") or [])
            _feats, _mask, num_choices, ordered, _dim = encode_choice_options(choice)
            del _feats, _mask, _dim
            count = int(num_choices or 0)
            choice_vec = picks_to_vector(options, picks[:count], ordered=bool(ordered))
            if choice_vec:
                listed = [list(vec) for vec in legal_actions]
                if choice_vec in listed:
                    return list(choice_vec)
                if ordered is False:
                    target = sorted(choice_vec)
                    for vec in legal_actions:
                        if sorted(vec) == target:
                            return list(vec)
                return list(choice_vec)
        if 0 <= flat < len(legal_actions):
            return list(legal_actions[flat])
        return list(legal_actions[0])

    @classmethod
    def load(cls, path: str) -> NumpyPolicy:
        with np.load(path) as packed:
            weights = {key: packed[key] for key in packed.files}
        return cls(weights)


def save_weights(state: dict[str, Any], path: str) -> None:
    arrays = {key: np.asarray(value, dtype=np.float32) for key, value in state.items()}
    np.savez_compressed(path, **arrays)
