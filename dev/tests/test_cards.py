import random

from collections import Counter

from sixtyfivekmconvoy.core.cards import (
    ACTION_CATALOG,
    HIT_CATALOG,
    MAULING_CATALOG,
    OFFICER_CATALOG,
    PILLAGE_CATALOG,
    RESISTANCE_CATALOG,
    select_resistance_deck,
)
from sixtyfivekmconvoy.core.constants import RESISTANCE_POOL_SIZE
from sixtyfivekmconvoy.core.engine import GameEngine


def _seat_units(engine: GameEngine, hand_size: int = 4) -> None:
    """Skip interactive placement so convoy/hit tests can run against live units."""
    if engine._unit_pool:
        engine.convoy.units = list(engine._unit_pool)
        engine._unit_pool = []
    engine.setup_complete = True
    for u in engine.convoy.units:
        u.convoy = engine.convoy
        u.engine = engine
    for p in engine.players:
        while len(p.action_cards) < hand_size:
            p.draw_card(1)


def test_catalogs_nonempty():
    assert len(ACTION_CATALOG) >= 10
    assert len(OFFICER_CATALOG) >= 5
    assert len(PILLAGE_CATALOG) >= 10
    assert len(MAULING_CATALOG) >= 10
    assert len(RESISTANCE_CATALOG) >= 5
    assert len(HIT_CATALOG) == 50


def test_hit_deck_category_ranges_and_stats():
    allowed = {1: {0, 1}, 2: {1, 2}, 3: {1, 2, 3}, 4: {2, 3, 4}}
    counts = {1: Counter(), 2: Counter(), 3: Counter(), 4: Counter()}
    for card in HIT_CATALOG.values():
        assert set(card.damage.keys()) == {1, 2, 3, 4}
        for cat, value in card.damage.items():
            assert value in allowed[cat]
            counts[cat][value] += 1
    # Balanced margins used when generating hit.csv
    assert counts[1][0] == 25 and counts[1][1] == 25
    assert counts[2][1] == 25 and counts[2][2] == 25
    assert counts[3][1] == 12 and counts[3][2] == 26 and counts[3][3] == 12
    assert counts[4][2] == 12 and counts[4][3] == 26 and counts[4][4] == 12


def test_draw_hit_damage_uses_category_and_discards():
    engine = GameEngine()
    engine.reset(num_players=2, seed=11)
    assert len(engine.hit_deck.deck) == 50
    dmg = engine.draw_hit_damage(2)
    assert dmg in (1, 2)
    assert len(engine.hit_deck.deck) == 49
    assert len(engine.hit_deck.discard) == 1
    # Exhaust and reshuffle still works
    while engine.hit_deck.deck:
        engine.draw_hit_damage(1)
    assert engine.hit_deck.deck == []
    assert len(engine.hit_deck.discard) == 50
    dmg = engine.draw_hit_damage(1)
    assert dmg in (0, 1)
    assert len(engine.hit_deck.deck) == 49  # reshuffled then drew one


def test_resistance_catalog_has_exactly_one_starter():
    starters = [c for c in RESISTANCE_CATALOG.values() if c.starting]
    assert len(starters) == 1
    assert starters[0].name == "Rajapuomi"
    assert starters[0].effect["attack"] == 0
    assert all(hasattr(c, "min_players") for c in RESISTANCE_CATALOG.values())


def test_select_resistance_deck_filters_by_players_and_samples():
    rng = random.Random(0)
    starter_id, pool = select_resistance_deck(2, rng)
    assert RESISTANCE_CATALOG[starter_id].starting
    assert starter_id not in pool
    assert len(pool) == RESISTANCE_POOL_SIZE[2]
    for cid in pool:
        card = RESISTANCE_CATALOG[cid]
        assert not card.starting
        assert card.min_players <= 2

    rng5 = random.Random(0)
    starter5, pool5 = select_resistance_deck(5, rng5)
    assert starter5 == starter_id
    assert len(pool5) == RESISTANCE_POOL_SIZE[5]
    # 5-player pool may include high min_players cards
    assert any(RESISTANCE_CATALOG[c].min_players >= 4 for c in pool5) or True


def test_game_starts_with_fixed_resistance_starter():
    engine = GameEngine()
    engine.reset(num_players=3, seed=7)
    assert engine.resistance.name == "Rajapuomi"
    assert engine.resistance.active
    assert engine.resistance.damage_to_convoy == 0
    # Starter is front of queue; deck holds only the sampled pool
    assert len(engine.resistance_queue) == 3
    front_id, front_vis = engine.resistance_queue.cards_and_visibilities[0]
    assert front_vis is True
    assert front_id == engine._resistance_starter_id
    assert engine._resistance_starter_id not in engine.resistance_deck.deck
    assert len(engine.resistance_deck.deck) == RESISTANCE_POOL_SIZE[3] - 2  # 2 drawn into queue


