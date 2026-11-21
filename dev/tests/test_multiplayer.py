"""Several humans at one table: cap, simultaneous placement, per-player log."""

from sixtyfivekmconvoy.api.session import SessionManager
from sixtyfivekmconvoy.core.constants import ChoiceType


def _two_humans(pause=True):
    mgr = SessionManager(max_games=3)
    table = mgr.create_table(num_players=3, name="Foo", seed=1, pause_after_actions=pause)
    mgr.join_table(table.table_id, "Bar")
    session, _human = mgr.start_table(table.table_id)
    return mgr, session


def test_table_requires_a_player_name():
    mgr = SessionManager(max_games=2)
    try:
        mgr.create_table(num_players=2, name="  ", seed=1)
        created = True
    except ValueError as exc:
        created = False
        assert "nimi" in str(exc).lower()
    assert not created
    table = mgr.create_table(num_players=2, name="Foo", seed=1)
    try:
        mgr.join_table(table.table_id, "")
        joined = True
    except ValueError:
        joined = False
    assert not joined


def test_lobby_password_defaults_and_can_be_replaced():
    from fastapi import HTTPException

    from sixtyfivekmconvoy.api.app import (
        UnlockRequest,
        issue_gate_token,
        lobby_password_matches,
        set_lobby_password,
        unlock_lobby,
    )

    set_lobby_password("")
    assert lobby_password_matches("1234")
    assert not lobby_password_matches("nope")
    set_lobby_password("salasana")
    try:
        unlock_lobby(UnlockRequest(password="1234"))
        opened = True
    except HTTPException as exc:
        opened = False
        assert exc.status_code == 401
    assert not opened
    token = unlock_lobby(UnlockRequest(password="salasana"))["token"]
    assert token == issue_gate_token()
    set_lobby_password("1234")


def test_waiting_tables_count_toward_the_cap():
    mgr = SessionManager(max_games=2)
    mgr.create_table(num_players=2, name="A", seed=1)
    mgr.create(num_players=2, seed=2)
    try:
        mgr.create_table(num_players=2, name="B", seed=3)
        raised = False
    except RuntimeError:
        raised = True
    assert raised
    status = mgr.lobby_status()
    assert status["max_games"] == 2
    assert status["games_in_use"] == 2
    assert len(status["tables"]) == 1


def test_join_then_start_leaves_empty_seats_as_bots():
    mgr = SessionManager(max_games=3)
    table = mgr.create_table(num_players=3, name="Foo", seed=4, pause_after_actions=False)
    _table, seat = mgr.join_table(table.table_id, "Bar")
    assert seat == 1
    session, human = mgr.start_table(table.table_id, seat=0)
    assert human == "player_0"
    assert session.human_seats == {"player_0", "player_1"}
    assert "player_2" in session.bots
    assert session.engine.players[0].name == "Foo"
    assert session.engine.players[1].name == "Bar"
    assert session.engine.players[2].name == "Botti"
    assert table.started_game_id == session.game_id
    # The waiting table no longer occupies a second slot.
    assert mgr.lobby_status()["games_in_use"] == 1
    try:
        mgr.join_table(table.table_id, "Late")
        joined = True
    except ValueError:
        joined = False
    assert not joined


def test_assign_lists_every_waiting_unit_at_once():
    _mgr, session = _two_humans(pause=False)
    session.apply_human_choice("player_1", [2, 1, 0])
    session.apply_human_choice("player_0", [0, 1, 2])
    snap = session.snapshot("player_0")
    pending = snap["pending"]
    assert pending["choicetype"] == int(ChoiceType.CHOOSE_CARD)
    assert pending["num_choice"] == 1
    assert pending["payload"]["reason"] == "assign"
    assert len(pending["assign_units"]) == 3
    assert pending["assign_units"][0]["index"] == pending["payload"]["assign_unit"]["index"]


def test_one_assign_click_keeps_every_card():
    mgr = SessionManager(max_games=2)
    table = mgr.create_table(num_players=3, name="Ada", seed=4, pause_after_actions=True)
    session, _human = mgr.start_table(table.table_id)
    session.apply_human_choice("player_0", [0, 1, 2])
    if session.awaiting_continue:
        session.continue_play("player_0")
    snap = session.snapshot("player_0")
    pending = snap["pending"]
    cards = list(pending["options"][: len(pending["assign_units"])])
    assert len(cards) == 3
    session.apply_human_choice("player_0", cards)
    player = session.engine.players[0]
    units = [u for u in session.engine.convoy.units if u.player is player]
    assert [u.actioncard for u in units] == [[card] for card in cards]
    for card in cards:
        assert card not in player.action_cards


