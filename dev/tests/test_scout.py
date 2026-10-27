"""Scout action: reveal hidden resistance/mauling/pillage queue cards."""

from sixtyfivekmconvoy.core import actions as action_mod
from sixtyfivekmconvoy.core.cards import ACTION_CATALOG
from sixtyfivekmconvoy.core.constants import ActionName, ChoiceType
from sixtyfivekmconvoy.core.engine import GameEngine
from sixtyfivekmconvoy.core.models import UnitType


def _seat_front_infantry(engine: GameEngine):
    if engine._unit_pool:
        engine.convoy.units = list(engine._unit_pool)
        engine._unit_pool = []
    engine.setup_complete = True
    for u in engine.convoy.units:
        u.convoy = engine.convoy
        u.engine = engine
    inf = next(u for u in engine.convoy.units if u.unittype == UnitType.INFANTRY)
    others = [u for u in engine.convoy.units if u is not inf]
    engine.convoy.units = [inf] + others
    return inf


def _scout_face():
    """Infantry scout face on action card #10 (Tiedustele, zone A, mod 3)."""
    faces = ACTION_CATALOG[10].describe()
    scout = next(f for f in faces if ActionName.normalize(f["action_name"]) == ActionName.SCOUT)
    assert scout["zone"] == "A"
    assert scout["troop_type"] == "I"
    return scout


def test_scout_not_unimplemented():
    assert ActionName.SCOUT not in ActionName.UNIMPLEMENTED


def test_front_infantry_can_scout_hidden_resistance_on_card_10():
    engine = GameEngine()
    engine.reset(num_players=2, seed=3)
    inf = _seat_front_infantry(engine)
    assert inf.zone() == "A"
    assert engine.resistance_queue.contains_hidden_cards()

    face = _scout_face()
    assert action_mod.why_action_impossible(engine, inf.index(), face) == []
    assert action_mod.is_action_possible(engine, inf.index(), face)
    codes = [c for c, _ in action_mod.scoutable_queues(engine)]
    assert action_mod.SCOUT_QUEUE_RESISTANCE in codes


def test_scout_blocked_when_no_hidden_cards():
    engine = GameEngine()
    engine.reset(num_players=2, seed=5)
    inf = _seat_front_infantry(engine)
    # Reveal everything
    for queue in (
        engine.resistance_queue,
        engine.mauling_queue,
        engine.pillage_queue,
    ):
        for i, (_, vis) in enumerate(list(queue.cards_and_visibilities)):
            if not vis:
                queue.reveal_card(i)
    assert action_mod.scoutable_queues(engine) == []
    face = _scout_face()
    why = action_mod.why_action_impossible(engine, inf.index(), face)
    assert why
    assert "nothing to scout" in why[0]


def test_scout_blocked_outside_zone_a():
    engine = GameEngine()
    engine.reset(num_players=2, seed=7)
    inf = _seat_front_infantry(engine)
    # Move infantry to the back (zone E for 2p)
    others = [u for u in engine.convoy.units if u is not inf]
    engine.convoy.units = others + [inf]
    assert inf.zone() == "E"
    face = _scout_face()
    why = action_mod.why_action_impossible(engine, inf.index(), face)
    assert any("zone" in r for r in why)


def test_resolve_scout_reveals_resistance_hidden_card():
    engine = GameEngine()
    engine.reset(num_players=2, seed=9)
    inf = _seat_front_infantry(engine)
    hidden_before = sum(
        1 for _, vis in engine.resistance_queue.cards_and_visibilities if not vis
    )
    assert hidden_before >= 1

    gen = action_mod.resolve_scout(engine, inf, count=1)
    req = next(gen)
    assert req.choicetype == ChoiceType.CHOOSE_QUEUE_TO_SCOUT
    assert action_mod.SCOUT_QUEUE_RESISTANCE in req.options
    try:
        gen.send([action_mod.SCOUT_QUEUE_RESISTANCE])
        raise AssertionError("expected StopIteration")
    except StopIteration as stop:
        revealed = stop.value

    assert len(revealed) == 1
    assert revealed[0].startswith("resistance:")
    hidden_after = sum(
        1 for _, vis in engine.resistance_queue.cards_and_visibilities if not vis
    )
    assert hidden_after == hidden_before - 1
    assert any("scouted resistance" in m for m in engine.messages)


def test_resolve_scout_auto_picks_only_scoutable_queue():
    engine = GameEngine()
    engine.reset(num_players=2, seed=11)
    inf = _seat_front_infantry(engine)
    # Leave only resistance hidden
    for i, (_, vis) in enumerate(list(engine.mauling_queue.cards_and_visibilities)):
        if not vis:
            engine.mauling_queue.reveal_card(i)
    assert action_mod.scoutable_queues(engine) == [
        (action_mod.SCOUT_QUEUE_RESISTANCE, "resistance")
    ]

    gen = action_mod.resolve_scout(engine, inf, count=1)
    try:
        next(gen)
        raise AssertionError("single-queue scout should not yield a choice")
    except StopIteration as stop:
        revealed = stop.value
    assert len(revealed) == 1
    assert revealed[0].startswith("resistance:")


def test_frustrated_log_includes_block_reasons_for_scout():
    engine = GameEngine()
    engine.reset(num_players=2, seed=13)
    inf = _seat_front_infantry(engine)
    # Exhaust scoutability
    for queue in (engine.resistance_queue, engine.mauling_queue, engine.pillage_queue):
        for i, (_, vis) in enumerate(list(queue.cards_and_visibilities)):
            if not vis:
                queue.reveal_card(i)

    face = _scout_face()
    why = action_mod.why_action_impossible(engine, inf.index(), face)
    assert why
    # Simulate the frustrated broadcast shape used by the engine
    engine._broadcast(
        f"{action_mod.unit_log_label(inf)} frustrated on card 10 "
        f"(unit#{inf.index()} zone={inf.zone()} type=jalkaväki; "
        f"{action_mod.hidden_queue_summary(engine)}): scout:{','.join(why)}",
        kind="frustrated",
        blocked=[{"action_name": "scout", "reasons": why}],
    )
    assert engine.event_log
    assert engine.event_log[-1]["detail"]["kind"] == "frustrated"
    assert "nothing to scout" in engine.messages[-1]
