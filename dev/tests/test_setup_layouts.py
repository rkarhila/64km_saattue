from sixtyfivekmconvoy.core.setup_layouts import (
    SETUP_POOLS,
    pattern_for_players,
    pick_setup_pattern,
    slots_for_player,
    validate_pools,
)
from sixtyfivekmconvoy.agents.random_agent import RandomAgent
from sixtyfivekmconvoy.core.engine import GameEngine
from sixtyfivekmconvoy.core.constants import ChoiceType
import random


def test_pools_valid():
    validate_pools()
    for n in (2, 3, 4, 5):
        assert 1 <= len(SETUP_POOLS[n]) <= 12


def test_slots_one_per_third():
    for n, pool in SETUP_POOLS.items():
        third = n
        for pat in pool:
            for p in range(n):
                slots = slots_for_player(pat, p)
                assert len(slots) == 3
                thirds = [s // third for s in slots]
                assert sorted(thirds) == [0, 1, 2]


def test_full_formation_filters_absent_players():
    full = "123452341534512"
    assert pattern_for_players(full, 5) == tuple(int(ch) - 1 for ch in full)
    # 12345 | 23415 | 34512 → drop 4 and 5 → 123 | 231 | 312
    assert pattern_for_players(full, 3) == (0, 1, 2, 1, 2, 0, 2, 0, 1)
    # drop 3, 4 and 5 → 12 | 21 | 12
    assert pattern_for_players(full, 2) == (0, 1, 1, 0, 0, 1)
    for n in (2, 3, 4, 5):
        pat = pattern_for_players(full, n)
        assert len(pat) == 3 * n
        for p in range(n):
            assert sorted(i // n for i, owner in enumerate(pat) if owner == p) == [0, 1, 2]


def test_every_mauling_card_orders_every_player_count():
    from sixtyfivekmconvoy.core.cards import load_mauling_deck

    deck = load_mauling_deck()
    for card in deck.values():
        for n in (2, 3, 4, 5):
            pat = pattern_for_players(card.formations["5"], n)
            assert len(pat) == 3 * n


def test_order_card_sets_pattern_then_opens_the_table():
    from sixtyfivekmconvoy.core.cards import MAULING_CATALOG

    engine = GameEngine()
    engine.reset(num_players=3, seed=11)
    card = MAULING_CATALOG[engine.setup_order_card_id]
    assert engine.setup_pattern == pattern_for_players(card.formations["5"], 3)
    assert engine.setup_order_card_id not in engine.mauling_deck.deck
    assert engine.setup_order_card_id not in engine.mauling_deck.discard
    assert engine.mauling_queue.cards_and_visibilities == []
    assert engine.resistance.active is False

    from sixtyfivekmconvoy.core.constants import ChoiceType

    while engine.pending_choice().choicetype == ChoiceType.PLACE_UNITS:
        engine.step([0, 1, 2])

    assert engine.setup_complete
    assert engine.setup_order_card_id in engine.mauling_deck.discard
    assert len(engine.mauling_queue) == 3
    queued = [card_id for card_id, _ in engine.mauling_queue.cards_and_visibilities]
    assert engine.setup_order_card_id not in queued
    assert engine.resistance.name == "Rajapuomi"
    assert engine.resistance.active


def test_placement_phase_then_play():
    engine = GameEngine()
    engine.reset(num_players=3, seed=11, max_rounds=30)
    assert engine.setup_complete is False
    agents = {pid: RandomAgent(seed=50 + i) for i, pid in enumerate(engine.agent_ids())}
    steps = 0
    while not engine.terminal:
        pending = engine.pending_choice()
        assert pending is not None
        if steps == 0:
            assert pending.choicetype == ChoiceType.PLACE_UNITS
        legal = engine.legal_actions()
        engine.step(agents[pending.player_id].choose(legal))
        steps += 1
        if steps > 30_000:
            break
    assert engine.terminal
    assert engine.setup_complete
    assert engine.winner_ranking() is not None
    # After play only a few units remain; pattern length was 9 at setup.
    assert len(engine.setup_pattern) == 9
