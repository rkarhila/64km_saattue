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
    for cand in league_search_paths():
        if (cand / "league.json").exists():
            return cand
    return league_search_paths()[0]


def list_league_bots(league_path: str | Path | None = None) -> dict[str, Any]:
    """
    List active league checkpoints for the lobby.

    Reads ``league.json`` directly (no torch). Returns a payload with ``bots``,
    ``league``, ``exists``, and optional ``error`` / ``searched``.
    """
    searched = [str(p) for p in league_search_paths()[:8]]
    root = Path(league_path) if league_path else default_league_path()
    registry = root / "league.json"
    if not registry.exists():
        return {
            "league": str(root),
            "exists": False,
            "bots": [],
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

    rows: list[dict[str, Any]] = []
    for e in entries:
        if not isinstance(e, dict):
            continue
        if e.get("active") is False:
            continue
        eid = str(e.get("id") or "")
        name = str(e.get("name") or eid)
        step = int(e.get("step") or 0)
        tags = list(e.get("tags") or [])
        rows.append(
            {
                "id": eid,
                "name": name,
                "step": step,
                "tags": tags,
                "parent_id": e.get("parent_id"),
                "created_at": float(e.get("created_at") or 0),
                "label": f"{name} ({eid[:8]}, step {step})",
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


def make_seat_bots(
    agent_ids: list[str],
    *,
    human_id: str,
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
    """
    meta: dict[str, Any] = {
        "bot_kind": bot_kind,
        "bot_id": None,
        "bot_name": None,
        "league": None,
    }
    other_ids = [pid for pid in agent_ids if pid != human_id]

    if bot_kind == "random" or not bot_id:
        bots: dict[str, SeatBot] = {
            pid: RandomAgent(seed=(seed or 0) + 50 + i)
            for i, pid in enumerate(other_ids)
        }
        meta["bot_kind"] = "random"
        return bots, meta

    try:
        from sixtyfivekmconvoy.rl.agent import RLAgent
        from sixtyfivekmconvoy.rl.league import League
    except ImportError as exc:
        raise RuntimeError(
            "RL bots require torch (`pip install -e '.[rl]'`)"
        ) from exc

    root = Path(league_path) if league_path else default_league_path()
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
        }
    )
    return bots, meta
