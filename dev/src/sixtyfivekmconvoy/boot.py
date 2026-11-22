"""Choose a version directory before the engine is imported.

Importing anything under ``sixtyfivekmconvoy.core`` loads the engine, which
reads the config and the card files immediately. This module does not.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

_SLUG = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,40}$")


def versions_root() -> Path:
    raw = os.environ.get("CONVOY_VERSIONS", "").strip()
    if raw:
        return Path(raw)
    # boot.py -> dev/src/sixtyfivekmconvoy/boot.py
    return Path(__file__).resolve().parents[2] / "versions"


def version_dir(version: str) -> Path:
    slug = (version or "").strip()
    if not _SLUG.match(slug):
        raise ValueError(f"unknown version {version!r}")
    path = versions_root() / slug
    if not path.is_dir():
        raise FileNotFoundError(f"version {slug} is not in {versions_root()}")
    return path


def version_cards_dir(version: str) -> Path:
    path = version_dir(version) / "cards"
    if not path.is_dir():
        raise FileNotFoundError(f"version {version} has no cards directory")
    return path


def version_bots_dir(version: str) -> Path:
    """RL checkpoints for this version. The directory may not exist yet."""
    return version_dir(version) / "bots"


def prepare_version(name: str) -> Path:
    """Point this process at a version directory. Call before importing the engine."""
    root_parent = versions_root()
    slug = (name or "").strip()
    os.environ["CONVOY_VERSION"] = slug
    os.environ["CONVOY_VERSIONS"] = str(root_parent)
    path = version_dir(slug)
    os.environ["CONVOY_CARDS"] = str(path / "cards")
    return path
