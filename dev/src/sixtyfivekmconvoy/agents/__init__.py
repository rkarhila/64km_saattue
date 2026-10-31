from .random_agent import RandomAgent
from .human_agent import HumanAgent

__all__ = ["RandomAgent", "HumanAgent", "RLAgent"]


def __getattr__(name: str):
    if name == "RLAgent":
        from sixtyfivekmconvoy.rl.agent import RLAgent

        return RLAgent
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
