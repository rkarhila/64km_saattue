"""League registry + optional short self-play smoke (requires torch)."""

from __future__ import annotations

import json

import pytest

torch = pytest.importorskip("torch")

from sixtyfivekmconvoy.env.spaces import observation_size
from sixtyfivekmconvoy.rl.agent import RLAgent
from sixtyfivekmconvoy.rl.league import League
from sixtyfivekmconvoy.rl.policy import MaskedActorCritic
from sixtyfivekmconvoy.rl.ppo import PPOConfig
from sixtyfivekmconvoy.rl.selfplay import SelfPlayConfig, SelfPlayTrainer


def test_league_add_branch_lineage(tmp_path):
    league = League(tmp_path / "league")
    model = MaskedActorCritic(
        obs_dim=observation_size(3), hidden=32, n_layers=1, lstm_hidden=32
    )
    root = league.add(model, name="root", tags=["init"])
    child = league.branch(root.id, name="fork-a", tags=["style-a"])
    assert child.parent_id == root.id
    assert (tmp_path / "league" / child.path).exists()

    loaded = league.load_model(child.id)
    assert isinstance(loaded, MaskedActorCritic)
    assert loaded.recurrent
    chain = league.lineage(child.id)
    assert [e.name for e in chain] == ["root", "fork-a"]

    league.promote(child.id, tag="playtest")
    assert "playtest" in league.get(child.id).tags

    rows = league.list(tag="playtest")
    assert len(rows) == 1
    assert rows[0].id == child.id

    exported = league.export_bot(child.id, tmp_path / "bot.pt")
    assert exported.exists()
    bot = RLAgent.from_checkpoint(exported)
    import numpy as np

    obs = np.zeros(observation_size(3), dtype=np.float32)
    mask = np.zeros(256, dtype=np.float32)
    mask[0] = 1
    action = bot.act(obs, [[0]], action_mask=mask)
    assert action == 0
    bot.reset_memory()


def test_league_sample_opponents(tmp_path):
    import numpy as np

    league = League(tmp_path / "league")
    model = MaskedActorCritic(
        obs_dim=observation_size(3), hidden=32, n_layers=1, lstm_hidden=32
    )
    a = league.add(model, name="a")
    b = league.branch(a.id, name="b")
    league.add(model, name="c", parent_id=b.id)
    rng = np.random.default_rng(0)
    ids = league.sample_opponent_ids(rng, k=5)
    assert len(ids) == 5
    assert set(ids) <= {e.id for e in league.list()}


def test_selfplay_short_train(tmp_path):
    league = League(tmp_path / "league")
    cfg = SelfPlayConfig(
        num_players=2,
        seed=1,
        total_timesteps=400,
        rollout_steps=128,
        checkpoint_every_steps=200,
        eval_every_steps=200,
        eval_episodes=2,
        hidden=32,
        n_layers=1,
        lstm_hidden=32,
        lstm_layers=2,
        device="cpu",
        ppo=PPOConfig(epochs=1, minibatch_size=64, lr=1e-3, bptt_len=8),
    )
    logs: list[str] = []
    trainer = SelfPlayTrainer(
        league,
        cfg,
        learner_name="smoke",
        log_fn=logs.append,
    )
    result = trainer.train()
    assert result["steps"] >= 400
    assert result["final_id"] in league.entries
    assert len(league.list()) >= 2
    registry = json.loads((tmp_path / "league" / "league.json").read_text())
    assert registry["entries"]
