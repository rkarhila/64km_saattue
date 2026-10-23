"""Interactive terminal human vs random bots on the pure engine."""

from __future__ import annotations

import argparse
import json

from sixtyfivekmconvoy.agents.random_agent import RandomAgent
from sixtyfivekmconvoy.core.engine import ChoiceRequest, GameEngine


def _prompt_choice(request: ChoiceRequest, legal: list[list[int]]) -> list[int]:
    print("\n" + "=" * 60)
    print(request.description)
    print(f"choicetype={int(request.choicetype)} num={request.num_choices}")
    print(f"options={request.options}")
    print(f"{len(legal)} legal combinations (showing up to 30):")
    for i, vec in enumerate(legal[:30]):
        print(f"  [{i}] {vec}")
    while True:
        raw = input("Select legal index (or comma-separated values): ").strip()
        if raw.isdigit():
            idx = int(raw)
            if 0 <= idx < len(legal):
                return list(legal[idx])
        else:
            try:
                vec = [int(x.strip()) for x in raw.split(",") if x.strip() != ""]
                if vec in legal:
                    return vec
            except ValueError:
                pass
        print("Invalid — try again.")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Terminal play: human seat 0 vs random bots")
    parser.add_argument("--players", type=int, default=3)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--human-seat", type=int, default=0)
    args = parser.parse_args(argv)

    engine = GameEngine()
    engine.reset(num_players=args.players, seed=args.seed)
    bots = {
        pid: RandomAgent(seed=args.seed + 10 + i)
        for i, pid in enumerate(engine.agent_ids())
        if int(pid.split("_")[1]) != args.human_seat
    }
    human_id = f"player_{args.human_seat}"

    while not engine.terminal:
        pending = engine.pending_choice()
        if pending is None:
            break
        legal = engine.legal_actions()
        if pending.player_id == human_id:
            view = engine.observe(human_id)
            print(json.dumps({k: view[k] for k in ("round", "stage", "resistance", "players") if k in view}, indent=2))
            print("Convoy:")
            for i, u in enumerate(view.get("convoy") or []):
                print(f"  {i}: P{u['player']} {u['unit_type']} T{u['tiredness']} carry={u['carry']} zone={u.get('zone')}")
            choice = _prompt_choice(pending, legal)
        else:
            choice = bots[pending.player_id].choose(legal)
        result = engine.step(choice)
        if result.message:
            print(">>", result.message)
        if result.terminal:
            print("Ranking:")
            for r in result.ranking or []:
                print(f"  Player {r['number']}: PP={r['promotion_points']} cash={r['total_cash']}")
            break


if __name__ == "__main__":
    main()
