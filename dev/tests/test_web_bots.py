"""Web session bots: random vs league RL."""

from __future__ import annotations

from pathlib import Path

import pytest

from sixtyfivekmconvoy.api.bots import default_league_path, list_league_bots, make_seat_bots
from sixtyfivekmconvoy.api.session import SessionManager


def test_list_league_bots_from_training_run():
    root = Path("runs/league")
    if not (root / "league.json").exists():
        pytest.skip("no runs/league from training")
    payload = list_league_bots(root)
    assert payload["exists"]
    assert payload["bots"]
    assert payload["bots"][0]["id"]
    assert "label" in payload["bots"][0]


def test_make_random_bots():
    bots, meta = make_seat_bots(
        ["player_0", "player_1", "player_2"],
        human_id="player_0",
        seed=1,
        bot_kind="random",
    )
    assert set(bots) == {"player_1", "player_2"}
    assert meta["bot_kind"] == "random"
    assert bots["player_1"].choose([[0], [1]]) in ([0], [1])


def test_session_create_with_rl_bot():
    pytest.importorskip("torch")
    root = Path("runs/league")
    if not (root / "league.json").exists():
        pytest.skip("no runs/league from training")
    bots = list_league_bots(root)["bots"]
    assert bots
    mgr = SessionManager()
    session = mgr.create(
        num_players=3,
        human_seat=0,
        seed=2,
        pause_after_actions=False,
        bot_kind="rl",
        bot_id=bots[0]["id"],
        league_path=str(root),
    )
    assert session.bot_meta["bot_kind"] == "rl"
    assert session.bot_meta["bot_id"] == bots[0]["id"]
    snap = session.snapshot("player_0")
    assert snap["bots"]["bot_kind"] == "rl"
    # Bots should have advanced past pure human-only pending if any.
    assert "player_1" in session.bots


def test_default_league_path_points_somewhere():
    path = default_league_path()
    assert path.name == "league"
