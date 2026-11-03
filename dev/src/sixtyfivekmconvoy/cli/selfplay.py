"""Run N random agents to completion and dump episode stats JSONL."""

from __future__ import annotations

import argparse
import json
import sys

from sixtyfivekmconvoy.agents.random_agent import RandomAgent
from sixtyfivekmconvoy.core.engine import GameEngine


def run_episode(num_players: int, seed: int | None, verbose: bool = False) -> dict:
    engine = GameEngine()
    engine.reset(num_players=num_players, seed=seed)
    agents = {pid: RandomAgent(seed=None if seed is None else seed + i + 1) for i, pid in enumerate(engine.agent_ids())}

    steps = 0
    while not engine.terminal:
        pending = engine.pending_choice()
        if pending is None:
            break
        legal = engine.legal_actions()
        choice = agents[pending.player_id].choose(legal)
        if verbose and steps % 20 == 0:
            print(f"step={steps} agent={pending.player_id} choice={choice} :: {pending.description[:80]}")
        result = engine.step(choice)
        steps += 1
        if result.terminal:
            break
        if steps > 50_000:
            raise RuntimeError("Episode exceeded 50k steps — likely stuck")

    stats = engine.stats.to_json()
    stats["steps"] = steps
    stats["ranking"] = engine.winner_ranking()
    return stats


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Self-play with random agents")
    parser.add_argument("--players", type=int, default=3)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--episodes", type=int, default=1)
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("-o", "--output", type=str, default=None, help="JSONL output path")
    args = parser.parse_args(argv)

    out = open(args.output, "w", encoding="utf-8") if args.output else sys.stdout
    try:
        for ep in range(args.episodes):
            seed = None if args.seed is None else args.seed + ep
            stats = run_episode(args.players, seed, verbose=args.verbose)
            out.write(json.dumps(stats) + "\n")
            if args.verbose or out is sys.stdout:
                ranking = stats.get("ranking") or []
                print(
                    f"episode {ep}: rounds={stats.get('rounds')} steps={stats.get('steps')} "
                    f"ranking={[ (r['number'], r['promotion_points'], r['total_cash']) for r in ranking ]}",
                    file=sys.stderr if out is not sys.stdout else sys.stdout,
                )
    finally:
        if args.output:
            out.close()


if __name__ == "__main__":
    main()
