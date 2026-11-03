"""Self-play RL training, league checkpoints, and branched bot policies."""

from __future__ import annotations

__all__ = [
    "League",
    "MaskedActorCritic",
    "PPOTrainer",
    "RLAgent",
    "SelfPlayTrainer",
]


def __getattr__(name: str):
    if name == "League":
        from .league import League

        return League
    if name == "MaskedActorCritic":
        from .policy import MaskedActorCritic

        return MaskedActorCritic
    if name == "PPOTrainer":
        from .ppo import PPOTrainer

        return PPOTrainer
    if name == "RLAgent":
        from .agent import RLAgent

        return RLAgent
    if name == "SelfPlayTrainer":
        from .selfplay import SelfPlayTrainer

        return SelfPlayTrainer
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
