"""Scout action: reveal hidden queue cards, or draw from a deck when all known."""

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


def _reveal_all_queues(engine: GameEngine) -> None:
    for queue in (
        engine.resistance_queue,
        engine.mauling_queue,
        engine.pillage_queue,
    ):
        for i, (_, vis) in enumerate(list(queue.cards_and_visibilities)):
            if not vis:
                queue.reveal_card(i)


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


def test_scout_still_legal_when_no_hidden_cards():
    engine = GameEngine()
    engine.reset(num_players=2, seed=5)
    inf = _seat_front_infantry(engine)
    _reveal_all_queues(engine)
    assert action_mod.scoutable_queues(engine) == []
    face = _scout_face()
    assert action_mod.why_action_impossible(engine, inf.index(), face) == []


def test_scout_blocked_outside_zone_a():
    engine = GameEngine()
    engine.reset(num_players=2, seed=7)
    inf = _seat_front_infantry(engine)
    others = [u for u in engine.convoy.units if u is not inf]
    engine.convoy.units = others + [inf]
    assert inf.zone() == "E"
    face = _scout_face()
    why = action_mod.why_action_impossible(engine, inf.index(), face)
    assert any("zone" in r for r in why)


def test_resolve_scout_reveals_resistance_hidden_card():
    engine = GameEngine()
    engine.reset(num_players=2, seed=9)
    engine.pause_after_actions = False
    inf = _seat_front_infantry(engine)

    resistance_hidden_indices = [
        idx
        for idx, (_, vis) in enumerate(engine.resistance_queue.cards_and_visibilities)
        if not vis
    ]
    assert resistance_hidden_indices

    gen = action_mod.resolve_scout(engine, inf, count=1)
    req = next(gen)

    assert req.choicetype == ChoiceType.CHOOSE_CARDS_TO_SCOUT
    assert req.num_choices == 1

    resistance_opt = 200 + resistance_hidden_indices[0]
    assert resistance_opt in req.options

    try:
        gen.send([resistance_opt])
        raise AssertionError("expected StopIteration")
    except StopIteration as stop:
        revealed = stop.value

    assert len(revealed) == 1
    assert revealed[0].startswith("resistance:")
    assert engine.resistance_queue.cards_and_visibilities[resistance_hidden_indices[0]][1] is True


def test_resolve_scout_reorders_when_multiple_from_same_queue():
    engine = GameEngine()
    engine.reset(num_players=2, seed=12)
    engine.pause_after_actions = False
    inf = _seat_front_infantry(engine)

    resistance_queue = engine.resistance_queue
    hidden_indices = [
        idx for idx, (_, vis) in enumerate(resistance_queue.cards_and_visibilities) if not vis
    ]
    assert len(hidden_indices) >= 2

    idx1, idx2 = hidden_indices[0], hidden_indices[1]
    card_id1 = resistance_queue.cards_and_visibilities[idx1][0]
    card_id2 = resistance_queue.cards_and_visibilities[idx2][0]

    gen = action_mod.resolve_scout(engine, inf, count=2)
    req = next(gen)

    assert req.choicetype == ChoiceType.CHOOSE_CARDS_TO_SCOUT
    assert req.num_choices == 2

    opt1 = 200 + idx1
    opt2 = 200 + idx2
    req2 = gen.send([opt1, opt2])

    assert req2.choicetype == ChoiceType.REORDER_SCOUTED_CARDS
    assert req2.num_choices == 2
    assert set(req2.options) == {idx1, idx2}

    try:
        gen.send([idx2, idx1])
        raise AssertionError("expected StopIteration")
    except StopIteration as stop:
        revealed = stop.value

    assert len(revealed) == 2
    assert resistance_queue.cards_and_visibilities[idx1][0] == card_id2
    assert resistance_queue.cards_and_visibilities[idx1][1] is True
    assert resistance_queue.cards_and_visibilities[idx2][0] == card_id1
    assert resistance_queue.cards_and_visibilities[idx2][1] is True


def test_resolve_scout_draws_from_deck_when_queues_known():
    engine = GameEngine()
    engine.reset(num_players=2, seed=15)
    engine.pause_after_actions = False
    inf = _seat_front_infantry(engine)
    _reveal_all_queues(engine)

    before_res_queue = len(engine.resistance_queue)
    before_deck = len(engine.resistance_deck.deck) + len(engine.resistance_deck.discard)

    gen = action_mod.resolve_scout(engine, inf, count=2)
    req = next(gen)
    assert req.choicetype == ChoiceType.CHOOSE_QUEUE_TO_SCOUT
    assert action_mod.SCOUT_QUEUE_RESISTANCE in req.options

    req2 = gen.send([action_mod.SCOUT_QUEUE_RESISTANCE])
    assert req2.choicetype == ChoiceType.CHOOSE_PILLAGE_CARD
    assert req2.payload.get("reason") == "scout_deck_pick"
    assert req2.payload.get("queue") == "resistance"
    assert len(req2.options) == 2

    keep = req2.options[0]
    other = req2.options[1]
    try:
        gen.send([keep])
        raise AssertionError("expected StopIteration")
    except StopIteration as stop:
        revealed = stop.value

    assert len(revealed) == 1
    assert revealed[0].startswith("resistance:")
    assert len(engine.resistance_queue) == before_res_queue + 1
    assert engine.resistance_queue.cards_and_visibilities[-1][0] == keep
    assert engine.resistance_queue.cards_and_visibilities[-1][1] is True
    assert other in engine.resistance_deck.discard
    assert (
        len(engine.resistance_deck.deck) + len(engine.resistance_deck.discard)
        == before_deck - 1
    )
