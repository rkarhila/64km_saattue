import pytest
from sixtyfivekmconvoy.core.cards import parse_mauling_target
from sixtyfivekmconvoy.core.engine import GameEngine
from sixtyfivekmconvoy.core.models import UnitType, Player, Unit
from sixtyfivekmconvoy.core.actions import mauling_target_units


def _seat_custom_convoy(engine: GameEngine, unittypes: list[int]):
    engine.setup_complete = True
    engine.convoy.units = []
    p = engine.players[0]
    for ut in unittypes:
        unit = Unit(p, ut)
        unit.convoy = engine.convoy
        unit.engine = engine
        engine.convoy.units.append(unit)


def test_parse_second_and_second_last():
    sel1 = parse_mauling_target("second:P")
    assert sel1["kind"] == "type"
    assert sel1["which"] == "second"
    assert sel1["unit_type"] == UnitType.PANZER

    sel2 = parse_mauling_target("second_last:I")
    assert sel2["kind"] == "type"
    assert sel2["which"] == "second_last"
    assert sel2["unit_type"] == UnitType.INFANTRY

    sel3 = parse_mauling_target("second:atrocity")
    assert sel3["kind"] == "atrocity"
    assert sel3["which"] == "second"


def test_mauling_target_units_second_and_second_last():
    engine = GameEngine()
    engine.reset(num_players=2, seed=10)
    
    # Custom convoy: [P, I, I, P, L, I]
    _seat_custom_convoy(engine, [
        UnitType.PANZER,    # Position 1, index 0
        UnitType.INFANTRY,  # Position 2, index 1
        UnitType.INFANTRY,  # Position 3, index 2
        UnitType.PANZER,    # Position 4, index 3
        UnitType.LOGISTICS, # Position 5, index 4
        UnitType.INFANTRY,  # Position 6, index 5
    ])
    
    # 1. second:P (Should be index 3)
    targets = mauling_target_units(engine.convoy, "second:P")
    assert len(targets) == 1
    assert targets[0].index() == 3

    # 2. second_last:I (Should be matched[-2] of [1, 2, 5] -> index 2)
    targets = mauling_target_units(engine.convoy, "second_last:I")
    assert len(targets) == 1
    assert targets[0].index() == 2

    # 3. second_last:P (Should be matched[-2] of [0, 3] -> index 0)
    targets = mauling_target_units(engine.convoy, "second_last:P")
    assert len(targets) == 1
    assert targets[0].index() == 0

    # 4. second:L (Only 1 logistics unit, so len(matched) < 2, should return empty list)
    targets = mauling_target_units(engine.convoy, "second:L")
    assert targets == []


def test_mauling_resistance_attack():
    from sixtyfivekmconvoy.core.actions import resolve_mauling
    from sixtyfivekmconvoy.core.models import Resistance
    from sixtyfivekmconvoy.core.constants import AttackType

    engine = GameEngine()
    engine.reset(num_players=2, seed=123)
    _seat_custom_convoy(engine, [UnitType.INFANTRY])
    unit = engine.convoy.units[0]
    
    # 1. No active resistance (engine.resistance.active is False)
    # The hit_category in the mauling card is set to 4, but because attack_type is 'R'
    # and resistance is not active, it should be overridden to 0 (no damage).
    gen1 = resolve_mauling(
        engine,
        {
            "name": "Resistance Ambush",
            "effect": {
                "target": "A1",
                "hit_category": 4,
                "discard": 0,
                "fail_hit_category": 0,
                "attack_type": "R",
            },
        },
    )
    try:
        next(gen1)
    except StopIteration as stop:
        msg = stop.value
    # Confirm 0 damage was dealt / no effect
    assert "takes 0" in msg or "hit cat" in msg or msg == "no effect"

    # 2. Active resistance with resistance_attack_category = 3
    # Let's set up an active resistance card description.
    res_desc = {
        "name": "Sissit",
        "effect": {
            "ambush_attack": "Sissit",
            "ambush_damage": "1",
            "ambush_target": "A1",
            "resistance_attack": "Tarkk’ampujia",
            "resistance_damage": "3",
            "resistance_target": "A1",
            "loot": 2,
            "durability": 3,
            "damage": {"I": 1, "P": 1},
        }
    }
    engine.resistance = Resistance(res_desc, engine)
    assert engine.resistance.active is True
    assert engine.resistance.attack_category == 1
    assert engine.resistance.ambush_target == "A1"
    assert engine.resistance.resistance_attack_category == 3
    assert engine.resistance.resistance_target == "A1"

    # Now let's run the R-type mauling card. The hit_category in the card description (e.g. 1)
    # should be overridden to 3 (the resistance_attack_category value).
    # To test this perfectly, we can check how many cards are drawn from the hit table or the message.
    # Let's mock draw_hit_damage to return a known damage, e.g. 4, for category 3.
    original_draw = engine.draw_hit_damage
    engine.draw_hit_damage = lambda cat: 4 if cat == 3 else 0

    gen2 = resolve_mauling(
        engine,
        {
            "name": "Resistance Ambush",
            "effect": {
                "target": "A1",
                "hit_category": 1, # Should be overridden to 3
                "discard": 0,
                "fail_hit_category": 0,
                "attack_type": "R",
            },
        },
    )
    try:
        next(gen2)
    except StopIteration as stop:
        msg2 = stop.value
    
    assert "takes 4 damage" in msg2

    # 3. Defensive soaking as "G".
    # A unit defending against "G" should soak this R-type attack (since it counts as G).
    # Let's re-seat custom convoy so we have a fresh unit with full capacity
    _seat_custom_convoy(engine, [UnitType.INFANTRY])
    unit = engine.convoy.units[0]
    # Let's set unit to defend as "G".
    unit.resolve_defend(AttackType.GROUND, "_")
    assert unit.defending == "G"

    gen3 = resolve_mauling(
        engine,
        {
            "name": "Resistance Ambush",
            "effect": {
                "target": "A1",
                "hit_category": 1, # Should be overridden to 3
                "discard": 0,
                "fail_hit_category": 0,
                "attack_type": "R",
            },
        },
    )
    try:
        next(gen3)
    except StopIteration as stop:
        msg3 = stop.value
    
    assert "Defense soaks" in msg3 or "Defense soaks up all damage." in msg3

    # Restore draw_hit_damage
    engine.draw_hit_damage = original_draw


