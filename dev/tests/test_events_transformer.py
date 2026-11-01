"""Formal event rows stay visibility-safe and feed the transformer trunk."""

from __future__ import annotations

import numpy as np
import pytest

torch = pytest.importorskip("torch")

from sixtyfivekmconvoy.env.spaces import flatten_observation, observation_size
from sixtyfivekmconvoy.rl.events import EVENT_PILLAGE, EVENT_WINDOW, make_event
from sixtyfivekmconvoy.rl.policy import MaskedActorCritic


def test_hidden_card_id_is_zeroed():
    hidden = make_event(EVENT_PILLAGE, card_id=12, card_visible=False, amount=3)
    shown = make_event(EVENT_PILLAGE, card_id=12, card_visible=True, amount=3)
    assert hidden[6] == 0 and hidden[8] == 0
    assert shown[6] == 12 and shown[8] == 1


def test_observation_appends_event_window():
    obs = {
        "round": 1,
        "stage": 2,
        "terminal": False,
        "you": 0,
        "resistance": {},
        "players": [],
        "convoy": [],
        "decks": {"rows": []},
        "choice": None,
        "event_rows": [make_event(EVENT_PILLAGE, amount=2, card_visible=False, card_id=9)],
    }
    vec = flatten_observation(obs, 0, 3)
    assert vec.shape == (observation_size(3),)
    assert vec.shape[0] > EVENT_WINDOW


def test_transformer_act_runs():
    dim = observation_size(3)
    model = MaskedActorCritic(
        obs_dim=dim, hidden=32, n_layers=1, lstm_hidden=32, lstm_layers=1, sequence="transformer"
    )
    model.eval()
    obs = np.zeros(dim, dtype=np.float32)
    mask = np.zeros(256, dtype=np.float32)
    mask[0] = 1
    flat, logp, value, picks, vec = model.act(obs, mask, deterministic=True)
    assert flat in (0, -1)
    assert isinstance(logp, float) and isinstance(value, float)
    assert picks
    assert not any(isinstance(m, torch.nn.LSTM) for m in model.modules())
    data = model.checkpoint_dict()
    assert data["sequence"] == "transformer"
    loaded = MaskedActorCritic.from_checkpoint(data)
    assert loaded.sequence == "transformer"
