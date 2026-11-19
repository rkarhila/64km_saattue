#!/usr/bin/env python3
"""Train the retire-cards rules for 6 hours, then log winner statistics.

Profile ``retire``: cashing four cards removes them from the game and pays
1 cash. PPO minibatches are 128, and eight of them are accumulated before
each Adam step (effective batch 1024). A minibatch of 512 does not fit the
128-token transformer on a 3 GB card. Every training episode draws 2, 3,
4, or 5 players.

After training, the final policy plays until 10 000 completed rounds have
been recorded at each player count (40 000 rounds in total). One JSON
object per game is appended to ``play_games.jsonl``. ``play_summary.json``
holds the aggregated winner statistics:

1. starting unit positions
2. card played and the action chosen from it
3. cards spent to pay for actions
4. cards removed for money
5. income sources over the whole game
6. income sources on rounds that awarded a promotion point
7. end condition and how many rounds the game lasted

If the league already has a checkpoint for this run, training loads the
newest one and keeps its step count. Win rate is measured over 32 games.
Adam moments start over; only the network weights are stored.

Run on the GTX 1050 machine, from ``dev/``::

    PYTHONPATH=src python scripts/train_6h_retire.py
"""

from __future__ import annotations

import os

os.environ["CONVOY_CONFIG"] = "retire"

import argparse
import json
from pathlib import Path

import numpy as np


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--league", default="runs/league_retire6h")
    p.add_argument("--name", default="retire6h")
    p.add_argument("--hours", type=float, default=6.0)
    p.add_argument("--device", default="cuda")
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--num-envs", type=int, default=8)
    p.add_argument("--minibatch-size", type=int, default=128)
    p.add_argument("--grad-accum-steps", type=int, default=8)
    p.add_argument("--rollout-steps", type=int, default=2048)
    p.add_argument("--rounds", type=int, default=10_000)
    p.add_argument("--eval-episodes", type=int, default=32)
    p.add_argument("--lr", type=float, default=3e-4)
    p.add_argument(
        "--lr-end",
        type=float,
        default=None,
        help="If set, the learning rate falls linearly from --lr to this value over --hours.",
    )
    p.add_argument("--player-counts", type=int, nargs="+", default=[2, 3, 4, 5])
    p.add_argument("--skip-train", action="store_true")
    p.add_argument(
        "--checkpoint",
        default="",
        help="League id or name to play. Defaults to the checkpoint training just wrote.",
    )
    return p


def train(args: argparse.Namespace) -> str:
    import torch

    from sixtyfivekmconvoy.rl.league import League
    from sixtyfivekmconvoy.rl.ppo import PPOConfig
    from sixtyfivekmconvoy.rl.selfplay import SelfPlayConfig, SelfPlayTrainer

    if str(args.device).startswith("cuda") and not torch.cuda.is_available():
        raise SystemExit(
            "CUDA is not available in this Python. "
            "Activate the GPU environment, then rerun this script."
        )
    league = League(args.league)
    counts = tuple(int(n) for n in args.player_counts)
    resumed = _latest_named(league, args.name)
    policy = None
    parent_id = None
    if resumed is not None:
        policy = league.load_model(resumed.id, map_location=args.device)
        parent_id = resumed.id
        print(
            f"resume {resumed.id} ({resumed.name}) "
            f"step={resumed.step} episodes={resumed.episodes}",
            flush=True,
        )
    cfg = SelfPlayConfig(
        num_players=max(counts),
        player_counts=counts,
        seed=args.seed,
        total_timesteps=100_000_000,
        max_seconds=float(args.hours) * 3600.0,
        rollout_steps=args.rollout_steps,
        checkpoint_every_steps=20_000,
        eval_every_steps=20_000,
        eval_episodes=int(args.eval_episodes),
        hidden=512,
        n_layers=2,
        width=256,
        d_model=256,
        nhead=4,
        dim_feedforward=1024,
        tf_layers=4,
        num_envs=args.num_envs,
        max_cycles=200_000,
        device=args.device,
        log_path=str(Path(args.league) / "train_6h.jsonl"),
        lr_end=args.lr_end,
        ppo=PPOConfig(
            lr=float(args.lr),
            minibatch_size=args.minibatch_size,
            grad_accum_steps=args.grad_accum_steps,
        ),
    )
    trainer = SelfPlayTrainer(
        league,
        cfg,
        policy=policy,
        learner_name=args.name,
        parent_id=parent_id,
    )
    if resumed is not None:
        trainer.global_step = int(resumed.step)
        trainer.episodes = int(resumed.episodes)
    result = trainer.train()
    summary = {
        "final_id": result["final_id"],
        "steps": result["steps"],
        "learner_steps": result["learner_steps"],
        "episodes": result["episodes"],
        "elapsed_sec": result["elapsed_sec"],
        "steps_per_sec": result["steps_per_sec"],
        "config": "retire",
        "eval_episodes": int(args.eval_episodes),
        "resumed_from": None
        if resumed is None
        else {
            "id": resumed.id,
            "name": resumed.name,
            "step": resumed.step,
            "episodes": resumed.episodes,
        },
        "minibatch_size": args.minibatch_size,
        "grad_accum_steps": args.grad_accum_steps,
        "lr": float(args.lr),
        "lr_end": args.lr_end,
        "player_counts": list(counts),
        "league": str(Path(args.league).resolve()),
    }
    out = Path(args.league) / "train_6h.json"
    out.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return str(result["final_id"])


