"""Recurrent policy, richer obs, and AR multi-slot decoding."""

from __future__ import annotations

import numpy as np
import pytest

torch = pytest.importorskip("torch")

from sixtyfivekmconvoy.core.constants import ChoiceType
from sixtyfivekmconvoy.env.spaces import (
    MAX_OPTIONS,
    encode_choice_options,
    flatten_observation,
    observation_size,
    picks_to_vector,
)
from sixtyfivekmconvoy.rl.agent import RLAgent
from sixtyfivekmconvoy.rl.policy import MaskedActorCritic


def test_observation_includes_queues_and_options_without_facedown_ids():
    obs = {
        "round": 1,
        "stage": 2,
        "terminal": False,
        "you": 0,
        "resistance": {"active": True, "durability": 5},
        "players": [
            {
                "number": 0,
                "cash_this_round": 1,
                "total_cash": 10,
                "promotion_points": 2,
                "card_count": 3,
                "cards": [1, 2, 3],
            }
        ],
        "convoy": [],
        "decks": {
            "rows": [
                {
                    "key": "pillage",
                    "deck": 10,
                    "discard": 1,
                    "queue": [
                        {"visible": False},
                        {"visible": True, "id": 7, "name": "Loot"},
                    ],
                },
                {"key": "resistance", "deck": 5, "discard": 0, "queue": []},
                {"key": "mauling", "deck": 5, "discard": 0, "queue": []},
                {"key": "officer", "deck": 5, "discard": 0, "queue": []},
            ]
        },
        "choice": {
            "choicetype": int(ChoiceType.CHOOSE_PILLAGE_CARD),
            "options": [7, 9],
            "num_choice": 1,
        },
    }
    vec = flatten_observation(obs, 0, 3)
    assert vec.shape == (observation_size(3),)
    assert vec.dtype == np.float32
    # Face-down queue entries must not inject a real card id into the vector
    # beyond the hidden-count feature (id 7 appears only as a visible slot).
    assert observation_size() > 169


def test_picks_to_vector_ordered_and_unordered():
    opts = [10, 20, 30]
    assert picks_to_vector(opts, [2, 0], ordered=True) == [30, 10]
    assert picks_to_vector(opts, [2, 0], ordered=False) == [10, 30]


def test_encode_choice_options_mask():
    feats, mask, n, ordered, ctype = encode_choice_options(
        {
            "choicetype": int(ChoiceType.CHOOSE_CARDS_TO_DISCARD),
            "options": [1, 2, 3, 4],
            "num_choice": 2,
        }
    )
    assert feats.shape == (MAX_OPTIONS, 4)
    assert mask.sum() == 4
    assert n == 2
    assert ordered is False
    assert ctype == int(ChoiceType.CHOOSE_CARDS_TO_DISCARD)


def test_transformer_checkpoint_roundtrip(tmp_path):
    dim = observation_size(3)
    model = MaskedActorCritic(
        obs_dim=dim,
        hidden=32,
        n_layers=1,
        width=24,
        d_model=32,
        nhead=4,
        dim_feedforward=64,
        tf_layers=1,
    )
    assert not any(isinstance(m, torch.nn.LSTM) for m in model.modules())
    path = tmp_path / "ckpt.pt"
    torch.save({"policy": model.checkpoint_dict()}, path)
    loaded = MaskedActorCritic.from_checkpoint(
        torch.load(path, map_location="cpu", weights_only=False)["policy"]
    )
    assert loaded.width == 24
    assert loaded.d_model == 32
    assert loaded.tf_layers == 1
    assert loaded.sequence == "transformer"
    assert loaded.obs_dim == dim
    bot = RLAgent(loaded, deterministic=True)
    obs = np.zeros(dim, dtype=np.float32)
    mask = np.zeros(256, dtype=np.float32)
    mask[:3] = 1
    a1 = bot.act(obs, [[0], [1], [2]], action_mask=mask)
    a2 = bot.act(obs, [[0], [1], [2]], action_mask=mask)
    assert a1 in (0, 1, 2) and a2 in (0, 1, 2)
    bot.reset_memory()


def test_act_batch_matches_single_row():
    dim = observation_size(3)
    model = MaskedActorCritic(obs_dim=dim, hidden=32, n_layers=1, width=24)
    model.eval()
    obs = np.zeros((3, dim), dtype=np.float32)
    mask = np.zeros((3, 256), dtype=np.float32)
    mask[:, 0] = 1
    rows = model.act_batch(obs, mask, deterministic=True)
    assert len(rows) == 3
    one = model.act(obs[0], mask[0], deterministic=True)
    assert rows[0][0] == one[0]
    assert rows[0][2] == one[2]


def test_gae_stops_at_episode_boundary():
    from sixtyfivekmconvoy.rl.buffer import RolloutBuffer

    buf = RolloutBuffer(obs_dim=4, n_actions=2, capacity=8, gamma=1.0, gae_lambda=1.0)
    step = {
        "obs": np.zeros(4, np.float32),
        "mask": np.ones(2, np.float32),
        "action_idx": 0,
        "logprob": 0.0,
        "value": 0.0,
        "picks": [0],
        "num_picks": 0,
    }
    buf.extend_episode([{**step, "reward": 1.0, "done": True}])
    buf.extend_episode([{**step, "reward": 0.0, "done": True}])
    # gamma=1, value=0, lambda=1 → advantage equals that step's own reward.
    assert buf.advantages[0] == pytest.approx(1.0)
    assert buf.advantages[1] == pytest.approx(0.0)


def test_ar_act_returns_choice_vector():
    dim = observation_size(3)
    model = MaskedActorCritic(obs_dim=dim, hidden=32, n_layers=1, lstm_hidden=24)
    model.eval()
    choice = {
        "choicetype": int(ChoiceType.CHOOSE_CARDS_TO_DISCARD),
        "options": [5, 6, 7],
        "num_choice": 2,
    }
    raw = {
        "round": 0,
        "stage": 0,
        "terminal": False,
        "you": 0,
        "resistance": {},
        "players": [{"number": 0, "card_count": 0, "cards": []}],
        "convoy": [],
        "decks": {"rows": []},
        "choice": choice,
    }
    obs = flatten_observation(raw, 0, 3)
    mask = np.ones(256, dtype=np.float32)
    flat, logp, val, picks, vec = model.act(
        obs,
        mask,
        deterministic=True,
        options=choice["options"],
        ordered=False,
        num_choices=2,
    )
    assert len(picks) == 2
    assert len(vec) == 2
    assert set(vec).issubset({5, 6, 7})
    assert flat == -1
    assert isinstance(logp, float) and isinstance(val, float)
