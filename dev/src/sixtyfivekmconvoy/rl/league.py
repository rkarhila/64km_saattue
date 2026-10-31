"""Checkpoint league: versioned policies with parent lineage / branching."""

from __future__ import annotations

import json
import shutil
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import torch

from sixtyfivekmconvoy.rl.policy import MaskedActorCritic


@dataclass
class LeagueEntry:
    """One frozen (or live) policy version in the league."""

    id: str
    name: str
    parent_id: str | None = None
    path: str = ""
    created_at: float = field(default_factory=time.time)
    step: int = 0
    episodes: int = 0
    metrics: dict[str, float] = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)
    active: bool = True
    config: dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> LeagueEntry:
        return cls(
            id=str(data["id"]),
            name=str(data["name"]),
            parent_id=data.get("parent_id"),
            path=str(data.get("path") or ""),
            created_at=float(data.get("created_at") or time.time()),
            step=int(data.get("step") or 0),
            episodes=int(data.get("episodes") or 0),
            metrics=dict(data.get("metrics") or {}),
            tags=list(data.get("tags") or []),
            active=bool(data.get("active", True)),
            config=dict(data.get("config") or {}),
        )


class League:
    """
    On-disk registry of policy checkpoints.

    Layout::

        root/
          league.json
          checkpoints/
            <id>.pt

    Branching creates a new id that copies weights and records ``parent_id``.
    Opponent sampling draws from active entries (optionally excluding the
    currently training learner).
    """

    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.ckpt_dir = self.root / "checkpoints"
        self.registry_path = self.root / "league.json"
        self.entries: dict[str, LeagueEntry] = {}
        self.root.mkdir(parents=True, exist_ok=True)
        self.ckpt_dir.mkdir(parents=True, exist_ok=True)
        if self.registry_path.exists():
            self._load()

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _load(self) -> None:
        raw = json.loads(self.registry_path.read_text(encoding="utf-8"))
        self.entries = {
            e["id"]: LeagueEntry.from_json(e) for e in raw.get("entries", [])
        }

    def save(self) -> None:
        payload = {
            "version": 1,
            "entries": [e.to_json() for e in sorted(self.entries.values(), key=lambda x: x.created_at)],
        }
        self.registry_path.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    # ------------------------------------------------------------------
    # Mutations
    # ------------------------------------------------------------------

    def _new_id(self) -> str:
        return uuid.uuid4().hex[:12]

    def _ckpt_path(self, entry_id: str) -> Path:
        return self.ckpt_dir / f"{entry_id}.pt"

    def add(
        self,
        model: MaskedActorCritic,
        *,
        name: str,
        parent_id: str | None = None,
        step: int = 0,
        episodes: int = 0,
        metrics: dict[str, float] | None = None,
        tags: Iterable[str] | None = None,
        config: dict[str, Any] | None = None,
        entry_id: str | None = None,
    ) -> LeagueEntry:
        eid = entry_id or self._new_id()
        path = self._ckpt_path(eid)
        payload = {
            "policy": model.checkpoint_dict(),
            "meta": {
                "id": eid,
                "name": name,
                "parent_id": parent_id,
                "step": step,
                "episodes": episodes,
            },
        }
        torch.save(payload, path)
        entry = LeagueEntry(
            id=eid,
            name=name,
            parent_id=parent_id,
            path=str(path.relative_to(self.root)),
            step=step,
            episodes=episodes,
            metrics=dict(metrics or {}),
            tags=list(tags or []),
            config=dict(config or {}),
        )
        self.entries[eid] = entry
        self.save()
        return entry

    def update_metrics(self, entry_id: str, **metrics: float) -> LeagueEntry:
        entry = self.entries[entry_id]
        entry.metrics.update({k: float(v) for k, v in metrics.items()})
        self.save()
        return entry

    def tag(self, entry_id: str, *tags: str) -> LeagueEntry:
        entry = self.entries[entry_id]
        for t in tags:
            if t not in entry.tags:
                entry.tags.append(t)
        self.save()
        return entry

    def set_active(self, entry_id: str, active: bool = True) -> LeagueEntry:
        entry = self.entries[entry_id]
        entry.active = active
        self.save()
        return entry

    def branch(
        self,
        parent_id: str,
        *,
        name: str,
        tags: Iterable[str] | None = None,
        map_location: str | torch.device = "cpu",
    ) -> LeagueEntry:
        """Fork a new lineage from ``parent_id`` (copies weights)."""
        parent = self.entries[parent_id]
        model = self.load_model(parent_id, map_location=map_location)
        return self.add(
            model,
            name=name,
            parent_id=parent_id,
            step=parent.step,
            episodes=parent.episodes,
            metrics=dict(parent.metrics),
            tags=list(tags or []) + ["branch"],
            config=dict(parent.config),
        )

    def promote(
        self,
        entry_id: str,
        *,
        name: str | None = None,
        tag: str = "playtest",
    ) -> LeagueEntry:
        """Mark a checkpoint for playtesting (active + tag)."""
        entry = self.entries[entry_id]
        if name:
            entry.name = name
        if tag not in entry.tags:
            entry.tags.append(tag)
        entry.active = True
        self.save()
        return entry

    def delete(self, entry_id: str, *, remove_file: bool = True) -> None:
        entry = self.entries.pop(entry_id)
        if remove_file:
            path = self.root / entry.path if entry.path else self._ckpt_path(entry_id)
            if path.exists():
                path.unlink()
        self.save()

    # ------------------------------------------------------------------
    # Queries / loading
    # ------------------------------------------------------------------

    def get(self, entry_id: str) -> LeagueEntry:
        return self.entries[entry_id]

    def find_by_name(self, name: str) -> LeagueEntry | None:
        for e in self.entries.values():
            if e.name == name:
                return e
        return None

    def resolve(self, name_or_id: str) -> LeagueEntry:
        if name_or_id in self.entries:
            return self.entries[name_or_id]
        by_name = self.find_by_name(name_or_id)
        if by_name is not None:
            return by_name
        raise KeyError(f"no league entry named or id={name_or_id!r}")

    def list(
        self,
        *,
        active_only: bool = False,
        tag: str | None = None,
    ) -> list[LeagueEntry]:
        rows = list(self.entries.values())
        if active_only:
            rows = [e for e in rows if e.active]
        if tag is not None:
            rows = [e for e in rows if tag in e.tags]
        return sorted(rows, key=lambda e: e.created_at)

    def lineage(self, entry_id: str) -> list[LeagueEntry]:
        """Parent chain from root → ``entry_id``."""
        chain: list[LeagueEntry] = []
        seen: set[str] = set()
        cur: str | None = entry_id
        while cur and cur not in seen:
            seen.add(cur)
            entry = self.entries[cur]
            chain.append(entry)
            cur = entry.parent_id
        chain.reverse()
        return chain

    def load_model(
        self,
        name_or_id: str,
        *,
        map_location: str | torch.device = "cpu",
    ) -> MaskedActorCritic:
        entry = self.resolve(name_or_id)
        path = self.root / entry.path if entry.path else self._ckpt_path(entry.id)
        data = torch.load(path, map_location=map_location, weights_only=False)
        return MaskedActorCritic.from_checkpoint(data["policy"], map_location=map_location)

    def sample_opponent_ids(
        self,
        rng: np.random.Generator,
        *,
        k: int,
        exclude: Iterable[str] | None = None,
        prefer_tags: Iterable[str] | None = None,
        include_latest_weight: float = 0.4,
    ) -> list[str]:
        """
        Sample ``k`` opponent checkpoint ids from active league members.

        Mixes uniform historical opponents with a bias toward the newest entry
        (``include_latest_weight``).
        """
        exclude_set = set(exclude or [])
        pool = [e for e in self.list(active_only=True) if e.id not in exclude_set]
        if prefer_tags:
            tagged = [e for e in pool if any(t in e.tags for t in prefer_tags)]
            if tagged:
                pool = tagged
        if not pool:
            return []

        latest = max(pool, key=lambda e: e.created_at)
        out: list[str] = []
        for _ in range(k):
            if rng.random() < include_latest_weight:
                out.append(latest.id)
            else:
                out.append(str(rng.choice(pool).id))
        return out

    def export_bot(self, name_or_id: str, dest: str | Path) -> Path:
        """Copy a checkpoint to ``dest`` for standalone playtest use."""
        entry = self.resolve(name_or_id)
        src = self.root / entry.path if entry.path else self._ckpt_path(entry.id)
        dest_path = Path(dest)
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest_path)
        return dest_path
