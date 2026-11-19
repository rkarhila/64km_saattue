#!/usr/bin/env python3
"""Train 30 minutes from the earliest checkpoint with the best eval win rate.

Rewards are the current self-play defaults (one cash outweighs the shaping
terms). The learning rate stays at 3e-4. A second run starts from that same
checkpoint again.

Run on the GTX 1050 machine, from ``dev/``::

    PYTHONPATH=src python scripts/train_30m_best.py --league runs/league_table --name reward30
"""

from __future__ import annotations

import os

os.environ["CONVOY_CONFIG"] = "retire"

import argparse
import json
from pathlib import Path


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--league", default="runs/league_table")
    p.add_argument("--name", default="reward30")
    p.add_argument("--minutes", type=float, default=30.0)
    p.add_argument("--device", default="cuda")
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--num-envs", type=int, default=8)
    p.add_argument("--minibatch-size", type=int, default=128)
    p.add_argument("--grad-accum-steps", type=int, default=8)
    p.add_argument("--rollout-steps", type=int, default=2048)
    p.add_argument("--eval-episodes", type=int, default=32)
    p.add_argument("--lr", type=float, default=3e-4)
    p.add_argument("--player-counts", type=int, nargs="+", default=[2, 3, 4, 5])
    return p


def first_best(league):
    """Earliest league entry that reached the highest stored eval win rate."""
    scored = [
        entry
        for entry in league.list()
        if "eval_win_rate" in (entry.metrics or {})
    ]
    if not scored:
        raise SystemExit(f"No checkpoint in {league.root} has an eval win rate.")
    best = max(float(entry.metrics["eval_win_rate"]) for entry in scored)
    tied = [
        entry
        for entry in scored
        if float(entry.metrics["eval_win_rate"]) == best
    ]
    return min(tied, key=lambda entry: (int(entry.step), float(entry.created_at))), tied


def _kept_tensors(path: Path) -> tuple[int, int, int, int]:
    """How many checkpoint tensors match the live network."""
    import torch

    from sixtyfivekmconvoy.env.spaces import observation_size
    from sixtyfivekmconvoy.rl.policy import MaskedActorCritic

    data = torch.load(path, map_location="cpu", weights_only=False)
    policy = data["policy"]
    stored = int(policy.get("obs_dim", 0))
    live = int(observation_size())
    model = MaskedActorCritic.from_checkpoint(policy, map_location="cpu")
    state = policy["state_dict"]
    model_state = model.state_dict()
    kept = sum(
        1
        for key, value in state.items()
        if key in model_state and tuple(value.shape) == tuple(model_state[key].shape)
    )
    return stored, live, kept, len(state)


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
    chosen, tied = first_best(league)
    path = league.root / chosen.path if chosen.path else league._ckpt_path(chosen.id)
    stored, live, kept, total = _kept_tensors(path)
    rate = float(chosen.metrics["eval_win_rate"])
    print(
        f"first best {chosen.id} ({chosen.name}) "
        f"step={chosen.step} eval_win_rate={rate:.5f} "
        f"tied={len(tied)}",
        flush=True,
    )
    if len(tied) > 1:
        later = [entry.name for entry in tied if entry.id != chosen.id]
        print(f"later ties left unused: {', '.join(later)}", flush=True)
    if stored != live:
        print(
            f"checkpoint observation is {stored}, the live table is {live}. "
            f"Kept {kept} of {total} tensors. The action-card projection "
            f"does not fit the wider card token and starts from its new init.",
            flush=True,
        )
    counts = tuple(int(n) for n in args.player_counts)
    policy = league.load_model(chosen.id, map_location=args.device)
    cfg = SelfPlayConfig(
        num_players=max(counts),
        player_counts=counts,
        seed=args.seed,
        total_timesteps=100_000_000,
        max_seconds=float(args.minutes) * 60.0,
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
        log_path=str(Path(args.league) / "train_30m.jsonl"),
        ppo=PPOConfig(
            lr=float(args.lr),
            minibatch_size=args.minibatch_size,
            grad_accum_steps=args.grad_accum_steps,
        ),
    )
    print(
        f"rewards cash={cfg.cash_reward} pp={cfg.pp_reward} "
        f"rest={cfg.rest_relief_reward} dodge={cfg.mauling_dodge_reward} "
        f"frustration={cfg.frustration_penalty} "
        f"mauling_per_point={cfg.mauling_damage_penalty} "
        f"lr={cfg.ppo.lr}",
        flush=True,
    )
    trainer = SelfPlayTrainer(
        league,
        cfg,
        policy=policy,
        learner_name=args.name,
        parent_id=chosen.id,
    )
    trainer.global_step = int(chosen.step)
    trainer.episodes = int(chosen.episodes)
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
        "resumed_from": {
            "id": chosen.id,
            "name": chosen.name,
            "step": chosen.step,
            "episodes": chosen.episodes,
            "eval_win_rate": rate,
        },
        "minibatch_size": args.minibatch_size,
        "grad_accum_steps": args.grad_accum_steps,
        "lr": float(args.lr),
        "cash_reward": cfg.cash_reward,
        "pp_reward": cfg.pp_reward,
        "rest_relief_reward": cfg.rest_relief_reward,
        "mauling_dodge_reward": cfg.mauling_dodge_reward,
        "frustration_penalty": cfg.frustration_penalty,
        "mauling_damage_penalty": cfg.mauling_damage_penalty,
        "player_counts": list(counts),
        "league": str(Path(args.league).resolve()),
    }
    out = Path(args.league) / "train_30m.json"
    out.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return str(result["final_id"])


def main(argv: list[str] | None = None) -> None:
    train(build_parser().parse_args(argv))


if __name__ == "__main__":
    main()
