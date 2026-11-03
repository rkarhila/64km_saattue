#!/usr/bin/env python3
"""Train the GTX 1050 transformer for 4 hours.

FP32 network for compute capability 6.1: transformer width 256, 4 heads
(head size 64), feedforward 1024, 4 transformer layers, encoder width 512,
decision width 256. About 4.5M parameters.

Run from ``dev/`` in the environment that has the CUDA 12.6 PyTorch wheel::

    PYTHONPATH=src python scripts/train_4h.py

Checkpoints, ``train_4h.jsonl`` (one row per rollout), and ``train_4h.json``
(the final totals) are written under ``runs/league_tf4h/``. The jsonl rows
split each rollout into game-process time, forward-pass time, PPO update
time, and eval time, and record episode length, return, losses, and GPU
memory. The hour limit stops training after the rollout that crosses it.
The step cap is only a backstop.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from sixtyfivekmconvoy.rl.league import League
from sixtyfivekmconvoy.rl.ppo import PPOConfig
from sixtyfivekmconvoy.rl.selfplay import SelfPlayConfig, SelfPlayTrainer


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--league", default="runs/league_tf4h")
    p.add_argument("--name", default="tf1050")
    p.add_argument("--hours", type=float, default=4.0)
    p.add_argument("--device", default="cuda")
    p.add_argument("--players", type=int, default=3)
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--num-envs", type=int, default=8)
    p.add_argument("--minibatch-size", type=int, default=256)
    p.add_argument("--rollout-steps", type=int, default=2048)
    p.add_argument("--lr", type=float, default=3e-4)
    p.add_argument("--hidden", type=int, default=512)
    p.add_argument("--n-layers", type=int, default=2)
    p.add_argument("--width", type=int, default=256)
    p.add_argument("--d-model", type=int, default=256)
    p.add_argument("--nhead", type=int, default=4)
    p.add_argument("--ff", type=int, default=1024)
    p.add_argument("--tf-layers", type=int, default=4)
    p.add_argument("--checkpoint-every", type=int, default=20_000)
    p.add_argument("--eval-every", type=int, default=20_000)
    p.add_argument("--eval-episodes", type=int, default=8)
    p.add_argument(
        "--timesteps-cap",
        type=int,
        default=100_000_000,
        help="Environment-step cap. The hour limit stops the run first.",
    )
    return p


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    if str(args.device).startswith("cuda"):
        import torch

        if not torch.cuda.is_available():
            raise SystemExit(
                "CUDA is not available in this Python. "
                "Activate the GPU environment, then rerun this script."
            )

    league = League(args.league)
    cfg = SelfPlayConfig(
        num_players=args.players,
        seed=args.seed,
        total_timesteps=args.timesteps_cap,
        max_seconds=float(args.hours) * 3600.0,
        rollout_steps=args.rollout_steps,
        checkpoint_every_steps=args.checkpoint_every,
        eval_every_steps=args.eval_every,
        eval_episodes=args.eval_episodes,
        hidden=args.hidden,
        n_layers=args.n_layers,
        width=args.width,
        d_model=args.d_model,
        nhead=args.nhead,
        dim_feedforward=args.ff,
        tf_layers=args.tf_layers,
        num_envs=args.num_envs,
        device=args.device,
        log_path=str(Path(args.league) / "train_4h.jsonl"),
        ppo=PPOConfig(lr=args.lr, minibatch_size=args.minibatch_size),
    )
    trainer = SelfPlayTrainer(league, cfg, learner_name=args.name)
    result = trainer.train()
    summary = {
        "final_id": result["final_id"],
        "steps": result["steps"],
        "learner_steps": result["learner_steps"],
        "episodes": result["episodes"],
        "elapsed_sec": result["elapsed_sec"],
        "steps_per_sec": result["steps_per_sec"],
        "learner_per_sec": result["learner_per_sec"],
        "time_sim_sec": result["time_sim_sec"],
        "time_infer_sec": result["time_infer_sec"],
        "time_update_sec": result["time_update_sec"],
        "time_eval_sec": result["time_eval_sec"],
        "time_other_sec": result["time_other_sec"],
        "log": str((Path(args.league) / "train_4h.jsonl").resolve()),
        "league": str(Path(args.league).resolve()),
    }
    out = Path(args.league) / "train_4h.json"
    out.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
