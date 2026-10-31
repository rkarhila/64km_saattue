"""Named balance profiles for rules + RL training.

Set env ``CONVOY_CONFIG`` to a module name under this package (default: ``default``)
before importing game code so rewards stay tied to a specific profile.
"""

from __future__ import annotations

import importlib
import os
from types import ModuleType

_ACTIVE: ModuleType | None = None


def available_configs() -> list[str]:
    from pathlib import Path

    root = Path(__file__).resolve().parent
    return sorted(
        p.stem
        for p in root.glob("*.py")
        if p.stem != "__init__" and not p.stem.startswith("_")
    )


def load_config(name: str | None = None) -> ModuleType:
    """Load (or reload) a balance profile by module name."""
    global _ACTIVE
    name = (name or os.environ.get("CONVOY_CONFIG") or "default").strip()
    _ACTIVE = importlib.import_module(f"{__package__}.{name}")
    return _ACTIVE


def get_config() -> ModuleType:
    global _ACTIVE
    if _ACTIVE is None:
        load_config()
    assert _ACTIVE is not None
    return _ACTIVE


def config_name() -> str:
    cfg = get_config()
    return str(getattr(cfg, "CONFIG_NAME", getattr(cfg, "__name__", "unknown")))
