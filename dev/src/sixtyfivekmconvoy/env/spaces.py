"""Observation helpers for ConvoyEnv."""

from __future__ import annotations

from typing import Any

import numpy as np

from sixtyfivekmconvoy.core.constants import ChoiceType
from sixtyfivekmconvoy.env.card_features import (
    CARD_FEAT_DIM,
    N_CARD_SLOTS,
    QUEUE_SLOTS,
    encode_card_block,
)
from sixtyfivekmconvoy.env.table_features import (
    CARD_TOKEN_DIM,
    FORMATION_SEATS,
    HIT_PILES,
    N_ACTIONS,
    OFFICER_DIM,
    OFFICER_QUEUE_SLOTS,
    OPTION_UNIT_DIM,
    PLAYER_FEAT,
    RESISTANCE_FEAT,
    TUCK_DIM,
    UNIT_FEAT,
    UNIT_STACKS,
    action_option_one_hot,
    encode_tuck,
    entries_from_action_json,
    entries_from_unit,
    formation_features,
    hand_tokens,
    hit_pile_features,
    hit_piles_from_engine,
    officer_queue_tokens,
    player_features,
    resistance_features,
    stack_flags,
    stack_tokens,
    troop_option_one_hot,
    write_assign_option,
    unit_features,
)
from sixtyfivekmconvoy.rl.events import EVENT_FIELDS, EVENT_WINDOW, events_to_features


MAX_UNITS = 15
MAX_HAND = 20
MAX_PLAYERS = 5
# Discrete action index budget (legacy flat path / mask length).
MAX_LEGAL = 256
# Autoregressive choice decoder caps.
MAX_OPTIONS = 32
MAX_PICKS = 8
MAX_QUEUE_VISIBLE = QUEUE_SLOTS
# valid, id, slot, type, action one-hot, 3 placement seats, then the
# target unit (troop, zone, place) and two legality bits on each face.
OPTION_FEAT_DIM = 4 + N_ACTIONS + 9 + OPTION_UNIT_DIM


def _norm_id(card_id: Any, scale: float = 100.0) -> float:
    try:
        return float(int(card_id)) / scale
    except (TypeError, ValueError):
        return 0.0


def _queue_entries(
    queue_json: list[Any] | None,
) -> tuple[list[float], list[tuple[int | None, bool]], list[float]]:
    """Counts, ordered (id, visible) slots, and packed face-up ids for officers."""
    q = queue_json or []
    hidden = 0
    slots: list[tuple[int | None, bool]] = []
    visible_ids: list[float] = []
    for entry in q:
        if not isinstance(entry, dict):
            if entry == "?" or entry is None:
                hidden += 1
                slots.append((None, False))
            else:
                visible_ids.append(_norm_id(entry) if isinstance(entry, int) else 0.5)
                slots.append((int(entry) if isinstance(entry, int) else None, True))
            continue
        if entry.get("visible"):
            visible_ids.append(_norm_id(entry.get("id")))
            raw_id = entry.get("id")
            try:
                card_id: int | None = int(raw_id)
            except (TypeError, ValueError):
                card_id = None
            slots.append((card_id, True))
        else:
            hidden += 1
            slots.append((None, False))
    n = len(q)
    counts = [n / 10.0, hidden / 10.0, (n - hidden) / 10.0]
    return counts, slots, visible_ids


def encode_choice_options(
    choice: dict[str, Any] | None,
) -> tuple[np.ndarray, np.ndarray, int, bool, int]:
    """
    Return (option_feats [MAX_OPTIONS, D], option_mask [MAX_OPTIONS],
            num_choices, ordered, choicetype_int).
    """
    feats = np.zeros((MAX_OPTIONS, OPTION_FEAT_DIM), dtype=np.float32)
    mask = np.zeros(MAX_OPTIONS, dtype=np.float32)
    if not choice:
        return feats, mask, 0, False, -1
    opts = list(choice.get("options") or [])
    n_pick = int(choice.get("num_choice") or choice.get("num_choices") or 1)
    ctype = int(choice.get("choicetype", -1))
    ordered = choice_is_ordered(ctype)
    n_avail = min(len(opts), MAX_OPTIONS)
    n_pick = max(0, min(n_pick, MAX_PICKS, n_avail if n_avail else 0))
    payload = choice.get("payload") or {}
    action_faces = list(payload.get("actions") or [])
    for i, opt in enumerate(opts[:MAX_OPTIONS]):
        mask[i] = 1.0
        feats[i, 0] = 1.0
        feats[i, 1] = _norm_id(opt)
        feats[i, 2] = i / max(1, MAX_OPTIONS - 1)
        feats[i, 3] = ctype / 12.0 if ctype >= 0 else 0.0
        if ctype == int(ChoiceType.CHOOSE_ACTION) and i < len(action_faces):
            face = action_faces[i].get("face") if isinstance(action_faces[i], dict) else None
            action_option_one_hot((face or {}).get("action_name"), feats[i])
        elif ctype == int(ChoiceType.PLACE_UNITS):
            troop_option_one_hot(opt, feats[i])
        elif ctype == int(ChoiceType.CHOOSE_CARD):
            write_assign_option(payload, opt, feats[i])
    return feats, mask, n_pick, ordered, ctype


