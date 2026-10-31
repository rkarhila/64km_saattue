"""Order action: assign a hand card to a neighbouring Wait unit."""

from sixtyfivekmconvoy.core import actions as action_mod
from sixtyfivekmconvoy.core.cards import ACTION_CATALOG
from sixtyfivekmconvoy.core.constants import ActionName, ChoiceType
from sixtyfivekmconvoy.core.engine import GameEngine
from sixtyfivekmconvoy.core.models import Unit, UnitType


def _setup_three_units():
    engine = GameEngine()
    engine.reset(num_players=2, seed=11)
    engine.setup_complete = True
    engine.pause_after_actions = False
    engine.current_action_index = 0
    engine.convoy.units = []

    p0 = engine.players[0]
    u_prev = Unit(p0, UnitType.INFANTRY)
    u_order = Unit(p0, UnitType.INFANTRY)
    u_follow = Unit(p0, UnitType.INFANTRY)
    for u in (u_prev, u_order, u_follow):
        u.convoy = engine.convoy
        u.engine = engine
    engine.convoy.units = [u_prev, u_order, u_follow]
    return engine, p0, u_prev, u_order, u_follow


def _order_face_infantry():
    faces = ACTION_CATALOG[5].describe()
    face = next(
        f for f in faces if ActionName.normalize(f["action_name"]) == ActionName.ORDER
    )
    assert face["troop_type"] == "I"
    return face


def _mark_waited(unit: Unit, card_id: int = 15) -> None:
    unit.actioncard = [card_id]
    unit.actiontaken = [0]
    unit.action_resolution = [
        {
            "kind": "card",
            "face_index": 0,
            "option": 0,
            "name": "Röökitauko",
            "action_name": "Wait",
        }
    ]


def test_order_not_unimplemented():
    assert ActionName.ORDER not in ActionName.UNIMPLEMENTED


def test_order_blocked_without_neighbour_wait():
    engine, p0, u_prev, u_order, u_follow = _setup_three_units()
    p0.action_cards = [17, 18]
    face = _order_face_infantry()
    # Neighbours have cards but neither waited / has Wait face.
    u_prev.actioncard = [0]
    u_prev.actiontaken = [0]
    u_prev.action_resolution = [
        {"kind": "card", "face_index": 0, "name": "Hyökkää", "action_name": "Attack"}
    ]
    u_follow.actioncard = [0]
    why = action_mod.why_action_impossible(engine, u_order.index(), face)
    assert why
    assert any("neighbouring wait" in r for r in why)


def test_order_legal_when_previous_waited():
    engine, p0, u_prev, u_order, u_follow = _setup_three_units()
    p0.action_cards = [17]
    _mark_waited(u_prev)
    face = _order_face_infantry()
    assert action_mod.order_wait_targets(engine, u_order) == [u_prev]
    assert action_mod.why_action_impossible(engine, u_order.index(), face) == []


def test_order_legal_when_following_has_wait_card():
    engine, p0, u_prev, u_order, u_follow = _setup_three_units()
    p0.action_cards = [17]
    u_follow.actioncard = [15]  # Wait face, not yet resolved
    u_follow.actiontaken = [None]
    face = _order_face_infantry()
    assert action_mod.order_wait_targets(engine, u_order) == [u_follow]
    assert action_mod.why_action_impossible(engine, u_order.index(), face) == []


def test_resolve_order_previous_wait_returns_card():
    engine, p0, u_prev, u_order, u_follow = _setup_three_units()
    p0.action_cards = [17]  # Rest (cost 0)
    _mark_waited(u_prev)
    u_prev.tired = 2

    gen = action_mod.resolve_order(engine, u_order)
    req = next(gen)
    assert req.choicetype == ChoiceType.CHOOSE_CARD
    assert 17 in req.options
    try:
        gen.send([17])
        raise AssertionError("expected StopIteration")
    except StopIteration as stop:
        summary = stop.value

    assert "ordered" in summary
    assert "returned" in summary
    assert 17 in p0.action_cards  # assigned card returned to orderer
    assert u_prev.tired == 0  # Rest applied on waiter
    assert u_prev.current_action_type == "resting"


def test_resolve_order_reveals_following_wait_card():
    engine, p0, u_prev, u_order, u_follow = _setup_three_units()
    p0.action_cards = [17]
    u_follow.actioncard = [15]
    u_follow.actiontaken = [None]
    u_follow.tired = 2

    gen = action_mod.resolve_order(engine, u_order)
    req = next(gen)
    assert req.choicetype == ChoiceType.CHOOSE_CARD
    # Reveal happens before the hand-card choice.
    assert 0 in u_follow.revealed_card_indices
    try:
        gen.send([17])
    except StopIteration:
        pass

    assert 17 in p0.action_cards
    assert u_follow.tired == 0


def test_order_blocked_when_no_card_left_after_cost():
    engine, p0, u_prev, u_order, u_follow = _setup_three_units()
    _mark_waited(u_prev)
    u_order.tired = 1  # Order cost = 1
    p0.action_cards = [17]  # exactly enough to pay, nothing left to assign
    face = _order_face_infantry()
    why = action_mod.why_action_impossible(engine, u_order.index(), face)
    assert any("hand card left" in r for r in why)
