"""Per-player field-of-view JSON for web UI and observations."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .engine import ChoiceRequest, GameEngine
    from .models import Player


def player_view(
    engine: GameEngine,
    player: Player,
    *,
    choice: ChoiceRequest | None = None,
    message: str | None = None,
) -> dict[str, Any]:
    deck_state = {
        "decks": {
            "action": engine.action_deck.to_json(),
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
    }
    state: dict[str, Any] = {
        "convoy": engine.convoy.to_json(playerview=player),
        "players": [p.to_json(playerview=player) for p in engine.players],
        "decks": deck_state,
        "resistance": engine.resistance.to_json(),
        "round": engine.rounds.count if engine.rounds else 0,
        "stage": engine.rounds.stage if engine.rounds else -1,
        "terminal": engine.terminal,
        "you": player.number,
        "log": list(engine.messages),
        "setup_complete": getattr(engine, "setup_complete", True),
        "setup_pattern": list(getattr(engine, "setup_pattern", ()) or ()),
    }
    if message:
        state["message"] = message
    if choice is not None and choice.player_id == player.agent_id():
        state["choice"] = choice.to_json()
    return state
