"""PettingZoo adapter. Importing this package does not load PettingZoo."""

__all__ = ["ConvoyEnv"]


def __getattr__(name: str):
    if name == "ConvoyEnv":
        from .convoy_env import ConvoyEnv

        return ConvoyEnv
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