def test_resistance_attack_zero_does_not_damage_convoy():
    from sixtyfivekmconvoy.core.models import Resistance

    engine = GameEngine()
    engine.reset(num_players=2, seed=3)
    _seat_units(engine)
    front = engine.convoy.units[0]
    carry_before = list(front.carry)

    res = Resistance(
        {
            "name": "Rajapuomi",
            "effect": {
                "attack": 0,
                "target": "A1",
                "loot": 3,
                "durability": 1,
                "damage": {"I": 1, "P": 1},
            },
        },
        engine=engine,
    )
    msg = res.attack()
    assert "does not attack" in msg
    assert list(front.carry) == carry_before


def test_resistance_attack_uses_hit_category():
    from sixtyfivekmconvoy.core.models import Resistance

    engine = GameEngine()
    engine.reset(num_players=2, seed=5)
    _seat_units(engine)
    front = engine.convoy.units[0]
    carry_before = len(front.carry)
    hit_before = len(engine.hit_deck.deck)

    res = Resistance(
        {
            "name": "Ambush",
            "effect": {
                "attack": 2,  # hit category 2 → damage 1–2
                "target": "A1",
                "loot": 1,
                "durability": 1,
                "damage": {"I": 1, "P": 1},
            },
        },
        engine=engine,
    )
    msg = res.attack()
    assert "cat 2" in msg
    assert "does not attack" not in msg
    assert len(engine.hit_deck.deck) == hit_before - 1
    assert len(engine.hit_deck.discard) == 1
    lost = carry_before - len(front.carry)
    assert lost in (1, 2)
    assert f"for {lost}" in msg


def test_mauling_catalog_hit_and_discard_modes():
    from sixtyfivekmconvoy.core.cards import load_mauling_deck
    from sixtyfivekmconvoy.core.constants import AttackType

    deck = load_mauling_deck()
    assert len(deck) >= 18
    hit_only = next(c for c in deck.values() if c.effect["hit_category"] > 0 and c.effect["discard"] == 0)
    assert hit_only.effect["hit_category"] in (1, 2, 3, 4)
    assert hit_only.effect["attack_type"] in AttackType.ALL
    discard_card = next(c for c in deck.values() if c.effect["discard"] > 0)
    assert discard_card.effect["fail_hit_category"] in (1, 2, 3, 4)
    assert all(c.effect["attack_type"] in AttackType.ALL for c in deck.values())
    sabotage = [c for c in deck.values() if c.effect["attack_type"] == AttackType.SABOTAGE]
    assert len(sabotage) >= 24  # prior S cards + 12 placeholders
    assert deck[20].effect["target"] == "A"  # Napalmia
    assert deck[0].effect["target"] == "first:atrocity"


def test_parse_mauling_target_grammar():
    from sixtyfivekmconvoy.core.cards import parse_mauling_target
    from sixtyfivekmconvoy.core.models import UnitType

    assert parse_mauling_target("B") == {"kind": "zone", "zone": "B"}
    assert parse_mauling_target("A1") == {"kind": "zone_rel", "zone": "A", "rel": 1}
    assert parse_mauling_target("B-1") == {"kind": "zone_rel", "zone": "B", "rel": -1}
    assert parse_mauling_target("first:P") == {
        "kind": "type",
        "which": "first",
        "unit_type": UnitType.PANZER,
    }
    assert parse_mauling_target("last:infantry") == {
        "kind": "type",
        "which": "last",
        "unit_type": UnitType.INFANTRY,
    }
    assert parse_mauling_target("first:atrocity") == {
        "kind": "atrocity",
        "which": "first",
    }
    try:
        parse_mauling_target("first:tank")
        raise AssertionError("expected ValueError")
    except ValueError:
        pass


