"""Episode statistics for balancing experiments."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Any


@dataclass
class EpisodeStats:
    seed: int | None = None
    num_players: int = 0
    rounds: int = 0
    action_counts: Counter = field(default_factory=Counter)
    officer_picks: list[tuple[int, str]] = field(default_factory=list)
    resistance_kills: int = 0
    units_lost: int = 0
    ranking: list[dict] = field(default_factory=list)
    events: list[dict] = field(default_factory=list)

    def record_action(self, player: int, action_name: str) -> None:
        self.action_counts[action_name] += 1
        self.events.append({"type": "action", "player": player, "action": action_name})

    def record_officer_pick(self, player: int, name: str) -> None:
        self.officer_picks.append((player, name))
        self.events.append({"type": "officer", "player": player, "officer": name})

    def record_resistance_kill(self) -> None:
        self.resistance_kills += 1

    def finalize(self, ranking: list[dict], rounds: int) -> None:
        self.ranking = ranking
        self.rounds = rounds

    def to_json(self) -> dict[str, Any]:
        return {
            "seed": self.seed,
            "num_players": self.num_players,
            "rounds": self.rounds,
            "action_counts": dict(self.action_counts),
            "officer_picks": self.officer_picks,
            "resistance_kills": self.resistance_kills,
            "units_lost": self.units_lost,
            "ranking": self.ranking,
        }
