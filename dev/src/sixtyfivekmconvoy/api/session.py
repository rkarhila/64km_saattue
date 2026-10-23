"""In-memory game sessions: one human seat + bot seats (multi-seat ready)."""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field
from typing import Any

from sixtyfivekmconvoy.agents.random_agent import RandomAgent
from sixtyfivekmconvoy.core.card_display import describe_action_card
from sixtyfivekmconvoy.core.constants import ChoiceType
from sixtyfivekmconvoy.core.engine import GameEngine
from sixtyfivekmconvoy.core.i18n import unit_type_label


@dataclass
class GameSession:
    game_id: str
    engine: GameEngine
    human_seats: set[str]
    bots: dict[str, RandomAgent] = field(default_factory=dict)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    # When True, stop after a step that appends log lines (unless human must act).
    pause_after_actions: bool = True
    awaiting_continue: bool = False

    def is_human(self, player_id: str) -> bool:
        return player_id in self.human_seats

    def set_pause_after_actions(self, enabled: bool) -> None:
        self.pause_after_actions = enabled
        if not enabled and self.awaiting_continue:
            # Clearing pause while waiting: resume immediately is caller's job
            pass

    def snapshot(self, player_id: str) -> dict[str, Any]:
        view = self.engine.observe(player_id)
        pending = self.engine.pending_choice()
        # While paused for continue, suppress choice UI even if a bot is "pending"
        show_choice = (
            pending is not None
            and pending.player_id == player_id
            and not self.awaiting_continue
        )
        legal = self.engine.legal_actions() if show_choice else []
        pending_json = pending.to_json() if show_choice else None
        if pending_json is not None:
            pending_json["card_catalog"] = self._card_catalog_for_pending(pending)
            assign_units = self._assign_units_for_pending(pending, player_id)
            if assign_units:
                pending_json["assign_units"] = assign_units

        player = self.engine._player_by_id(player_id)
        hand_cards = {
            str(cid): describe_action_card(cid) for cid in player.action_cards
        }
        # All face-up convoy cards (own always; others after they act).
        placed: dict[str, Any] = {}
        for u in self.engine.convoy.units:
            if not u.actioncard:
                continue
            action = u.to_json(playerview=player).get("action") or {}
            if action.get("face_up") and action.get("card") is not None:
                placed[str(action["card"])] = describe_action_card(action["card"])

        return {
            "game_id": self.game_id,
            "state": view,
            "pending": pending_json,
            "legal_actions": legal,
            "hand_cards": hand_cards,
            "placed_cards": placed,
            "player_colors": [
                "red",
                "green",
                "blue",
                "orange",
                "purple",
            ][: len(self.engine.players)],
            "terminal": self.engine.terminal,
            "ranking": self.engine.winner_ranking(),
            "stats": self.engine.stats.to_json() if self.engine.terminal else None,
            "awaiting_continue": self.awaiting_continue,
            "pause_after_actions": self.pause_after_actions,
            "setup_complete": self.engine.setup_complete,
            "setup_pattern": list(self.engine.setup_pattern),
        }

    def _card_catalog_for_pending(self, pending) -> dict[str, Any]:
        catalog: dict[str, Any] = {}
        if pending.choicetype in (
            ChoiceType.CHOOSE_CARD,
            ChoiceType.CHOOSE_CARDS_TO_DISCARD,
        ):
            for opt in pending.options:
                if isinstance(opt, int):
                    catalog[str(opt)] = describe_action_card(opt)
        if pending.choicetype == ChoiceType.CHOOSE_ACTION:
            cid = (pending.payload or {}).get("card_id")
            if isinstance(cid, int):
                catalog[str(cid)] = describe_action_card(cid)
        return catalog

    def _assign_units_for_pending(self, pending, player_id: str) -> list[dict[str, Any]]:
        if pending.choicetype != ChoiceType.CHOOSE_CARD:
            return []
        player = self.engine._player_by_id(player_id)
        units = [u for u in self.engine.convoy.units if u.player is player]
        if pending.num_choices != len(units) or pending.num_choices < 2:
            return []
        return [
            {
                "index": u.index(),
                "unit_type": u.type_to_str[u.unittype],
                "unit_type_label": unit_type_label(u.unittype),
            }
            for u in units
        ]

    def _human_must_act(self) -> bool:
        pending = self.engine.pending_choice()
        return (
            pending is not None
            and pending.player_id in self.human_seats
            and not self.engine.terminal
        )

    def _should_pause(self, log_len_before: int) -> bool:
        if not self.pause_after_actions:
            return False
        if self.engine.terminal:
            return False
        if len(self.engine.messages) <= log_len_before:
            return False
        # Don't block the human behind a Continue when they have a choice waiting.
        if self._human_must_act():
            return False
        return True

    def apply_human_choice(self, player_id: str, choice: list[int]) -> dict[str, Any]:
        if self.awaiting_continue:
            raise ValueError("Press continue before making another choice")
        pending = self.engine.pending_choice()
        if pending is None or pending.player_id != player_id:
            raise ValueError("Not your turn")
        legal = self.engine.legal_actions()
        if choice not in legal:
            if len(choice) == 1 and 0 <= choice[0] < len(legal):
                choice = list(legal[choice[0]])
            else:
                raise ValueError(f"Illegal choice {choice}")
        before = len(self.engine.messages)
        self.engine.step(choice)
        if self._should_pause(before):
            self.awaiting_continue = True
            return self.snapshot(player_id)
        self._run_bots()
        return self.snapshot(player_id)

    def continue_play(self, player_id: str) -> dict[str, Any]:
        """Resume after a pause (or no-op if not paused)."""
        self.awaiting_continue = False
        if self.engine.terminal:
            return self.snapshot(player_id)
        if self._human_must_act():
            return self.snapshot(player_id)
        self._run_bots()
        return self.snapshot(player_id)

    def _run_bots(self) -> None:
        self.awaiting_continue = False
        while not self.engine.terminal:
            pending = self.engine.pending_choice()
            if pending is None:
                break
            if pending.player_id in self.human_seats:
                break
            bot = self.bots[pending.player_id]
            before = len(self.engine.messages)
            self.engine.step(bot.choose(self.engine.legal_actions()))
            if self._should_pause(before):
                self.awaiting_continue = True
                break


class SessionManager:
    def __init__(self) -> None:
        self.sessions: dict[str, GameSession] = {}

    def create(
        self,
        num_players: int = 3,
        human_seat: int = 0,
        seed: int | None = None,
        max_rounds: int = 200,
        pause_after_actions: bool = True,
    ) -> GameSession:
        engine = GameEngine()
        engine.reset(num_players=num_players, seed=seed, max_rounds=max_rounds)
        game_id = uuid.uuid4().hex[:10]
        human_id = f"player_{human_seat}"
        bots = {
            pid: RandomAgent(seed=(seed or 0) + 50 + i)
            for i, pid in enumerate(engine.agent_ids())
            if pid != human_id
        }
        session = GameSession(
            game_id=game_id,
            engine=engine,
            human_seats={human_id},
            bots=bots,
            pause_after_actions=pause_after_actions,
        )
        session._run_bots()
        self.sessions[game_id] = session
        return session

    def get(self, game_id: str) -> GameSession:
        return self.sessions[game_id]
