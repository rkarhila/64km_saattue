"""Fixed integer event rows for the policy (no text).

Each row is ``EVENT_FIELDS`` ints. Card ids are zero unless ``visible`` is set,
so a seat never receives a secret and is asked to ignore it.
"""

from __future__ import annotations

from typing import Any

EVENT_WINDOW = 32
# type, round, stage, actor, target, queue, card_id, amount, card_visible
EVENT_FIELDS = 9

EVENT_NONE = 0
EVENT_ACTION = 1
EVENT_PILLAGE = 2
EVENT_MAULING = 3
EVENT_REVEAL = 4
EVENT_CASH = 5
EVENT_PROMOTE = 6
EVENT_DAMAGE = 7
EVENT_INFLUENCE = 8
EVENT_PLACE = 9
EVENT_ROUND = 10
N_EVENT_TYPES = 11

QUEUE_NONE = -1
QUEUE_PILLAGE = 0
QUEUE_MAULING = 1
QUEUE_RESISTANCE = 2
QUEUE_OFFICER = 3


def make_event(
    event_type: int,
    *,
    round_n: int = 0,
    stage: int = -1,
    actor: int = -1,
    target: int = -1,
    queue: int = QUEUE_NONE,
    card_id: int = 0,
    amount: int = 0,
    card_visible: bool = False,
) -> list[int]:
    """One formal event. Hidden cards store id 0 and card_visible 0."""
    cid = int(card_id) if card_visible else 0
    return [
        int(event_type),
        int(round_n),
        int(stage),
        int(actor),
        int(target),
        int(queue),
        cid,
        int(amount),
        1 if card_visible and cid else 0,
    ]


def blank_event() -> list[int]:
    return [0] * EVENT_FIELDS


def recent_events(rows: list[list[int]] | None, window: int = EVENT_WINDOW) -> list[list[int]]:
    """Last ``window`` rows, oldest first, padded with blanks on the left."""
    src = list(rows or [])
    tail = src[-window:]
    pad = window - len(tail)
    return [blank_event() for _ in range(pad)] + [
        (list(row) + [0] * EVENT_FIELDS)[:EVENT_FIELDS] for row in tail
    ]


def events_to_features(
    rows: list[list[int]] | None,
    *,
    viewer: int = 0,
    num_players: int | None = None,
) -> list[float]:
    """Normalized floats for the observation tail. Hidden card ids stay 0.

    When ``num_players`` is set, actor and target seats are rotated so
    ``viewer`` is player 0. Unset seats (negative) stay unset.
    """
    feats: list[float] = []
    for row in recent_events(rows):
        etype, rnd, stage, actor, target, queue, cid, amount, vis = row
        if num_players:
            if actor >= 0:
                actor = (int(actor) - int(viewer)) % int(num_players)
            if target >= 0:
                target = (int(target) - int(viewer)) % int(num_players)
        feats.extend(
            [
                etype / max(1, N_EVENT_TYPES - 1),
                rnd / 40.0,
                (stage + 1) / 8.0,
                (actor + 1) / 6.0,
                (target + 1) / 6.0,
                (queue + 1) / 5.0,
                (cid / 100.0) if vis else 0.0,
                amount / 20.0,
                float(vis),
            ]
        )
    return feats


def event_from_detail(
    detail: dict[str, Any],
    *,
    round_n: int,
    stage: int,
) -> list[int] | None:
    """Build a row when a broadcast passes ``event_type``."""
    if "event_type" not in detail:
        return None
    return make_event(
        int(detail["event_type"]),
        round_n=round_n,
        stage=stage,
        actor=int(detail.get("actor", -1)),
        target=int(detail.get("target", -1)),
        queue=int(detail.get("queue", QUEUE_NONE)),
        card_id=int(detail.get("card_id", 0) or 0),
        amount=int(detail.get("amount", 0) or 0),
        card_visible=bool(detail.get("card_visible", False)),
    )
