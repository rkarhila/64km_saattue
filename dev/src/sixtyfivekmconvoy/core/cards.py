"""Card decks, queues, and CSV loaders."""

from __future__ import annotations

import csv
import os
import random
from dataclasses import dataclass, field
from typing import Any

from .constants import ActionName

_DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "cards")


def _cards_path(name: str) -> str:
    return os.path.join(_DATA_DIR, name)


# ---------------------------------------------------------------------------
# Generic deck / queue
# ---------------------------------------------------------------------------


class CardDeck:
    """Draw/discard pile with optional name/effect lookup by card id."""

    def __init__(
        self,
        card_ids: list[int] | None = None,
        *,
        shuffled: bool = True,
        names_and_effects: dict[int, Any] | None = None,
        rng: random.Random | None = None,
    ):
        self.rng = rng or random.Random()
        self.names_and_effects = names_and_effects or {}
        if card_ids is None:
            card_ids = list(self.names_and_effects.keys())
        self.deck = list(card_ids)
        self.discard: list[int] = []
        if shuffled:
            self.rng.shuffle(self.deck)

    def get_card(self, shuffle_if_necessary: bool = True) -> int:
        if not self.deck:
            if not shuffle_if_necessary or not self.discard:
                raise RuntimeError("Deck empty and cannot reshuffle")
            self.reshuffle()
        return self.deck.pop(0)

    def return_card(self, card: int) -> None:
        self.deck.insert(0, card)

    def discard_card(self, card: int) -> None:
        self.discard.append(card)

    def reshuffle(self) -> None:
        self.deck = self.discard
        self.rng.shuffle(self.deck)
        self.discard = []

    def get_sizes(self) -> tuple[int, int]:
        return len(self.deck), len(self.discard)

    def to_json(self) -> dict:
        return {"deck": len(self.deck), "discard": len(self.discard)}

    def get_name(self, card: int) -> str | None:
        data = self.names_and_effects.get(card)
        if data is None:
            return None
        if hasattr(data, "name"):
            return data.name
        if isinstance(data, dict):
            return data.get("name")
        return None

    def describe(self, card: int) -> Any:
        data = self.names_and_effects[card]
        if hasattr(data, "describe"):
            return data.describe()
        return data


class CardQueue:
    def __init__(self, deck: CardDeck | None = None):
        self.cards_and_visibilities: list[list] = []
        self.deck = deck

    def __len__(self) -> int:
        return len(self.cards_and_visibilities)

    def remove_card(self, index: int = 0) -> tuple[int, bool]:
        card, visibility = self.cards_and_visibilities.pop(index)
        return card, visibility

    def put_card(self, card: int, visible: bool = False) -> None:
        self.cards_and_visibilities.append([card, visible])

    def return_card(self, card: int, visible: bool = False) -> None:
        self.cards_and_visibilities.insert(0, [card, visible])

    def contains_hidden_cards(self) -> bool:
        return any(not vis for _, vis in self.cards_and_visibilities)

    def reveal_card(self, index: int = 0) -> None:
        self.cards_and_visibilities[index][1] = True

    def reveal_next_hidden(self) -> None:
        for entry in self.cards_and_visibilities:
            if not entry[1]:
                entry[1] = True
                break

    def to_arr(self) -> list:
        if self.deck is not None and self.deck.names_and_effects:
            return [
                self.deck.get_name(c) if vis else "?"
                for c, vis in self.cards_and_visibilities
            ]
        return [c if vis else "?" for c, vis in self.cards_and_visibilities]

    def to_json(self) -> list[dict[str, Any]]:
        """Queue cards for UI. Index 0 is the front (next to resolve)."""
        out: list[dict[str, Any]] = []
        for card_id, visible in self.cards_and_visibilities:
            if not visible:
                out.append({"visible": False})
                continue
            entry: dict[str, Any] = {
                "visible": True,
                "id": card_id,
                "name": None,
                "detail": None,
            }
            if self.deck is not None:
                entry["name"] = self.deck.get_name(card_id) or str(card_id)
                try:
                    desc = self.deck.describe(card_id)
                except KeyError:
                    desc = None
                entry["detail"] = queue_card_detail(desc)
            else:
                entry["name"] = str(card_id)
            out.append(entry)
        return out

    def describe(self, index: int) -> Any:
        assert self.deck is not None
        return self.deck.describe(self.cards_and_visibilities[index][0])


