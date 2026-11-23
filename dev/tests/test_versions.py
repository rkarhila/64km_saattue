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
        assert meta["cards"][: len(CARD_FILES)] == list(CARD_FILES)
        assert (folder / "config.py").is_file()
        for name in meta["cards"]:
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
from sixtyfivekmconvoy.core.config import (
    CARDS_TO_DEAL,
    CASH_TO_WIN,
    CONFIG_NAME,
    MAULING_QUEUE_FACE_UP,
    PILLAGE_QUEUE_FACE_UP,
    RESISTANCE_QUEUE_LENGTH,
    SCOUT_RESISTANCE_DRAW,
    USE_OFFICER_QUEUE,
)
from sixtyfivekmconvoy.core.constants import ChoiceType
from sixtyfivekmconvoy.core.engine import GameEngine

assert CONFIG_NAME == "minimal"
assert CARDS_TO_DEAL == 3
assert CASH_TO_WIN == 5
assert USE_OFFICER_QUEUE is False
assert MAULING_QUEUE_FACE_UP is True
assert PILLAGE_QUEUE_FACE_UP is True
assert RESISTANCE_QUEUE_LENGTH == 1
assert SCOUT_RESISTANCE_DRAW == 1
engine = GameEngine()
engine.reset(num_players=3, seed=1)
assert len(engine.officer_queue) == 0
assert len(engine.resistance_queue) == 1
front_id, front_visible = engine.resistance_queue.cards_and_visibilities[0]
assert front_visible is True
assert engine.resistance.name == engine.resistance_deck.get_name(front_id)
assert engine.mauling_queue.cards_and_visibilities
assert all(visible for _, visible in engine.mauling_queue.cards_and_visibilities)
pending = engine.pending_choice()
assert pending is not None
assert pending.choicetype == ChoiceType.PLACE_UNITS
assert len(engine.players[0].action_cards) == 3
assert engine.resistance.active
assert engine.resistance.durability == 1
assert engine.resistance.name == "Rajaportti"
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


def test_default_queues_show_officers_and_hide_card_backs():
    from sixtyfivekmconvoy.core.config import (
        MAULING_QUEUE_FACE_UP,
        PILLAGE_QUEUE_FACE_UP,
        USE_OFFICER_QUEUE,
    )
    from sixtyfivekmconvoy.core.engine import GameEngine
    from sixtyfivekmconvoy.core.view import player_view

    assert USE_OFFICER_QUEUE is True
    assert MAULING_QUEUE_FACE_UP is False
    assert PILLAGE_QUEUE_FACE_UP is False
    engine = GameEngine()
    engine.reset(num_players=2, seed=1)
    assert len(engine.officer_queue) == 2
    visible = [flag for _, flag in engine.mauling_queue.cards_and_visibilities]
    assert visible[0] is True
    assert visible[1:] == [False, False]
    engine.resistance.loot = 1
    engine.resistance.distribute_loot()
    assert engine.pillage_queue.cards_and_visibilities[-1][1] is False
    view = player_view(engine, engine.players[0])
    rows = view["decks"]["rows"]
    assert "officer" in [row["key"] for row in rows]
    assert view["cards_to_deal"] == 5
    assert view["promotions_to_win"] == 6
    assert view["cash_to_win"] == 25
    assert view["acting_unit"] is None


def test_face_up_queues_and_hidden_officers(monkeypatch):
    import sixtyfivekmconvoy.core.config as game_config
    from sixtyfivekmconvoy.core.engine import GameEngine
    from sixtyfivekmconvoy.core.view import player_view

    monkeypatch.setattr(game_config, "USE_OFFICER_QUEUE", False)
    monkeypatch.setattr(game_config, "MAULING_QUEUE_FACE_UP", True)
    monkeypatch.setattr(game_config, "PILLAGE_QUEUE_FACE_UP", True)
    engine = GameEngine()
    engine.reset(num_players=2, seed=1)
    assert len(engine.officer_queue) == 0
    assert all(flag for _, flag in engine.mauling_queue.cards_and_visibilities)
    engine.resistance.loot = 1
    engine.resistance.distribute_loot()
    assert engine.pillage_queue.cards_and_visibilities[-1][1] is True
    rows = player_view(engine, engine.players[0])["decks"]["rows"]
    assert "officer" not in [row["key"] for row in rows]


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


def test_extra_card_csv_is_part_of_the_rules_copy(tmp_path, monkeypatch):
    version = tmp_path / "versions" / "sample"
    cards = version / "cards"
    cards.mkdir(parents=True)
    (version / "config.py").write_text("CONFIG_NAME = 'sample'\n", encoding="utf-8")
    for name in CARD_FILES:
        (cards / name).write_text("same\n", encoding="utf-8")
    (cards / "action_defs.csv").write_text("key\n", encoding="utf-8")
    monkeypatch.setenv("CONVOY_VERSIONS", str(tmp_path / "versions"))
    monkeypatch.setenv("CONVOY_VERSION", "sample")
    snap = tmp_path / "checkpoint"
    snapshot_rules(snap)
    assert (snap / "cards" / "action_defs.csv").read_text(encoding="utf-8") == "key\n"
    (cards / "action_defs.csv").write_text("changed\n", encoding="utf-8")
    warning = rules_warning(snap, (version / "config.py", cards))
    assert warning is not None
    assert "cards/action_defs.csv" in warning


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
