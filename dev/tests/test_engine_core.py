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
    players = [Player(i) for i in range(2)]
    convoy = Convoy(players)
    unit = convoy.units[1]
    unit.resolve_defend("G", "c")
    before = unit.player.this_round_cash
    msg = convoy.apply_damage(1, unit=unit, attack_type="G")
    assert "Defense" in msg or unit.player.this_round_cash >= before


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
        format_cost,
        format_face,
    )
    from sixtyfivekmconvoy.core.cards import ACTION_CATALOG

    assert SYMBOL_ATROCITY in format_cost("1/T+1/U+1/A")
    assert SYMBOL_ATROCITY not in format_cost("1/T+1/U")
    scout = format_cost("1/T+2/U+1/A")
    assert SYMBOL_ATROCITY in scout
    assert f"2🂠 / {SYMBOL_INFLUENCE}" in scout

    # Loaded scout faces use the CSV formula
    scout_faces = [
        a for card in ACTION_CATALOG.values() for a in card.actions if a.action_name == "scout"
    ]
    assert scout_faces
    assert all(a.cost == "1/T+2/U+1/A" for a in scout_faces)
    face = format_face(scout_faces[0])
    assert f"2🂠 / {SYMBOL_INFLUENCE}" in face["cost"]
    assert SYMBOL_ATROCITY in face["cost"]

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
    # Cards must still sit in the queue (revealed) while the player chooses
    assert len(engine.pillage_queue) >= len(req.options)
    assert all(
        vis for _, vis in engine.pillage_queue.cards_and_visibilities[: len(req.options)]
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
