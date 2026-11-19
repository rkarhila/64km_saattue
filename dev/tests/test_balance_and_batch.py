"""Effective PPO batch and winner-stat aggregation."""

import time
from types import SimpleNamespace

import numpy as np

from sixtyfivekmconvoy.env.convoy_env import ConvoyEnv
from sixtyfivekmconvoy.rl.balance_stats import summarize
from sixtyfivekmconvoy.rl.buffer import RolloutBuffer
from sixtyfivekmconvoy.rl.policy import MaskedActorCritic
from sixtyfivekmconvoy.rl.ppo import PPOConfig, PPOTrainer
from sixtyfivekmconvoy.rl.selfplay import SelfPlayTrainer


def test_grad_accum_steps_once_per_group():
    policy = MaskedActorCritic(
        hidden=32,
        n_layers=1,
        width=32,
        d_model=32,
        nhead=4,
        dim_feedforward=64,
        tf_layers=1,
        num_players=2,
    )
    trainer = PPOTrainer(
        policy,
        PPOConfig(epochs=1, minibatch_size=4, grad_accum_steps=2, lr=1e-3),
        device="cpu",
    )
    steps = {"n": 0}
    real = trainer.optimizer.step

    def wrapped(*args, **kwargs):
        steps["n"] += 1
        return real(*args, **kwargs)

    trainer.optimizer.step = wrapped
    buf = RolloutBuffer(policy.obs_dim, policy.n_actions, capacity=8)
    obs = np.zeros(policy.obs_dim, dtype=np.float32)
    mask = np.zeros(policy.n_actions, dtype=np.float32)
    mask[0] = 1.0
    rows = []
    for i in range(8):
        rows.append(
            {
                "obs": obs,
                "mask": mask,
                "reward": 0.0,
                "value": 0.0,
                "logprob": 0.0,
                "done": i == 7,
                "action_idx": 0,
            }
        )
    buf.extend_episode(rows)
    trainer.update(buf)
    # 8 rows, microbatch 4, accumulate 2 → one Adam step.
    assert steps["n"] == 1


def test_learning_rate_falls_linearly_to_the_floor():
    policy = MaskedActorCritic(
        hidden=32,
        n_layers=1,
        width=32,
        d_model=32,
        nhead=4,
        dim_feedforward=64,
        tf_layers=1,
        num_players=2,
    )
    updater = PPOTrainer(policy, PPOConfig(lr=1e-3), device="cpu")
    holder = SimpleNamespace(
        config=SimpleNamespace(
            ppo=SimpleNamespace(lr=1e-3),
            lr_end=3e-4,
            max_seconds=100.0,
        ),
        trainer=updater,
    )
    now = time.time()
    assert abs(SelfPlayTrainer._apply_lr_schedule(holder, now) - 1e-3) < 1e-6
    mid = SelfPlayTrainer._apply_lr_schedule(holder, now - 50)
    assert abs(mid - 6.5e-4) < 1e-6
    floor = SelfPlayTrainer._apply_lr_schedule(holder, now - 200)
    assert abs(floor - 3e-4) < 1e-12
    assert abs(updater.optimizer.param_groups[0]["lr"] - 3e-4) < 1e-12


def test_reset_can_change_player_count():
    env = ConvoyEnv(num_players=5, seed=1, fast=True)
    env.reset(seed=1, options={"num_players": 2})
    assert env.num_players == 2
    assert len(env.engine.players) == 2
    assert env.observe("player_0").shape[0] == env.observe("player_1").shape[0]


def test_summary_counts_winner_fields():
    summary = summarize(
        [
            {
                "end_reason": "cash",
                "rounds": 4,
                "start_positions": [{"unit": "panzer", "index": 0}],
                "plays": [
                    {"card_id": 3, "card_name": "Hyökkää", "action_name": "attack"}
                ],
                "payments": [{"cards": [{"id": 8, "name": "Lepo"}]}],
                "cards_for_money": [{"cards": [{"id": 9, "name": "Poista"}]}],
                "income": {"attack": 2, "retire cards": 2},
                "promotion_income": {"attack": 2},
            }
        ]
    )
    assert summary["games"] == 1
    assert summary["rounds"] == 4
    assert summary["end_conditions"]["cash"] == 1
    assert summary["start_positions"]["panzer@0"] == 1
    assert summary["income"]["retire cards"] == 2
    assert summary["promotion_round_income"]["attack"] == 2
    assert "3|Hyökkää|attack" in summary["card_actions"]
