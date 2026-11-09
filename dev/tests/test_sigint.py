"""Sigint action: scout-like, limited to the mauling queue/deck."""

from sixtyfivekmconvoy.core import actions as action_mod
from sixtyfivekmconvoy.core.cards import ACTION_CATALOG
from sixtyfivekmconvoy.core.constants import ActionName, ChoiceType
from sixtyfivekmconvoy.core.engine import GameEngine
from sixtyfivekmconvoy.core.models import UnitType


def _seat_logistics_in_zone_ab(engine: GameEngine):
    engine._open_table()
    if engine._unit_pool:
        engine.convoy.units = list(engine._unit_pool)
        engine._unit_pool = []
    engine.setup_complete = True
    for u in engine.convoy.units:
        u.convoy = engine.convoy
        u.engine = engine
    logi = next(u for u in engine.convoy.units if u.unittype == UnitType.LOGISTICS)
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


def test_sigint_still_legal_when_mauling_fully_revealed():
    engine = GameEngine()
    engine.reset(num_players=2, seed=5)
    logi = _seat_logistics_in_zone_ab(engine)
    for i, (_, vis) in enumerate(list(engine.mauling_queue.cards_and_visibilities)):
        if not vis:
            engine.mauling_queue.reveal_card(i)
    face = _sigint_face()
    assert action_mod.why_action_impossible(engine, logi.index(), face) == []


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


def test_sigint_flips_the_last_hidden_card_then_peeks_two():
    engine = GameEngine()
    engine.reset(num_players=2, seed=12)
    engine.pause_after_actions = False
    logi = _seat_logistics_in_zone_ab(engine)
    hidden = [
        idx
        for idx, (_, vis) in enumerate(engine.mauling_queue.cards_and_visibilities)
        if not vis
    ]
    assert len(hidden) >= 2
    for idx in hidden[1:]:
        engine.mauling_queue.reveal_card(idx)
    kept_down = hidden[0]

    gen = action_mod.resolve_scout(
        engine,
        logi,
        count=3,
        allowed_queue_codes={action_mod.SCOUT_QUEUE_MAULING},
        verb="sigint",
    )
    req = next(gen)
    assert req.choicetype == ChoiceType.CHOOSE_PILLAGE_CARD
    assert req.payload.get("queue") == "mauling"
    assert len(req.options) == 2
    assert engine.mauling_queue.cards_and_visibilities[kept_down][1] is True
    keep = req.options[0]
    try:
        gen.send([keep])
        raise AssertionError("expected StopIteration")
    except StopIteration:
        pass
    assert engine.mauling_queue.cards_and_visibilities[-1] == [keep, True]


def test_resolve_sigint_draws_from_mauling_deck_when_known():
    engine = GameEngine()
    engine.reset(num_players=2, seed=11)
    engine.pause_after_actions = False
    logi = _seat_logistics_in_zone_ab(engine)
    for i, (_, vis) in enumerate(list(engine.mauling_queue.cards_and_visibilities)):
        if not vis:
            engine.mauling_queue.reveal_card(i)

    before = len(engine.mauling_queue)
    gen = action_mod.resolve_scout(
        engine,
        logi,
        count=3,
        allowed_queue_codes={action_mod.SCOUT_QUEUE_MAULING},
        verb="sigint",
    )
    # Single allowed deck → no queue choice.
    req = next(gen)
    assert req.choicetype == ChoiceType.CHOOSE_PILLAGE_CARD
    assert req.payload.get("queue") == "mauling"
    assert len(req.options) == 3

    keep = req.options[1]
    try:
        gen.send([keep])
        raise AssertionError("expected StopIteration")
    except StopIteration as stop:
        revealed = stop.value

    assert len(revealed) == 1
    assert revealed[0].startswith("mauling:")
    assert len(engine.mauling_queue) == before + 1
    assert engine.mauling_queue.cards_and_visibilities[-1][0] == keep
    assert engine.mauling_queue.cards_and_visibilities[-1][1] is True
