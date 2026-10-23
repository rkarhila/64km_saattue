"""Uniform random policy over legal actions."""

from __future__ import annotations

import random
from typing import Any


class RandomAgent:
    def __init__(self, seed: int | None = None):
        self.rng = random.Random(seed)

    def act(self, observation: Any, legal_actions: list[list[int]]) -> int:
        if not legal_actions:
            return 0
        return self.rng.randrange(len(legal_actions))

    def choose(self, legal_actions: list[list[int]]) -> list[int]:
        if not legal_actions:
            return []
        return list(self.rng.choice(legal_actions))