def choice_is_ordered(choicetype: int) -> bool:
    return choicetype in (
        int(ChoiceType.CHOOSE_CARD),
        int(ChoiceType.CHOOSE_ACTION),
        int(ChoiceType.REORDER_SCOUTED_CARDS),
        int(ChoiceType.PLACE_UNITS),
    )


def picks_to_vector(
    options: list[Any], picks: list[int], *, ordered: bool
) -> list[int]:
    """Map option-index picks → engine choice vector (option values)."""
    if ordered:
        vec: list[int] = []
        for p in picks:
            if p < 0 or p >= len(options):
                continue
            val = options[p]
            try:
                vec.append(int(val))
            except (TypeError, ValueError):
                vec.append(val)  # type: ignore[arg-type]
        return vec
    # Unordered: emit options in ascending index order (matches combinations()).
    paired = sorted(
        ((p, options[p]) for p in picks if 0 <= p < len(options)),
        key=lambda t: t[0],
    )
    vec = []
    for _, val in paired:
        try:
            vec.append(int(val))
        except (TypeError, ValueError):
            vec.append(val)  # type: ignore[arg-type]
    return vec


def relative_seat(seat: int, viewer: int, num_players: int) -> int:
    """Rotate seats so ``viewer`` is player 0. Negative seats stay unset."""
    if seat < 0 or num_players <= 0:
        return int(seat)
    return (int(seat) - int(viewer)) % int(num_players)


def _viewer_seat_order(viewer: int, num_players: int) -> list[int]:
    """Absolute seats in the order the viewer should see them, self first."""
    n = max(1, int(num_players))
    return [(int(viewer) + k) % n for k in range(n)]


def _append(parts: list[np.ndarray], values: np.ndarray) -> None:
    parts.append(np.asarray(values, dtype=np.float32).reshape(-1))