def test_reorder_ambush():
    from sixtyfivekmconvoy.core.models import Resistance, UnitType

    engine = GameEngine()
    engine.reset(num_players=2, seed=123)
    
    # Custom convoy of 6 units: [I, I, I, I, I, I]
    # Position: 1, 2, 3, 4, 5, 6
    _seat_custom_convoy(engine, [
        UnitType.INFANTRY,
        UnitType.INFANTRY,
        UnitType.INFANTRY,
        UnitType.INFANTRY,
        UnitType.INFANTRY,
        UnitType.INFANTRY,
    ])
    
    # Manually configure zones for a 2-player layout
    # E.g. A has 2 units (positions 1, 2), B has 3 units (positions 3, 4, 5), C or E has remainder
    engine.convoy.zones = {
        "A": [0, 1],
        "B": [2, 3, 4],
        "C": [5],
        "E": [],
    }

    # Verify positions and zones
    assert [u.position() for u in engine.convoy.units] == [1, 2, 3, 4, 5, 6]
    assert [u.zone() for u in engine.convoy.units] == ["A", "A", "B", "B", "B", "C"]

    # 1. Ambush with target A, damage "reorder"
    res_desc1 = {
        "name": "Käännetty kyltti",
        "effect": {
            "ambush_attack": "Käännetty kyltti",
            "ambush_damage": "reorder",
            "ambush_target": "A",
            "resistance_attack": "Tarkk’ampujia",
            "resistance_damage": "1",
            "resistance_target": "A1",
            "loot": 1,
            "durability": 1,
        }
    }
    res1 = Resistance(res_desc1, engine)
    # Trigger attack (which does the reordering)
    msg1 = res1.attack()
    assert "reordered units in zones A" in msg1

    # Expected order: not_in_target_zones (3, 4, 5, 6) + reversed(in_target_zones) (2, 1)
    # Wait, when they reorder, their index() changes because the list elements are moved.
    # To identify units uniquely, let's keep references to the original unit objects.
    orig_units = list(engine.convoy.units) # [u1, u2, u3, u4, u5, u6]
    
    # Reset convoy to original order first
    engine.convoy.units = list(orig_units)
    assert engine.convoy.units == orig_units

    res1.attack()
    # Now check the reordered list of unit objects
    # Expected: [u3, u4, u5, u6, u2, u1]
    expected_order_a = [orig_units[2], orig_units[3], orig_units[4], orig_units[5], orig_units[1], orig_units[0]]
    assert engine.convoy.units == expected_order_a

    # 2. Ambush with target AB, damage "reorder"
    # Reset convoy to original order first
    engine.convoy.units = list(orig_units)
    
    res_desc2 = {
        "name": "Käännetty kyltti",
        "effect": {
            "ambush_attack": "Käännetty kyltti",
            "ambush_damage": "reorder",
            "ambush_target": "AB",
            "resistance_attack": "Tarkk’ampujia",
            "resistance_damage": "1",
            "resistance_target": "A1",
            "loot": 1,
            "durability": 1,
        }
    }
    res2 = Resistance(res_desc2, engine)
    msg2 = res2.attack()
    assert "reordered units in zones AB" in msg2

    # Expected order: not_in_target_zones (6) + reversed(in_target_zones) (5, 4, 3, 2, 1)
    # Expected: [u6, u5, u4, u3, u2, u1]
    expected_order_ab = [orig_units[5], orig_units[4], orig_units[3], orig_units[2], orig_units[1], orig_units[0]]
    assert engine.convoy.units == expected_order_ab

