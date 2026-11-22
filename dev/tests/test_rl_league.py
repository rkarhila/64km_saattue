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
    assert (tmp_path / "league" / root.rules / "config.py").is_file()
    assert (tmp_path / "league" / child.rules / "cards" / "action.csv").is_file()

    loaded = league.load_model(child.id)
    assert isinstance(loaded, MaskedActorCritic)
    assert loaded.sequence == "transformer"
    assert loaded.recurrent is False
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
        width=32,
        d_model=32,
        nhead=4,
        dim_feedforward=64,
        tf_layers=1,
        num_envs=4,
        device="cpu",
        log_path=str(tmp_path / "league" / "train.jsonl"),
        ppo=PPOConfig(epochs=1, minibatch_size=64, lr=1e-3),
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
    lines = (tmp_path / "league" / "train.jsonl").read_text().splitlines()
    rows = [json.loads(line) for line in lines]
    assert rows[0]["type"] == "start"
    assert rows[-1]["type"] == "end"
    rollouts = [row for row in rows if row["type"] == "rollout"]
    assert rollouts
    assert "sim_sec" in rollouts[0] and "update_sec" in rollouts[0]
    assert result["time_update_sec"] >= 0.0


def test_frozen_opponents_keep_only_one_on_the_training_device(tmp_path, monkeypatch):
    league = League(tmp_path / "league")
    cfg = SelfPlayConfig(
        hidden=32,
        n_layers=1,
        width=32,
        d_model=32,
        nhead=4,
        dim_feedforward=64,
        tf_layers=1,
        rollout_steps=8,
        num_envs=1,
        num_players=2,
        device="cpu",
    )
    trainer = SelfPlayTrainer(league, cfg, learner_name="cache", log_fn=lambda _m: None)
    init_id = league.list()[0].id
    second = league.add(trainer.policy, name="other")
    first = trainer._load_frozen(init_id)
    other = trainer._load_frozen(second.id)
    assert trainer._gpu_frozen_id == second.id
    assert len(trainer._frozen_cache) == 2
    assert next(first.policy.parameters()).device.type == "cpu"
    assert next(other.policy.parameters()).device.type == "cpu"

    calls: list[str] = []
    trainer.device = torch.device("cuda")
    monkeypatch.setattr(torch.cuda, "is_available", lambda: True)
    monkeypatch.setattr(torch.cuda, "empty_cache", lambda: calls.append("empty"))
    trainer._park_frozen()
    assert trainer._gpu_frozen_id is None
    assert calls == ["empty"]
    assert next(other.policy.parameters()).device.type == "cpu"

    trainer._release_frozen_cache()
    assert trainer._frozen_cache == {}
    assert calls == ["empty", "empty"]
