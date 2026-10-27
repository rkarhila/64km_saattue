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
    
    # Check that we have hidden cards in resistance queue
    resistance_hidden_indices = [
        idx for idx, (_, vis) in enumerate(engine.resistance_queue.cards_and_visibilities) if not vis
    ]
    assert resistance_hidden_indices

    # Run scout action for 1 card
    gen = action_mod.resolve_scout(engine, inf, count=1)
    req = next(gen)
    
    assert req.choicetype == ChoiceType.CHOOSE_CARDS_TO_SCOUT
    assert req.num_choices == 1
    
    # Option for resistance queue index 0 should be 200 (since 2 = resistance queue code)
    resistance_opt = 200 + resistance_hidden_indices[0]
    assert resistance_opt in req.options
    
    # Send choice to scout that card
    try:
        gen.send([resistance_opt])
        raise AssertionError("expected StopIteration")
    except StopIteration as stop:
        revealed = stop.value

    assert len(revealed) == 1
    assert revealed[0].startswith("resistance:")
    # Verify the selected card is now face-up (visible = True)
    assert engine.resistance_queue.cards_and_visibilities[resistance_hidden_indices[0]][1] is True


def test_resolve_scout_reorders_when_multiple_from_same_queue():
    engine = GameEngine()
    engine.reset(num_players=2, seed=12)
    inf = _seat_front_infantry(engine)
    
    # Ensure there are at least two hidden cards in resistance queue
    resistance_queue = engine.resistance_queue
    hidden_indices = [
        idx for idx, (_, vis) in enumerate(resistance_queue.cards_and_visibilities) if not vis
    ]
    assert len(hidden_indices) >= 2
    
    idx1, idx2 = hidden_indices[0], hidden_indices[1]
    card_id1 = resistance_queue.cards_and_visibilities[idx1][0]
    card_id2 = resistance_queue.cards_and_visibilities[idx2][0]
    
    # Start scouting 2 cards
    gen = action_mod.resolve_scout(engine, inf, count=2)
    req = next(gen)
    
    assert req.choicetype == ChoiceType.CHOOSE_CARDS_TO_SCOUT
    assert req.num_choices == 2
    
    opt1 = 200 + idx1
    opt2 = 200 + idx2
    assert opt1 in req.options
    assert opt2 in req.options
    
    # Select both options
    req2 = gen.send([opt1, opt2])
    
    # Because we selected multiple cards from the same queue, it should ask us to reorder them
    assert req2.choicetype == ChoiceType.REORDER_SCOUTED_CARDS
    assert req2.num_choices == 2
    assert set(req2.options) == {idx1, idx2}
    
    # Send reordered option: swap their order
    try:
        gen.send([idx2, idx1])
        raise AssertionError("expected StopIteration")
    except StopIteration as stop:
        revealed = stop.value
        
    assert len(revealed) == 2
    # Verify that cards are indeed swapped and both are now face-up
    assert resistance_queue.cards_and_visibilities[idx1][0] == card_id2
    assert resistance_queue.cards_and_visibilities[idx1][1] is True
    assert resistance_queue.cards_and_visibilities[idx2][0] == card_id1
    assert resistance_queue.cards_and_visibilities[idx2][1] is True


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