def _latest_named(league, name: str):
    """Newest league entry for this run, by step then creation time."""
    matches = [
        entry
        for entry in league.list()
        if entry.name == name or entry.name.startswith(f"{name}-")
    ]
    if not matches:
        return None
    return max(matches, key=lambda entry: (entry.step, entry.created_at))


def play_player_count(policy, n: int, rounds_target: int, seed0: int, device: str):
    import torch

    from sixtyfivekmconvoy.env.convoy_env import ConvoyEnv
    from sixtyfivekmconvoy.env.spaces import MAX_LEGAL
    from sixtyfivekmconvoy.rl.balance_stats import winner_record

    env = ConvoyEnv(
        num_players=n,
        fast=True,
        balance_trace=True,
        max_cycles=300_000,
        reward_mode="win",
    )
    policy.eval()
    records = []
    total = 0
    game_i = 0
    safety = max(1, rounds_target * 4)
    while total < rounds_target and game_i < safety:
        env.reset(seed=seed0 + game_i)
        guard = 0
        while (
            env.agents
            and not all(env.terminations.values())
            and not all(env.truncations.values())
        ):
            agent = env.agent_selection
            info = env.infos.get(agent) or {}
            spec = info.get("choice_spec") or {}
            obs = env.observe(agent)
            mask = info.get("action_mask")
            if mask is None:
                mask = np.zeros(MAX_LEGAL, dtype=np.float32)
            with torch.no_grad():
                flat_idx, _logp, _value, _picks, choice_vec = policy.act(
                    obs,
                    mask,
                    deterministic=False,
                    options=spec.get("options"),
                    ordered=spec.get("ordered"),
                    num_choices=spec.get("num_choices"),
                )
            if choice_vec:
                env.step(list(choice_vec))
            else:
                env.step(int(flat_idx))
            guard += 1
            if guard > 300_000:
                break
        rec = winner_record(env.engine)
        if rec is None:
            rec = {
                "seed": seed0 + game_i,
                "num_players": n,
                "winner": None,
                "rounds": 1,
                "end_reason": "truncated",
                "start_positions": [],
                "plays": [],
                "payments": [],
                "cards_for_money": [],
                "income": {},
                "promotion_income": {},
            }
        elif not env.engine.terminal:
            rec["end_reason"] = "truncated"
        rec["num_players"] = n
        records.append(rec)
        total += int(rec["rounds"])
        game_i += 1
        if game_i % 25 == 0 or total >= rounds_target:
            print(
                f"players={n} games={game_i} rounds={total}/{rounds_target}",
                flush=True,
            )
    return records


def play(args: argparse.Namespace, checkpoint: str) -> None:
    import torch

    from sixtyfivekmconvoy.rl.balance_stats import summarize
    from sixtyfivekmconvoy.rl.league import League

    device = args.device
    if str(device).startswith("cuda") and not torch.cuda.is_available():
        device = "cpu"
    league = League(args.league)
    policy = league.load_model(checkpoint, map_location=device)
    policy.to(device)
    policy.eval()
    root = Path(args.league)
    root.mkdir(parents=True, exist_ok=True)
    games_path = root / "play_games.jsonl"
    by_count: dict[str, dict] = {}
    with games_path.open("w", encoding="utf-8") as handle:
        for index, n in enumerate(args.player_counts):
            rows = play_player_count(
                policy,
                int(n),
                int(args.rounds),
                seed0=10_000 * (index + 1) + int(args.seed),
                device=device,
            )
            for row in rows:
                handle.write(json.dumps(row) + "\n")
            handle.flush()
            by_count[str(n)] = summarize(rows)
    summary = {
        "checkpoint": checkpoint,
        "config": "retire",
        "rounds_target_per_count": int(args.rounds),
        "by_player_count": by_count,
        "games_log": str(games_path.resolve()),
    }
    out = root / "play_summary.json"
    out.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"summary": str(out.resolve()), "games": str(games_path.resolve())}, indent=2))


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    checkpoint = args.checkpoint
    if not args.skip_train:
        checkpoint = train(args)
    if not checkpoint:
        raise SystemExit("No checkpoint to play. Pass --checkpoint or train first.")
    play(args, checkpoint)


if __name__ == "__main__":
    main()
