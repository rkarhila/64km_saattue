"""Action faces, officers, and the small board fields the table shows.

This module does not import the observation layout. Both the JSON flatten
path and the fast engine path call the same helpers.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

import numpy as np

from sixtyfivekmconvoy.core.cards import ACTION_CATALOG
from sixtyfivekmconvoy.core.constants import ActionName
from sixtyfivekmconvoy.core.cost import parse_cost_rates

ACTION_NAMES: tuple[str, ...] = (
    ActionName.ATTACK,
    ActionName.ASSAULT,
    ActionName.BYPASS,
    ActionName.DEFEND,
    ActionName.EXIT,
    ActionName.HUMAN_SHIELDS,
    ActionName.ORDER,
    ActionName.PATROL,
    ActionName.PILLAGE,
    ActionName.PROMOTE,
    ActionName.REST,
    ActionName.RETREAT,
    ActionName.SCOUT,
    ActionName.SEARCH,
    ActionName.SERVICE,
    ActionName.SIGINT,
    ActionName.SOBER_UP,
    ActionName.WAIT,
    ActionName.SUICIDAL_ATTACK,
    ActionName.SEARCH_PILLAGE_COMBO,
    ActionName.PILLAGE_WITH_EXTRA_ATROCITY,
    ActionName.EXIT_FROM_C_WITH_COST,
    ActionName.SELL,
)
N_ACTIONS = len(ACTION_NAMES)
_ACTION_INDEX = {name: i for i, name in enumerate(ACTION_NAMES)}

PASSIVE_EFFECTS: tuple[str, ...] = (
    "no_boozing_while_pillaging",
    "extra_damage_in_zone_A",
    "extra_pillage_search_card",
    "atrocity_conversion",
    "extra_carry_capacity",
)
DISCARD_EFFECTS: tuple[str, ...] = (
    "suicidal_attack",
    "search_pillage_combo",
    "pillage_with_extra_atrocity",
    "exit_from_c_with_cost",
)

# One printed face. An empty face is the zero vector; the card header says
# whether a card is there.
F_ACT = 0
F_MOD = N_ACTIONS
F_ZA = F_MOD + 1
F_ZB = F_MOD + 2
F_ZC = F_MOD + 3
F_ZE = F_MOD + 4
F_TP = F_MOD + 5
F_TI = F_MOD + 6
F_TL = F_MOD + 7
F_TANY = F_MOD + 8
F_COST_T = F_MOD + 9
F_COST_U = F_MOD + 10
F_COST_A = F_MOD + 11
F_COST_FLAT = F_MOD + 12
F_TIRE = F_MOD + 13
F_TOX = F_MOD + 14
FACE_DIM = F_TOX + 1

HEADER_DIM = 7
H_PRESENT = 0
H_HIDDEN = 1
H_STACK = 2
H_ID = 3
H_RESOLVED = 4
H_FRUSTRATED = 5
H_CHOSEN = 6
# Printed faces, then one slot for an officer action on this unit.
FACE_SLOTS = 5
CARD_TOKEN_DIM = HEADER_DIM + FACE_SLOTS * FACE_DIM

OFFICER_DIM = 27
O_PRESENT = 0
O_HIDDEN = 1
O_SLOT = 2
O_PASSIVE = 3
O_DISCARD = 8
O_TP = 12
O_TI = 13
O_TL = 14
O_ZA = 15
O_ZB = 16
O_ZC = 17
O_ZE = 18
O_ACT = 19
O_MOD = 20
O_COST_T = 21
O_COST_U = 22
O_COST_A = 23
O_COST_FLAT = 24
O_TIRE = 25
O_TOX = 26

TUCK_SLOTS = 2
TUCK_DIM = TUCK_SLOTS * OFFICER_DIM
OFFICER_QUEUE_SLOTS = 6
UNIT_STACKS = 2
MARKER_SLOTS = 4
CARRY_SLOTS = 4
FORMATION_SEATS = 15
DENOMS = (1, 3, 5, 10)

RESISTANCE_FEAT = 2 + MARKER_SLOTS * 2 + 1
HIT_PILES = 4
PLAYER_FEAT = 4 + len(DENOMS) * 2 + 2
UNIT_FEAT = 31

# Choice-option tail: action one-hot, three placement seats, then the
# unit this card would be assigned to and two legality bits per face.
OPTION_ACTION_AT = 4
OPTION_TROOP_AT = 4 + N_ACTIONS
OPTION_TROOP_SEATS = 3
OPTION_UNIT_AT = OPTION_TROOP_AT + OPTION_TROOP_SEATS * 3
ASSIGN_FACE_SLOTS = 4
OPTION_UNIT_DIM = 3 + 4 + 1 + ASSIGN_FACE_SLOTS * 2


def _rel(seat: int, viewer: int, num_players: int) -> int:
    if seat < 0 or num_players <= 0:
        return int(seat)
    return (int(seat) - int(viewer)) % int(num_players)


def _zone_bits(text: str, out: np.ndarray, base: int) -> None:
    for ch in (text or "").upper():
        idx = "ABCE".find(ch)
        if idx >= 0:
            out[base + idx] = 1.0


def _troop_bits(text: str, out: np.ndarray, base: int, *, any_at: int | None) -> None:
    raw = (text or "").upper()
    if raw in ("A", "ANY"):
        out[base] = out[base + 1] = out[base + 2] = 1.0
        if any_at is not None:
            out[any_at] = 1.0
        return
    if "P" in raw:
        out[base] = 1.0
    if "I" in raw:
        out[base + 1] = 1.0
    if "L" in raw:
        out[base + 2] = 1.0


def _cost_bits(cost: Any, out: np.ndarray, base: int) -> None:
    parsed = parse_cost_rates(cost)
    if isinstance(parsed, int):
        out[base + 3] = parsed / 4.0
        return
    tired, influence, atrocity = parsed
    out[base] = tired / 2.0
    out[base + 1] = influence / 2.0
    out[base + 2] = atrocity / 2.0


def encode_action_face(face: dict[str, Any] | None) -> np.ndarray:
    out = np.zeros(FACE_DIM, dtype=np.float32)
    if not face:
        return out
    name = ActionName.normalize(face.get("action_name"))
    idx = _ACTION_INDEX.get(name or "")
    if idx is not None:
        out[F_ACT + idx] = 1.0
    out[F_MOD] = float(face.get("action_modifier") or 0) / 10.0
    _zone_bits(str(face.get("zone") or ""), out, F_ZA)
    _troop_bits(str(face.get("troop_type") or ""), out, F_TP, any_at=F_TANY)
    _cost_bits(face.get("cost"), out, F_COST_T)
    out[F_TIRE] = 1.0 if face.get("tire") else 0.0
    out[F_TOX] = 1.0 if face.get("intoxicate") else 0.0
    return out


@lru_cache(maxsize=None)
def _cached_faces(card_id: int) -> tuple[tuple[float, ...], ...]:
    card = ACTION_CATALOG.get(int(card_id))
    faces = card.describe() if card is not None else []
    packed: list[tuple[float, ...]] = []
    for i in range(FACE_SLOTS):
        face = faces[i] if i < len(faces) else None
        packed.append(tuple(float(v) for v in encode_action_face(face)))
    return tuple(packed)


def officer_action_face(officer: Any) -> dict[str, Any] | None:
    """The discard action an officer adds to a unit, or None for a passive."""
    if isinstance(officer, dict):
        if not officer.get("discard_effect") or not officer.get("action_type"):
            return None
        return {
            "action_name": officer.get("action_type"),
            "action_modifier": officer.get("action_modifier") or 0,
            "zone": officer.get("zone") or "",
            "troop_type": officer.get("troop_type") or "A",
            "cost": officer.get("cost") or "0",
            "tire": officer.get("tire") or 0,
            "intoxicate": officer.get("intoxicate") or 0,
        }
    describe = getattr(officer, "get_discard_action_description", None)
    if describe is None:
        return None
    return describe() or None


def first_officer_action_face(officers: list[Any] | None) -> dict[str, Any] | None:
    for officer in officers or []:
        face = officer_action_face(officer)
        if face is not None:
            return face
    return None


def encode_card_token(
    *,
    present: bool,
    visible: bool,
    card_id: int | None,
    stack: int,
    resolved: bool = False,
    frustrated: bool = False,
    chosen: int | None = None,
    officer_face: dict[str, Any] | None = None,
) -> np.ndarray:
    """One action card. A hidden card keeps the header and zeros the faces.

    ``officer_face`` is written into the last face slot when this card is on a
    unit that has an officer discard action. Hand cards leave that slot empty.
    """
    out = np.zeros(CARD_TOKEN_DIM, dtype=np.float32)
    if not present:
        return out
    out[H_PRESENT] = 1.0
    out[H_STACK] = float(stack) / 2.0
    if not visible or card_id is None:
        out[H_HIDDEN] = 1.0
        return out
    out[H_ID] = float(int(card_id)) / 25.0
    out[H_RESOLVED] = 1.0 if resolved else 0.0
    out[H_FRUSTRATED] = 1.0 if frustrated else 0.0
    if chosen is not None and int(chosen) >= 0:
        out[H_CHOSEN] = float(int(chosen)) / 3.0
    for i, face in enumerate(_cached_faces(int(card_id))):
        start = HEADER_DIM + i * FACE_DIM
        out[start : start + FACE_DIM] = face
    if officer_face:
        start = HEADER_DIM + (FACE_SLOTS - 1) * FACE_DIM
        out[start : start + FACE_DIM] = encode_action_face(officer_face)
    return out


def encode_officer(
    desc: dict[str, Any] | None, *, present: bool, visible: bool, slot: int
) -> np.ndarray:
    out = np.zeros(OFFICER_DIM, dtype=np.float32)
    if not present:
        return out
    out[O_PRESENT] = 1.0
    out[O_SLOT] = slot / 5.0
    if not visible or not desc:
        out[O_HIDDEN] = 1.0
        return out
    passive = desc.get("passive_effect") or ""
    if passive in PASSIVE_EFFECTS:
        out[O_PASSIVE + PASSIVE_EFFECTS.index(passive)] = 1.0
    discard = desc.get("discard_effect") or ""
    if discard in DISCARD_EFFECTS:
        out[O_DISCARD + DISCARD_EFFECTS.index(discard)] = 1.0
    _troop_bits(str(desc.get("troop_type") or ""), out, O_TP, any_at=None)
    _zone_bits(str(desc.get("zone") or ""), out, O_ZA)
    if desc.get("action_type"):
        name = ActionName.normalize(desc.get("action_type"))
        idx = _ACTION_INDEX.get(name or "")
        if idx is not None:
            out[O_ACT] = idx / float(N_ACTIONS)
        out[O_MOD] = float(desc.get("action_modifier") or 0) / 10.0
        _cost_bits(desc.get("cost"), out, O_COST_T)
        out[O_TIRE] = 1.0 if desc.get("tire") else 0.0
        out[O_TOX] = 1.0 if desc.get("intoxicate") else 0.0
    return out


def encode_tuck(officers: list[dict[str, Any]] | None) -> np.ndarray:
    out = np.zeros(TUCK_DIM, dtype=np.float32)
    for i, desc in enumerate(list(officers or [])[:TUCK_SLOTS]):
        if not isinstance(desc, dict):
            continue
        out[i * OFFICER_DIM : (i + 1) * OFFICER_DIM] = encode_officer(
            desc, present=True, visible=True, slot=i
        )
    return out


def hand_tokens(card_ids: list[Any], n_slots: int) -> np.ndarray:
    out = np.zeros((n_slots, CARD_TOKEN_DIM), dtype=np.float32)
    for i, card_id in enumerate(list(card_ids)[:n_slots]):
        try:
            cid = int(card_id)
        except (TypeError, ValueError):
            continue
        out[i] = encode_card_token(
            present=True, visible=True, card_id=cid, stack=0
        )
    return out


def stack_tokens(entries: list[dict[str, Any]], n_slots: int = UNIT_STACKS) -> np.ndarray:
    out = np.zeros((n_slots, CARD_TOKEN_DIM), dtype=np.float32)
    for entry in entries[:n_slots]:
        slot = int(entry.get("stack") or 0)
        if slot < 0 or slot >= n_slots:
            continue
        chosen = entry.get("chosen")
        out[slot] = encode_card_token(
            present=bool(entry.get("present", True)),
            visible=bool(entry.get("visible")),
            card_id=entry.get("card_id"),
            stack=slot,
            resolved=bool(entry.get("resolved")),
            frustrated=bool(entry.get("frustrated")),
            chosen=None if chosen is None else int(chosen),
            officer_face=entry.get("officer_face"),
        )
    return out


def stack_flags(entries: list[dict[str, Any]]) -> tuple[bool, bool, bool, bool]:
    return (
        any(entry.get("present", True) for entry in entries),
        any(bool(entry.get("visible")) for entry in entries),
        any(bool(entry.get("resolved")) for entry in entries),
        any(bool(entry.get("frustrated")) for entry in entries),
    )


def _chosen(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def entries_from_unit(unit: Any, *, viewer_is_owner: bool) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    cards = list(getattr(unit, "actioncard", []) or [])
    resolutions = list(getattr(unit, "action_resolution", []) or [])
    taken = list(getattr(unit, "actiontaken", []) or [])
    revealed = set(getattr(unit, "revealed_card_indices", set()) or ())
    officer_face = first_officer_action_face(getattr(unit, "officers", None))
    for i, card_id in enumerate(cards):
        resolution = None
        if i < len(resolutions) and resolutions[i] is not None:
            resolution = resolutions[i]
        elif i < len(taken) and taken[i] is not None:
            resolution = {"kind": "card", "face_index": None}
        resolved = resolution is not None
        face_up = viewer_is_owner or resolved or i in revealed
        entries.append(
            {
                "present": True,
                "visible": face_up,
                "card_id": int(card_id) if face_up else None,
                "stack": i,
                "resolved": resolved,
                "frustrated": bool(resolution and resolution.get("kind") == "frustrated"),
                "chosen": _chosen(resolution.get("face_index")) if resolution else None,
                "officer_face": officer_face if face_up else None,
            }
        )
    return entries


def entries_from_action_json(
    action: dict[str, Any] | None, officers: list[Any] | None = None
) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    officer_face = first_officer_action_face(officers)
    for entry in list((action or {}).get("cards") or []):
        if not isinstance(entry, dict):
            continue
        visible = bool(entry.get("face_up"))
        raw = entry.get("card")
        try:
            card_id = int(raw) if visible and raw is not None else None
        except (TypeError, ValueError):
            card_id = None
            visible = False
        entries.append(
            {
                "present": True,
                "visible": visible and card_id is not None,
                "card_id": card_id,
                "stack": int(entry.get("index") or len(entries)),
                "resolved": bool(entry.get("resolved")),
                "frustrated": bool(entry.get("frustrated")),
                "chosen": _chosen(entry.get("chosen_face_index")),
                "officer_face": officer_face if visible and card_id is not None else None,
            }
        )
    return entries


def officer_queue_tokens(
    entries: list[tuple[dict[str, Any] | None, bool]], n_slots: int = OFFICER_QUEUE_SLOTS
) -> np.ndarray:
    out = np.zeros((n_slots, OFFICER_DIM), dtype=np.float32)
    for i, (desc, visible) in enumerate(entries[:n_slots]):
        out[i] = encode_officer(
            desc if visible else None,
            present=True,
            visible=bool(visible and desc),
            slot=i,
        )
    return out


def chip_counts(counters: list[Any] | None) -> list[float]:
    found = {value: 0 for value in DENOMS}
    for counter in counters or []:
        raw = counter.get("value") if isinstance(counter, dict) else getattr(counter, "value", None)
        try:
            value = int(raw)
        except (TypeError, ValueError):
            continue
        if value in found:
            found[value] += 1
    return [found[value] / 10.0 for value in DENOMS]


def marker_features(markers: list[Any] | None) -> np.ndarray:
    """Four damage values, four categories, then the full count / 4."""
    out = np.zeros(MARKER_SLOTS * 2 + 1, dtype=np.float32)
    rows = list(markers or [])
    for i, marker in enumerate(rows[:MARKER_SLOTS]):
        if not isinstance(marker, dict):
            continue
        out[i] = float(marker.get("damage") or 0) / 10.0
        out[MARKER_SLOTS + i] = float(marker.get("category") or 0) / 10.0
    out[-1] = len(rows) / 4.0
    return out


def carry_features(carry: list[Any] | None) -> np.ndarray:
    out = np.zeros(CARRY_SLOTS, dtype=np.float32)
    for i, value in enumerate(list(carry or [])[:CARRY_SLOTS]):
        try:
            out[i] = float(value) / 10.0
        except (TypeError, ValueError):
            continue
    return out


def formation_features(
    pattern: list[Any] | tuple[Any, ...] | None,
    viewer: int,
    num_players: int,
) -> np.ndarray:
    """Convoy order, front first. The viewer's own seats are always 1/6."""
    out = np.zeros(FORMATION_SEATS, dtype=np.float32)
    if not pattern:
        return out
    for i, owner in enumerate(list(pattern)[:FORMATION_SEATS]):
        try:
            seat = int(owner)
        except (TypeError, ValueError):
            continue
        out[i] = (_rel(seat, viewer, num_players) + 1) / 6.0
    return out


