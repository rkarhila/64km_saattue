"""Observation helpers for ConvoyEnv."""

from __future__ import annotations

from typing import Any

import numpy as np

from sixtyfivekmconvoy.core.constants import ChoiceType
from sixtyfivekmconvoy.rl.events import EVENT_FIELDS, EVENT_WINDOW, events_to_features


MAX_UNITS = 15
MAX_HAND = 20
MAX_PLAYERS = 5
# Discrete action index budget (legacy flat path / mask length).
MAX_LEGAL = 256
# Autoregressive choice decoder caps.
MAX_OPTIONS = 32
MAX_PICKS = 8
MAX_QUEUE_VISIBLE = 6
OPTION_FEAT_DIM = 4  # valid, id_norm, slot_norm, type_hint


def _norm_id(card_id: Any, scale: float = 100.0) -> float:
    try:
        return float(int(card_id)) / scale
    except (TypeError, ValueError):
        return 0.0


def _queue_features(queue_json: list[Any] | None) -> list[float]:
    """Length, hidden/visible counts, then up to MAX_QUEUE_VISIBLE face-up ids."""
    q = queue_json or []
    n = len(q)
    hidden = 0
    visible_ids: list[float] = []
    for entry in q:
        if not isinstance(entry, dict):
            if entry == "?" or entry is None:
                hidden += 1
            else:
                visible_ids.append(_norm_id(entry) if isinstance(entry, int) else 0.5)
            continue
        if entry.get("visible"):
            visible_ids.append(_norm_id(entry.get("id")))
        else:
            hidden += 1
    feats = [
        n / 10.0,
        hidden / 10.0,
        (n - hidden) / 10.0,
    ]
    for i in range(MAX_QUEUE_VISIBLE):
        feats.append(visible_ids[i] if i < len(visible_ids) else 0.0)
    return feats


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
    for i, opt in enumerate(opts[:MAX_OPTIONS]):
        mask[i] = 1.0
        feats[i, 0] = 1.0
        feats[i, 1] = _norm_id(opt)
        feats[i, 2] = i / max(1, MAX_OPTIONS - 1)
        feats[i, 3] = ctype / 12.0 if ctype >= 0 else 0.0
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


