#!/usr/bin/env python3
"""Train a fresh retire policy, lengthening the game as the score settles.

Starts from a new network in an empty league. Games are capped at 1 round,
then 3, then 5, and so on by two rounds, up to 25.

For 1, 3 and 5 rounds the number to follow is the learner's cash plus
pillage chips still on its units, averaged over each 32-game eval. Games
are 3 or 4 players. The phase moves on when the mean of the last three
evals is past 2 cash per round and the latest eval has stopped growing
(within half a cash of the better of the two before it). From 7 rounds on,
follow the eval win rate: the last three average at least 0.45 and each is
at least 0.375. See ``rl/curriculum.py``.

The learning rate stays at 3e-4. This machine's sandbox has no CUDA; run it
on the GTX 1050, from ``dev/``::

    PYTHONPATH=src python scripts/train_curriculum.py

A second run needs a new ``--league`` directory. This script never loads an
old checkpoint.
"""

from __future__ import annotations

import os

os.environ["CONVOY_CONFIG"] = "retire"

import argparse
import json
from pathlib import Path

from sixtyfivekmconvoy.rl.curriculum import (
    CASH_PER_ROUND,
    PHASE_MAX,
    PHASE_START,
    cash_phase_ready,
    follows_cash,
    next_round_cap,
    phase_converged,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--league", default="runs/league_curriculum")
    parser.add_argument("--name", default="curriculum")
    parser.add_argument(
        "--hours",
        type=float,
        default=None,
        help="Optional wall-clock stop. Omit to run until the 25-round phase settles.",
    )
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--num-envs", type=int, default=8)
    parser.add_argument("--minibatch-size", type=int, default=128)
    parser.add_argument("--grad-accum-steps", type=int, default=8)
    parser.add_argument("--rollout-steps", type=int, default=2048)
    parser.add_argument("--eval-episodes", type=int, default=32)
    parser.add_argument("--lr", type=float, default=3e-4)
    parser.add_argument("--player-counts", type=int, nargs="+", default=[3, 4])
    return parser


def _watch_phase(trainer, row: dict) -> None:
    rounds = int(trainer.config.max_rounds)
    if follows_cash(rounds):
        cash: list[float] = trainer._phase_cash
        cash.append(float(row.get("eval_cash_mean", 0.0)))
        recent = [round(value, 3) for value in cash[-3:]]
        trainer.log(
            f"phase max_rounds={rounds} cash gate "
            f"eval_cash_mean={cash[-1]:.3f} bar={CASH_PER_ROUND * rounds:.1f} "
            f"last3={recent}"
        )
        ready = cash_phase_ready(cash, rounds)
    else:
        rates: list[float] = trainer._phase_win_rates
        rates.append(float(row["eval_win_rate"]))
        recent = [round(rate, 5) for rate in rates[-3:]]
        trainer.log(
            f"phase max_rounds={rounds} win-rate gate "
            f"eval_win_rate={rates[-1]:.5f} last3={recent}"
        )
        ready = phase_converged(rates)
    if not ready:
        return
    nxt = next_round_cap(rounds, limit=PHASE_MAX)
    if nxt is None:
        trainer.log(
            f"{PHASE_MAX}-round phase settled "
            f"(mean of last three evals >= 0.45). Stopping."
        )
        trainer.stop_requested = True
        return
    trainer.log(
        f"phase settled at {rounds} rounds. "
        f"Next games are capped at {nxt} rounds."
    )
    trainer.config.max_rounds = nxt
    trainer._phase_cash.clear()
    trainer._phase_win_rates.clear()


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
    if league.list():
        raise SystemExit(
            f"{args.league} already has checkpoints. This run starts from a "
            "fresh network. Pass a new --league directory."
        )
    counts = tuple(int(n) for n in args.player_counts)
    max_seconds = None if args.hours is None else float(args.hours) * 3600.0
    cfg = SelfPlayConfig(
        num_players=max(counts),
        player_counts=counts,
        seed=args.seed,
        total_timesteps=100_000_000,
        max_seconds=max_seconds,
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
        max_rounds=PHASE_START,
        device=args.device,
        log_path=str(Path(args.league) / "train_curriculum.jsonl"),
        ppo=PPOConfig(
            lr=float(args.lr),
            minibatch_size=args.minibatch_size,
            grad_accum_steps=args.grad_accum_steps,
        ),
    )
    print(
        f"fresh curriculum from {PHASE_START} to {PHASE_MAX} rounds. "
        f"Through 5 rounds, advance when mean cash passes "
        f"{CASH_PER_ROUND:g} per round and stops growing. "
        f"After that, advance on eval win rate. "
        f"lr={cfg.ppo.lr} cash={cfg.cash_reward} pp={cfg.pp_reward}",
        flush=True,
    )
    trainer = SelfPlayTrainer(league, cfg, learner_name=args.name)
    trainer._phase_cash = []
    trainer._phase_win_rates = []
    trainer.after_eval = _watch_phase
    result = trainer.train()
    summary = {
        "final_id": result["final_id"],
        "steps": result["steps"],
        "learner_steps": result["learner_steps"],
        "episodes": result["episodes"],
        "elapsed_sec": result["elapsed_sec"],
        "steps_per_sec": result["steps_per_sec"],
        "config": "retire",
        "started_from": "fresh",
        "final_max_rounds": cfg.max_rounds,
        "eval_episodes": int(args.eval_episodes),
        "cash_per_round": CASH_PER_ROUND,
        "cash_phase_through": 5,
        "win_mean_at_least": 0.45,
        "win_each_at_least": 0.375,
        "minibatch_size": args.minibatch_size,
        "grad_accum_steps": args.grad_accum_steps,
        "lr": float(args.lr),
        "player_counts": list(counts),
        "league": str(Path(args.league).resolve()),
    }
    out = Path(args.league) / "train_curriculum.json"
    out.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return str(result["final_id"])


def main(argv: list[str] | None = None) -> None:
    train(build_parser().parse_args(argv))


if __name__ == "__main__":
    main()
