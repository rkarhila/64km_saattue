"""Sell replaces the round-end cash-in: the printed cost, conf income, conf fate."""

from sixtyfivekmconvoy.agents.random_agent import RandomAgent
from sixtyfivekmconvoy.core import actions as action_mod
from sixtyfivekmconvoy.core.cards import ACTION_CATALOG
from sixtyfivekmconvoy.core.configs import get_config, load_config
from sixtyfivekmconvoy.core.constants import ActionName, ChoiceType
from sixtyfivekmconvoy.core.engine import GameEngine
from sixtyfivekmconvoy.core.models import Unit, UnitType
from sixtyfivekmconvoy.env.table_features import (
    ACTION_NAMES,
    F_ACT,
    F_COST_FLAT,
    encode_action_face,
)


def _sell_face() -> dict:
    for card in ACTION_CATALOG.values():
        for face in card.describe():
            if face.get("action_name") == ActionName.SELL:
                return face
    raise AssertionError("no sell face")


def _ready(seed: int, hand_n: int):
    engine = GameEngine()
    engine.reset(num_players=2, seed=seed)
    engine.balance_trace = True
    engine.pause_after_actions = False
    engine._open_table()
    engine.setup_complete = True
    player = engine.players[0]
    deck = player.action_deck
    assert deck is not None
    cards = [deck.get_card() for _ in range(hand_n)]
    player.action_cards = list(cards)
    unit = Unit(player, UnitType.INFANTRY)
    unit.convoy = engine.convoy
    unit.engine = engine
    engine.convoy.units = [unit]
    return engine, player, deck, cards


def _resolve_sell(engine, cards):
    face = _sell_face()
    gen = action_mod.resolve_action(engine, 0, face, 1)
    try:
        request = next(gen)
    except StopIteration:
        return None
    assert request.choicetype == ChoiceType.CHOOSE_CARDS_TO_DISCARD
    assert request.num_choices == int(face["cost"])
    assert request.payload.get("sell") is True
    chosen = list(cards[: request.num_choices])
    try:
        gen.send(chosen)
    except StopIteration:
        pass
    return chosen


def test_sell_face_is_any_troop_with_a_flat_cost():
    face = _sell_face()
    assert face["cost"] == "4"
    assert set(face["limits"]) == {"P", "I", "L"}
    encoded = encode_action_face(face)
    assert encoded[F_ACT + ACTION_NAMES.index(ActionName.SELL)] == 1.0
    assert encoded[F_COST_FLAT] == 1.0


def test_default_sell_discards_and_pays_one():
    previous = get_config().CONFIG_NAME
    try:
        load_config("default")
        engine, player, deck, cards = _ready(1, 5)
        chosen = _resolve_sell(engine, cards)
        assert chosen is not None
        assert player.total_cash == 1
        assert all(card not in player.action_cards for card in chosen)
        assert cards[4] in player.action_cards
        assert not action_mod.is_action_possible(engine, 0, _sell_face())
        assert list(deck.discard[-4:]) == chosen
        assert deck.removed == []
        assert engine.cash_sources[0]["cash in cards"] == 1
        deck.deck = []
        deck.reshuffle()
        assert chosen[0] in deck.deck
    finally:
        load_config(previous)


def test_retire_sell_removes_cards_and_pays_one():
    previous = get_config().CONFIG_NAME
    try:
        load_config("retire")
        engine, player, deck, cards = _ready(2, 4)
        assert _resolve_sell(engine, cards) is None
        assert player.total_cash == 1
        assert player.action_cards == []
        assert cards[0] not in deck.discard
        assert cards[0] in deck.removed
        assert engine.cash_sources[0]["retire cards"] == 1
        assert engine.trace_cash_ins[0]["removed"] is True
        deck.deck = []
        deck.discard = [99]
        deck.reshuffle()
        assert cards[0] not in deck.deck
    finally:
        load_config(previous)


def test_bookkeeping_does_not_offer_a_cash_in():
    engine = GameEngine()
    engine.reset(num_players=2, seed=3, max_rounds=1)
    agents = {
        pid: RandomAgent(seed=10 + i) for i, pid in enumerate(engine.agent_ids())
    }
    seen = set()
    steps = 0
    while not engine.terminal:
        pending = engine.pending_choice()
        assert pending is not None
        seen.add(pending.choicetype)
        engine.step(agents[pending.player_id].choose(engine.legal_actions()))
        steps += 1
        assert steps < 20_000
    assert ChoiceType.CASH_IN_CARDS not in seen
    assert engine.end_reason == "max_rounds"