def resistance_features(res: Any) -> np.ndarray:
    out = np.zeros(RESISTANCE_FEAT, dtype=np.float32)
    if res is None:
        return out
    if isinstance(res, dict):
        if not res:
            return out
        active = bool(res.get("active"))
        durability = res.get("durability") or 0
        markers = res.get("damage_markers") or []
        named = bool(res.get("name"))
    else:
        active = bool(getattr(res, "active", False))
        durability = getattr(res, "durability", 0) or 0
        markers = getattr(res, "damage_markers", []) or []
        named = bool(getattr(res, "name", None))
    if not named and not active:
        return out
    out[0] = 1.0 if active else 0.0
    out[1] = float(durability) / 20.0
    out[2:] = marker_features(markers)
    return out


def hit_pile_features(decks: list[Any] | None) -> np.ndarray:
    out = np.zeros(HIT_PILES, dtype=np.float32)
    order = {1: 0, 3: 1, 5: 2, 10: 3}
    for deck in decks or []:
        if not isinstance(deck, dict):
            continue
        try:
            category = int(deck.get("category") or 0)
        except (TypeError, ValueError):
            continue
        idx = order.get(category)
        if idx is not None:
            out[idx] = float(deck.get("deck") or 0) / 20.0
    return out


def hit_piles_from_engine(engine: Any) -> list[dict[str, int]]:
    decks = getattr(engine, "hit_decks", {}) or {}
    rows = []
    for category in DENOMS:
        deck = decks.get(category)
        rows.append(
            {
                "category": category,
                "deck": len(deck.deck) if deck is not None else 0,
            }
        )
    return rows


