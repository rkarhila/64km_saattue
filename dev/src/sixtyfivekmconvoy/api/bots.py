"""Build seat bots for web/terminal sessions (random or league RL)."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Protocol

from sixtyfivekmconvoy.agents.random_agent import RandomAgent


class SeatBot(Protocol):
    def choose(self, legal_actions: list[list[int]], **kwargs: Any) -> list[int]: ...


def _repo_dev_root() -> Path:
    # api/bots.py → api → sixtyfivekmconvoy → src → dev
    return Path(__file__).resolve().parents[3]


def league_search_paths() -> list[Path]:
    """Ordered candidates for the bot league directory."""
    paths: list[Path] = []
    env = (os.environ.get("CONVOY_LEAGUE") or "").strip()
    if env:
        paths.append(Path(env).expanduser())
    version = (os.environ.get("CONVOY_VERSION") or "").strip()
    if version:
        from sixtyfivekmconvoy.core.versions import version_bots_dir

        paths.append(version_bots_dir(version))
    cwd = Path.cwd()
    paths.extend(
        [
            cwd / "runs" / "league",
            cwd / "dev" / "runs" / "league",
            _repo_dev_root() / "runs" / "league",
        ]
    )
    # Walk parents of cwd for runs/league (e.g. started from repo root).
    for parent in [cwd, *cwd.parents]:
        paths.append(parent / "runs" / "league")
        paths.append(parent / "dev" / "runs" / "league")
        if parent == parent.parent:
            break
    # Dedupe while preserving order.
    seen: set[str] = set()
    out: list[Path] = []
    for p in paths:
        key = str(p.resolve()) if p.exists() else str(p)
        if key in seen:
            continue
        seen.add(key)
        out.append(p)
    return out


def default_league_path() -> Path:
    version = (os.environ.get("CONVOY_VERSION") or "").strip()
    explicit = (os.environ.get("CONVOY_LEAGUE") or "").strip()
    if version and not explicit:
        from sixtyfivekmconvoy.core.versions import version_bots_dir

        return version_bots_dir(version)
    for cand in league_search_paths():
        if (cand / "league.json").exists() or (cand / "index.json").exists():
            return cand
    return league_search_paths()[0]


def iter_numpy_bots(bots_root: str | Path) -> list[dict[str, Any]]:
    """Browser checkpoints: ``bots/index.json`` plus one directory each."""
    from sixtyfivekmconvoy.core.versions import rules_warning

    root = Path(bots_root)
    index_path = root / "index.json"
    if not index_path.is_file():
        return []
    try:
        raw = json.loads(index_path.read_text(encoding="utf-8"))
    except Exception:
        return []
    rows: list[dict[str, Any]] = []
    for name in list(raw.get("bots") or []):
        folder = root / str(name)
        manifest_path = folder / "manifest.json"
        if not manifest_path.is_file():
            continue
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(manifest, dict):
            continue
        bot_id = str(manifest.get("id") or name)
        bot_name = str(manifest.get("name") or name)
        step = int(manifest.get("step") or 0)
        weights_name = str(manifest.get("weights") or "weights.npz")
        warning = rules_warning(folder if (folder / "config.py").is_file() else None)
        rows.append(
            {
                "id": bot_id,
                "name": bot_name,
                "step": step,
                "tags": ["numpy"],
                "label": f"{bot_name} ({bot_id[:8]}, step {step})",
                "warning": warning,
                "weights": str(folder / weights_name),
                "folder": str(folder),
            }
        )
    return rows


def numpy_bot(bots_root: str | Path | None, bot_id: str | None) -> dict[str, Any] | None:
    if not bots_root or not bot_id:
        return None
    wanted = str(bot_id)
    for row in iter_numpy_bots(bots_root):
        if row["id"] == wanted or row["name"] == wanted:
            return row
    return None


def list_league_bots(league_path: str | Path | None = None) -> dict[str, Any]:
    """
    List active league checkpoints for the lobby.

    Reads ``league.json`` directly (no torch). Returns a payload with ``bots``,
    ``league``, ``exists``, and optional ``error`` / ``searched``.
    """
    searched = [str(p) for p in league_search_paths()[:8]]
    root = Path(league_path) if league_path else default_league_path()
    numpy_rows = iter_numpy_bots(root)
    registry = root / "league.json"
    if not registry.exists():
        return {
            "league": str(root),
            "exists": bool(numpy_rows),
            "bots": numpy_rows,
            "searched": searched,
            "error": None,
        }
    try:
        raw = json.loads(registry.read_text(encoding="utf-8"))
        entries = list(raw.get("entries") or [])
    except Exception as exc:  # noqa: BLE001 — surface to UI
        return {
            "league": str(root),
            "exists": True,
            "bots": [],
            "searched": searched,
            "error": f"failed to read league.json: {exc}",
        }

    from sixtyfivekmconvoy.core.versions import rules_warning

    rows: list[dict[str, Any]] = list(numpy_rows)
    seen = {row["id"] for row in rows}
    for e in entries:
        if not isinstance(e, dict):
            continue
        if e.get("active") is False:
            continue
        eid = str(e.get("id") or "")
        if not eid or eid in seen:
            continue
        name = str(e.get("name") or eid)
        step = int(e.get("step") or 0)
        tags = list(e.get("tags") or [])
        rules_rel = str(e.get("rules") or "")
        snap = (root / rules_rel) if rules_rel else (root / "checkpoints" / f"{eid}.rules")
        rows.append(
            {
                "id": eid,
                "name": name,
                "step": step,
                "tags": tags,
                "parent_id": e.get("parent_id"),
                "created_at": float(e.get("created_at") or 0),
                "label": f"{name} ({eid[:8]}, step {step})",
                "warning": rules_warning(snap if snap.is_dir() else None),
            }
        )
    rows.sort(key=lambda r: r.get("created_at") or 0, reverse=True)
    return {
        "league": str(root),
        "exists": True,
        "bots": rows,
        "searched": searched,
        "error": None,
    }


def rules_warning_for_entry(root: Path, entry: Any) -> str | None:
    from sixtyfivekmconvoy.core.versions import rules_warning

    rules_rel = str(getattr(entry, "rules", "") or "")
    snap = (root / rules_rel) if rules_rel else (root / "checkpoints" / f"{entry.id}.rules")
    return rules_warning(snap if snap.is_dir() else None)


def make_seat_bots(
    agent_ids: list[str],
    *,
    human_id: str,
    human_ids: set[str] | None = None,
    seed: int | None = None,
    bot_kind: str = "random",
    league_path: str | Path | None = None,
    bot_id: str | None = None,
    deterministic: bool = True,
    device: str = "cpu",
) -> tuple[dict[str, SeatBot], dict[str, Any]]:
    """
    Build bots for every non-human seat.

    Returns (bots, meta) where meta describes what was loaded for the UI/snapshot.
    ``human_ids`` excludes every joined human; ``human_id`` is always excluded too.
    """
    meta: dict[str, Any] = {
        "bot_kind": bot_kind,
        "bot_id": None,
        "bot_name": None,
        "league": None,
        "warning": None,
    }
    humans = set(human_ids or ())
    humans.add(human_id)
    other_ids = [pid for pid in agent_ids if pid not in humans]

    if bot_kind == "random" or not bot_id:
        bots: dict[str, SeatBot] = {
            pid: RandomAgent(seed=(seed or 0) + 50 + i)
            for i, pid in enumerate(other_ids)
        }
        meta["bot_kind"] = "random"
        return bots, meta

    root = Path(league_path) if league_path else default_league_path()
    saved = numpy_bot(root, bot_id)
    if saved is not None and os.path.isfile(saved["weights"]):
        from sixtyfivekmconvoy.play_net import NumpyPolicy

        policy = NumpyPolicy.load(saved["weights"])
        bots = {pid: policy for pid in other_ids}
        meta.update(
            {
                "bot_kind": "rl",
                "bot_id": saved["id"],
                "bot_name": saved["name"],
                "league": str(root),
                "warning": saved.get("warning"),
            }
        )
        return bots, meta

    try:
        from sixtyfivekmconvoy.rl.agent import RLAgent
        from sixtyfivekmconvoy.rl.league import League
    except ImportError as exc:
        raise RuntimeError(
            "RL bots require torch (`pip install -e '.[rl]'`)"
        ) from exc

    if not (root / "league.json").exists():
        raise FileNotFoundError(f"league not found at {root}")
    league = League(root)
    entry = league.resolve(bot_id)
    policy = league.load_model(entry.id, map_location=device)
    bots = {
        pid: RLAgent(
            policy,
            deterministic=deterministic,
            device=device,
            seed=(seed or 0) + 50 + i,
        )
        for i, pid in enumerate(other_ids)
    }
    meta.update(
        {
            "bot_kind": "rl",
            "bot_id": entry.id,
            "bot_name": entry.name,
            "league": str(root),
            "warning": rules_warning_for_entry(root, entry),
        }
    )
    return bots, meta
