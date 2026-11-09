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
    assert convoy.category_after_defence(ground, 10, AttackType.GROUND) == 5
    assert convoy.category_after_defence(ground, 3, AttackType.GROUND) == 1
    assert convoy.category_after_defence(ground, 1, AttackType.GROUND) == 0
    assert ground.player.total_cash == cash_before + 3 * SOAK_GROUND_CASH
    assert ground.atrocities == atro_before + 3 * SOAK_GROUND_ATROCITIES

    air = convoy.units[2]
    air.resolve_defend(AttackType.AIR)
    cash_before = air.player.total_cash
    atro_before = air.atrocities
    assert convoy.category_after_defence(air, 5, AttackType.AIR) == 3
    assert air.player.total_cash == cash_before + SOAK_AIR_CASH
    assert air.atrocities == atro_before + SOAK_AIR_ATROCITIES

    sabotage = convoy.units[0]
    sabotage.resolve_defend(AttackType.SABOTAGE)
    cash_before = sabotage.player.total_cash
    atro_before = sabotage.atrocities
    assert convoy.category_after_defence(sabotage, 3, AttackType.SABOTAGE) == 1
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
    assert face["action_name"] == "scout"
    assert "{reveal_mauling_cash}" not in face["help"]["finnish_explanation"]
    assert "1 rahan" in face["help"]["finnish_explanation"]
    assert face["help"]["finnish_title"] == "Tiedustele"

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


def test_import_replays_through_continue_pause():
    from sixtyfivekmconvoy.api.session import SessionManager

    manager = SessionManager()
    session = manager.create(num_players=2, seed=1, pause_after_actions=True)
    human = next(iter(session.human_seats))
    session.apply_human_choice(human, [0, 1, 2])
    reason = session.continue_block_reason(human)
    assert reason
    assert "Jatka" in reason
    assert "Last log line:" in reason
    imported = manager.create_from_state_string(session.get_shareable_state_string())
    assert imported.continue_block_reason(human)


def test_officer_face_matches_action_cost_row():
    from sixtyfivekmconvoy.core.card_display import (
        SYMBOL_OFFICER_DISCARD,
        SYMBOL_PASSIVE,
        SYMBOL_TIREDNESS,
        passive_clues_for,
    )
    from sixtyfivekmconvoy.core.cards import OFFICER_CATALOG

    hatka = OFFICER_CATALOG[9]
    face = hatka.display_face()
    assert face["mode"] == "discard"
    assert face["title"] == hatka.name
    assert face["cost"] == f"2🂠 + {SYMBOL_OFFICER_DISCARD}"
    assert face["effects"] == ""

    spent = OFFICER_CATALOG[6].display_face()
    assert spent["cost"] == SYMBOL_OFFICER_DISCARD
    assert SYMBOL_TIREDNESS in spent["effects"]

    huikka = OFFICER_CATALOG[0].display_face()
    assert huikka["mode"] == "passive"
    assert huikka["effects"] == SYMBOL_PASSIVE
    clues = passive_clues_for([OFFICER_CATALOG[0], OFFICER_CATALOG[1]], "pillage")
    assert [c["name"] for c in clues] == [OFFICER_CATALOG[0].name]
    assert passive_clues_for([OFFICER_CATALOG[1]], "attack")


def test_action_help_covers_every_printed_action():
    from sixtyfivekmconvoy.core.card_display import action_help_for, format_face
    from sixtyfivekmconvoy.core.cards import ACTION_CATALOG

    seen = set()
    for card in ACTION_CATALOG.values():
        for action in card.actions:
            seen.add(action.action_name)
            face = format_face(action)
            assert face["help"]["finnish_explanation"]
            assert face["help"]["english_explanation"]
    assert "human shields" in seen
    smoke = action_help_for("wait", "Röökitauko")
    drink = action_help_for("wait", "Juomatauko")
    assert smoke["finnish_title"] == "Röökitauko"
    assert drink["finnish_title"] == "Juomatauko"
    suggested = action_help_for("attack", "Tietokone ehdottaa: Hyökkää!")
    assert suggested["finnish_title"] == "Hyökkää"
    assert "{attack_cash}" not in suggested["finnish_explanation"]
    assert "2 rahaa" in suggested["finnish_explanation"]
    renamed = action_help_for("rest", "Uusi: Lepää")
    assert renamed["finnish_title"] == "Lepää"


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


def test_pillage_sober_chooses_front_or_revealed():
    from sixtyfivekmconvoy.core.constants import ChoiceType

    engine = GameEngine()
    engine.reset(num_players=2, seed=1)
    engine.pillage_queue = CardQueue(engine.pillage_deck)
    hidden = engine.pillage_deck.get_card()
    revealed = engine.pillage_deck.get_card()
    hidden_back = engine.pillage_deck.get_card()
    engine.pillage_queue.put_card(hidden, visible=False)
    engine.pillage_queue.put_card(revealed, visible=True)
    engine.pillage_queue.put_card(hidden_back, visible=False)

    unit = engine._unit_pool[0]
    unit.convoy = engine.convoy
    unit.engine = engine
    unit.under_influence = 0
    engine.convoy.units = [unit]

    gen = action_mod._resolve_pillage(engine, unit, modifier=3)
    req = next(gen)
    assert req.choicetype == ChoiceType.CHOOSE_PILLAGE_CARD
    assert req.options == [hidden, revealed]
    assert len(engine.pillage_queue) == 3

    try:
        gen.send([revealed])
        raise AssertionError("expected StopIteration")
    except StopIteration as stop:
        taken = stop.value
    assert taken == [engine.pillage_deck.describe(revealed)]
    assert [cid for cid, _ in engine.pillage_queue.cards_and_visibilities] == [
        hidden,
        hidden_back,
    ]


def test_pillage_drunk_takes_front_card():
    engine = GameEngine()
    engine.reset(num_players=2, seed=1)
    engine.pillage_queue = CardQueue(engine.pillage_deck)
    front = engine.pillage_deck.get_card()
    revealed = engine.pillage_deck.get_card()
    engine.pillage_queue.put_card(front, visible=False)
    engine.pillage_queue.put_card(revealed, visible=True)

    unit = engine._unit_pool[0]
    unit.convoy = engine.convoy
    unit.engine = engine
    unit.under_influence = 1
    engine.convoy.units = [unit]

    gen = action_mod._resolve_pillage(engine, unit, modifier=0)
    try:
        next(gen)
        raise AssertionError("drunk pillage should not ask")
    except StopIteration as stop:
        taken = stop.value
    assert taken == [engine.pillage_deck.describe(front)]
    assert engine.pillage_queue.cards_and_visibilities[0][0] == revealed


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
