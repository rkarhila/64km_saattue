"""Game versions: one directory each, with a config module and card CSVs.

A version is selected before the engine is imported:

- ``CONVOY_VERSION`` is the directory name under the versions root
- ``CONVOY_VERSIONS`` overrides the root (the browser sets this inside Pyodide)
- ``CONVOY_CARDS`` overrides the card directory

The default root is ``dev/versions`` next to ``src``. Training keeps using
``CONVOY_CONFIG`` and the package decks when ``CONVOY_VERSION`` is unset.
"""

from __future__ import annotations

import hashlib
import importlib.util
import os
import shutil
from pathlib import Path
from types import ModuleType

from sixtyfivekmconvoy.boot import (
    prepare_version,
    version_bots_dir,
    version_cards_dir,
    version_dir,
    versions_root,
)

CARD_FILES = (
    "action.csv",
    "action_help.csv",
    "hit.csv",
    "mauling.csv",
    "officer.csv",
    "pillage.csv",
    "resistance.csv",
)


def load_version_module(version: str) -> ModuleType:
    """Execute ``<version>/config.py`` and return it as a balance profile."""
    slug = (version or "").strip()
    path = version_dir(slug) / "config.py"
    if not path.is_file():
        raise FileNotFoundError(f"version {slug} has no config.py")
    spec = importlib.util.spec_from_file_location(f"convoy_version_{slug}", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def live_rules_paths() -> tuple[Path, Path]:
    """``(config.py, cards directory)`` the running process is playing."""
    version = os.environ.get("CONVOY_VERSION", "").strip()
    if version:
        root = version_dir(version)
        return root / "config.py", root / "cards"
    from .configs import get_config

    cfg = get_config()
    config_file = Path(str(getattr(cfg, "__file__", "") or ""))
    if not config_file.is_file():
        raise FileNotFoundError("active config file is missing")
    cards = Path(__file__).resolve().parents[1] / "data" / "cards"
    return config_file, cards


def _file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


def snapshot_rules(dest: Path) -> None:
    """Copy the live config and card CSVs next to a checkpoint."""
    config_file, cards = live_rules_paths()
    dest.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(config_file, dest / "config.py")
    card_dest = dest / "cards"
    card_dest.mkdir(parents=True, exist_ok=True)
    for name in CARD_FILES:
        src = cards / name
        if src.is_file():
            shutil.copyfile(src, card_dest / name)


def rules_changes(snapshot: Path, live: tuple[Path, Path] | None = None) -> list[str]:
    """Files under the snapshot whose bytes differ from the live rules."""
    if live is None:
        live = live_rules_paths()
    config_file, cards = live
    changed: list[str] = []
    snap_cfg = snapshot / "config.py"
    if (
        not snap_cfg.is_file()
        or not config_file.is_file()
        or _file_hash(snap_cfg) != _file_hash(config_file)
    ):
        changed.append("config.py")
    for name in CARD_FILES:
        saved = snapshot / "cards" / name
        current = cards / name
        if not saved.is_file() and not current.is_file():
            continue
        if (
            not saved.is_file()
            or not current.is_file()
            or _file_hash(saved) != _file_hash(current)
        ):
            changed.append(f"cards/{name}")
    return changed


def rules_warning(snapshot: Path | None, live: tuple[Path, Path] | None = None) -> str | None:
    """Finnish warning when a checkpoint's saved rules no longer match."""
    if snapshot is None or not (snapshot / "config.py").is_file():
        return "Tämän botin koulutuksen aikaisia sääntöjä ja kortteja ei ole tallennettu."
    changed = rules_changes(snapshot, live)
    if not changed:
        return None
    shown = ", ".join(changed[:6])
    extra = "" if len(changed) <= 6 else f" (+{len(changed) - 6})"
    return f"Sääntöjä tai kortteja on muutettu koulutuksen jälkeen: {shown}{extra}."
