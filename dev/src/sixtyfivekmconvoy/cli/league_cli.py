"""Inspect / branch / promote bots in a self-play league."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from sixtyfivekmconvoy.rl.league import League


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Manage the bot league")
    p.add_argument(
        "--league",
        type=str,
        default="runs/league",
        help="League root directory",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    list_p = sub.add_parser("list", help="List checkpoints")
    list_p.add_argument("--active", action="store_true")
    list_p.add_argument("--tag", type=str, default=None)

    show_p = sub.add_parser("show", help="Show one entry + lineage")
    show_p.add_argument("name_or_id")

    branch_p = sub.add_parser("branch", help="Fork a new bot lineage")
    branch_p.add_argument("parent")
    branch_p.add_argument("--name", required=True)
    branch_p.add_argument("--tag", action="append", default=[])

    promo_p = sub.add_parser("promote", help="Tag a bot for playtesting")
    promo_p.add_argument("name_or_id")
    promo_p.add_argument("--name", default=None)
    promo_p.add_argument("--tag", default="playtest")

    active_p = sub.add_parser("set-active", help="Enable/disable opponent sampling")
    active_p.add_argument("name_or_id")
    active_p.add_argument("--off", action="store_true")

    export_p = sub.add_parser("export", help="Copy a checkpoint file")
    export_p.add_argument("name_or_id")
    export_p.add_argument("-o", "--output", required=True)

    eval_p = sub.add_parser(
        "eval",
        help="Quick eval: checkpoint vs league / random seats",
    )
    eval_p.add_argument("name_or_id")
    eval_p.add_argument("--players", type=int, default=3)
    eval_p.add_argument("--episodes", type=int, default=20)
    eval_p.add_argument("--seed", type=int, default=0)
    eval_p.add_argument("--device", type=str, default="cpu")

    return p


def _print_entry(e, *, lineage: list | None = None) -> None:
    tags = ",".join(e.tags) if e.tags else "-"
    metrics = " ".join(f"{k}={v:.3f}" for k, v in sorted(e.metrics.items())[:6])
    print(
        f"{e.id}  {e.name:28s}  parent={e.parent_id or '-':12s}  "
        f"step={e.step:<8d}  active={e.active}  tags={tags}"
    )
    if metrics:
        print(f"    metrics: {metrics}")
    if lineage:
        chain = " → ".join(f"{x.name}({x.id})" for x in lineage)
        print(f"    lineage: {chain}")


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    league = League(args.league)

    if args.cmd == "list":
        rows = league.list(active_only=args.active, tag=args.tag)
        if not rows:
            print("(empty league)")
            return
        for e in rows:
            _print_entry(e)
        return

    if args.cmd == "show":
        e = league.resolve(args.name_or_id)
        _print_entry(e, lineage=league.lineage(e.id))
        print(json.dumps(e.to_json(), indent=2))
        return

    if args.cmd == "branch":
        parent = league.resolve(args.parent)
        child = league.branch(parent.id, name=args.name, tags=args.tag)
        print(f"branched {parent.id} → {child.id} ({child.name})")
        return

    if args.cmd == "promote":
        e = league.promote(league.resolve(args.name_or_id).id, name=args.name, tag=args.tag)
        print(f"promoted {e.id} ({e.name}) tags={e.tags}")
        return

    if args.cmd == "set-active":
        e = league.set_active(league.resolve(args.name_or_id).id, active=not args.off)
        print(f"{e.id} active={e.active}")
        return

    if args.cmd == "export":
        dest = league.export_bot(args.name_or_id, args.output)
        print(f"exported → {dest}")
        return

    if args.cmd == "eval":
        from sixtyfivekmconvoy.agents.random_agent import RandomAgent
        from sixtyfivekmconvoy.env.convoy_env import ConvoyEnv
        from sixtyfivekmconvoy.rl.agent import RLAgent

        entry = league.resolve(args.name_or_id)
        bot = RLAgent(
            league.load_model(entry.id, map_location=args.device),
            deterministic=True,
            device=args.device,
        )
        env = ConvoyEnv(num_players=args.players, reward_mode="win", max_cycles=50_000)
        wins = 0
        returns = []
        for ep in range(args.episodes):
            env.reset(seed=args.seed + ep)
            seat = ep % args.players
            hero = f"player_{seat}"
            randoms = {
                a: RandomAgent(seed=args.seed + 100 + i)
                for i, a in enumerate(env.possible_agents)
            }
            steps = 0
            while env.agents and not all(env.terminations.values()):
                agent = env.agent_selection
                legal = env.infos[agent].get("legal_actions") or []
                mask = env.infos[agent].get("action_mask")
                obs = env.observe(agent)
                if agent == hero:
                    action = bot.act(obs, legal, action_mask=mask)
                else:
                    action = randoms[agent].act(obs, legal)
                env.step(action if legal else 0)
                steps += 1
                if steps > 50_000:
                    break
            ret = float(env._cumulative_rewards.get(hero, 0.0))
            returns.append(ret)
            ranking = env.engine.winner_ranking() or []
            if ranking and f"player_{ranking[0]['number']}" == hero:
                wins += 1
        print(
            json.dumps(
                {
                    "bot": entry.id,
                    "name": entry.name,
                    "episodes": args.episodes,
                    "win_rate_vs_random": wins / max(1, args.episodes),
                    "return_mean": sum(returns) / max(1, len(returns)),
                },
                indent=2,
            )
        )
        return

    raise SystemExit(f"unknown command {args.cmd}")


if __name__ == "__main__":
    main()
