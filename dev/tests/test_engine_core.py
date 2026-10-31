from sixtyfivekmconvoy.agents.random_agent import RandomAgent
from sixtyfivekmconvoy.core import actions as action_mod
from sixtyfivekmconvoy.core.cards import CardQueue
from sixtyfivekmconvoy.core.engine import GameEngine
from sixtyfivekmconvoy.core.models import Convoy, Player, UnitType


def test_zones_three_players():
    players = [Player(i) for i in range(3)]
    convoy = Convoy(players)
    assert set(convoy.zones.keys()) == {"A", "B", "C", "E"}
    assert len(convoy.units) == 9
    # Front units in A/B
    assert convoy.units[0].zone() in "ABE"
    assert convoy.units[-1].zone() == "E"


def test_damage_removes_unit():
    players = [Player(i) for i in range(2)]
    convoy = Convoy(players)
    unit = convoy.units[0]
    status = unit.apply_damage(3)
    assert status == -1
    assert unit.is_damaged()


def test_defend_soak_increments():
    from sixtyfivekmconvoy.core.config import (
        SOAK_AIR_ATROCITIES,
        SOAK_AIR_CASH,
        SOAK_GROUND_ATROCITIES,
        SOAK_GROUND_CASH,
        SOAK_SABOTAGE_ATROCITIES,
        SOAK_SABOTAGE_CASH,
    )
    from sixtyfivekmconvoy.core.constants import AttackType

    players = [Player(i) for i in range(2)]
    convoy = Convoy(players)

    ground = convoy.units[1]
    ground.resolve_defend(AttackType.GROUND)
    cash_before = ground.player.total_cash
    atro_before = ground.atrocities
    msg = convoy.apply_damage(1, unit=ground, attack_type=AttackType.GROUND)
    assert "Defense" in msg
    assert ground.player.total_cash == cash_before + SOAK_GROUND_CASH
    assert ground.atrocities == atro_before + SOAK_GROUND_ATROCITIES

    air = convoy.units[2]
    air.resolve_defend(AttackType.AIR)
    cash_before = air.player.total_cash
    atro_before = air.atrocities
    msg = convoy.apply_damage(1, unit=air, attack_type=AttackType.AIR)
    assert "Defense" in msg
    assert air.player.total_cash == cash_before + SOAK_AIR_CASH
    assert air.atrocities == atro_before + SOAK_AIR_ATROCITIES

    sabotage = convoy.units[0]
    sabotage.resolve_defend(AttackType.SABOTAGE)
    cash_before = sabotage.player.total_cash
    atro_before = sabotage.atrocities
    msg = convoy.apply_damage(1, unit=sabotage, attack_type=AttackType.SABOTAGE)
    assert "Defense" in msg
    assert sabotage.player.total_cash == cash_before + SOAK_SABOTAGE_CASH
    assert sabotage.atrocities == atro_before + SOAK_SABOTAGE_ATROCITIES


def test_promote_requires_matching_officer_troop_type():
    from sixtyfivekmconvoy.core import actions as action_mod
    from sixtyfivekmconvoy.core.cards import OFFICER_CATALOG
    from sixtyfivekmconvoy.core.constants import ActionName
    from sixtyfivekmconvoy.core.engine import GameEngine
    from sixtyfivekmconvoy.core.models import UnitType

    # Letter sets from CSV troop_type
    assert action_mod.officer_troop_letters(OFFICER_CATALOG[0]) == {"P", "I", "L"}  # A
    assert action_mod.officer_troop_letters(OFFICER_CATALOG[1]) == {"I", "P"}  # IP
    assert action_mod.officer_troop_letters(OFFICER_CATALOG[4]) == {"L"}  # L
    assert action_mod.officer_troop_letters(OFFICER_CATALOG[6]) == {"I"}  # I

    engine = GameEngine()
    engine.reset(num_players=2, seed=7)
    # Bypass setup placement: seat a convoy with known troop types.
    engine.convoy = Convoy(engine.players)
    for u in engine.convoy.units:
        u.engine = engine

    engine.officer_queue.cards_and_visibilities.clear()
    seq_for_l = next(
        seq for seq, oid in engine.officer_id_mapping.items() if oid == 4
    )
    engine.officer_queue.put_card(seq_for_l, visible=True)

    logistics = next(u for u in engine.convoy.units if u.unittype == UnitType.LOGISTICS)
    panzer = next(u for u in engine.convoy.units if u.unittype == UnitType.PANZER)

    promote = {
        "name": "Promote",
        "action_name": ActionName.PROMOTE,
        "action_modifier": 0,
        "zone": "ABCE",
        "troop_type": "A",
        "cost": "0",
        "tire": 0,
        "intoxicate": 0,
        "limits": {"P": "ABCE", "I": "ABCE", "L": "ABCE"},
    }
    assert action_mod.matching_officer_queue_indices(engine, logistics) == [0]
    assert action_mod.matching_officer_queue_indices(engine, panzer) == []
    assert action_mod.is_action_possible(engine, logistics.index(), promote)
    assert not action_mod.is_action_possible(engine, panzer.index(), promote)
    why = action_mod.why_action_impossible(engine, panzer.index(), promote)
    assert any("no officer" in r for r in why)


