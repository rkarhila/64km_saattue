"""ConvoyEnv reward modes: win + PP/cash proxies."""

from __future__ import annotations

import pytest

pytest.importorskip("pettingzoo")

from sixtyfivekmconvoy.env.convoy_env import ConvoyEnv


def test_win_mode_rewards_pp_and_cash_deltas():
    env = ConvoyEnv(
        num_players=2,
        seed=0,
        reward_mode="win",
        pp_reward=0.25,
        cash_reward=0.05,
        win_reward=1.0,
        lose_reward=0.0,
    )
    env.reset(seed=0)
    p0 = env.engine.players[0]
    # Simulate bookkeeping-style gains without playing out a full game.
    p0.promotion_points = 1
    p0.total_cash = 4
    env._assign_win_mode_rewards(terminal=False)
    assert env.rewards["player_0"] == pytest.approx(0.25 + 0.05 * 4)
    assert env.rewards["player_1"] == pytest.approx(0.0)
    assert env._cumulative_rewards["player_0"] == pytest.approx(0.25 + 0.2)

    # Second call with no further gains → 0 proxy.
    env._assign_win_mode_rewards(terminal=False)
    assert env.rewards["player_0"] == pytest.approx(0.0)


def test_win_mode_terminal_bonus_for_first_place():
    env = ConvoyEnv(
        num_players=2,
        seed=1,
        reward_mode="win",
        pp_reward=0.0,
        cash_reward=0.0,
        win_reward=1.0,
        lose_reward=-0.5,
    )
    env.reset(seed=1)
    env.engine.players[0].promotion_points = 3
    env.engine.players[0].total_cash = 10
    env.engine.players[1].promotion_points = 1
    env.engine.players[1].total_cash = 99
    env.engine.ranking = env.engine._compute_ranking()
    env.engine.terminal = True
    env._snapshot_score_baselines()  # no proxy deltas
    env._assign_win_mode_rewards(terminal=True)
    assert env.engine.winner_ranking()[0]["number"] == 0
    assert env.rewards["player_0"] == pytest.approx(1.0)
    assert env.rewards["player_1"] == pytest.approx(-0.5)


def test_win_mode_penalises_frustration_and_keeps_the_other_shaping():
    env = ConvoyEnv(num_players=2, seed=0, reward_mode="win", pp_reward=0.0, cash_reward=0.0)
    env.reset(seed=0)
    env.engine.note_shaping("action_ok", 0, action="rest")
    env.engine.note_shaping("frustrated", 0)
    env.engine.note_shaping("rest_relief", 0)
    env.engine.note_shaping("mauling_dodge", 0)
    env.engine.note_shaping("mauling_damage", 1, damage=4)
    env._assign_win_mode_rewards(terminal=False)
    assert env.rewards["player_0"] == pytest.approx(
        -env.frustration_penalty + env.rest_relief_reward + env.mauling_dodge_reward
    )
    assert env.rewards["player_1"] == pytest.approx(-env.mauling_damage_penalty * 4)
    assert env.engine.shaping_events == []


def test_one_cash_outweighs_every_shaping_term():
    env = ConvoyEnv(num_players=2, seed=0)
    cash = env.cash_reward
    assert env.pp_reward > cash > 0
    assert cash > env.rest_relief_reward
    assert cash > env.mauling_dodge_reward
    assert cash > env.frustration_penalty
    assert cash > env.action_reward
    # Hit categories are 1, 3, 5, and 10.
    assert cash > 10 * env.mauling_damage_penalty