def player_features(player: Any, *, hand_scale: float) -> np.ndarray:
    out = np.zeros(PLAYER_FEAT, dtype=np.float32)
    if player is None:
        return out
    if isinstance(player, dict):
        out[0] = float(player.get("cash_this_round") or 0) / 20.0
        out[1] = float(player.get("total_cash") or 0) / 50.0
        out[2] = float(player.get("promotion_points") or 0) / 10.0
        out[3] = float(player.get("card_count") or 0) / hand_scale
        out[4:8] = chip_counts(player.get("round_counters"))
        out[8:12] = chip_counts(player.get("bank_counters"))
        out[12] = float(player.get("deck") or 0) / 40.0
        out[13] = float(player.get("discard") or 0) / 40.0
        return out
    out[0] = float(player.this_round_cash) / 20.0
    out[1] = float(player.total_cash) / 50.0
    out[2] = float(player.promotion_points) / 10.0
    out[3] = float(len(player.action_cards)) / hand_scale
    out[4:8] = chip_counts(player.round_counters)
    out[8:12] = chip_counts(player.bank_counters)
    deck = player.action_deck
    if deck is not None:
        draw_n, discard_n = deck.get_sizes()
        out[12] = draw_n / 40.0
        out[13] = discard_n / 40.0
    return out