def test_defence_actions_set_matching_attack_letters():
    from sixtyfivekmconvoy.core import actions as action_mod
    from sixtyfivekmconvoy.core.constants import ActionName, AttackType

    assert action_mod.ATTACK_TYPE_BY_DEFENCE_ACTION[ActionName.HUMAN_SHIELDS] == AttackType.AIR
    assert action_mod.ATTACK_TYPE_BY_DEFENCE_ACTION[ActionName.DEFEND] == AttackType.GROUND
    assert action_mod.ATTACK_TYPE_BY_DEFENCE_ACTION[ActionName.PATROL] == AttackType.SABOTAGE
    assert ActionName.HUMAN_SHIELDS not in ActionName.UNIMPLEMENTED
    assert ActionName.PATROL not in ActionName.UNIMPLEMENTED


def test_token_cost_formulas_from_csv_strings():
    players = [Player(0), Player(1)]
    convoy = Convoy(players)
    unit = convoy.units[0]
    unit.tired = 2
    unit.under_influence = 1
    unit.atrocities = 3

    assert action_mod.get_cost(unit, "1/T+1/U+1/A") == 2 + 1 + 3
    assert action_mod.get_cost(unit, "1/T+1/U") == 2 + 1
    assert action_mod.get_cost(unit, "1/T+2/U+1/A") == 2 + 2 + 3
    # Legacy shorthand
    assert action_mod.get_cost(unit, "T") == 2 + 1 + 3
    unit.under_influence = 0
    assert action_mod.get_cost(unit, "1/T+2/U+1/A") == 2 + 3
    # Flat numeric costs unchanged
    assert action_mod.get_cost(unit, "1") == 1
    assert action_mod.get_cost(unit, 0) == 0


def test_format_cost_follows_csv_formula():
    from sixtyfivekmconvoy.core.card_display import (
        SYMBOL_ATROCITY,
        SYMBOL_INFLUENCE,
        SYMBOL_TIREDNESS,
        format_cost,
        format_effects,
        format_face,
        format_reward_label,
    )
    from sixtyfivekmconvoy.core.cards import ACTION_CATALOG
    from sixtyfivekmconvoy.core.constants import ActionName

    assert format_cost("1/T+1/U+1/A") == (
        f"🂠 {SYMBOL_TIREDNESS}{SYMBOL_INFLUENCE}{SYMBOL_ATROCITY}"
    )
    assert format_cost("1/T+1/U") == f"🂠 {SYMBOL_TIREDNESS}{SYMBOL_INFLUENCE}"
    assert SYMBOL_ATROCITY not in format_cost("1/T+1/U")
    scout = format_cost("1/T+2/U+1/A")
    assert scout == f"🂠 {SYMBOL_TIREDNESS}{SYMBOL_ATROCITY} + 🂠🂠 {SYMBOL_INFLUENCE}"

    assert format_effects(1, 0) == f"→ +{SYMBOL_TIREDNESS}"
    assert format_effects(2, 1) == f"→ +2{SYMBOL_TIREDNESS}  → {SYMBOL_INFLUENCE}"
    assert format_reward_label(2, 1) == f"(+2 +{SYMBOL_ATROCITY})"

    scout_faces = [
        a for card in ACTION_CATALOG.values() for a in card.actions if a.action_name == "scout"
    ]
    assert scout_faces
    assert all(a.cost == "1/T+2/U+1/A" for a in scout_faces)
    face = format_face(scout_faces[0])
    assert face["cost"] == scout
    assert face["reward"]["label"].startswith("(+")

    shields = format_face(
        {
            "name": "Ihmiskilpiä",
            "action_name": ActionName.HUMAN_SHIELDS,
            "action_modifier": 0,
            "cost": "1/T+1/U+1/A",
            "tire": 1,
            "intoxicate": 0,
            "troop_type": "A",
            "zone": "ABCE",
        }
    )
    assert shields["reward"]["cash"] > 0
    assert shields["reward"]["atrocities"] == 1
    assert shields["reward"]["label"].startswith("(")

    attack_faces = [
        a for card in ACTION_CATALOG.values() for a in card.actions if a.action_name == "attack"
    ]
    assert attack_faces
    assert all(a.cost == "1/T+1/U" for a in attack_faces)


