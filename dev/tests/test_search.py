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


def test_resolve_search_draws_modifier_into_pillage_queue():
    engine = GameEngine()
    engine.reset(num_players=2, seed=4)
    _seat(engine)
    panzer = next(u for u in engine.convoy.units if u.unittype == UnitType.PANZER)
    face = _search_face_card_9()
    count = int(face["action_modifier"])
    assert count == 2
    before_deck = len(engine.pillage_deck.deck)
    before_queue = len(engine.pillage_queue)

    drawn = action_mod.resolve_search(engine, panzer, count)
    assert len(drawn) == count
    assert len(engine.pillage_queue) == before_queue + count
    assert len(engine.pillage_deck.deck) == before_deck - count
    # Face-down in queue
    assert all(
        not vis
        for cid, vis in engine.pillage_queue.cards_and_visibilities
        if cid in drawn
    )
    assert any("search → pillage queue" in m for m in engine.messages)
