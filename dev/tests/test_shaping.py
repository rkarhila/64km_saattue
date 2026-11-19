"""Training-only shaping notes. They do not pay in-game cash."""

from __future__ import annotations

from sixtyfivekmconvoy.core.actions import _apply_category_hit, resolve_action
from sixtyfivekmconvoy.core.constants import ActionName
from sixtyfivekmconvoy.core.engine import GameEngine
from sixtyfivekmconvoy.core.models import Unit, UnitType


def _finish(gen):
    try:
        next(gen)
    except StopIteration as stop:
        return stop.value
    raise AssertionError("action asked for a choice")


def _engine(players: int = 2) -> GameEngine:
    engine = GameEngine()
    engine.reset(num_players=players, seed=1)
    engine.pause_after_actions = False
    return engine


def _seat(engine: GameEngine, count: int = 3) -> list[Unit]:
    owner = engine.players[0]
    seated = []
    for _ in range(count):
        unit = Unit(owner, UnitType.INFANTRY)
        unit.convoy = engine.convoy
        unit.engine = engine
        seated.append(unit)
    engine.convoy.units = seated
    return seated


def _show_mauling(engine: GameEngine, card_id: int, *, visible: bool) -> None:
    engine.mauling_queue.cards_and_visibilities.insert(0, [card_id, visible])


def _kinds(engine: GameEngine) -> list[str]:
    return [event["kind"] for event in engine.take_shaping_events()]


def test_rest_relief_counts_tired_and_influence_together():
    engine = _engine()
    unit = _seat(engine)[0]
    action = {"action_name": ActionName.REST, "action_modifier": 0, "cost": 0, "name": "Lepo"}

    unit.tired = 2
    unit.under_influence = 0
    _finish(resolve_action(engine, 0, action, 0))
    assert _kinds(engine) == []

    unit.tired = 2
    unit.under_influence = 1
    _finish(resolve_action(engine, unit.index(), action, 0))
    assert _kinds(engine) == ["rest_relief"]

    unit.tired = 0
    unit.under_influence = 3
    _finish(resolve_action(engine, unit.index(), action, 0))
    assert _kinds(engine) == ["rest_relief"]


def test_retreat_off_a_visible_mauling_target_is_noted():
    engine = _engine()
    _seat(engine)
    # Card 27 aims at A1, the front of zone A (index 0 with two players).
    _show_mauling(engine, 27, visible=True)
    action = {
        "action_name": ActionName.RETREAT,
        "action_modifier": 1,
        "cost": 0,
        "name": "Suojatulta!",
    }
    mover = engine.convoy.units[0]
    _finish(resolve_action(engine, 0, action, 0))
    assert mover.index() != 0
    assert _kinds(engine) == ["mauling_dodge"]


def test_hidden_mauling_and_a_move_that_stays_targeted_pay_nothing():
    hidden = _engine()
    _seat(hidden)
    _show_mauling(hidden, 27, visible=False)
    action = {
        "action_name": ActionName.RETREAT,
        "action_modifier": 1,
        "cost": 0,
        "name": "Suojatulta!",
    }
    _finish(resolve_action(hidden, 0, action, 0))
    assert _kinds(hidden) == []

    # Card 20 hits all of zone A. With three players that zone is two seats,
    # so one step back stays inside it.
    staying = _engine(3)
    # Four units keeps index 1 inside zone A. The exit zone would otherwise
    # swallow the back of a three-unit convoy.
    _seat(staying, 4)
    _show_mauling(staying, 20, visible=True)
    mover = staying.convoy.units[0]
    _finish(resolve_action(staying, 0, action, 0))
    assert mover.zone() == "A"
    assert _kinds(staying) == []


def test_mauling_penalty_scales_with_damage_drawn():
    engine = _engine()
    unit = _seat(engine)[0]
    engine.draw_hit_damage = lambda category: 4  # type: ignore[method-assign]
    _apply_category_hit(engine, unit, 1, "G")
    events = engine.take_shaping_events()
    assert events == [{"kind": "mauling_damage", "player": unit.player.number, "damage": 4}]

    engine.draw_hit_damage = lambda category: 0  # type: ignore[method-assign]
    _apply_category_hit(engine, engine.convoy.units[1], 1, "G")
    assert engine.take_shaping_events() == []


def test_a_resolved_action_is_not_a_shaping_bonus():
    engine = _engine()
    stepped = False
    for _ in range(40):
        pending = engine.pending_choice()
        if pending is None or engine.terminal:
            break
        legal = engine.legal_actions()
        assert legal
        engine.step(list(legal[0]))
        stepped = True
        assert "action_ok" not in _kinds(engine)
    assert stepped
