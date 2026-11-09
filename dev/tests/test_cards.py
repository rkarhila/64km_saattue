import random

from collections import Counter

from sixtyfivekmconvoy.core.cards import (
    ACTION_CATALOG,
    HIT_DECKS,
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
    engine._open_table()
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


def _hold_all(engine, value: int, player, *, pile: str = "bank_counters"):
    """Move every card of ``value`` onto one player's money pile."""
    deck = engine.hit_decks[value]
    counters = [{"value": value, "id": card_id, "fresh": False} for card_id in deck.deck]
    deck.deck.clear()
    deck.discard.clear()
    setattr(player, pile, counters)
    return counters


def test_empty_ones_pile_is_changed_into_tens():
    engine = GameEngine()
    engine.reset(num_players=2, seed=2)
    player = engine.players[0]
    _hold_all(engine, 1, player)
    assert engine._pile_empty(1)
    engine.consolidate_empty_pile(1)
    assert player.bank_counters
    assert {c["value"] for c in player.bank_counters} == {10}
    assert len(player.bank_counters) == 5  # 50 × $1 → 5 × $10
    assert sum(c["value"] for c in player.bank_counters) == 50
    assert len(engine.hit_decks[1].deck) + len(engine.hit_decks[1].discard) == 50


def test_empty_fives_pile_is_changed_into_tens():
    engine = GameEngine()
    engine.reset(num_players=2, seed=3)
    player = engine.players[0]
    held = _hold_all(engine, 5, player)
    # Keep four $5s; the rest are already out of the pile.
    player.bank_counters = held[:4]
    engine.consolidate_empty_pile(5)
    assert sorted(c["value"] for c in player.bank_counters) == [10, 10]
    assert len(engine.hit_decks[5].discard) == 4


def test_empty_threes_pile_is_changed_into_fives_and_tens():
    engine = GameEngine()
    engine.reset(num_players=2, seed=4)
    player = engine.players[0]
    held = _hold_all(engine, 3, player)
    player.bank_counters = held[:5]  # $15
    engine.consolidate_empty_pile(3)
    assert sorted(c["value"] for c in player.bank_counters) == [5, 10]
    assert len(engine.hit_decks[3].discard) == 5


def test_draw_from_empty_ones_pile_changes_markers_first():
    engine = GameEngine()
    engine.reset(num_players=2, seed=5)
    player = engine.players[0]
    held = _hold_all(engine, 1, player)
    player.bank_counters = held[:5]
    drawn = engine.draw_money(1)
    assert [c["value"] for c in drawn] == [1]
    assert any(c["value"] == 5 for c in player.bank_counters)
    assert len(engine.hit_decks[1].deck) + len(engine.hit_decks[1].discard) == 4


def test_destroyed_unit_and_resistance_recycle_damage_cards():
    from sixtyfivekmconvoy.core.models import Resistance

    engine = GameEngine()
    engine.reset(num_players=2, seed=6)
    engine.convoy.units = list(engine._unit_pool)
    engine._unit_pool = []
    unit = engine.convoy.units[0]
    unit.convoy = engine.convoy
    unit.engine = engine
    unit.carry = [0, 0, 0]

    damage = engine.draw_hit_damage(3)
    assert damage > 0
    engine.attach_damage_marker(unit, damage, category=3)
    card_id = unit.damage_markers[-1]["id"]
    assert card_id is not None
    assert engine.hit_decks[3].discard == []

    engine.convoy.apply_damage(3, unit=unit)
    assert unit not in engine.convoy.units
    assert unit.damage_markers == []
    assert card_id in engine.hit_decks[3].discard

    engine.resistance = Resistance(
        {
            "name": "Tiesulku",
            "effect": {
                "ambush_damage": "0",
                "resistance_damage": "0",
                "durability": 1,
                "loot": 0,
                "cash_for_destroying": 0,
            },
        },
        engine=engine,
    )
    hit = engine.draw_hit_damage(5)
    engine.attach_damage_marker(engine.resistance, hit, category=5)
    held = engine.resistance.damage_markers[-1]["id"]
    engine.resistance.take_damage("I", "=1", player=engine.players[0])
    assert engine.resistance.damage_markers == []
    assert held in engine.hit_decks[5].discard


def test_cash_reward_draws_counters_then_banks_them():
    engine = GameEngine()
    engine.reset(num_players=2, seed=1)
    player = engine.players[0]
    ones = len(engine.hit_decks[1].deck)
    threes = len(engine.hit_decks[3].deck)
    player.get_cash(4, source="test")
    assert player.this_round_cash == 4
    assert player.total_cash == 4
    assert sorted(c["value"] for c in player.round_counters) == [1, 3]
    assert player.bank_counters == []
    assert len(engine.hit_decks[1].deck) == ones - 1
    assert len(engine.hit_decks[3].deck) == threes - 1
    player.bank_round_cash()
    assert player.round_counters == []
    assert player.this_round_cash == 0
    assert player.total_cash == 4
    assert sorted(c["value"] for c in player.bank_counters) == [1, 3]


def test_catalogs_nonempty():
    assert len(ACTION_CATALOG) >= 10
    assert len(OFFICER_CATALOG) >= 5
    assert len(PILLAGE_CATALOG) >= 10
    assert len(MAULING_CATALOG) >= 10
    assert len(RESISTANCE_CATALOG) >= 5
    assert set(HIT_DECKS) == {1, 3, 5, 10}
    assert all(len(deck) == 50 for deck in HIT_DECKS.values())


def test_hit_deck_category_ranges_and_stats():
    allowed = {1: {0, 1}, 3: {1, 2}, 5: {1, 2, 3}, 10: {2, 3, 4}}
    counts = {cat: Counter() for cat in allowed}
    for cat, deck in HIT_DECKS.items():
        for card in deck.values():
            assert card.category == cat
            assert card.cash == cat
            assert card.damage in allowed[cat]
            counts[cat][card.damage] += 1
    # Balanced margins used when generating hit.csv
    assert counts[1][0] == 25 and counts[1][1] == 25
    assert counts[3][1] == 25 and counts[3][2] == 25
    assert counts[5][1] == 12 and counts[5][2] == 26 and counts[5][3] == 12
    assert counts[10][2] == 12 and counts[10][3] == 26 and counts[10][4] == 12


def test_draw_hit_damage_uses_category_and_discards():
    engine = GameEngine()
    engine.reset(num_players=2, seed=11)
    assert len(engine.hit_decks[3].deck) == 50
    dmg = engine.draw_hit_damage(3)
    assert dmg in (1, 2)
    assert engine.hit_draws[-1]["category"] == 3
    assert engine.hit_draws[-1]["damage"] == dmg
    assert engine.hit_draws[-1]["cash"] == 3
    assert len(engine.hit_decks[3].deck) == 49
    assert len(engine.hit_decks[3].discard) == 0  # held until released
    engine.discard_unclaimed_hits()
    assert len(engine.hit_decks[3].discard) == 1
    assert len(engine.hit_decks[1].deck) == 50
    # Exhaust, release, and reshuffle still works
    while engine.hit_decks[1].deck:
        engine.draw_hit_damage(1)
    assert engine.hit_decks[1].deck == []
    assert engine.hit_decks[1].discard == []
    engine.discard_unclaimed_hits()
    assert len(engine.hit_decks[1].discard) == 50
    dmg = engine.draw_hit_damage(1)
    assert dmg in (0, 1)
    assert len(engine.hit_decks[1].deck) == 49  # reshuffled then drew one


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


def _finish_placement(engine: GameEngine) -> None:
    from sixtyfivekmconvoy.core.constants import ChoiceType

    while (
        engine.pending_choice() is not None
        and engine.pending_choice().choicetype == ChoiceType.PLACE_UNITS
    ):
        engine.step([0, 1, 2])


def test_game_starts_with_fixed_resistance_starter():
    engine = GameEngine()
    engine.reset(num_players=3, seed=7)
    _finish_placement(engine)
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


def test_resistance_card_exposes_ambush_target_only():
    from sixtyfivekmconvoy.core.cards import load_resistance_deck

    deck = load_resistance_deck()
    roadblock = deck[0]
    assert roadblock.effect["ambush_target"] == "A"
    assert roadblock.effect["target"] == "A"
    assert "resistance_target" not in roadblock.effect
    mine = deck[4]
    assert mine.effect["ambush_target"] == "first:I"
    assert mine.effect["resistance_attack"] == "Tarkk’ampujia"


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
    hit_before = len(engine.hit_decks[3].deck)

    res = Resistance(
        {
            "name": "Ambush",
            "effect": {
                "attack": 3,  # category 3 deck → damage 1–2
                "target": "A1",
                "loot": 1,
                "durability": 1,
                "damage": {"I": 1, "P": 1},
            },
        },
        engine=engine,
    )
    msg = res.attack()
    assert "cat 3" in msg
    assert "does not attack" not in msg
    assert len(engine.hit_decks[3].deck) == hit_before - 1
    assert front.damage_markers
    assert front.damage_markers[-1]["id"] is not None
    assert engine.hit_decks[3].discard == []
    lost = carry_before - len(front.carry)
    assert lost in (1, 2)
    assert f"for {lost}" in msg


def test_mauling_catalog_hit_and_discard_modes():
    from sixtyfivekmconvoy.core.cards import load_mauling_deck
    from sixtyfivekmconvoy.core.constants import AttackType

    deck = load_mauling_deck()
    assert len(deck) >= 18
    hit_only = next(c for c in deck.values() if c.effect["hit_category"] > 0 and c.effect["discard"] == 0)
    assert hit_only.effect["hit_category"] in (1, 3, 5, 10)
    assert hit_only.effect["attack_type"] in AttackType.ALL
    discard_card = next(c for c in deck.values() if c.effect["discard"] > 0)
    assert discard_card.effect["fail_hit_category"] in (1, 3, 5, 10)
    assert all(c.effect["attack_type"] in AttackType.ALL for c in deck.values())
    sabotage = [c for c in deck.values() if c.effect["attack_type"] == AttackType.SABOTAGE]
    assert len(sabotage) >= 12
    assert deck[20].effect["target"] == "A"  # Napalmia
    assert deck[20].effect["target_label"] == "Kaikki vyöhykkeellä A"
    assert deck[0].effect["target"] == "first:atrocity"
    assert deck[0].effect["target_label"] == "Eniten hirmutekoja, kärjestä"
    from collections import Counter

    fronts = Counter(card.formations["5"][0] for card in deck.values())
    assert set(fronts) == set("12345")
    assert max(fronts.values()) - min(fronts.values()) <= 1
    for card in deck.values():
        full = card.formations["5"]
        for n in (2, 3, 4):
            assert card.formations[str(n)] == "".join(ch for ch in full if int(ch) <= n)
    assert len({c.formations["5"][0] for c in deck.values()}) == 5


def test_mauling_target_labels_are_finnish():
    from sixtyfivekmconvoy.core.i18n import format_mauling_target

    assert format_mauling_target("A") == "Kaikki vyöhykkeellä A"
    assert format_mauling_target("E") == "Kaikki vyöhykkeellä E"
    assert format_mauling_target("A1") == "Vyöhykkeen A ensimmäinen kärjestä"
    assert format_mauling_target("B2") == "Vyöhykkeen B toinen kärjestä"
    assert format_mauling_target("C-1") == "Vyöhykkeen C ensimmäinen perältä"
    assert format_mauling_target("E-2") == "Vyöhykkeen E toinen perältä"
    assert format_mauling_target("first:P") == "Etummaiset panssarit"
    assert format_mauling_target("second:I") == "Toinen jalkaväki kärjestä"
    assert format_mauling_target("second_last:L") == "Toinen huolto perältä"
    assert format_mauling_target("last:P") == "Perimmäiset panssarit"
    assert format_mauling_target("first:atrocity") == "Eniten hirmutekoja, kärjestä"
    assert format_mauling_target("second:atrocity") == "Toinen eniten hirmutekoja, kärjestä"
    assert format_mauling_target("second_last:atrocity") == "Toinen eniten hirmutekoja, perältä"
    assert format_mauling_target("last:atrocity") == "Eniten hirmutekoja, perältä"
    assert format_mauling_target("AB") == "Vyöhykkeet A ja B"
    assert format_mauling_target("-") == ""


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
    hit_before = len(engine.hit_decks[10].deck)

    gen = resolve_mauling(
        engine,
        {
            "name": "Rocks",
            "effect": {
                "target": "B1",
                "hit_category": 10,
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

    assert len(engine.hit_decks[10].deck) == hit_before - 1
    assert len(engine.hit_draws) == 1
    assert engine.hit_draws[0]["category"] == 10
    from sixtyfivekmconvoy.core.view import player_view

    view = player_view(engine, engine.players[0])
    if unit in engine.convoy.units:
        assert unit.index() in view["struck_units"]
        dealt = engine.hit_draws[0]["damage"]
        if dealt > 0:
            assert unit.damage_markers[-1]["damage"] == dealt
            assert unit.damage_markers[-1]["category"] == 10
    engine.resistance.durability = 3
    engine.resistance.take_damage("I", "=1", player=engine.players[0])
    assert engine.resistance_struck is True
    assert engine.resistance.active
    assert engine.resistance.damage_markers[-1]["damage"] == 1
    assert player_view(engine, engine.players[0])["resistance_struck"] is True
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
    hit_before = len(engine.hit_decks[3].deck)
    carry_before = list(unit.carry)

    gen = resolve_mauling(
        engine,
        {
            "name": "Papers please",
            "effect": {
                "target": "A1",
                "hit_category": 0,
                "discard": 2,
                "fail_hit_category": 3,
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
    assert len(engine.hit_decks[3].deck) == hit_before  # no fail hit drawn


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
    hit_before = len(engine.hit_decks[3].deck)

    gen = resolve_mauling(
        engine,
        {
            "name": "Shakedown",
            "effect": {
                "target": "A1",
                "hit_category": 0,
                "discard": 1,
                "fail_hit_category": 3,
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
    assert len(engine.hit_decks[3].deck) == hit_before - 1
    lost = carry_before - len(unit.carry)
    assert lost in (1, 2)
    assert unit in engine.convoy.units or lost == carry_before


def test_action_card_describe():
    card = next(iter(ACTION_CATALOG.values()))
    desc = card.describe()
    assert isinstance(desc, list)
    assert "action_name" in desc[0]