def _defence_bits(letter: str | None, out: np.ndarray, base: int) -> None:
    idx = {"A": 0, "G": 1, "S": 2}.get((letter or "").upper()[:1])
    if idx is not None:
        out[base + idx] = 1.0


def unit_features(
    *,
    unit_type: str,
    owner: int,
    viewer: int,
    num_players: int,
    tired: float,
    influence: float,
    atrocities: float,
    carry: list[Any],
    zone: str,
    defending: str | None,
    markers: list[Any],
    has_card: bool,
    face_up: bool,
    resolved: bool,
    frustrated: bool,
) -> np.ndarray:
    out = np.zeros(UNIT_FEAT, dtype=np.float32)
    type_index = {
        "panzer": 0,
        "infantry": 1,
        "logistics": 2,
        "pnz": 0,
        "inf": 1,
        "log": 2,
    }
    out[type_index.get((unit_type or "").lower(), 0)] = 1.0
    denom = max(1, num_players - 1)
    out[3] = float(_rel(owner, viewer, num_players)) / denom
    out[4] = float(tired) / 10.0
    out[5] = float(influence) / 10.0
    out[6] = float(atrocities) / 10.0
    out[7:11] = carry_features(carry)
    _zone_bits(zone, out, 11)
    _defence_bits(defending, out, 15)
    out[18:27] = marker_features(markers)
    out[27] = 1.0 if has_card else 0.0
    out[28] = 1.0 if face_up else 0.0
    out[29] = 1.0 if resolved else 0.0
    out[30] = 1.0 if frustrated else 0.0
    return out


