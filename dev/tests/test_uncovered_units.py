"""A unit with no action card leaves the convoy at the order phase."""

from sixtyfivekmconvoy.core.cards import OFFICER_CATALOG
from sixtyfivekmconvoy.core.constants import ChoiceType
from sixtyfivekmconvoy.core.engine import GameEngine


def _place_then(hands: list[list[int]] | None) -> tuple[GameEngine, object]:
    """Play through setup. If hands is set, those replace the dealt hands."""
    engine = GameEngine()
    engine.reset(num_players=2, seed=1)
    engine.pause_after_actions = False
    placed = 0
    while True:
        pending = engine.pending_choice()
        assert pending is not None
        if pending.choicetype != ChoiceType.PLACE_UNITS:
            return engine, pending
        placed += 1
        if hands is not None and placed == len(engine.players):
            for player, cards in zip(engine.players, hands):
                assert player.action_deck is not None
                player.action_deck.deck.clear()
                player.action_deck.discard.clear()
                player.action_cards = list(cards)
        engine.step([0, 1, 2])


def test_full_hand_assigns_a_card_to_every_unit():
    engine, pending = _place_then(None)
    assert pending.choicetype == ChoiceType.CHOOSE_CARD
    assert pending.num_choices == 1
    unit = pending.payload["assign_unit"]
    assert unit["index"] == unit["place"]
    assert unit["zone"] in "ABCE"
    assert pending.payload["assign_faces"]
    assert len(engine.convoy.units) == 6


def test_short_hand_discards_the_units_left_without_a_card():
    engine, pending = _place_then([[11], [1, 2, 3, 4, 5]])
    assert pending.choicetype == ChoiceType.DISCARD_UNITS
    assert pending.player_id == "player_0"
    assert pending.num_choices == 2
    assert len(pending.options) == 3

    keep_index = pending.options[2]
    keep = next(u for u in engine.convoy.units if u.index() == keep_index)
    victim = next(u for u in engine.convoy.units if u.index() == pending.options[0])
    victim.damage_markers.append(
        {"damage": 3, "category": 1, "id": 7, "fresh": True}
    )
    officer = next(iter(OFFICER_CATALOG.values()))
    victim.officers.append(officer)
    officer_seq = next(
        seq
        for seq, real in engine.officer_id_mapping.items()
        if real == officer.officer_id
    )
    engine.step(list(pending.options[:2]))

    assert victim not in engine.convoy.units
    assert keep in engine.convoy.units
    assert victim.convoy is None
    assert victim.officers == []
    assert 7 in engine.hit_decks[1].discard
    assert officer_seq in engine.officer_deck.discard
    assert any("ei riitä toimintokorttia" in line for line in engine.messages)
    assert sum(1 for u in engine.convoy.units if u.player.number == 0) == 1

    nxt = engine.pending_choice()
    assert nxt is not None
    assert nxt.choicetype == ChoiceType.CHOOSE_CARD
    assert nxt.player_id == "player_0"
    assert nxt.num_choices == 1
    engine.step([11])
    assert keep.actioncard == [11]
    assert engine.players[0].action_cards == []


def test_empty_hand_removes_every_unit_without_asking():
    engine, pending = _place_then([[], [1, 2, 3, 4, 5]])
    assert all(u.player.number != 0 for u in engine.convoy.units)
    assert pending.choicetype == ChoiceType.CHOOSE_CARD
    assert pending.player_id == "player_1"
    assert pending.num_choices == 1
    assert pending.payload["assign_unit"]["place"] == pending.payload["assign_unit"]["index"]
    assert any("ei riitä toimintokorttia" in line for line in engine.messages)


def test_draw_stops_when_the_deck_is_empty():
    engine = GameEngine()
    engine.reset(num_players=2, seed=1)
    player = engine.players[0]
    assert player.action_deck is not None
    player.action_deck.deck.clear()
    player.action_deck.discard.clear()
    player.action_cards = []
    player.draw_card(5)
    assert player.action_cards == []
