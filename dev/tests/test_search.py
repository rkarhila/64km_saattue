"""Search action (Etsi ryöstettävää): always legal; fills pillage queue."""

from sixtyfivekmconvoy.core import actions as action_mod
from sixtyfivekmconvoy.core.cards import ACTION_CATALOG
from sixtyfivekmconvoy.core.constants import ActionName
from sixtyfivekmconvoy.core.engine import GameEngine
from sixtyfivekmconvoy.core.models import UnitType


def _seat(engine: GameEngine):
    if engine._unit_pool:
        engine.convoy.units = list(engine._unit_pool)
        engine._unit_pool = []
    engine.setup_complete = True
    for u in engine.convoy.units:
        u.convoy = engine.convoy
        u.engine = engine


def _search_face_card_9():
    faces = ACTION_CATALOG[9].describe()
    face = next(
        f
        for f in faces
        if ActionName.normalize(f["action_name"]) == ActionName.SEARCH
    )
    assert face["troop_type"] == "P"
    assert face["zone"] == "ABCE"
    return face


def test_search_not_unimplemented():
    assert ActionName.SEARCH not in ActionName.UNIMPLEMENTED


def test_card_9_search_always_legal_for_panzer():
    engine = GameEngine()
    engine.reset(num_players=2, seed=2)
    _seat(engine)
    panzer = next(u for u in engine.convoy.units if u.unittype == UnitType.PANZER)
    face = _search_face_card_9()
    # Even with empty pillage queue / no hidden cards, search is legal.
    assert len(engine.pillage_queue) == 0
    assert action_mod.scoutable_queues(engine)  # resistance/mauling still hidden
    assert action_mod.why_action_impossible(engine, panzer.index(), face) == []
    assert action_mod.is_action_possible(engine, panzer.index(), face)


def test_resolve_search_draws_and_scouts_interactive():
    from sixtyfivekmconvoy.core.constants import ChoiceType

    engine = GameEngine()
    engine.reset(num_players=2, seed=4)
    _seat(engine)
    panzer = next(u for u in engine.convoy.units if u.unittype == UnitType.PANZER)
    face = _search_face_card_9()
    count = int(face["action_modifier"])
    assert count == 2
    before_deck = len(engine.pillage_deck.deck)
    before_queue = len(engine.pillage_queue)

    gen = action_mod.resolve_search(engine, panzer, count)
    req = next(gen)
    
    assert req.choicetype == ChoiceType.CHOOSE_CARDS_TO_SCOUT
    assert req.num_choices == 2
    # The options should be the indices [0, 1] of the newly added face-down pillage cards
    assert 0 in req.options
    assert 1 in req.options

    # Choose to reveal them
    req2 = gen.send([0, 1])
    
    # Since we chose 2 cards, it should prompt to reorder them
    assert req2.choicetype == ChoiceType.REORDER_SCOUTED_CARDS
    assert req2.num_choices == 2
    
    # Send swap order
    try:
        gen.send([1, 0])
        raise AssertionError("expected StopIteration")
    except StopIteration as stop:
        summary_parts = stop.value

    assert len(summary_parts) == 1
    assert "searched and revealed" in summary_parts[0]
    
    # Verify that the two cards in the queue are now face up
    assert len(engine.pillage_queue) == before_queue + count
    assert engine.pillage_queue.cards_and_visibilities[0][1] is True
    assert engine.pillage_queue.cards_and_visibilities[1][1] is True
    assert any("search → pillage queue" in m for m in engine.messages)
