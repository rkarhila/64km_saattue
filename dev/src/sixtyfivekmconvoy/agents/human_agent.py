"""Human choice bridge for CLI / web adapters."""

from __future__ import annotations

from typing import Callable

from sixtyfivekmconvoy.core.engine import ChoiceRequest


class HumanAgent:
    """Calls an injected callback to obtain a choice vector."""

    def __init__(self, choose_fn: Callable[[ChoiceRequest, list[list[int]]], list[int]]):
        self.choose_fn = choose_fn

    def choose(self, request: ChoiceRequest, legal_actions: list[list[int]]) -> list[int]:
        return self.choose_fn(request, legal_actions)
