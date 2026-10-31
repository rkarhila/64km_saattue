from sixtyfivekmconvoy.core.engine import GameEngine
from sixtyfivekmconvoy.core.models import UnitType, Unit, Resistance
from sixtyfivekmconvoy.core.constants import ActionName, ChoiceType
from sixtyfivekmconvoy.core import actions as action_mod
from sixtyfivekmconvoy.core.config import (
    SCOUT_CASH,
    SERVICE_CASH,
    ATTACK_CASH,
    FIRST_UNIT_ADVANCE_CASH,
    RESISTANCE_HIT_CASH,
)


def _setup_custom_game():
    engine = GameEngine()
    engine.reset(num_players=2, seed=42)
    engine.setup_complete = True
    engine.convoy.units = []

    p0 = engine.players[0]
    p1 = engine.players[1]

    u0 = Unit(p0, UnitType.INFANTRY)
    u0.convoy = engine.convoy
    u0.engine = engine

    u1 = Unit(p1, UnitType.PANZER)
    u1.convoy = engine.convoy
    u1.engine = engine

    u2 = Unit(p0, UnitType.LOGISTICS)
    u2.convoy = engine.convoy
    u2.engine = engine

    engine.convoy.units = [u0, u1, u2]
    return engine, p0, p1, u0, u1, u2


def test_incentive_scout():
    engine, p0, p1, u0, u1, u2 = _setup_custom_game()
    engine.pause_after_actions = False
    initial_cash = p0.total_cash

    resistance_hidden_indices = [
        idx
        for idx, (_, vis) in enumerate(engine.resistance_queue.cards_and_visibilities)
        if not vis
    ]
    assert resistance_hidden_indices

    opt = 200 + resistance_hidden_indices[0]

    gen = action_mod.resolve_scout(engine, u0, count=1)
    req = next(gen)
    assert req.choicetype == ChoiceType.CHOOSE_CARDS_TO_SCOUT

    try:
        gen.send([opt])
    except StopIteration:
        pass

    assert p0.total_cash == initial_cash + SCOUT_CASH


def test_incentive_service_other_player():
    engine, p0, p1, u0, u1, u2 = _setup_custom_game()
    u1.tired = 2
    initial_cash = p0.total_cash

    gen = action_mod._resolve_service(engine, u0)
    try:
        next(gen)
    except StopIteration:
        pass

    assert u1.tired == 1
    assert p0.total_cash == initial_cash + SERVICE_CASH


def test_incentive_service_same_player():
    engine, p0, p1, u0, u1, u2 = _setup_custom_game()
    engine.convoy.units = [u0, u2, u1]
    u2.tired = 2
    u1.tired = 0
    initial_cash = p0.total_cash

    gen = action_mod._resolve_service(engine, u0)
    try:
        next(gen)
    except StopIteration:
        pass

    assert u2.tired == 1
    assert p0.total_cash == initial_cash + SERVICE_CASH


def test_incentive_attack_and_destroy_resistance():
    engine, p0, p1, u0, u1, u2 = _setup_custom_game()
    initial_cash = p0.total_cash
    destroy_cash = 5

    res_desc = {
        "name": "Test Resistance",
        "effect": {
            "ambush_attack": "",
            "ambush_damage": "0",
            "ambush_target": "A1",
            "resistance_attack": "",
            "resistance_damage": "0",
            "resistance_target": "A1",
            "loot": 0,
            "durability": 1,
            "cash_for_destroying": destroy_cash,
            "damage": {},
        },
    }
    engine.resistance = Resistance(res_desc, engine)

    gen = action_mod.resolve_action(
        engine,
        actor_idx=u0.index(),
        action={
            "action_name": ActionName.ATTACK,
            "action_modifier": 1,
            "cost": "0",
        },
        cardnumber=0,
    )
    try:
        next(gen)
    except StopIteration:
        pass

    # Destroy cash from the resistance card + ATTACK_CASH incentive.
    expected_gain = destroy_cash + ATTACK_CASH
    assert p0.total_cash == initial_cash + expected_gain


def test_resistance_hit_cash_when_not_destroyed():
    engine, p0, p1, u0, u1, u2 = _setup_custom_game()
    initial_cash = p0.total_cash

    res_desc = {
        "name": "Tanky",
        "effect": {
            "ambush_damage": "0",
            "ambush_target": "A1",
            "resistance_damage": "0",
            "resistance_target": "A1",
            "loot": 0,
            "durability": 3,
            "cash_for_destroying": 9,
            "damage": {},
        },
    }
    engine.resistance = Resistance(res_desc, engine)

    gen = action_mod.resolve_action(
        engine,
        actor_idx=u0.index(),
        action={
            "action_name": ActionName.ATTACK,
            "action_modifier": 1,
            "cost": "0",
        },
        cardnumber=0,
    )
    try:
        next(gen)
    except StopIteration:
        pass

    assert engine.resistance.active
    assert p0.total_cash == initial_cash + RESISTANCE_HIT_CASH + ATTACK_CASH


def test_incentive_first_unit_advance():
    engine, p0, p1, u0, u1, u2 = _setup_custom_game()
    initial_cash = p0.total_cash
    engine.resistance.active = False

    first_unit = engine.convoy.units[0]
    assert first_unit.player == p0

    engine.convoy.move_resting_and_damaged_units()
    first_unit = engine.convoy.units[0]
    first_unit.player.get_cash(FIRST_UNIT_ADVANCE_CASH)

    assert p0.total_cash == initial_cash + FIRST_UNIT_ADVANCE_CASH


def test_resistance_csv_loads_cash_for_destroying():
    from sixtyfivekmconvoy.core.cards import RESISTANCE_CATALOG

    card = RESISTANCE_CATALOG[19]
    assert card.effect.get("cash_for_destroying") == 1
    hard = RESISTANCE_CATALOG[17]
    assert hard.effect.get("cash_for_destroying") == 4


def test_action_face_exposes_cash_bonus():
    from sixtyfivekmconvoy.core.card_display import format_face
    from sixtyfivekmconvoy.core.constants import ActionName

    face = format_face(
        {
            "name": "Huolla",
            "action_name": ActionName.SERVICE,
            "action_modifier": 0,
            "cost": "0",
            "tire": 0,
            "intoxicate": 0,
            "troop_type": "A",
            "zone": "ABCE",
        }
    )
    assert face["cash_bonus"] == SERVICE_CASH
    assert face["reward"]["label"] == f"(+{SERVICE_CASH})"
