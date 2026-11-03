#!/usr/bin/env python3
"""
Wall-clock fork-alternate self-play schedule (option B).

1) Resume a league checkpoint and train shared for ``--shared-hours``.
2) Branch ``alpha`` / ``beta`` with specialized PP vs cash shaping.
3) Alternate training blocks for ``--alt-hours`` or until head-to-head
   win rate stays near 50% for ``--converge-streak`` paired evals.

Run from the ``dev/`` directory::

    PYTHONPATH=src python scripts/train_fork_schedule.py \\
      --league runs/league_rnn50k \\
      --from main-init \\
      --shared-hours 1 \\
      --alt-hours 6 \\
      --device cpu
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any

from sixtyfivekmconvoy.rl.league import League
from sixtyfivekmconvoy.rl.match import head_to_head
from sixtyfivekmconvoy.rl.ppo import PPOConfig
from sixtyfivekmconvoy.rl.selfplay import SelfPlayConfig, SelfPlayTrainer


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Timed shared pretrain → fork → alternate specialized bots"
    )
    p.add_argument(
        "--league",
        type=str,
        default="runs/league_rnn50k",
        help="League directory to resume / write into",
    )
    p.add_argument(
        "--from",
        dest="from_id",
        type=str,
        default="main-init",
        help="Resume id/name/prefix (default: main-init)",
    )
    p.add_argument("--shared-hours", type=float, default=1.0)
    p.add_argument("--alt-hours", type=float, default=6.0)
    p.add_argument("--block-minutes", type=float, default=20.0)
    p.add_argument("--players", type=int, default=3)
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--device", type=str, default="cpu")
    p.add_argument("--hidden", type=int, default=256)
    p.add_argument("--n-layers", type=int, default=2)
    p.add_argument("--width", type=int, default=128)
    p.add_argument("--num-envs", type=int, default=8)
    p.add_argument("--minibatch-size", type=int, default=256)
    p.add_argument("--lr", type=float, default=3e-4)
    p.add_argument("--rollout-steps", type=int, default=2048)
    p.add_argument("--checkpoint-every", type=int, default=5_000)
    p.add_argument("--eval-every", type=int, default=10_000)
    p.add_argument("--eval-episodes", type=int, default=8)
    p.add_argument("--h2h-episodes", type=int, default=12)
    p.add_argument("--converge-lo", type=float, default=0.40)
    p.add_argument("--converge-hi", type=float, default=0.60)
    p.add_argument("--converge-streak", type=int, default=3)
    p.add_argument("--sibling-weight", type=float, default=0.7)
    p.add_argument(
        "--timesteps-cap",
        type=int,
        default=50_000_000,
        help="Hard env-step cap per train() call (wall-clock usually stops first)",
    )
    p.add_argument(
        "--alpha-name", type=str, default="alpha", help="Fork lineage name"
    )
    p.add_argument(
        "--beta-name", type=str, default="beta", help="Fork lineage name"
    )
    return p


def _log_jsonl(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, default=str) + "\n")


def _make_trainer(
    league: League,
    *,
    policy,
    learner_name: str,
    parent_id: str | None,
    args: argparse.Namespace,
    max_seconds: float,
    seed: int,
    league_name: str,
    pp_reward: float,
    cash_reward: float,
    ent_coef: float,
    prefer_opponent_ids: list[str] | None = None,
    global_step: int = 0,
    episodes: int = 0,
) -> SelfPlayTrainer:
    cfg = SelfPlayConfig(
        num_players=args.players,
        seed=seed,
        total_timesteps=args.timesteps_cap,
        max_seconds=max_seconds,
        rollout_steps=args.rollout_steps,
        checkpoint_every_steps=args.checkpoint_every,
        eval_every_steps=args.eval_every,
        eval_episodes=args.eval_episodes,
        hidden=args.hidden,
        n_layers=args.n_layers,
        width=args.width,
        num_envs=args.num_envs,
        device=args.device,
        reward_mode="win",
        pp_reward=pp_reward,
        cash_reward=cash_reward,
        league_name=league_name,
        prefer_opponent_ids=list(prefer_opponent_ids or []),
        prefer_opponent_weight=args.sibling_weight,
        include_self_mirror=0.15,
        ppo=PPOConfig(
            lr=args.lr, minibatch_size=args.minibatch_size, ent_coef=ent_coef
        ),
    )
    trainer = SelfPlayTrainer(
        league,
        cfg,
        policy=policy,
        learner_name=learner_name,
        parent_id=parent_id,
    )
    trainer.global_step = int(global_step)
    trainer.episodes = int(episodes)
    return trainer


def _latest_lineage(league: League, name: str) -> Any:
    entry = league.latest_by_name_prefix(name)
    if entry is None:
        raise KeyError(f"no checkpoints for lineage {name!r}")
    return entry


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    league_root = Path(args.league)
    league = League(league_root)
    log_path = league_root / "fork_schedule.log.jsonl"
    summary_path = league_root / "fork_schedule_summary.json"

    start = league.resolve_flexible(args.from_id)
    print(
        f"resume {start.id} ({start.name}) step={start.step} "
        f"league={league_root.resolve()}",
        flush=True,
    )

    shared_sec = float(args.shared_hours) * 3600.0
    alt_sec = float(args.alt_hours) * 3600.0
    block_sec = float(args.block_minutes) * 60.0

    # ------------------------------------------------------------------
    # Phase 1: shared pretrain
    # ------------------------------------------------------------------
    policy = league.load_model(start.id, map_location=args.device)
    trainer = _make_trainer(
        league,
        policy=policy,
        learner_name="main",
        parent_id=start.id,
        args=args,
        max_seconds=shared_sec,
        seed=args.seed,
        league_name="main",
        pp_reward=0.25,
        cash_reward=0.05,
        ent_coef=0.01,
        global_step=start.step,
        episodes=start.episodes,
    )
    t_shared0 = time.time()
    shared_result = trainer.train()
    shared_elapsed = time.time() - t_shared0
    shared_final = shared_result["final_id"]
    _log_jsonl(
        log_path,
        {
            "phase": "shared",
            "fork": "main",
            "from_id": start.id,
            "final_id": shared_final,
            "steps": shared_result["steps"],
            "elapsed_sec": shared_elapsed,
            "steps_per_sec": shared_result.get("steps_per_sec"),
        },
    )
    print(
        f"shared done final={shared_final} "
        f"steps={shared_result['steps']} "
        f"elapsed={shared_elapsed:.1f}s "
        f"sps={shared_result.get('steps_per_sec', 0):.1f}",
        flush=True,
    )

    # ------------------------------------------------------------------
    # Phase 2: fork
    # ------------------------------------------------------------------
    alpha = league.branch(
        shared_final,
        name=args.alpha_name,
        tags=["fork", "specialized", "alpha"],
        map_location=args.device,
    )
    beta = league.branch(
        shared_final,
        name=args.beta_name,
        tags=["fork", "specialized", "beta"],
        map_location=args.device,
    )
    print(
        f"forked {shared_final} → alpha={alpha.id} beta={beta.id}",
        flush=True,
    )
    _log_jsonl(
        log_path,
        {
            "phase": "fork",
            "parent_id": shared_final,
            "alpha_id": alpha.id,
            "beta_id": beta.id,
        },
    )

    # Specialization: alpha = PP-heavy / lower entropy; beta = cash-heavy / higher entropy
    fork_specs = {
        "alpha": {
            "entry": alpha,
            "pp_reward": 0.45,
            "cash_reward": 0.03,
            "ent_coef": 0.005,
            "seed": args.seed + 10,
        },
        "beta": {
            "entry": beta,
            "pp_reward": 0.15,
            "cash_reward": 0.12,
            "ent_coef": 0.02,
            "seed": args.seed + 20,
        },
    }

    # ------------------------------------------------------------------
    # Phase 3: alternate blocks
    # ------------------------------------------------------------------
    alt_deadline = time.time() + alt_sec
    converge_streak = 0
    converged = False
    block_idx = 0
    h2h_history: list[dict[str, Any]] = []
    order = ["alpha", "beta"]

    while time.time() < alt_deadline:
        remaining = alt_deadline - time.time()
        if remaining <= 1.0:
            break
        block_budget = min(block_sec, remaining)
        fork_name = order[block_idx % 2]
        sibling_name = order[(block_idx + 1) % 2]
        spec = fork_specs[fork_name]
        latest = _latest_lineage(league, fork_name)
        sibling_latest = _latest_lineage(league, sibling_name)

        policy = league.load_model(latest.id, map_location=args.device)
        trainer = _make_trainer(
            league,
            policy=policy,
            learner_name=fork_name,
            parent_id=latest.id,
            args=args,
            max_seconds=block_budget,
            seed=spec["seed"],
            league_name=fork_name,
            pp_reward=float(spec["pp_reward"]),
            cash_reward=float(spec["cash_reward"]),
            ent_coef=float(spec["ent_coef"]),
            prefer_opponent_ids=[sibling_latest.id],
            global_step=latest.step,
            episodes=latest.episodes,
        )
        print(
            f"alt block {block_idx} train={fork_name} "
            f"from={latest.id} budget={block_budget:.0f}s "
            f"sibling={sibling_latest.id}",
            flush=True,
        )
        t0 = time.time()
        result = trainer.train()
        elapsed = time.time() - t0
        row = {
            "phase": "alternate",
            "block": block_idx,
            "fork": fork_name,
            "from_id": latest.id,
            "final_id": result["final_id"],
            "steps": result["steps"],
            "elapsed_sec": elapsed,
            "steps_per_sec": result.get("steps_per_sec"),
            "pp_reward": spec["pp_reward"],
            "cash_reward": spec["cash_reward"],
            "ent_coef": spec["ent_coef"],
        }
        _log_jsonl(log_path, row)
        print(
            f"  → {result['final_id']} steps={result['steps']} "
            f"elapsed={elapsed:.1f}s sps={result.get('steps_per_sec', 0):.1f}",
            flush=True,
        )

        # After each alpha+beta pair, run head-to-head.
        if block_idx % 2 == 1:
            a_latest = _latest_lineage(league, "alpha")
            b_latest = _latest_lineage(league, "beta")
            h2h = head_to_head(
                league,
                a_latest.id,
                b_latest.id,
                episodes=args.h2h_episodes,
                num_players=args.players,
                seed=args.seed + 1000 + block_idx,
                device=args.device,
            )
            wr = float(h2h["alpha_win_rate"])
            in_band = args.converge_lo <= wr <= args.converge_hi
            converge_streak = converge_streak + 1 if in_band else 0
            h2h_row = {
                "phase": "h2h",
                "block": block_idx,
                **h2h,
                "in_band": in_band,
                "converge_streak": converge_streak,
            }
            h2h_history.append(h2h_row)
            _log_jsonl(log_path, h2h_row)
            print(
                f"  h2h alpha_wr={wr:.3f} "
                f"streak={converge_streak}/{args.converge_streak}",
                flush=True,
            )
            if converge_streak >= args.converge_streak:
                converged = True
                print("converged — stopping alternate phase", flush=True)
                break

        block_idx += 1

    alpha_final = _latest_lineage(league, args.alpha_name)
    beta_final = _latest_lineage(league, args.beta_name)
    summary = {
        "league": str(league_root.resolve()),
        "resumed_from": {"id": start.id, "name": start.name, "step": start.step},
        "shared_final_id": shared_final,
        "shared_elapsed_sec": shared_elapsed,
        "alpha_final": {"id": alpha_final.id, "name": alpha_final.name, "step": alpha_final.step},
        "beta_final": {"id": beta_final.id, "name": beta_final.name, "step": beta_final.step},
        "blocks_completed": block_idx + 1,
        "converged": converged,
        "h2h_history": h2h_history,
        "log": str(log_path),
    }
    summary_path.write_text(json.dumps(summary, indent=2, default=str) + "\n")
    print(json.dumps(summary, indent=2, default=str), flush=True)


if __name__ == "__main__":
    main()