def flatten_observation(obs: dict[str, Any], agent_index: int, num_players: int) -> np.ndarray:
    """Build a fixed-size float32 vector from a player FOV dict.

    The viewer is always player 0. Other seats follow in turn order.
    """
    feats: list[float] = []

    # Self identity. The viewer is always the first player in its own report.
    one_hot = [0.0] * MAX_PLAYERS
    one_hot[0] = 1.0
    feats.extend(one_hot)

    feats.append(float(obs.get("round", 0)))
    feats.append(float(obs.get("stage", -1)))
    feats.append(1.0 if obs.get("terminal") else 0.0)

    # Resistance
    res = obs.get("resistance") or {}
    feats.append(1.0 if res.get("active") else 0.0)
    feats.append(float(res.get("durability") or 0) / 20.0)

    # Players, rotated so the viewer occupies slot 0.
    players = obs.get("players") or []
    by_number = {
        int(p.get("number", i)): p for i, p in enumerate(players) if isinstance(p, dict)
    }
    own_cards: list[Any] = []
    order = _viewer_seat_order(agent_index, num_players)
    for i in range(MAX_PLAYERS):
        p = by_number.get(order[i]) if i < len(order) else None
        if p is not None:
            feats.extend(
                [
                    float(p.get("cash_this_round", 0)) / 20.0,
                    float(p.get("total_cash", 0)) / 50.0,
                    float(p.get("promotion_points", 0)) / 10.0,
                    float(p.get("card_count", 0)) / MAX_HAND,
                ]
            )
            if i == 0 and "cards" in p:
                own_cards = list(p.get("cards") or [])
        else:
            feats.extend([0.0, 0.0, 0.0, 0.0])

    # Convoy units
    convoy = obs.get("convoy") or []
    for i in range(MAX_UNITS):
        if i < len(convoy):
            u = convoy[i]
            ut = {
                "panzer": 0,
                "infantry": 1,
                "logistics": 2,
                "Pnz": 0,
                "Inf": 1,
                "Log": 2,
            }.get(u.get("unit_type"), 0)
            ut_oh = [0.0, 0.0, 0.0]
            ut_oh[ut] = 1.0
            feats.extend(ut_oh)
            owner = relative_seat(int(u.get("player", 0)), agent_index, num_players)
            feats.append(float(owner) / max(1, num_players - 1))
            feats.append(float(u.get("tiredness", 0)) / 10.0)
            feats.append(1.0 if u.get("under_influence") else 0.0)
            feats.append(float(u.get("atrocities", 0)) / 10.0)
            carry = u.get("carry") or []
            feats.append(len(carry) / 4.0)
            feats.append(sum(c for c in carry if c > 0) / 20.0)
            zone = str(u.get("zone") or "")
            feats.append(1.0 if zone == "A" else 0.0)
            feats.append(1.0 if zone == "B" else 0.0)
            feats.append(1.0 if zone == "C" else 0.0)
            feats.append(float(len(u.get("officers") or [])) / 4.0)
            feats.append(float(len(u.get("cards") or u.get("actioncard") or [])) / 4.0)
        else:
            feats.extend([0.0] * 14)

    # Own hand (card ids, FOV-safe — only own cards are present)
    for i in range(MAX_HAND):
        if i < len(own_cards):
            feats.append(_norm_id(own_cards[i], scale=25.0))
        else:
            feats.append(0.0)
    feats.append(len(own_cards) / MAX_HAND)

    # Decks / queues from FOV rows (visible ids only)
    rows = ((obs.get("decks") or {}).get("rows")) or []
    row_by_key = {
        r.get("key"): r for r in rows if isinstance(r, dict) and r.get("key")
    }
    for key in ("resistance", "pillage", "mauling", "officer"):
        row = row_by_key.get(key) or {}
        feats.append(float(row.get("deck") or 0) / 40.0)
        feats.append(float(row.get("discard") or 0) / 40.0)
        feats.extend(_queue_features(row.get("queue")))

    # Pending choice meta + option slots
    choice = obs.get("choice")
    feats.append(1.0 if choice else 0.0)
    opt_feats, opt_mask, n_pick, ordered, ctype = encode_choice_options(choice)
    feats.append(ctype / 12.0 if ctype >= 0 else -0.1)
    feats.append(float(n_pick) / MAX_PICKS)
    feats.append(1.0 if ordered else 0.0)
    feats.append(float(opt_mask.sum()) / MAX_OPTIONS)
    feats.extend(opt_feats.reshape(-1).tolist())
    feats.extend(opt_mask.tolist())
    # Formal event window (already visibility-masked). Oldest padded on the left.
    feats.extend(
        events_to_features(
            obs.get("event_rows"), viewer=agent_index, num_players=num_players
        )
    )

    return np.asarray(feats, dtype=np.float32)


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
    res = engine.resistance
    if res is not None and res.name:
        out[i] = 1.0 if res.active else 0.0
        out[i + 1] = float(res.durability or 0) / 20.0
    i += 2

    own_cards: list[Any] = []
    by_number = {p.number: p for p in engine.players}
    order = _viewer_seat_order(agent_index, num_players)
    for p_i in range(MAX_PLAYERS):
        p = by_number.get(order[p_i]) if p_i < len(order) else None
        if p is not None:
            out[i] = float(p.this_round_cash) / 20.0
            out[i + 1] = float(p.total_cash) / 50.0
            out[i + 2] = float(p.promotion_points) / 10.0
            out[i + 3] = float(len(p.action_cards)) / MAX_HAND
            if p_i == 0:
                own_cards = p.action_cards
        i += 4

    type_index = {"panzer": 0, "infantry": 1, "logistics": 2}
    units = engine.convoy.units if engine.convoy is not None else []
    denom = max(1, num_players - 1)
    for u_i in range(MAX_UNITS):
        if u_i < len(units):
            u = units[u_i]
            ut = type_index.get(u.type_to_str.get(u.unittype, ""), 0)
            out[i + ut] = 1.0
            owner = relative_seat(u.player.number, agent_index, num_players)
            out[i + 3] = float(owner) / denom
            out[i + 4] = float(u.tired) / 10.0
            out[i + 5] = 1.0 if u.under_influence else 0.0
            out[i + 6] = float(u.atrocities) / 10.0
            carry = u.carry
            out[i + 7] = len(carry) / 4.0
            out[i + 8] = sum(c for c in carry if c > 0) / 20.0
            zone = u.zone() if u.convoy is not None else ""
            out[i + 9] = 1.0 if zone == "A" else 0.0
            out[i + 10] = 1.0 if zone == "B" else 0.0
            out[i + 11] = 1.0 if zone == "C" else 0.0
            out[i + 12] = float(len(u.officers)) / 4.0
            # player_view stores action cards under "action", which the flat
            # vector does not read. Keep that zero so the layout stays put.
        i += 14

    for h_i in range(MAX_HAND):
        if h_i < len(own_cards):
            out[i] = _norm_id(own_cards[h_i], scale=25.0)
        i += 1
    out[i] = len(own_cards) / MAX_HAND
    i += 1

    queues = (
        ("resistance", engine.resistance_deck, engine.resistance_queue),
        ("pillage", engine.pillage_deck, engine.pillage_queue),
        ("mauling", engine.mauling_deck, engine.mauling_queue),
        ("officer", engine.officer_deck, engine.officer_queue),
    )
    for _key, deck, queue in queues:
        deck_n, discard_n = deck.get_sizes()
        out[i] = deck_n / 40.0
        out[i + 1] = discard_n / 40.0
        i += 2
        entries = queue.cards_and_visibilities
        n = len(entries)
        hidden = 0
        visible: list[float] = []
        for card_id, vis in entries:
            if vis:
                visible.append(_norm_id(card_id))
            else:
                hidden += 1
        out[i] = n / 10.0
        out[i + 1] = hidden / 10.0
        out[i + 2] = (n - hidden) / 10.0
        i += 3
        for q_i in range(MAX_QUEUE_VISIBLE):
            if q_i < len(visible):
                out[i] = visible[q_i]
            i += 1

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
    ev = np.asarray(
        events_to_features(
            list(engine.event_rows), viewer=agent_index, num_players=num_players
        ),
        dtype=np.float32,
    )
    out[-ev.shape[0] :] = ev
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


def option_block_slices(obs_dim: int | None = None) -> tuple[int, int, int, int]:
    """
    Return (opt_feats_start, opt_feats_end, opt_mask_start, opt_mask_end)
    into the flat observation vector.
    """
    dim = obs_dim if obs_dim is not None else observation_size()
    # Event window is appended after the option mask.
    mask_end = dim - EVENT_WINDOW * EVENT_FIELDS
    mask_start = mask_end - MAX_OPTIONS
    feats_end = mask_start
    feats_start = feats_end - MAX_OPTIONS * OPTION_FEAT_DIM
    return feats_start, feats_end, mask_start, mask_end
