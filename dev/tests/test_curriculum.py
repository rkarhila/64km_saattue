"""Round cap and the number that advances the training phase."""

from sixtyfivekmconvoy.agents.random_agent import RandomAgent
from sixtyfivekmconvoy.core.engine import GameEngine
from sixtyfivekmconvoy.core.models import Unit, UnitType
from sixtyfivekmconvoy.rl.curriculum import (
    cash_phase_ready,
    cash_with_carried_loot,
    follows_cash,
    next_round_cap,
    phase_converged,
)


def test_scored_cash_counts_loot_still_on_the_unit():
    engine = GameEngine()
    engine.reset(num_players=2, seed=1)
    player = engine.players[0]
    player.get_cash(2)
    unit = Unit(player, UnitType.INFANTRY)
    unit.carry = [3, 1, 0]
    engine.convoy.units = [unit]
    assert cash_with_carried_loot(engine, 0) == 6.0
    assert cash_with_carried_loot(engine, 1) == 0.0


def test_short_phases_follow_cash_until_it_passes_two_per_round():
    assert follows_cash(1) and follows_cash(5)
    assert not follows_cash(7)
    assert not cash_phase_ready([1.0, 1.0, 1.0], 1)
    assert not cash_phase_ready([2.5, 3.0, 4.0], 1)
    assert not cash_phase_ready([2.5, 3.0, 1.0], 1)
    assert cash_phase_ready([2.5, 3.0, 2.4], 1)
    # Exactly 2 per round has not passed the bar.
    assert not cash_phase_ready([6.0, 6.0, 6.0], 3)
    assert cash_phase_ready([6.5, 8.0, 7.0], 3)


def test_phase_advances_on_a_stable_win_rate_above_chance():
    assert not phase_converged([0.50, 0.50])
    assert phase_converged([0.50, 0.47, 0.44])
    assert phase_converged([0.375, 0.50, 0.50])
    # One spike cannot carry two coin-flips. 0.34 is below the 0.375 floor.
    assert not phase_converged([0.60, 0.34, 0.50])
    # Tight, but only the fair-table rate of about 0.32.
    assert not phase_converged([0.34, 0.31, 0.33])
    assert next_round_cap(1) == 3
    assert next_round_cap(23) == 25
    assert next_round_cap(25) is None


def test_one_round_cap_ends_after_the_opening_round():
    engine = GameEngine()
    engine.reset(num_players=2, seed=3, max_rounds=1)
    agents = {
        pid: RandomAgent(seed=10 + i) for i, pid in enumerate(engine.agent_ids())
    }
    steps = 0
    while not engine.terminal:
        pending = engine.pending_choice()
        assert pending is not None
        engine.step(agents[pending.player_id].choose(engine.legal_actions()))
        steps += 1
        assert steps < 20_000
    assert engine.end_reason == "max_rounds"
    assert engine.rounds.count == 0