def action_option_one_hot(name: str | None, out: np.ndarray) -> None:
    idx = _ACTION_INDEX.get(ActionName.normalize(name) or "")
    if idx is not None:
        out[OPTION_ACTION_AT + idx] = 1.0


def write_assign_option(payload: dict[str, Any] | None, card_id: Any, out: np.ndarray) -> None:
    """Stamp the target unit and each face's legality onto one card option."""
    if not payload or payload.get("reason") != "assign":
        return
    unit = payload.get("assign_unit") or {}
    troop = {"panzer": 0, "infantry": 1, "logistics": 2}.get(
        str(unit.get("unit_type") or "").lower()
    )
    if troop is not None:
        out[OPTION_UNIT_AT + troop] = 1.0
    _zone_bits(str(unit.get("zone") or ""), out, OPTION_UNIT_AT + 3)
    try:
        place = int(unit.get("place"))
    except (TypeError, ValueError):
        place = -1
    if place >= 0:
        out[OPTION_UNIT_AT + 7] = place / max(1, FORMATION_SEATS - 1)
    faces = (payload.get("assign_faces") or {}).get(str(card_id)) or []
    for i, row in enumerate(list(faces)[:ASSIGN_FACE_SLOTS]):
        if not isinstance(row, (list, tuple)) or len(row) < 2:
            continue
        base = OPTION_UNIT_AT + 8 + i * 2
        out[base] = 1.0 if row[0] else 0.0
        out[base + 1] = 1.0 if row[1] else 0.0


def troop_option_one_hot(value: Any, out: np.ndarray) -> None:
    """Write one placement order as three seats, each a P/I/L bit."""
    from sixtyfivekmconvoy.core.setup_layouts import PLACEMENT_ORDERS

    try:
        index = int(value)
    except (TypeError, ValueError):
        return
    if not 0 <= index < len(PLACEMENT_ORDERS):
        return
    for seat, troop in enumerate(PLACEMENT_ORDERS[index]):
        out[OPTION_TROOP_AT + seat * 3 + troop] = 1.0
