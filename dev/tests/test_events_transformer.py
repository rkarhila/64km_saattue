"""Formal event rows stay visibility-safe and feed the transformer trunk."""

from __future__ import annotations

import numpy as np
import pytest

torch = pytest.importorskip("torch")

from sixtyfivekmconvoy.env.spaces import flatten_observation, observation_size
from sixtyfivekmconvoy.rl.events import EVENT_PILLAGE, EVENT_WINDOW, make_event
from sixtyfivekmconvoy.rl.policy import MaskedActorCritic


def test_fast_observation_matches_player_view():
    from sixtyfivekmconvoy.core.engine import GameEngine
    from sixtyfivekmconvoy.env.spaces import fill_observation

    engine = GameEngine()
    engine.reset(num_players=2, seed=1)
    compared = 0
    for _ in range(40):
        if engine.terminal or engine._pending is None:
            break
        idx = int(engine._pending.player_id.split("_")[1])
        slow = flatten_observation(engine.observe(engine._pending.player_id), idx, 2)
        fast = fill_observation(engine, idx, 2)
        assert slow.shape == fast.shape
        assert np.allclose(slow, fast)
        compared += 1
        engine.step(engine.legal_actions()[0])
    assert compared >= 6


def test_bot_observes_itself_as_first_player():
    from sixtyfivekmconvoy.core.engine import GameEngine
    from sixtyfivekmconvoy.env.spaces import MAX_PLAYERS, fill_observation

    engine = GameEngine()
    engine.reset(num_players=3, seed=3)
    engine.players[0].total_cash = 10
    engine.players[1].total_cash = 20
    engine.players[2].total_cash = 30
    engine._broadcast(
        "acted",
        event_type=1,
        actor=2,
        target=1,
        card_visible=True,
        card_id=4,
        amount=1,
    )
    cash_at = MAX_PLAYERS + 3 + 2 + 1
    for seat, own, nxt, last in (
        (0, 10, 20, 30),
        (1, 20, 30, 10),
        (2, 30, 10, 20),
    ):
        vec = fill_observation(engine, seat, 3)
        slow = flatten_observation(engine.observe(f"player_{seat}"), seat, 3)
        assert np.allclose(vec, slow)
        assert vec[0] == 1.0
        assert vec[1:MAX_PLAYERS].sum() == 0.0
        assert abs(vec[cash_at] - own / 50.0) < 1e-6
        assert abs(vec[cash_at + 4] - nxt / 50.0) < 1e-6
        assert abs(vec[cash_at + 8] - last / 50.0) < 1e-6
        # Newest event: actor 2 and target 1, rotated into the viewer's frame.
        actor = (2 - seat) % 3
        target = (1 - seat) % 3
        assert abs(vec[-6] - (actor + 1) / 6.0) < 1e-6
        assert abs(vec[-5] - (target + 1) / 6.0) < 1e-6


def test_event_ring_drops_text_log_when_disabled():
    from sixtyfivekmconvoy.core.engine import GameEngine
    from sixtyfivekmconvoy.rl.events import EVENT_WINDOW

    engine = GameEngine()
    engine.record_text_log = False
    engine.reset(num_players=2, seed=2)
    assert engine.messages == []
    for i in range(EVENT_WINDOW + 8):
        engine._broadcast(
            f"line {i}",
            event_type=1,
            card_visible=True,
            card_id=i,
            amount=1,
        )
    assert engine.messages == []
    assert len(engine.event_rows) == EVENT_WINDOW
    assert list(engine.event_rows)[-1][6] == EVENT_WINDOW + 7


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