def flatten_observation(obs: dict[str, Any], agent_index: int, num_players: int) -> np.ndarray:
    """Build a fixed-size float32 vector from a player FOV dict.

    The viewer is always player 0. Other seats follow in turn order.
    Card faces sit in the token tail, after the board the MLP reads.
    """
    parts: list[np.ndarray] = []
    one_hot = np.zeros(MAX_PLAYERS, dtype=np.float32)
    one_hot[0] = 1.0
    _append(parts, one_hot)
    _append(
        parts,
        np.asarray(
            [
                float(obs.get("round", 0)),
                float(obs.get("stage", -1)),
                1.0 if obs.get("terminal") else 0.0,
            ],
            dtype=np.float32,
        ),
    )
    _append(parts, resistance_features(obs.get("resistance") or {}))
    _append(parts, hit_pile_features(obs.get("hit_decks")))
    _append(parts, formation_features(obs.get("setup_pattern"), agent_index, num_players))

    players = obs.get("players") or []
    by_number = {
        int(p.get("number", i)): p for i, p in enumerate(players) if isinstance(p, dict)
    }
    own_cards: list[Any] = []
    order = _viewer_seat_order(agent_index, num_players)
    player_block = np.zeros(MAX_PLAYERS * PLAYER_FEAT, dtype=np.float32)
    for i in range(MAX_PLAYERS):
        p = by_number.get(order[i]) if i < len(order) else None
        if p is None:
            continue
        player_block[i * PLAYER_FEAT : (i + 1) * PLAYER_FEAT] = player_features(
            p, hand_scale=MAX_HAND
        )
        if i == 0 and "cards" in p:
            own_cards = list(p.get("cards") or [])
    _append(parts, player_block)

    convoy = obs.get("convoy") or []
    unit_block = np.zeros(MAX_UNITS * UNIT_FEAT, dtype=np.float32)
    stack_block = np.zeros((MAX_UNITS, UNIT_STACKS, CARD_TOKEN_DIM), dtype=np.float32)
    tuck_block = np.zeros((MAX_UNITS, TUCK_DIM), dtype=np.float32)
    for i, u in enumerate(convoy[:MAX_UNITS]):
        if not isinstance(u, dict):
            continue
        entries = entries_from_action_json(u.get("action"), u.get("officers"))
        has_card, face_up, resolved, frustrated = stack_flags(entries)
        unit_block[i * UNIT_FEAT : (i + 1) * UNIT_FEAT] = unit_features(
            unit_type=str(u.get("unit_type") or ""),
            owner=int(u.get("player") or 0),
            viewer=agent_index,
            num_players=num_players,
            tired=float(u.get("tiredness") or 0),
            influence=float(u.get("under_influence") or 0),
            atrocities=float(u.get("atrocities") or 0),
            carry=list(u.get("carry") or []),
            zone=str(u.get("zone") or ""),
            defending=u.get("defending"),
            markers=list(u.get("damage_markers") or []),
            has_card=has_card,
            face_up=face_up,
            resolved=resolved,
            frustrated=frustrated,
        )
        stack_block[i] = stack_tokens(entries)
        tuck_block[i] = encode_tuck(u.get("officers"))
    _append(parts, unit_block)
    _append(parts, np.asarray([len(own_cards) / MAX_HAND], dtype=np.float32))

    rows = ((obs.get("decks") or {}).get("rows")) or []
    row_by_key = {
        r.get("key"): r for r in rows if isinstance(r, dict) and r.get("key")
    }
    content_slots: dict[str, list[tuple[int | None, bool]]] = {}
    officer_pairs: list[tuple[dict[str, Any] | None, bool]] = []
    for key in ("resistance", "pillage", "mauling", "officer"):
        row = row_by_key.get(key) or {}
        counts, slots, _visible_ids = _queue_entries(row.get("queue"))
        _append(
            parts,
            np.asarray(
                [float(row.get("deck") or 0) / 40.0, float(row.get("discard") or 0) / 40.0, *counts],
                dtype=np.float32,
            ),
        )
        if key == "officer":
            for entry in row.get("queue") or []:
                if isinstance(entry, dict) and entry.get("visible"):
                    officer_pairs.append((entry, True))
                else:
                    officer_pairs.append((None, False))
        else:
            content_slots[key] = slots

    choice = obs.get("choice")
    opt_feats, opt_mask, n_pick, ordered, ctype = encode_choice_options(choice)
    _append(
        parts,
        np.asarray(
            [
                1.0 if choice else 0.0,
                ctype / 12.0 if ctype >= 0 else -0.1,
                float(n_pick) / MAX_PICKS,
                1.0 if ordered else 0.0,
                float(opt_mask.sum()) / MAX_OPTIONS,
            ],
            dtype=np.float32,
        ),
    )
    _append(parts, opt_feats.reshape(-1))
    _append(parts, opt_mask)
    _append(parts, encode_card_block(content_slots).reshape(-1))
    _append(parts, officer_queue_tokens(officer_pairs).reshape(-1))
    _append(parts, hand_tokens(own_cards, MAX_HAND).reshape(-1))
    _append(parts, stack_block.reshape(-1))
    _append(parts, tuck_block.reshape(-1))
    _append(
        parts,
        np.asarray(
            events_to_features(
                obs.get("event_rows"), viewer=agent_index, num_players=num_players
            ),
            dtype=np.float32,
        ),
    )
    return np.concatenate(parts)