def test_unit_log_label_uses_color_and_type():
    players = [Player(0), Player(1), Player(2)]
    convoy = Convoy(players)
    # Player 2's first unit — color "blue"
    unit = next(u for u in convoy.units if u.player.number == 2)
    label = action_mod.unit_log_label(unit)
    assert label.startswith("blue ")
    assert any(
        tok in label
        for tok in ("panssarit", "jalkaväki", "huolto", "panzer", "infantry", "logistics")
    )


def test_retreat_identity_loop_tires_each_unit_once():
    """Regression: index-based loops re-resolved the retreating unit and skipped the next."""
    players = [Player(0), Player(1)]
    convoy = Convoy(players)
    u0, u1 = convoy.units[0], convoy.units[1]
    assert u0.can_overtake(-1) and u1.can_overtake(-1)

    # Correct: track by identity (as engine now does)
    for unit in [u0, u1]:
        convoy.move_unit(unit.index(), -1)
        unit.tire()

    assert u0.tired == 1
    assert u1.tired == 1
    assert u0.under_influence == 0
    assert u1.under_influence == 0


def test_stale_index_loop_double_tires_first_unit():
    """Document the old bug: after retreat, index 1 points at the unit that just moved."""
    players = [Player(0), Player(1)]
    convoy = Convoy(players)
    u0, u1 = convoy.units[0], convoy.units[1]
    original_second = u1

    for unit_idx in [0, 1]:
        unit = convoy.units[unit_idx]
        convoy.move_unit(unit_idx, -1)
        unit.tire()

    # First unit was processed twice; the original second unit never tired.
    assert u0.tired == 2
    assert original_second.tired == 0


def test_pillage_keeps_queue_populated_during_choice():
    from sixtyfivekmconvoy.core.constants import ChoiceType

    engine = GameEngine()
    engine.reset(num_players=2, seed=1)
    engine.pillage_queue = CardQueue(engine.pillage_deck)
    for _ in range(3):
        engine.pillage_queue.put_card(engine.pillage_deck.get_card(), visible=False)

    unit = engine._unit_pool[0]
    unit.convoy = engine.convoy
    unit.engine = engine
    engine.convoy.units = [unit]
    assert unit.index() == 0

    gen = action_mod._resolve_pillage(engine, unit, modifier=0)
    try:
        req = next(gen)
    except StopIteration as e:
        raise AssertionError("expected a pillage choice") from e

    assert req.choicetype == ChoiceType.CHOOSE_PILLAGE_CARD
    assert len(req.options) >= 1
    # Cards must still sit in the queue (face-down) while the player chooses
    assert len(engine.pillage_queue) >= len(req.options)
    assert all(
        not vis for _, vis in engine.pillage_queue.cards_and_visibilities[: len(req.options)]
    )
    assert req.payload and req.payload.get("pillage_cards")


def test_seeded_random_episode_terminates():
    engine = GameEngine()
    engine.reset(num_players=3, seed=42)
    agents = {pid: RandomAgent(seed=100 + i) for i, pid in enumerate(engine.agent_ids())}
    steps = 0
    while not engine.terminal:
        pending = engine.pending_choice()
        assert pending is not None
        legal = engine.legal_actions()
        assert legal, f"No legal actions for {pending}"
        choice = agents[pending.player_id].choose(legal)
        result = engine.step(choice)
        steps += 1
        assert steps < 20_000
        if result.terminal:
            break
    assert engine.terminal
    ranking = engine.winner_ranking()
    assert ranking is not None
    assert len(ranking) == 3
    assert engine.stats.rounds >= 0
