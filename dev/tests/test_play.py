"""Solo play entry used by the Pyodide page. No FastAPI."""

import json
import os
import subprocess
import sys
from pathlib import Path

from sixtyfivekmconvoy.core.constants import ChoiceType
import numpy as np

from sixtyfivekmconvoy.play import LocalLobby, bot_observation, new_solo, pyodide_files


def test_play_import_does_not_load_fastapi():
    env = os.environ.copy()
    env["PYTHONPATH"] = "src"
    code = (
        "import sixtyfivekmconvoy.play, sys; "
        "assert 'fastapi' not in sys.modules"
    )
    subprocess.check_call([sys.executable, "-c", code], env=env)


def test_pyodide_file_list_is_complete():
    listed = json.loads(Path("web/pyodide_files.json").read_text(encoding="utf-8"))
    assert listed == pyodide_files()
    assert "api/app.py" not in listed
    assert "env/convoy_env.py" not in listed
    assert "rl/policy.py" not in listed
    assert any(name.endswith("action.csv") for name in listed)


def test_new_solo_deals_a_hand_to_the_human():
    session = new_solo(num_players=3, name="Ada", seed=1, pause_after_actions=False)
    snap = session.snapshot("player_0")
    assert snap["pending"]["choicetype"] == int(ChoiceType.PLACE_UNITS)
    placed = session.apply_human_choice("player_0", [0, 1, 2])
    assert placed["state"]["convoy"]


def test_bot_observation_is_a_finite_vector():
    session = new_solo(num_players=3, name="Ada", seed=1, pause_after_actions=False)
    vector = bot_observation(session, "player_1")
    assert vector.ndim == 1
    assert vector.shape[0] > 100
    assert np.isfinite(vector).all()


def test_rules_route_follows_the_retire_profile():
    from sixtyfivekmconvoy.core.configs import load_config

    load_config("retire")
    try:
        status, payload = LocalLobby().handle("GET", "/rules/placeholders", {}, {})
    finally:
        load_config("default")
    assert status == 200
    assert "poistuvat pelistä" in payload["cash_in_sentence"]


def test_local_lobby_starts_after_the_password():
    lobby = LocalLobby()
    status, payload = lobby.handle("POST", "/lobby/unlock", {"password": "nope"}, {})
    assert status == 401
    status, payload = lobby.handle("POST", "/lobby/unlock", {"password": "1234"}, {})
    assert status == 200
    headers = {"X-Convoy-Token": payload["token"]}
    status, opened = lobby.handle(
        "POST",
        "/tables",
        {"num_players": 3, "name": "Ada", "seed": 1, "bot_kind": "random"},
        headers,
    )
    assert status == 200
    status, started = lobby.handle(
        "POST",
        f"/tables/{opened['table_id']}/start?seat=0",
        {},
        headers,
    )
    assert status == 200
    assert started["snapshot"]["pending"]["choicetype"] == int(ChoiceType.PLACE_UNITS)
    status, refused = lobby.handle(
        "POST",
        "/tables",
        {"num_players": 3, "name": "Ada", "seed": 1, "bot_kind": "rl", "bot_id": "x"},
        headers,
    )
    assert status == 400
