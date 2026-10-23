"""In-memory game sessions: one human seat + bot seats (multi-seat ready)."""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field
from typing import Any

from sixtyfivekmconvoy.agents.random_agent import RandomAgent
from sixtyfivekmconvoy.core.engine import GameEngine


@dataclass
class GameSession:
    game_id: str
    engine: GameEngine
    human_seats: set[str]
    bots: dict[str, RandomAgent] = field(default_factory=dict)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    def is_human(self, player_id: str) -> bool:
        return player_id in self.human_seats

    def snapshot(self, player_id: str) -> dict[str, Any]:
        view = self.engine.observe(player_id)
        pending = self.engine.pending_choice()
        legal = self.engine.legal_actions() if pending and pending.player_id == player_id else []
        return {
            "game_id": self.game_id,
            "state": view,
            "pending": pending.to_json() if pending and pending.player_id == player_id else None,
            "legal_actions": legal,
            "terminal": self.engine.terminal,
            "ranking": self.engine.winner_ranking(),
            "stats": self.engine.stats.to_json() if self.engine.terminal else None,
        }

    def apply_human_choice(self, player_id: str, choice: list[int]) -> dict[str, Any]:
        pending = self.engine.pending_choice()
        if pending is None or pending.player_id != player_id:
            raise ValueError("Not your turn")
        legal = self.engine.legal_actions()
        if choice not in legal:
            # Allow index into legal_actions
            if len(choice) == 1 and 0 <= choice[0] < len(legal):
                choice = list(legal[choice[0]])
            else:
                raise ValueError(f"Illegal choice {choice}")
        self.engine.step(choice)
        self._run_bots()
        return self.snapshot(player_id)

    def _run_bots(self) -> None:
        while not self.engine.terminal:
            pending = self.engine.pending_choice()
            if pending is None:
                break
            if pending.player_id in self.human_seats:
                break
            bot = self.bots[pending.player_id]
            choice = bot.choose(self.engine.legal_actions())
            self.engine.step(choice)


class SessionManager:
    def __init__(self) -> None:
        self.sessions: dict[str, GameSession] = {}

    def create(
        self,
        num_players: int = 3,
        human_seat: int = 0,
        seed: int | None = None,
        max_rounds: int = 200,
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
        )
        # Advance bots until human's turn (or terminal)
        session._run_bots()
        self.sessions[game_id] = session
        return session

    def get(self, game_id: str) -> GameSession:
        return self.sessions[game_id]