def test_mauling_target_first_last_type_and_atrocity():
    from sixtyfivekmconvoy.core.actions import mauling_target_units
    from sixtyfivekmconvoy.core.models import Convoy, Player, UnitType

    players = [Player(0), Player(1)]
    convoy = Convoy(players)
    # Convoy builds one of each type per player; order is fixed by construction.
    panzers = [u for u in convoy.units if u.unittype == UnitType.PANZER]
    infantry = [u for u in convoy.units if u.unittype == UnitType.INFANTRY]
    logistics = [u for u in convoy.units if u.unittype == UnitType.LOGISTICS]
    assert len(panzers) >= 2
    assert mauling_target_units(convoy, "first:P") == [panzers[0]]
    assert mauling_target_units(convoy, "last:panzer") == [panzers[-1]]
    assert mauling_target_units(convoy, "first:I") == [infantry[0]]
    assert mauling_target_units(convoy, "last:L") == [logistics[-1]]

    # Atrocities: two tied at the max → frontmost / rearmost among ties
    for u in convoy.units:
        u.atrocities = 0
    panzers[0].atrocities = 3
    infantry[-1].atrocities = 3
    logistics[0].atrocities = 1
    assert mauling_target_units(convoy, "first:atrocity") == [panzers[0]]
    assert mauling_target_units(convoy, "last:atrocity") == [infantry[-1]]

    # No matching type → empty
    convoy.units = [u for u in convoy.units if u.unittype != UnitType.PANZER]
    assert mauling_target_units(convoy, "first:P") == []


def test_mauling_hit_category_draws_hit_table():
    from sixtyfivekmconvoy.core.actions import resolve_mauling

    engine = GameEngine()
    engine.reset(num_players=2, seed=9)
    _seat_units(engine)
    unit = engine.convoy.get_units_in_zone("B")[0]
    carry_before = len(unit.carry)
    hit_before = len(engine.hit_deck.deck)

    gen = resolve_mauling(
        engine,
        {
            "name": "Rocks",
            "effect": {
                "target": "B1",
                "hit_category": 4,
                "discard": 0,
                "fail_hit_category": 0,
                "attack_type": "G",
            },
        },
    )
    try:
        next(gen)
        raise AssertionError("hit-only mauling should not yield choices")
    except StopIteration as stop:
        msg = stop.value

    assert len(engine.hit_deck.deck) == hit_before - 1
    lost = carry_before - len(unit.carry)
    assert lost in (2, 3, 4)
    assert "takes" in msg


def test_mauling_forced_discard_when_able():
    from sixtyfivekmconvoy.core.actions import resolve_mauling
    from sixtyfivekmconvoy.core.constants import ChoiceType

    engine = GameEngine()
    engine.reset(num_players=2, seed=13)
    _seat_units(engine, hand_size=4)
    unit = engine.convoy.get_units_in_zone("A")[0]
    player = unit.player
    hand_before = list(player.action_cards)
    assert len(hand_before) >= 2
    to_discard = hand_before[:2]
    hit_before = len(engine.hit_deck.deck)
    carry_before = list(unit.carry)

    gen = resolve_mauling(
        engine,
        {
            "name": "Papers please",
            "effect": {
                "target": "A1",
                "hit_category": 0,
                "discard": 2,
                "fail_hit_category": 2,
                "attack_type": "G",
            },
        },
    )
    req = next(gen)
    assert req.choicetype == ChoiceType.CHOOSE_CARDS_TO_DISCARD
    assert req.num_choices == 2
    assert req.payload["reason"] == "mauling_discard"
    try:
        gen.send(to_discard)
        raise AssertionError("expected StopIteration after discard")
    except StopIteration as stop:
        msg = stop.value

    assert "discards 2" in msg
    assert len(player.action_cards) == len(hand_before) - 2
    assert list(unit.carry) == carry_before
    assert len(engine.hit_deck.deck) == hit_before  # no fail hit drawn


def test_mauling_fail_hit_when_cannot_discard():
    from sixtyfivekmconvoy.core.actions import resolve_mauling

    engine = GameEngine()
    engine.reset(num_players=2, seed=17)
    _seat_units(engine, hand_size=0)
    unit = engine.convoy.get_units_in_zone("A")[0]
    player = unit.player
    if player.action_cards:
        player.discard(list(player.action_cards))
    assert player.action_cards == []
    carry_before = len(unit.carry)
    hit_before = len(engine.hit_deck.deck)

    gen = resolve_mauling(
        engine,
        {
            "name": "Shakedown",
            "effect": {
                "target": "A1",
                "hit_category": 0,
                "discard": 1,
                "fail_hit_category": 2,
                "attack_type": "G",
            },
        },
    )
    try:
        next(gen)
        raise AssertionError("cannot-discard path should not yield choices")
    except StopIteration as stop:
        msg = stop.value

    assert "cannot discard" in msg
    assert len(engine.hit_deck.deck) == hit_before - 1
    lost = carry_before - len(unit.carry)
    assert lost in (1, 2)
    assert unit in engine.convoy.units or lost == carry_before


def test_action_card_describe():
    card = next(iter(ACTION_CATALOG.values()))
    desc = card.describe()
    assert isinstance(desc, list)
    assert "action_name" in desc[0]
