"""Helpers for timed fork schedule (sibling sampling + wall-clock config)."""

from __future__ import annotations

import numpy as np
import pytest

torch = pytest.importorskip("torch")

from sixtyfivekmconvoy.env.spaces import observation_size
from sixtyfivekmconvoy.rl.league import League
from sixtyfivekmconvoy.rl.policy import MaskedActorCritic
from sixtyfivekmconvoy.rl.selfplay import SelfPlayConfig


def test_sample_opponent_prefer_ids(tmp_path):
    league = League(tmp_path / "league")
    model = MaskedActorCritic(
        obs_dim=observation_size(3), hidden=16, n_layers=1, lstm_hidden=16, lstm_layers=1
    )
    a = league.add(model, name="alpha-x", tags=["alpha"])
    b = league.add(model, name="beta-x", tags=["beta"])
    league.add(model, name="other", tags=["other"])
    rng = np.random.default_rng(0)
    ids = league.sample_opponent_ids(
        rng,
        k=40,
        prefer_ids=[b.id],
        prefer_id_weight=0.9,
        include_latest_weight=0.0,
    )
    assert ids.count(b.id) >= 25


def test_resolve_flexible_prefix(tmp_path):
    league = League(tmp_path / "league")
    model = MaskedActorCritic(
        obs_dim=observation_size(3), hidden=16, n_layers=1, lstm_hidden=16, lstm_layers=1
    )
    league.add(model, name="main-init")
    later = league.add(model, name="main-step100")
    hit = league.resolve_flexible("main")
    assert hit.id == later.id


def test_selfplay_config_wallclock_fields():
    cfg = SelfPlayConfig(max_seconds=60.0, pp_reward=0.4, cash_reward=0.1)
    assert cfg.max_seconds == 60.0
    assert cfg.pp_reward == 0.4
