"""Printed mauling, resistance, and pillage faces as a fixed float vector.

One linear layer embeds each slot. Face-down slots keep the deck type and the
queue index, and zero the effect. Empty pads are the zero vector.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

import numpy as np

from sixtyfivekmconvoy.core.cards import (
    MAULING_CATALOG,
    PILLAGE_CATALOG,
    RESISTANCE_CATALOG,
)

QUEUE_SLOTS = 8
CARD_FEAT_DIM = 41
CONTENT_QUEUES = ("resistance", "pillage", "mauling")
N_CARD_SLOTS = len(CONTENT_QUEUES) * QUEUE_SLOTS

F_PRESENT = 0
F_HIDDEN = 1
F_TYPE_MAULING = 2
F_TYPE_RESISTANCE = 3
F_TYPE_PILLAGE = 4
F_SLOT = 5
F_ZONE_A = 6
F_ZONE_B = 7
F_ZONE_C = 8
F_ZONE_E = 9
F_WHOLE_ZONE = 10
F_REL_FRONT = 11
F_REL_BACK = 12
F_WHICH = 13
F_TYPE_P = 14
F_TYPE_I = 15
F_TYPE_L = 16
F_ATROCITY = 17
F_HIT = 18
F_FROM_RESISTANCE = 19
F_DISCARD = 20
F_FAIL_HIT = 21
F_ATK_A = 22
F_ATK_G = 23
F_ATK_S = 24
F_ATK_R = 25
F_ATROCITY_THRESHOLD = 26
F_AMBUSH = 27
F_REORDER = 28
F_COUNTER = 29
F_RES_LOOT = 30
F_DURABILITY = 31
F_DESTROY_CASH = 32
F_MIN_PLAYERS = 33
F_STARTING = 34
F_CASH = 35
F_LOOT = 36
F_ATROCITIES = 37
F_DRUNK_ATROCITIES = 38
F_CARDS = 39
F_INTOXICATE = 40

_TYPE_INDEX = {
    "mauling": F_TYPE_MAULING,
    "resistance": F_TYPE_RESISTANCE,
    "pillage": F_TYPE_PILLAGE,
}
_ZONE_INDEX = {"A": F_ZONE_A, "B": F_ZONE_B, "C": F_ZONE_C, "E": F_ZONE_E}
_WHICH = {"first": 1.0, "second": 0.5, "second_last": -0.5, "last": -1.0}
_TROOP = {
    "p": F_TYPE_P,
    "pnz": F_TYPE_P,
    "panzer": F_TYPE_P,
    "i": F_TYPE_I,
    "inf": F_TYPE_I,
    "infantry": F_TYPE_I,
    "l": F_TYPE_L,
    "log": F_TYPE_L,
    "logistics": F_TYPE_L,
}
_ATROCITY_KEYS = frozenset({"atrocity", "atrocities", "atr"})
_ATTACK = {"A": F_ATK_A, "G": F_ATK_G, "S": F_ATK_S, "R": F_ATK_R}
_CATALOGS = {
    "mauling": MAULING_CATALOG,
    "resistance": RESISTANCE_CATALOG,
    "pillage": PILLAGE_CATALOG,
}


def _num(value: Any) -> float:
    if value is None or isinstance(value, bool):
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if not text or text.lower() == "reorder":
        return 0.0
    try:
        return float(text)
    except ValueError:
        return 0.0


def _loot_total(value: Any) -> float:
    if isinstance(value, (list, tuple)):
        return float(sum(_num(item) for item in value))
    return _num(value)


def encode_target(target: str, out: np.ndarray) -> None:
    """Write a target code into indices 6–17. ``AB`` sets both zone bits."""
    text = (target or "").strip()
    if not text or text == "-":
        return
    lower = text.lower()
    for prefix in ("second_last:", "second:", "first:", "last:"):
        if lower.startswith(prefix):
            which, _, key = lower.partition(":")
            out[F_WHICH] = _WHICH[which]
            key = key.strip()
            if key in _ATROCITY_KEYS:
                out[F_ATROCITY] = 1.0
            elif key in _TROOP:
                out[_TROOP[key]] = 1.0
            return
    upper = text.upper()
    if upper and all(ch in "ABCE" for ch in upper):
        for ch in upper:
            out[_ZONE_INDEX[ch]] = 1.0
        out[F_WHOLE_ZONE] = 1.0
        return
    if upper[:1] in "ABCE":
        rel = upper[1:]
        if rel and (rel.isdigit() or (rel[0] in "+-" and rel[1:].isdigit())):
            out[_ZONE_INDEX[upper[0]]] = 1.0
            steps = int(rel)
            if steps > 0:
                out[F_REL_FRONT] = steps / 6.0
            elif steps < 0:
                out[F_REL_BACK] = abs(steps) / 6.0


def _fill_mauling(out: np.ndarray, effect: dict[str, Any]) -> None:
    encode_target(str(effect.get("target") or ""), out)
    attack = str(effect.get("attack_type") or "G").strip().upper()[:1] or "G"
    # R stores a placeholder category so the deck validates. The category that
    # is actually drawn comes from the active resistance card.
    if attack == "R":
        out[F_FROM_RESISTANCE] = 1.0
    else:
        out[F_HIT] = _num(effect.get("hit_category")) / 10.0
    out[F_DISCARD] = _num(effect.get("discard")) / 4.0
    out[F_FAIL_HIT] = _num(effect.get("fail_hit_category")) / 10.0
    atk = _ATTACK.get(attack)
    if atk is not None:
        out[atk] = 1.0
    out[F_ATROCITY_THRESHOLD] = _num(effect.get("atrocity_threshold")) / 10.0


def _fill_resistance(out: np.ndarray, desc: dict[str, Any]) -> None:
    effect = desc.get("effect") or {}
    encode_target(str(effect.get("ambush_target") or ""), out)
    ambush = effect.get("ambush_damage")
    if str(ambush or "").strip().lower() == "reorder":
        out[F_REORDER] = 1.0
    else:
        out[F_AMBUSH] = _num(ambush) / 10.0
    out[F_COUNTER] = _num(effect.get("resistance_damage")) / 10.0
    out[F_RES_LOOT] = _num(effect.get("loot")) / 6.0
    out[F_DURABILITY] = _num(effect.get("durability")) / 12.0
    out[F_DESTROY_CASH] = _num(effect.get("cash_for_destroying")) / 4.0
    out[F_MIN_PLAYERS] = _num(desc.get("min_players")) / 5.0
    out[F_STARTING] = 1.0 if desc.get("starting") else 0.0


def _fill_pillage(out: np.ndarray, reward: dict[str, Any]) -> None:
    out[F_CASH] = _num(reward.get("cash")) / 5.0
    out[F_LOOT] = _loot_total(reward.get("loot")) / 5.0
    out[F_ATROCITIES] = _num(reward.get("atrocities"))
    out[F_DRUNK_ATROCITIES] = _num(reward.get("atrocities_if_under_influence"))
    out[F_CARDS] = _num(reward.get("cards")) / 2.0
    out[F_INTOXICATE] = _num(reward.get("intoxicate"))


@lru_cache(maxsize=None)
def printed_card_features(kind: str, card_id: int) -> tuple[float, ...]:
    """Face-up contents with slot 0. Missing ids stay type-only."""
    out = np.zeros(CARD_FEAT_DIM, dtype=np.float32)
    out[F_PRESENT] = 1.0
    out[_TYPE_INDEX[kind]] = 1.0
    card = _CATALOGS[kind].get(int(card_id))
    if card is None:
        return tuple(float(v) for v in out)
    desc = card.describe()
    if kind == "mauling":
        _fill_mauling(out, desc.get("effect") or {})
    elif kind == "resistance":
        _fill_resistance(out, desc)
    else:
        _fill_pillage(out, desc.get("reward") or {})
    return tuple(float(v) for v in out)


def encode_slot(
    kind: str,
    card_id: int | None,
    *,
    visible: bool,
    slot: int,
) -> np.ndarray:
    """One queue position. A hidden card does not reveal the printed face."""
    out = np.zeros(CARD_FEAT_DIM, dtype=np.float32)
    if card_id is None and visible:
        return out
    if not visible:
        out[F_PRESENT] = 1.0
        out[F_HIDDEN] = 1.0
        out[_TYPE_INDEX[kind]] = 1.0
        out[F_SLOT] = slot / 5.0
        return out
    cached = printed_card_features(kind, int(card_id))
    out[:] = cached
    out[F_SLOT] = slot / 5.0
    return out


def encode_queue(
    kind: str, entries: list[tuple[int | None, bool]]
) -> np.ndarray:
    """Front-to-back slots. Entries past the eighth are dropped."""
    out = np.zeros((QUEUE_SLOTS, CARD_FEAT_DIM), dtype=np.float32)
    for slot, (card_id, visible) in enumerate(entries[:QUEUE_SLOTS]):
        out[slot] = encode_slot(kind, card_id, visible=visible, slot=slot)
    return out


def encode_card_block(
    queues: dict[str, list[tuple[int | None, bool]]],
) -> np.ndarray:
    """Resistance, then pillage, then mauling. Shape ``(24, 41)``."""
    parts = [encode_queue(kind, list(queues.get(kind) or [])) for kind in CONTENT_QUEUES]
    return np.concatenate(parts, axis=0)
