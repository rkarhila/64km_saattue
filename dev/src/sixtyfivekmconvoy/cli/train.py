"""Train a self-play PPO policy into a league of versioned bots."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from sixtyfivekmconvoy.rl.league import League
from sixtyfivekmconvoy.rl.ppo import PPOConfig
from sixtyfivekmconvoy.rl.selfplay import SelfPlayConfig, SelfPlayTrainer


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Self-play PPO training with a branched bot league"
    )
    p.add_argument(
        "--league",
        type=str,
        default="runs/league",
        help="League root directory (checkpoints + league.json)",
    )
    p.add_argument("--name", type=str, default="learner", help="Learner lineage name")
    p.add_argument(
        "--from",
        dest="from_id",
        type=str,
        default=None,
        help="Resume / branch from checkpoint id or name",
    )
    p.add_argument(
        "--branch-as",
        type=str,
        default=None,
        help="If set with --from, fork a new branch name before training",
    )
    p.add_argument("--players", type=int, default=3)
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--timesteps", type=int, default=50_000)
    p.add_argument("--rollout-steps", type=int, default=2048)
    p.add_argument("--checkpoint-every", type=int, default=10_000)
    p.add_argument("--eval-every", type=int, default=10_000)
    p.add_argument("--eval-episodes", type=int, default=8)
    p.add_argument("--hidden", type=int, default=256)
    p.add_argument("--lr", type=float, default=3e-4)
    p.add_argument("--device", type=str, default="cpu")
    p.add_argument(
        "--reward-mode",
        type=str,
        default="rank",
        choices=("rank", "points"),
    )
    p.add_argument(
        "-o",
        "--output",
        type=str,
        default=None,
        help="Optional JSON summary path",
    )
    return p


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    league = League(args.league)

    parent_id = None
    policy = None
    learner_name = args.name

    if args.from_id:
        parent = league.resolve(args.from_id)
        parent_id = parent.id
        if args.branch_as:
            branched = league.branch(parent.id, name=args.branch_as, tags=["train"])
            parent_id = branched.id
            learner_name = args.branch_as
            print(f"branched {parent.id} → {branched.id} ({branched.name})")
            policy = league.load_model(branched.id, map_location=args.device)
        else:
            learner_name = args.name or parent.name
            policy = league.load_model(parent.id, map_location=args.device)
            print(f"resuming from {parent.id} ({parent.name})")

    cfg = SelfPlayConfig(
        num_players=args.players,
        seed=args.seed,
        total_timesteps=args.timesteps,
        rollout_steps=args.rollout_steps,
        checkpoint_every_steps=args.checkpoint_every,
        eval_every_steps=args.eval_every,
        eval_episodes=args.eval_episodes,
        hidden=args.hidden,
        device=args.device,
        reward_mode=args.reward_mode,
        ppo=PPOConfig(lr=args.lr),
    )
    trainer = SelfPlayTrainer(
        league,
        cfg,
        policy=policy,
        learner_name=learner_name,
        parent_id=parent_id,
    )
    result = trainer.train()
    print(
        json.dumps(
            {
                "final_id": result["final_id"],
                "steps": result["steps"],
                "episodes": result["episodes"],
                "elapsed_sec": result["elapsed_sec"],
                "league": str(Path(args.league).resolve()),
            },
            indent=2,
        )
    )
    if args.output:
        Path(args.output).write_text(
            json.dumps(result, indent=2, default=str) + "\n",
            encoding="utf-8",
        )


if __name__ == "__main__":
    main()