def queue_card_detail(desc: Any) -> str | None:
    """Short secondary line for a revealed queue card."""
    if desc is None:
        return None
    if isinstance(desc, list):
        # Action cards are not normally queued; join face names if they are.
        names = [
            d.get("name") for d in desc if isinstance(d, dict) and d.get("name")
        ]
        return " · ".join(names) if names else None
    if not isinstance(desc, dict):
        return str(desc)
    for key in ("passive_description", "discard_description"):
        text = (desc.get(key) or "").strip()
        if text:
            return text
    for key in ("effect", "reward"):
        payload = desc.get(key)
        if isinstance(payload, dict) and payload:
            return ", ".join(f"{k}:{v}" for k, v in payload.items())
        if payload:
            return str(payload)
    return None


# ---------------------------------------------------------------------------
# Card types
# ---------------------------------------------------------------------------


@dataclass
class CardAction:
    cost: str
    action_name: str
    action_modifier: int
    zone: str
    troop_type: str
    tire: int
    intoxicate: int
    name: str
    limits: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.limits:
            if self.troop_type == "A":
                self.limits = {"I": self.zone, "P": self.zone, "L": self.zone}
            else:
                self.limits = {self.troop_type: self.zone}

    def describe(self) -> dict:
        return {
            "name": self.name,
            "cost": self.cost,
            "action_name": self.action_name,
            "action_modifier": self.action_modifier,
            "zone": self.zone,
            "troop_type": self.troop_type,
            "tire": self.tire,
            "intoxicate": self.intoxicate,
            "limits": self.limits,
        }


@dataclass
class ActionCard:
    id: int
    actions: list[CardAction]

    def describe(self) -> list[dict]:
        return [a.describe() for a in self.actions]


@dataclass
class OfficerCard:
    officer_id: int
    name: str
    passive_effect: str | None
    discard_effect: str | None
    passive_description: str = ""
    discard_description: str = ""
    troop_type: str | None = None
    zone: str | None = None
    action_type: str | None = None
    action_modifier: int | None = None
    cost: str | None = None
    tire: int | None = None
    intoxicate: int | None = None

    def describe(self) -> dict:
        return {
            "officer_id": self.officer_id,
            "name": self.name,
            "passive_effect": self.passive_effect,
            "discard_effect": self.discard_effect,
            "passive_description": self.passive_description,
            "discard_description": self.discard_description,
            "troop_type": self.troop_type,
            "zone": self.zone,
            "action_type": self.action_type,
            "action_modifier": self.action_modifier,
            "cost": self.cost,
            "tire": self.tire,
            "intoxicate": self.intoxicate,
        }

    def get_discard_action_description(self) -> dict | None:
        if not self.discard_effect or not self.action_type:
            return None
        return {
            "name": self.action_type,
            "action_name": ActionName.normalize(self.action_type),
            "action_modifier": self.action_modifier if self.action_modifier is not None else 0,
            "zone": self.zone or "",
            "troop_type": self.troop_type or "A",
            "cost": self.cost or "0",
            "tire": self.tire if self.tire is not None else 0,
            "intoxicate": self.intoxicate if self.intoxicate is not None else 0,
            "is_officer_discard": True,
            "officer": self,
            "limits": (
                {"I": self.zone or "ABCE", "P": self.zone or "ABCE", "L": self.zone or "ABCE"}
                if (self.troop_type or "A") == "A"
                else {(self.troop_type or "P"): self.zone or "ABCE"}
            ),
        }


@dataclass
class PillageCard:
    id: int
    name: str
    reward: dict

    def describe(self) -> dict:
        return {"name": self.name, "reward": self.reward}


@dataclass
class MaulingCard:
    id: int
    name: str
    effect: dict

    def describe(self) -> dict:
        return {"name": self.name, "effect": self.effect}


@dataclass
class ResistanceCard:
    id: int
    name: str
    effect: dict

    def describe(self) -> dict:
        return {"name": self.name, "effect": self.effect}


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------


