"""Per-player field-of-view JSON for web UI and observations."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from . import config
from .cards import CardDeck, CardQueue
from .constants import MIN_PLAYER_CARD_LIMIT
from .i18n import t

if TYPE_CHECKING:
    from .engine import ChoiceRequest, GameEngine
    from .models import Player


def _log_tail(messages: list[str], log_tail: int | None) -> list[str]:
    if log_tail is None or log_tail < 0 or len(messages) <= log_tail:
        return list(messages)
    return messages[-log_tail:]


def _deck_row(
    key: str,
    deck: CardDeck,
    queue: CardQueue | None = None,
) -> dict[str, Any]:
    sizes = deck.to_json()
    return {
        "key": key,
        "label": t(f"deck.{key}"),
        "deck": sizes.get("deck", 0),
        "discard": sizes.get("discard", 0),
        "queue": queue.to_json() if queue is not None else [],
    }


def player_view(
    engine: GameEngine,
    player: Player,
    *,
    choice: ChoiceRequest | None = None,
    message: str | None = None,
    include_events: bool = True,
    log_tail: int | None = None,
) -> dict[str, Any]:
    # Horizontal UI rows: discard | deck | queue (front = rightmost).
    table_decks = [
        _deck_row("resistance", engine.resistance_deck, engine.resistance_queue),
        _deck_row("pillage", engine.pillage_deck, engine.pillage_queue),
        _deck_row("mauling", engine.mauling_deck, engine.mauling_queue),
    ]
    if config.USE_OFFICER_QUEUE:
        table_decks.append(
            _deck_row("officer", engine.officer_deck, engine.officer_queue)
        )
    # Each player has their own action draw/discard; show the viewer's.
    viewer_action = player.action_deck
    if viewer_action is not None:
        table_decks.append(_deck_row("action", viewer_action, None))
    action_sizes = (
        viewer_action.to_json()
        if viewer_action is not None
        else {"deck": 0, "discard": 0}
    )
    deck_state = {
        "decks": {
            "action": action_sizes,
            "resistance": engine.resistance_deck.to_json(),
            "pillage": engine.pillage_deck.to_json(),
            "mauling": engine.mauling_deck.to_json(),
            "officer": engine.officer_deck.to_json(),
        },
        "queues": {
            "resistance": engine.resistance_queue.to_arr(),
            "pillage": engine.pillage_queue.to_arr(),
            "officer": engine.officer_queue.to_arr(),
            "mauling": engine.mauling_queue.to_arr(),
        },
        "rows": table_decks,
    }
    state: dict[str, Any] = {
        "convoy": engine.convoy.to_json(playerview=player),
        "players": [p.to_json(playerview=player) for p in engine.players],
        "decks": deck_state,
        "hit_decks": [
            {
                "category": category,
                "label": t(f"deck.hit_{category}"),
                "deck": len(engine.hit_decks[category].deck),
                "drawn": [
                    dict(card)
                    for card in engine.hit_draws
                    if card["category"] == category
                ],
            }
            for category in (1, 3, 5, 10)
        ],
        "struck_units": [
            unit.index()
            for unit in engine.struck_units
            if unit in engine.convoy.units
        ],
        "resistance_struck": bool(engine.resistance_struck),
        "resistance": engine.resistance.to_json(),
        "round": engine.rounds.count if engine.rounds else 0,
        "stage": engine.rounds.stage if engine.rounds else -1,
        "cards_to_deal": int(
            config.CARDS_TO_DEAL_FIRST_ROUND
            if engine.rounds and engine.rounds.count == 0
            else config.CARDS_TO_DEAL
        ),
        "promotions_to_win": int(config.PROMOTION_POINTS_TO_WIN),
        "cash_to_win": int(config.CASH_TO_WIN),
        "cash_win_at_end_of_round": bool(
            getattr(config, "CASH_WIN_AT_END_OF_ROUND", False)
        ),
        # Base hand keep, plus at most one logistics unit's free cargo slots (3).
        "hand_keep_base": int(MIN_PLAYER_CARD_LIMIT),
        "hand_keep_max": int(MIN_PLAYER_CARD_LIMIT) + 3,
        "acting_unit": getattr(engine, "acting_unit_index", None),
        "terminal": engine.terminal,
        "you": player.number,
        "log": _log_tail(engine.messages, log_tail),
        "setup_complete": getattr(engine, "setup_complete", True),
        "setup_pattern": list(getattr(engine, "setup_pattern", ()) or ()),
    }
    if not state["setup_complete"] and getattr(engine, "setup_order_card_id", None) is not None:
        desc = engine.mauling_deck.describe(engine.setup_order_card_id)
        state["setup_order_card"] = {
            "id": engine.setup_order_card_id,
            "visible": True,
            **(desc if isinstance(desc, dict) else {}),
        }
    if include_events:
        # Training observations. The web poll does not render these.
        state["events"] = list(getattr(engine, "event_log", []) or [])
        state["event_rows"] = list(getattr(engine, "event_rows", []) or [])
    if message:
        state["message"] = message
    if choice is not None and choice.player_id == player.agent_id():
        state["choice"] = choice.to_json()
    return state
