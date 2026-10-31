"""Sigint action: scout-like reveal, but only mauling queue cards."""

from sixtyfivekmconvoy.core import actions as action_mod
from sixtyfivekmconvoy.core.cards import ACTION_CATALOG
from sixtyfivekmconvoy.core.constants import ActionName, ChoiceType
from sixtyfivekmconvoy.core.engine import GameEngine
from sixtyfivekmconvoy.core.models import UnitType


def _seat_logistics_in_zone_ab(engine: GameEngine):
    if engine._unit_pool:
        engine.convoy.units = list(engine._unit_pool)
        engine._unit_pool = []
    engine.setup_complete = True
    for u in engine.convoy.units:
        u.convoy = engine.convoy
        u.engine = engine
    logi = next(u for u in engine.convoy.units if u.unittype == UnitType.LOGISTICS)
    # Put logistics near the front so zone is A or B (card allows AB).
    others = [u for u in engine.convoy.units if u is not logi]
    engine.convoy.units = [logi] + others
    assert logi.zone() in ("A", "B")
    return logi


def _sigint_face():
    """Logistics sigint face on action card #6 (Signaalitiedustelu, zone AB, mod 3)."""
    faces = ACTION_CATALOG[6].describe()
    face = next(
        f for f in faces if ActionName.normalize(f["action_name"]) == ActionName.SIGINT
    )
    assert face["zone"] == "AB"
    assert face["troop_type"] == "L"
    return face


def test_sigint_not_unimplemented():
    assert ActionName.SIGINT not in ActionName.UNIMPLEMENTED


def test_sigint_legal_when_mauling_has_hidden():
    engine = GameEngine()
    engine.reset(num_players=2, seed=3)
    logi = _seat_logistics_in_zone_ab(engine)
    assert engine.mauling_queue.contains_hidden_cards()
    face = _sigint_face()
    assert action_mod.why_action_impossible(engine, logi.index(), face) == []
    codes = [
        c
        for c, _ in action_mod.scoutable_queues(
            engine, allowed_codes={action_mod.SCOUT_QUEUE_MAULING}
        )
    ]
    assert codes == [action_mod.SCOUT_QUEUE_MAULING]


def test_sigint_blocked_when_mauling_fully_revealed():
    engine = GameEngine()
    engine.reset(num_players=2, seed=5)
    logi = _seat_logistics_in_zone_ab(engine)
    for i, (_, vis) in enumerate(list(engine.mauling_queue.cards_and_visibilities)):
        if not vis:
            engine.mauling_queue.reveal_card(i)
    # Resistance/pillage may still be hidden — sigint must still be blocked.
    assert engine.resistance_queue.contains_hidden_cards() or True
    face = _sigint_face()
    why = action_mod.why_action_impossible(engine, logi.index(), face)
    assert why
    assert "sigint" in why[0]


def test_resolve_sigint_only_offers_mauling_options():
    engine = GameEngine()
    engine.reset(num_players=2, seed=9)
    engine.pause_after_actions = False
    logi = _seat_logistics_in_zone_ab(engine)

    mauling_hidden = [
        idx
        for idx, (_, vis) in enumerate(engine.mauling_queue.cards_and_visibilities)
        if not vis
    ]
    assert mauling_hidden

    gen = action_mod.resolve_scout(
        engine,
        logi,
        count=1,
        allowed_queue_codes={action_mod.SCOUT_QUEUE_MAULING},
        verb="sigint",
    )
    req = next(gen)
    assert req.choicetype == ChoiceType.CHOOSE_CARDS_TO_SCOUT
    assert req.payload.get("verb") == "sigint"
    assert req.payload.get("allowed_queues") == ["mauling"]
    # Options encode queue code * 100 + index; mauling code is 1.
    assert req.options
    assert all(opt // 100 == action_mod.SCOUT_QUEUE_MAULING for opt in req.options)

    opt = 100 + mauling_hidden[0]
    assert opt in req.options
    try:
        gen.send([opt])
        raise AssertionError("expected StopIteration")
    except StopIteration as stop:
        revealed = stop.value

    assert revealed == [
        f"mauling:{engine.mauling_queue.deck.get_name(engine.mauling_queue.cards_and_visibilities[mauling_hidden[0]][0])}"
    ]
    assert engine.mauling_queue.cards_and_visibilities[mauling_hidden[0]][1] is True