def load_action_deck() -> dict[int, ActionCard]:
    deck: dict[int, dict[int, CardAction]] = {}
    with open(_cards_path("action.csv"), encoding="utf-8") as f:
        for row in csv.DictReader(f):
            zone = (row.get("zone") or "").strip()
            if not zone:
                continue
            action_type = row["action_type"].strip()
            if not action_type:
                continue
            card_id = int(row["card_id"])
            action_index = int(row["action_index"])
            action = CardAction(
                cost=(row.get("cost") or "0").strip() or "0",
                action_name=ActionName.normalize(action_type) or action_type,
                action_modifier=int(row["action_modifier"].strip() or 0),
                zone=zone,
                troop_type=row["troop_type"].strip(),
                tire=int(row["tire"].strip() or 0),
                intoxicate=int(row["intoxicate"].strip() or 0),
                name=(row["name"].strip() or action_type),
            )
            deck.setdefault(card_id, {})[action_index] = action
    return {
        cid: ActionCard(id=cid, actions=[bucket[i] for i in sorted(bucket)])
        for cid, bucket in sorted(deck.items())
    }


def load_officer_deck() -> dict[int, OfficerCard]:
    deck: dict[int, OfficerCard] = {}
    with open(_cards_path("officer.csv"), encoding="utf-8") as f:
        for row in csv.DictReader(f):
            oid = int(row["officer_id"].strip())
            deck[oid] = OfficerCard(
                officer_id=oid,
                name=row["name"].strip(),
                passive_effect=row["passive_effect"].strip() or None,
                discard_effect=row["discard_effect"].strip() or None,
                passive_description=row["passive_description"].strip(),
                discard_description=row["discard_description"].strip(),
                troop_type=row.get("troop_type", "").strip() or None,
                zone=row.get("zone", "").strip() or None,
                action_type=row.get("action_type", "").strip() or None,
                action_modifier=(
                    int(row["action_modifier"].strip())
                    if row.get("action_modifier", "").strip()
                    else None
                ),
                cost=row.get("cost", "").strip() or None,
                tire=int(row["tire"].strip()) if row.get("tire", "").strip() else None,
                intoxicate=(
                    int(row["intoxicate"].strip())
                    if row.get("intoxicate", "").strip()
                    else None
                ),
            )
    return deck


def load_pillage_deck() -> dict[int, PillageCard]:
    deck: dict[int, PillageCard] = {}
    with open(_cards_path("pillage.csv"), encoding="utf-8") as f:
        for row in csv.DictReader(f):
            loot_str = row["loot"].strip()
            loot = [int(x.strip()) for x in loot_str.split(",") if x.strip()] if loot_str else []
            cid = int(row["card_id"].strip())
            deck[cid] = PillageCard(
                id=cid,
                name=row["name"].strip(),
                reward={
                    "cash": int(row["cash"].strip()),
                    "loot": loot,
                    "atrocities": int(row["atrocities"].strip()),
                },
            )
    return deck


def load_mauling_deck() -> dict[int, MaulingCard]:
    deck: dict[int, MaulingCard] = {}
    with open(_cards_path("mauling.csv"), encoding="utf-8") as f:
        for row in csv.DictReader(f):
            cid = int(row["card_id"].strip())
            deck[cid] = MaulingCard(
                id=cid,
                name=row["name"].strip(),
                effect={
                    "damage": [int(row["damage_min"].strip()), int(row["damage_max"].strip())],
                    "target": row["target"].strip(),
                    "atrocity_threshold": int(row["atrocity_threshold"].strip()),
                    "type": row["type"].strip(),
                },
            )
    return deck


def load_resistance_deck() -> dict[int, ResistanceCard]:
    deck: dict[int, ResistanceCard] = {}
    with open(_cards_path("resistance.csv"), encoding="utf-8") as f:
        for row in csv.DictReader(f):
            cid = int(row["card_id"].strip())
            deck[cid] = ResistanceCard(
                id=cid,
                name=row["name"].strip(),
                effect={
                    "attack": int(row["attack"].strip()),
                    "target": row["target"].strip(),
                    "loot": int(row["loot"].strip()),
                    "durability": int(row["durability"].strip()),
                    "damage": {
                        "I": int(row["damage_I"].strip()),
                        "P": int(row["damage_P"].strip()),
                    },
                },
            )
    return deck


# Cached catalogs (immutable definitions)
ACTION_CATALOG = load_action_deck()
OFFICER_CATALOG = load_officer_deck()
PILLAGE_CATALOG = load_pillage_deck()
MAULING_CATALOG = load_mauling_deck()
RESISTANCE_CATALOG = load_resistance_deck()
