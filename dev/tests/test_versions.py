"""Version directories supply a config module and their own card files."""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from sixtyfivekmconvoy.api.bots import list_league_bots
from sixtyfivekmconvoy.core.cards import _cards_path
from sixtyfivekmconvoy.core.configs import available_configs, config_name, load_config
from sixtyfivekmconvoy.core.versions import (
    CARD_FILES,
    rules_warning,
    snapshot_rules,
    versions_root,
)

_DEV = Path(__file__).resolve().parents[1]


def test_version_directories_are_self_contained():
    root = versions_root()
    assert root == _DEV / "versions"
    index = json.loads((root / "index.json").read_text(encoding="utf-8"))
    ids = [entry["id"] for entry in index["versions"]]
    assert ids == ["alpha_01", "minimal", "dev"]
    for version_id in ids:
        folder = root / version_id
        meta = json.loads((folder / "version.json").read_text(encoding="utf-8"))
        assert meta["id"] == version_id
        assert meta["cards"] == list(CARD_FILES)
        assert (folder / "config.py").is_file()
        for name in CARD_FILES:
            assert (folder / "cards" / name).is_file()


def test_selected_version_loads_its_config_and_cards(monkeypatch):
    previous = config_name()
    monkeypatch.setenv("CONVOY_VERSIONS", str(_DEV / "versions"))
    monkeypatch.setenv("CONVOY_VERSION", "alpha_01")
    monkeypatch.setenv("CONVOY_CARDS", str(_DEV / "versions" / "dev" / "cards"))
    try:
        cfg = load_config()
        assert cfg.CONFIG_NAME == "alpha_01"
        assert cfg.CASH_IN_REMOVES_FROM_PLAY is True
        assert cfg.CASH_TO_WIN == 25
        path = Path(_cards_path("pillage.csv")).resolve()
        assert path == (_DEV / "versions" / "dev" / "cards" / "pillage.csv").resolve()
    finally:
        monkeypatch.delenv("CONVOY_VERSION", raising=False)
        if previous in available_configs():
            load_config(previous)
        else:
            load_config("default")


def test_minimal_loop_boots():
    env = os.environ.copy()
    env["CONVOY_VERSION"] = "minimal"
    env["CONVOY_VERSIONS"] = str(_DEV / "versions")
    env["PYTHONPATH"] = "src"
    script = """
from sixtyfivekmconvoy.core.config import CARDS_TO_DEAL, CASH_TO_WIN, CONFIG_NAME
from sixtyfivekmconvoy.core.constants import ChoiceType
from sixtyfivekmconvoy.core.engine import GameEngine

assert CONFIG_NAME == "minimal"
assert CARDS_TO_DEAL == 3
assert CASH_TO_WIN == 5
engine = GameEngine()
engine.reset(num_players=3, seed=1)
pending = engine.pending_choice()
assert pending is not None
assert pending.choicetype == ChoiceType.PLACE_UNITS
assert len(engine.players[0].action_cards) == 3
assert engine.resistance.active
assert engine.resistance.durability == 1
assert engine.resistance.name == "Tiesulku"
for _ in range(3):
    engine.step([0])
pending = engine.pending_choice()
assert pending is not None
assert pending.choicetype == ChoiceType.CHOOSE_CARD
"""
    subprocess.run(
        [sys.executable, "-c", script],
        cwd=_DEV,
        env=env,
        check=True,
    )


def test_rules_warning_names_the_changed_card(tmp_path):
    live = tmp_path / "version"
    cards = live / "cards"
    cards.mkdir(parents=True)
    (live / "config.py").write_text("CONFIG_NAME = 'sample'\n", encoding="utf-8")
    for name in CARD_FILES:
        (cards / name).write_text("same\n", encoding="utf-8")
    snap = tmp_path / "checkpoint"
    shutil.copytree(live, snap)
    live_paths = (live / "config.py", cards)
    assert rules_warning(snap, live_paths) is None
    (cards / "pillage.csv").write_text("changed\n", encoding="utf-8")
    warning = rules_warning(snap, live_paths)
    assert warning is not None
    assert "cards/pillage.csv" in warning
    assert rules_warning(tmp_path / "missing", live_paths)


def test_listed_checkpoint_warns_after_a_card_edit(tmp_path, monkeypatch):
    version = tmp_path / "versions" / "sample"
    cards = version / "cards"
    cards.mkdir(parents=True)
    (version / "config.py").write_text("CONFIG_NAME = 'sample'\n", encoding="utf-8")
    for name in CARD_FILES:
        (cards / name).write_text("same\n", encoding="utf-8")
    monkeypatch.setenv("CONVOY_VERSIONS", str(tmp_path / "versions"))
    monkeypatch.setenv("CONVOY_VERSION", "sample")
    monkeypatch.delenv("CONVOY_LEAGUE", raising=False)
    bots = version / "bots"
    snapshot_rules(bots / "checkpoints" / "abc.rules")
    (bots / "league.json").write_text(
        json.dumps(
            {
                "entries": [
                    {
                        "id": "abc",
                        "name": "sample-bot",
                        "active": True,
                        "step": 3,
                        "created_at": 1,
                        "rules": "checkpoints/abc.rules",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    (cards / "action.csv").write_text("edited\n", encoding="utf-8")
    payload = list_league_bots(bots)
    assert payload["exists"]
    assert "cards/action.csv" in (payload["bots"][0]["warning"] or "")


def test_server_version_is_chosen_before_import():
    env = os.environ.copy()
    env.pop("CONVOY_VERSION", None)
    env.pop("CONVOY_CARDS", None)
    env["PYTHONPATH"] = "src"
    script = """
from sixtyfivekmconvoy.boot import prepare_version
prepare_version("minimal")
from sixtyfivekmconvoy.core.config import CASH_TO_WIN, CONFIG_NAME
from sixtyfivekmconvoy.core.cards import _cards_dir
assert CONFIG_NAME == "minimal"
assert CASH_TO_WIN == 5
assert _cards_dir().endswith("versions/minimal/cards")
"""
    subprocess.run(
        [sys.executable, "-c", script],
        cwd=_DEV,
        env=env,
        check=True,
    )