def test_humans_place_units_at_the_same_time():
    _mgr, session = _two_humans()
    assert session.engine.setup_complete is False
    red = session.snapshot("player_0")
    blue = session.snapshot("player_1")
    assert red["pending"]["choicetype"] == int(ChoiceType.PLACE_UNITS)
    assert blue["pending"]["choicetype"] == int(ChoiceType.PLACE_UNITS)
    assert red["pending"]["payload"]["slots"] != blue["pending"]["payload"]["slots"]
    assert "Foo" in red["waiting_for"]
    assert "Bar" in red["waiting_for"]
    assert "sijoittamaan joukot" in red["waiting_for"]

    # Blue may submit before red. The convoy stays unbuilt until both have chosen.
    session.apply_human_choice("player_1", [2, 1, 0])
    assert session.engine.setup_complete is False
    assert session.snapshot("player_1")["pending"] is None
    still = session.snapshot("player_0")
    assert still["pending"]["choicetype"] == int(ChoiceType.PLACE_UNITS)
    assert "Foo" in still["waiting_for"]
    assert "Bar" not in still["waiting_for"]

    session.apply_human_choice("player_0", [0, 1, 2])
    assert session.engine.setup_complete is True
    assert len(session.engine.convoy.units) == 9


def test_one_players_log_clicks_do_not_block_the_other():
    _mgr, session = _two_humans(pause=True)
    session.apply_human_choice("player_1", [2, 1, 0])
    session.apply_human_choice("player_0", [0, 1, 2])
    blue = session.snapshot("player_1")
    red = session.snapshot("player_0")
    assert blue["awaiting_continue"] is True
    # The seat that must act still pages lines about the other units first.
    assert red["awaiting_continue"] is True
    assert red["pending"] is None
    assert "Foo" in blue["waiting_for"]
    assert "ryöstö" not in blue["waiting_for"]
    pending = session.engine.pending_choice()
    session.continue_play("player_1")
    assert session.engine.pending_choice() is pending
    for _ in range(80):
        red = session.snapshot("player_0")
        if not red["awaiting_continue"]:
            break
        session.continue_play("player_0")
    else:
        raise AssertionError("red never finished paging the log")
    red = session.snapshot("player_0")
    assert red["legal_actions"]
    # Blue can still be behind. That does not block red's choice.
    assert session.snapshot("player_1")["awaiting_continue"] is True
    session.apply_human_choice("player_0", red["legal_actions"][0])
    assert session.engine.pending_choice() is not pending


def test_web_snapshot_drops_training_events_and_old_log_lines():
    _mgr, session = _two_humans(pause=True)
    session.engine.messages.extend(f"line {i}" for i in range(80))
    session.engine.event_log.append({"msg": "training-only"})
    snap = session.snapshot("player_0")
    assert "events" not in snap["state"]
    assert "event_rows" not in snap["state"]
    assert len(snap["state"]["log"]) == 60
    assert snap["state"]["log"][-1] == "line 79"
    assert snap["awaiting_continue"] is True
    assert snap["pending"] is None


def test_log_pause_does_not_leave_the_bot_unacted():
    """A pause after one seat must not freeze the table before the bot between them."""
    _mgr, session = _two_humans(pause=True)
    session.apply_human_choice("player_0", [0, 1, 2])
    session.apply_human_choice("player_1", [1, 2, 0])
    saw_action = False
    for _ in range(80):
        if session.engine.terminal:
            break
        pending = session.engine.pending_choice()
        assert pending is not None
        assert pending.choicetype != ChoiceType.LOG_PAUSE
        if pending.choicetype == ChoiceType.CHOOSE_ACTION:
            saw_action = True
            actor = pending.player_id
            unit_index = (pending.payload or {}).get("unit_index")
            if isinstance(unit_index, int):
                for unit in session.engine.convoy.units:
                    if unit.index() >= unit_index:
                        break
                    if unit.player.agent_id() == actor:
                        continue
                    assert unit.actiontaken, (
                        f"{unit.player.agent_id()} at {unit.index()} has not acted, "
                        f"but the game is waiting on {actor}"
                    )
        assert pending.player_id in session.human_seats
        legal = session.engine.legal_actions()
        assert legal
        session.apply_human_choice(pending.player_id, list(legal[0]))
    assert saw_action


def test_waiting_line_names_a_pillage_choice():
    from sixtyfivekmconvoy.core.engine import ChoiceRequest

    _mgr, session = _two_humans(pause=False)
    session.placement_answers = None
    session.engine._pending = ChoiceRequest(
        player_id="player_0",
        choicetype=ChoiceType.CHOOSE_PILLAGE_CARD,
        options=[0, 1],
        num_choices=1,
        description="pillage",
    )
    text = session.waiting_for_text()
    assert text == "Odotetaan punaista pelaajaa Foo valitsemaan ryöstökortteja"