def fill_observation(
    engine: Any,
    agent_index: int,
    num_players: int,
    out: np.ndarray | None = None,
) -> np.ndarray:
    """
    Write the same vector as ``flatten_observation(player_view(...))`` straight
    from the engine. The viewer is always player 0. Skips deck-name lookups
    and the JSON view.
    """
    dim = observation_size(num_players)
    if out is None or out.shape != (dim,):
        out = np.zeros(dim, dtype=np.float32)
    else:
        out.fill(0.0)

    out[0] = 1.0
    i = MAX_PLAYERS
    rounds = engine.rounds
    out[i] = float(rounds.count if rounds else 0)
    out[i + 1] = float(rounds.stage if rounds else -1)
    out[i + 2] = 1.0 if engine.terminal else 0.0
    i += 3
    out[i : i + RESISTANCE_FEAT] = resistance_features(engine.resistance)
    i += RESISTANCE_FEAT
    out[i : i + HIT_PILES] = hit_pile_features(hit_piles_from_engine(engine))
    i += HIT_PILES
    out[i : i + FORMATION_SEATS] = formation_features(
        getattr(engine, "setup_pattern", ()), agent_index, num_players
    )
    i += FORMATION_SEATS

    own_cards: list[Any] = []
    by_number = {p.number: p for p in engine.players}
    order = _viewer_seat_order(agent_index, num_players)
    for p_i in range(MAX_PLAYERS):
        p = by_number.get(order[p_i]) if p_i < len(order) else None
        if p is not None:
            out[i : i + PLAYER_FEAT] = player_features(p, hand_scale=MAX_HAND)
            if p_i == 0:
                own_cards = list(p.action_cards)
        i += PLAYER_FEAT

    units = engine.convoy.units if engine.convoy is not None else []
    stack_block = np.zeros((MAX_UNITS, UNIT_STACKS, CARD_TOKEN_DIM), dtype=np.float32)
    tuck_block = np.zeros((MAX_UNITS, TUCK_DIM), dtype=np.float32)
    for u_i, u in enumerate(units[:MAX_UNITS]):
        owner_view = u.player.number == agent_index
        entries = entries_from_unit(u, viewer_is_owner=owner_view)
        has_card, face_up, resolved, frustrated = stack_flags(entries)
        out[i : i + UNIT_FEAT] = unit_features(
            unit_type=u.type_to_str.get(u.unittype, ""),
            owner=u.player.number,
            viewer=agent_index,
            num_players=num_players,
            tired=u.tired,
            influence=u.under_influence,
            atrocities=u.atrocities,
            carry=u.carry,
            zone=u.zone() if u.convoy is not None else "",
            defending=u.defending,
            markers=u.damage_markers,
            has_card=has_card,
            face_up=face_up,
            resolved=resolved,
            frustrated=frustrated,
        )
        stack_block[u_i] = stack_tokens(entries)
        tuck_block[u_i] = encode_tuck([officer.describe() for officer in u.officers])
        i += UNIT_FEAT
    i += (MAX_UNITS - min(len(units), MAX_UNITS)) * UNIT_FEAT
    out[i] = len(own_cards) / MAX_HAND
    i += 1

    queues = (
        ("resistance", engine.resistance_deck, engine.resistance_queue),
        ("pillage", engine.pillage_deck, engine.pillage_queue),
        ("mauling", engine.mauling_deck, engine.mauling_queue),
        ("officer", engine.officer_deck, engine.officer_queue),
    )
    content_slots: dict[str, list[tuple[int | None, bool]]] = {}
    officer_pairs: list[tuple[dict[str, Any] | None, bool]] = []
    for key, deck, queue in queues:
        deck_n, discard_n = deck.get_sizes()
        out[i] = deck_n / 40.0
        out[i + 1] = discard_n / 40.0
        i += 2
        entries = queue.cards_and_visibilities
        n = len(entries)
        hidden = 0
        slots: list[tuple[int | None, bool]] = []
        for card_id, vis in entries:
            if vis:
                slots.append((int(card_id), True))
                if key == "officer":
                    described = deck.describe(card_id)
                    officer_pairs.append((described if isinstance(described, dict) else None, True))
            else:
                hidden += 1
                slots.append((None, False))
                if key == "officer":
                    officer_pairs.append((None, False))
        out[i] = n / 10.0
        out[i + 1] = hidden / 10.0
        out[i + 2] = (n - hidden) / 10.0
        i += 3
        if key != "officer":
            content_slots[key] = slots

    pending = engine._pending
    show = pending is not None and pending.player_id == f"player_{agent_index}"
    fs, fe, ms, me = option_block_slices(dim)
    if i != fs - 5:
        raise RuntimeError(f"observation cursor {i} != choice block {fs - 5}")
    if show:
        choice = pending.to_json()
        out[i] = 1.0
        opt_feats, opt_mask, n_pick, ordered, ctype = encode_choice_options(choice)
        out[i + 1] = ctype / 12.0 if ctype >= 0 else -0.1
        out[i + 2] = float(n_pick) / MAX_PICKS
        out[i + 3] = 1.0 if ordered else 0.0
        out[i + 4] = float(opt_mask.sum()) / MAX_OPTIONS
        out[fs:fe] = opt_feats.reshape(-1)
        out[ms:me] = opt_mask
    else:
        out[i + 1] = -0.1
    layout = token_layout(dim)
    cards_at, officers_at, hand_at, stacks_at, tucks_at, events_at = layout
    out[cards_at[0] : cards_at[1]] = encode_card_block(content_slots).reshape(-1)
    out[officers_at[0] : officers_at[1]] = officer_queue_tokens(officer_pairs).reshape(-1)
    out[hand_at[0] : hand_at[1]] = hand_tokens(own_cards, MAX_HAND).reshape(-1)
    out[stacks_at[0] : stacks_at[1]] = stack_block.reshape(-1)
    out[tucks_at[0] : tucks_at[1]] = tuck_block.reshape(-1)
    out[events_at[0] : events_at[1]] = np.asarray(
        events_to_features(
            list(engine.event_rows), viewer=agent_index, num_players=num_players
        ),
        dtype=np.float32,
    )
    return out


