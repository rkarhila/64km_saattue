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
