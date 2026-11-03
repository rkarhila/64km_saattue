"""Search action: scout limited to the pillage queue/deck."""

from sixtyfivekmconvoy.core import actions as action_mod
from sixtyfivekmconvoy.core.cards import ACTION_CATALOG
from sixtyfivekmconvoy.core.constants import ActionName, ChoiceType
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


def test_card_9_search_legal_when_pillage_queue_empty():
    engine = GameEngine()
    engine.reset(num_players=2, seed=2)
    _seat(engine)
    panzer = next(u for u in engine.convoy.units if u.unittype == UnitType.PANZER)
    face = _search_face_card_9()
    assert len(engine.pillage_queue) == 0
    assert action_mod.why_action_impossible(engine, panzer.index(), face) == []
    assert action_mod.is_action_possible(engine, panzer.index(), face)


def test_search_illegal_when_pillage_queue_fully_revealed():
    engine = GameEngine()
    engine.reset(num_players=2, seed=3)
    _seat(engine)
    panzer = next(u for u in engine.convoy.units if u.unittype == UnitType.PANZER)
    face = _search_face_card_9()
    cid = engine.pillage_deck.get_card()
    engine.pillage_queue.put_card(cid, visible=True)
    reasons = action_mod.why_action_impossible(engine, panzer.index(), face)
    assert reasons
    assert "fully revealed" in reasons[0]
    assert not action_mod.is_action_possible(engine, panzer.index(), face)


def test_search_legal_when_pillage_has_face_down():
    engine = GameEngine()
    engine.reset(num_players=2, seed=5)
    _seat(engine)
    panzer = next(u for u in engine.convoy.units if u.unittype == UnitType.PANZER)
    face = _search_face_card_9()
    cid = engine.pillage_deck.get_card()
    engine.pillage_queue.put_card(cid, visible=False)
    assert action_mod.why_action_impossible(engine, panzer.index(), face) == []


def test_resolve_search_draws_from_pillage_deck_when_queue_empty():
    engine = GameEngine()
    engine.reset(num_players=2, seed=4)
    engine.pause_after_actions = False
    _seat(engine)
    panzer = next(u for u in engine.convoy.units if u.unittype == UnitType.PANZER)
    face = _search_face_card_9()
    count = int(face["action_modifier"])
    assert count == 2
    assert len(engine.pillage_queue) == 0
    before_deck = len(engine.pillage_deck.deck) + len(engine.pillage_deck.discard)

    gen = action_mod.resolve_search(engine, panzer, count)
    # Only pillage is allowed → skip deck choice, go straight to pick-one-of-N.
    req = next(gen)
    assert req.choicetype == ChoiceType.CHOOSE_PILLAGE_CARD
    assert req.payload.get("reason") == "scout_deck_pick"
    assert req.payload.get("queue") == "pillage"
    assert req.num_choices == 1
    assert len(req.options) == count

    keep = req.options[0]
    other = req.options[1]
    try:
        gen.send([keep])
        raise AssertionError("expected StopIteration")
    except StopIteration as stop:
        revealed = stop.value

    assert len(revealed) == 1
    assert revealed[0].startswith("pillage:")
    assert len(engine.pillage_queue) == 1
    assert engine.pillage_queue.cards_and_visibilities[0][0] == keep
    assert engine.pillage_queue.cards_and_visibilities[0][1] is True
    assert other in engine.pillage_deck.discard
    assert (
        len(engine.pillage_deck.deck) + len(engine.pillage_deck.discard)
        == before_deck - 1
    )


def test_resolve_search_reveals_existing_face_down_pillage():
    engine = GameEngine()
    engine.reset(num_players=2, seed=6)
    engine.pause_after_actions = False
    _seat(engine)
    panzer = next(u for u in engine.convoy.units if u.unittype == UnitType.PANZER)

    # Seed two face-down pillage cards — search must reveal, not pad from deck.
    c1 = engine.pillage_deck.get_card()
    c2 = engine.pillage_deck.get_card()
    engine.pillage_queue.put_card(c1, visible=False)
    engine.pillage_queue.put_card(c2, visible=False)
    before_deck = len(engine.pillage_deck.deck)

    gen = action_mod.resolve_search(engine, panzer, count=2)
    req = next(gen)
    assert req.choicetype == ChoiceType.CHOOSE_CARDS_TO_SCOUT
    assert req.num_choices == 2
    # Scout encoding: pillage code 0 → options are queue indices 0 and 1.
    assert set(req.options) == {0, 1}

    req2 = gen.send([0, 1])
    assert req2.choicetype == ChoiceType.REORDER_SCOUTED_CARDS

    try:
        gen.send([1, 0])
        raise AssertionError("expected StopIteration")
    except StopIteration as stop:
        revealed = stop.value

    assert len(revealed) == 2
    assert all(r.startswith("pillage:") for r in revealed)
    assert len(engine.pillage_deck.deck) == before_deck  # no extra draws
    assert engine.pillage_queue.cards_and_visibilities[0][1] is True
    assert engine.pillage_queue.cards_and_visibilities[1][1] is True


def test_resolve_search_does_not_pad_from_deck_when_queue_known():
    """Fully face-up pillage queue must not trigger deck draws."""
    engine = GameEngine()
    engine.reset(num_players=2, seed=7)
    engine.pause_after_actions = False
    _seat(engine)
    panzer = next(u for u in engine.convoy.units if u.unittype == UnitType.PANZER)

    c1 = engine.pillage_deck.get_card()
    engine.pillage_queue.put_card(c1, visible=True)
    before_deck = len(engine.pillage_deck.deck)
    before_q = len(engine.pillage_queue)

    gen = action_mod.resolve_search(engine, panzer, count=2)
    try:
        next(gen)
        raise AssertionError("expected no choices when queue is fully revealed")
    except StopIteration as stop:
        assert stop.value == []

    assert len(engine.pillage_deck.deck) == before_deck
    assert len(engine.pillage_queue) == before_q