_OBS_SIZE: dict[int, int] = {}


def observation_size(num_players: int = MAX_PLAYERS) -> int:
    cached = _OBS_SIZE.get(num_players)
    if cached is not None:
        return cached
    dummy = {
        "round": 0,
        "stage": 0,
        "terminal": False,
        "resistance": {},
        "players": [],
        "convoy": [],
        "choice": None,
        "you": 0,
        "decks": {"rows": []},
    }
    size = int(flatten_observation(dummy, 0, num_players).shape[0])
    _OBS_SIZE[num_players] = size
    return size


def token_tail_width() -> int:
    """Floats after the board. Does not call ``observation_size``."""
    return (
        N_CARD_SLOTS * CARD_FEAT_DIM
        + OFFICER_QUEUE_SLOTS * OFFICER_DIM
        + MAX_HAND * CARD_TOKEN_DIM
        + MAX_UNITS * UNIT_STACKS * CARD_TOKEN_DIM
        + MAX_UNITS * TUCK_DIM
        + EVENT_WINDOW * EVENT_FIELDS
    )


def token_layout(
    obs_dim: int | None = None,
) -> tuple[tuple[int, int], tuple[int, int], tuple[int, int], tuple[int, int], tuple[int, int], tuple[int, int]]:
    """Queue cards, officer queue, hand, unit stacks, tucks, events."""
    dim = obs_dim if obs_dim is not None else observation_size()
    cursor = dim - token_tail_width()

    def take(n: int) -> tuple[int, int]:
        nonlocal cursor
        start = cursor
        cursor += n
        return start, cursor

    return (
        take(N_CARD_SLOTS * CARD_FEAT_DIM),
        take(OFFICER_QUEUE_SLOTS * OFFICER_DIM),
        take(MAX_HAND * CARD_TOKEN_DIM),
        take(MAX_UNITS * UNIT_STACKS * CARD_TOKEN_DIM),
        take(MAX_UNITS * TUCK_DIM),
        take(EVENT_WINDOW * EVENT_FIELDS),
    )


def card_block_slice(obs_dim: int | None = None) -> tuple[int, int]:
    """Start and end of the queue-card block, the first token group."""
    return token_layout(obs_dim)[0]


def option_block_slices(obs_dim: int | None = None) -> tuple[int, int, int, int]:
    """
    Return (opt_feats_start, opt_feats_end, opt_mask_start, opt_mask_end)
    into the flat observation vector.
    """
    dim = obs_dim if obs_dim is not None else observation_size()
    mask_end = dim - token_tail_width()
    mask_start = mask_end - MAX_OPTIONS
    feats_end = mask_start
    feats_start = feats_end - MAX_OPTIONS * OPTION_FEAT_DIM
    return feats_start, feats_end, mask_start, mask_end
