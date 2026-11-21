"""In-memory tables and game sessions for several humans on one machine."""

from __future__ import annotations

import asyncio
import threading
import uuid
from dataclasses import dataclass, field
from typing import Any

from sixtyfivekmconvoy.api.bots import make_seat_bots
from sixtyfivekmconvoy.core.card_display import describe_action_card
from sixtyfivekmconvoy.core.constants import ChoiceType
from sixtyfivekmconvoy.core.engine import ChoiceRequest, GameEngine
from sixtyfivekmconvoy.core.i18n import unit_type_label

# Partitive, so the phrase reads "Odotetaan punaista pelaajaa Foo …".
_COLOR_PARTITIVE = ("punaista", "vihreää", "sinistä", "oranssia", "violettia")
_COLOR_NOMINATIVE = ("punainen", "vihreä", "sininen", "oranssi", "violetti")
_WAIT_VERB = {
    ChoiceType.PLACE_UNITS: "sijoittamaan joukot",
    ChoiceType.CHOOSE_CARD: "jakamaan käskyt",
    ChoiceType.CHOOSE_ACTION: "valitsemaan toiminnon",
    ChoiceType.CHOOSE_CARDS_TO_DISCARD: "valitsemaan kortteja",
    ChoiceType.CASH_IN_CARDS: "lunastamaan kortteja",
    ChoiceType.CHOOSE_QUEUE_TO_SCOUT: "valitsemaan jonon",
    ChoiceType.CHOOSE_PILLAGE_CARD: "valitsemaan ryöstökortteja",
    ChoiceType.CHOOSE_OFFICER: "valitsemaan upseerin",
    ChoiceType.CHOOSE_SERVICE: "valitsemaan huollon",
    ChoiceType.YES_NO: "vastaamaan",
    ChoiceType.CHOOSE_CARDS_TO_SCOUT: "valitsemaan kortteja",
    ChoiceType.REORDER_SCOUTED_CARDS: "järjestämään kortit",
    ChoiceType.LOG_PAUSE: "jatkamaan",
    ChoiceType.DISCARD_UNITS: "hylkäämään yksiköitä",
}


@dataclass
class GameSession:
    game_id: str
    engine: GameEngine
    human_seats: set[str]
    bots: dict[str, Any] = field(default_factory=dict)
    bot_meta: dict[str, Any] = field(default_factory=dict)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    # Sync HTTP handlers share one game. This keeps two polls from
    # stepping the engine at the same time.
    turn_lock: threading.Lock = field(default_factory=threading.Lock)
    # When True, stop after a step that appends log lines (unless human must act).
    pause_after_actions: bool = True
    awaiting_continue: bool = False
    human_choices: list[list[int]] = field(default_factory=list)
    # None once the opening placement has been committed. Until then, every
    # seat's answer is collected before the engine is stepped.
    placement_answers: dict[str, list[int]] | None = None
    # How many log lines this human has clicked through. Multi-human games
    # do not freeze the engine on those clicks.
    log_seen: dict[str, int] = field(default_factory=dict)
    revision: int = 0
    # Last log-pause state already drained, so polls do not repeat it.
    _pause_drain_mark: tuple | None = None
    _share_key: tuple | None = None
    _share_value: str = ""

    def is_human(self, player_id: str) -> bool:
        return player_id in self.human_seats

    def set_pause_after_actions(self, enabled: bool) -> None:
        self.pause_after_actions = enabled
        self.engine.pause_after_actions = enabled
        if not enabled:
            if self.awaiting_continue:
                # Clearing pause while waiting: resume immediately is caller's job
                pass
            pending = self.engine.pending_choice()
            if pending is not None and pending.choicetype == ChoiceType.LOG_PAUSE:
                self.engine.clear_hit_draws()
                self.engine.step([0])
                self._run_bots()
                self.revision += 1

    def _several_humans(self) -> bool:
        return len(self.human_seats) > 1

    def snapshot(self, player_id: str) -> dict[str, Any]:
        # A log pause is not a seat's turn. With several humans it used to
        # freeze the table on "waiting for red" before the bot between them acted.
        self._drain_multi_log_pause()
        view = self.engine.observe(player_id, web=True)
        pending = self.engine.pending_choice()
        synthetic: ChoiceRequest | None = None
        if self.placement_answers is not None and player_id in self.human_seats:
            if player_id not in self.placement_answers:
                synthetic = self._placement_request(player_id)
                pending = synthetic
            else:
                pending = None
        # LOG_PAUSE is shown via the floating continue panel, not the choice UI.
        log_pause_for_human = (
            synthetic is None
            and pending is not None
            and pending.choicetype == ChoiceType.LOG_PAUSE
            and pending.player_id == player_id
        )
        choice_for_me = (
            pending is not None
            and pending.player_id == player_id
            and pending.choicetype != ChoiceType.LOG_PAUSE
        )
        continue_hint = None
        log_cursor = self.log_seen.get(player_id, 0)
        if self._several_humans():
            unread = (
                self.pause_after_actions
                and log_cursor < len(self.engine.messages)
            )
            # Each viewer pages their own lines, including the player whose
            # turn it is. Someone else's clicks do not move the engine.
            awaiting = bool(unread and not self.engine.terminal)
            if awaiting and self.engine.messages:
                idx = min(self.log_seen.get(player_id, 0), len(self.engine.messages) - 1)
                continue_hint = self.engine.messages[idx]
        else:
            awaiting = self.awaiting_continue or log_pause_for_human
            if awaiting and self.engine.messages:
                # The pause description is a short prompt. The log line names
                # who acted, which is what the continue box should show.
                continue_hint = self.engine.messages[-1]
            elif awaiting and log_pause_for_human and pending is not None:
                continue_hint = pending.description or None
        if self._several_humans():
            show_choice = choice_for_me and not awaiting
        else:
            # While paused for continue, suppress choice UI even if a bot is "pending"
            show_choice = (
                pending is not None
                and pending.player_id == player_id
                and not awaiting
                and pending.choicetype != ChoiceType.LOG_PAUSE
            )
        if show_choice and synthetic is not None:
            legal = synthetic.legal_action_vectors()
            pending_json = synthetic.to_json()
        elif show_choice and pending is not None:
            legal = self.engine.legal_actions()
            pending_json = pending.to_json()
        else:
            legal = []
            pending_json = None
        if pending_json is not None:
            pending_json["card_catalog"] = self._card_catalog_for_pending(pending)
            assign_units = self._assign_units_for_pending(pending, player_id)
            if assign_units:
                pending_json["assign_units"] = assign_units
                pending_json["assign_legality"] = self._assign_legality_for_pending(
                    player_id
                )
                blocked = getattr(self.engine, "_last_assign_block_reasons", None)
                if blocked:
                    pending_json["assign_block_reasons"] = blocked

        player = self.engine._player_by_id(player_id)
        hand_cards = {
            str(cid): describe_action_card(cid) for cid in player.action_cards
        }
        # All face-up convoy cards (own always; others after they act),
        # including WAIT-queued extras in the stack.
        placed: dict[str, Any] = {}
        for u in self.engine.convoy.units:
            if not u.actioncard:
                continue
            action = u.to_json(playerview=player).get("action") or {}
            entries = action.get("cards") or []
            if not entries and action.get("face_up") and action.get("card") is not None:
                entries = [action]
            for entry in entries:
                if entry.get("face_up") and entry.get("card") is not None:
                    placed[str(entry["card"])] = describe_action_card(entry["card"])

        from sixtyfivekmconvoy.core import config as game_config

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
            "awaiting_continue": awaiting,
            "continue_hint": continue_hint,
            "waiting_for": self.waiting_for_text(),
            "revision": self.revision,
            "log_cursor": log_cursor,
            "pause_after_actions": self.pause_after_actions,
            "setup_complete": self.engine.setup_complete,
            "setup_pattern": list(self.engine.setup_pattern),
            "shareable_state": self.get_shareable_state_string(),
            "config_name": getattr(game_config, "CONFIG_NAME", "default"),
            "bots": dict(self.bot_meta or {}),
            "cash_rewards": {
                "service": int(getattr(game_config, "SERVICE_CASH", 0) or 0),
                "attack": int(getattr(game_config, "ATTACK_CASH", 0) or 0),
                "scout": int(getattr(game_config, "REVEAL_RESISTANCE_CASH", 0) or 0),
                "reveal_mauling": int(
                    getattr(game_config, "REVEAL_MAULING_CASH", 0) or 0
                ),
                "reveal_resistance": int(
                    getattr(game_config, "REVEAL_RESISTANCE_CASH", 0) or 0
                ),
                "resistance_hit": int(
                    getattr(game_config, "RESISTANCE_HIT_CASH", 0) or 0
                ),
            },
        }

    def get_shareable_state_string(self) -> str:
        import json
        import zlib
        import base64

        key = (self.revision, len(self.human_choices), self.engine.seed)
        if key == self._share_key:
            return self._share_value
        human_seat_str = next(iter(self.human_seats))
        human_seat = int(human_seat_str.split("_")[1])
        data = {
            "p": len(self.engine.players),
            "s": self.engine.seed,
            "h": human_seat,
            "pa": self.pause_after_actions,
            "c": self.human_choices,
            "bk": (self.bot_meta or {}).get("bot_kind") or "random",
            "bid": (self.bot_meta or {}).get("bot_id"),
            "bl": (self.bot_meta or {}).get("league"),
        }
        json_bytes = json.dumps(data, separators=(",", ":")).encode("utf-8")
        compressed = zlib.compress(json_bytes)
        encoded = base64.urlsafe_b64encode(compressed).decode("utf-8")
        self._share_key = key
        self._share_value = encoded
        return encoded

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
        target = (pending.payload or {}).get("assign_unit")
        if isinstance(target, dict) and "index" in target:
            player = self.engine._player_by_id(player_id)
            waiting = [
                u
                for u in self.engine.convoy.units
                if u.player is player and not u.actioncard
            ]
            if not waiting:
                return [target]
            return [
                {
                    "index": u.index(),
                    "unit_type": u.type_to_str[u.unittype],
                    "unit_type_label": unit_type_label(u.unittype),
                    "zone": u.zone(),
                    "place": u.index(),
                }
                for u in waiting
            ]
        player = self.engine._player_by_id(player_id)
        units = [u for u in self.engine.convoy.units if u.player is player]
        if pending.num_choices != len(units) or pending.num_choices < 1:
            return []
        return [
            {
                "index": u.index(),
                "unit_type": u.type_to_str[u.unittype],
                "unit_type_label": unit_type_label(u.unittype),
            }
            for u in units
        ]

    def _assign_legality_for_pending(self, player_id: str) -> dict[str, dict[str, list[int]]]:
        """unit_index -> card_id -> legal face indices (for assign-time strikethrough)."""
        from sixtyfivekmconvoy.core import actions as action_mod

        player = self.engine._player_by_id(player_id)
        units = [u for u in self.engine.convoy.units if u.player is player]
        out: dict[str, dict[str, list[int]]] = {}
        # Parallel map of block reasons for debugging (does not affect UI contract).
        block_reasons: dict[str, dict[str, dict[str, list[str]]]] = {}
        for unit in units:
            by_card: dict[str, list[int]] = {}
            by_card_blocked: dict[str, dict[str, list[str]]] = {}
            unit_idx = unit.index()
            for cid in player.action_cards:
                faces = player.action_deck.describe(cid) if player.action_deck else []
                legal: list[int] = []
                blocked: dict[str, list[str]] = {}
                if isinstance(faces, list):
                    for face_i, desc in enumerate(faces):
                        if not isinstance(desc, dict):
                            continue
                        why = action_mod.why_action_impossible(
                            self.engine, unit_idx, desc
                        )
                        if not why:
                            legal.append(face_i)
                        else:
                            blocked[str(face_i)] = why
                by_card[str(cid)] = legal
                if blocked:
                    by_card_blocked[str(cid)] = blocked
            out[str(unit_idx)] = by_card
            if by_card_blocked:
                block_reasons[str(unit_idx)] = by_card_blocked
        # Stash on engine so a snapshot/log can reference last assign diagnostics.
        self.engine._last_assign_block_reasons = block_reasons  # type: ignore[attr-defined]
        return out

    def _placement_request(self, player_id: str) -> ChoiceRequest:
        from sixtyfivekmconvoy.core.models import UnitType
        from sixtyfivekmconvoy.core.setup_layouts import slots_for_player

        number = int(player_id.split("_")[1])
        slots = slots_for_player(self.engine.setup_pattern, number)
        troops = [
            {
                "unit_type": UnitType.PANZER,
                "unit_type_label": unit_type_label(UnitType.PANZER),
            },
            {
                "unit_type": UnitType.INFANTRY,
                "unit_type_label": unit_type_label(UnitType.INFANTRY),
            },
            {
                "unit_type": UnitType.LOGISTICS,
                "unit_type_label": unit_type_label(UnitType.LOGISTICS),
            },
        ]
        return ChoiceRequest(
            player_id=player_id,
            choicetype=ChoiceType.PLACE_UNITS,
            options=[UnitType.PANZER, UnitType.INFANTRY, UnitType.LOGISTICS],
            num_choices=3,
            description=(
                "Sijoita panssarit, jalkaväki ja huolto paikkoihin "
                + ", ".join(str(s) for s in slots)
            ),
            payload={
                "slots": list(slots),
                "pattern": list(self.engine.setup_pattern),
                "troops": troops,
            },
        )

    def _remember_bot_placements(self) -> None:
        pending = self.engine.pending_choice()
        if pending is None or pending.choicetype != ChoiceType.PLACE_UNITS:
            self.placement_answers = None
            return
        self.placement_answers = {}
        legal = pending.legal_action_vectors()
        for pid, bot in self.bots.items():
            seat = int(pid.split("_")[1])
            obs = self.engine.observe(pid)
            try:
                choice = list(
                    bot.choose(
                        legal,
                        observation=obs,
                        agent_index=seat,
                        num_players=len(self.engine.players),
                        raw_choice=obs.get("choice"),
                    )
                )
            except Exception:
                choice = list(legal[0])
            if choice not in legal:
                choice = list(legal[0])
            self.placement_answers[pid] = choice

    def _accept_placement(self, player_id: str, choice: list[int]) -> dict[str, Any]:
        if self.placement_answers is None:
            raise ValueError("Not your turn")
        if player_id not in self.human_seats or player_id in self.placement_answers:
            raise ValueError("Not your turn")
        req = self._placement_request(player_id)
        legal = req.legal_action_vectors()
        if choice not in legal:
            if len(choice) == 1 and 0 <= choice[0] < len(legal):
                choice = list(legal[choice[0]])
            else:
                raise ValueError(f"Illegal choice {choice}")
        self.placement_answers[player_id] = list(choice)
        self.human_choices.append(list(choice))
        if all(p.agent_id() in self.placement_answers for p in self.engine.players):
            self._commit_placements()
        else:
            self.revision += 1
        return self.snapshot(player_id)

    def _commit_placements(self) -> None:
        assert self.placement_answers is not None
        before = len(self.engine.messages)
        for player in self.engine.players:
            pid = player.agent_id()
            pending = self.engine.pending_choice()
            if (
                pending is None
                or pending.choicetype != ChoiceType.PLACE_UNITS
                or pending.player_id != pid
            ):
                who = pending.player_id if pending is not None else "nobody"
                raise RuntimeError(f"expected {pid} to place, engine has {who}")
            self.engine.step(self.placement_answers[pid])
        self.placement_answers = None
        self.revision += 1
        if self._should_pause(before):
            self.awaiting_continue = True
            return
        self._run_bots()

    def waiting_for_text(self) -> str:
        if self.engine.terminal:
            return ""
        if self.placement_answers is not None:
            waiting = [
                p
                for p in self.engine.players
                if p.agent_id() not in self.placement_answers
                and p.agent_id() in self.human_seats
            ]
            return _waiting_sentence(waiting, "sijoittamaan joukot")
        if not self._several_humans() and (
            self.awaiting_continue or self._pending_is_log_pause()
        ):
            humans = [
                p
                for p in self.engine.players
                if p.agent_id() in self.human_seats
            ]
            return _waiting_sentence(humans, "jatkamaan")
        pending = self.engine.pending_choice()
        if pending is None:
            return ""
        try:
            player = self.engine._player_by_id(pending.player_id)
        except KeyError:
            return ""
        verb = _WAIT_VERB.get(pending.choicetype, "toimimaan")
        return _waiting_sentence([player], verb)

    def _human_must_act(self) -> bool:
        pending = self.engine.pending_choice()
        return (
            pending is not None
            and pending.player_id in self.human_seats
            and not self.engine.terminal
        )

    def _pending_is_log_pause(self) -> bool:
        pending = self.engine.pending_choice()
        return (
            pending is not None
            and pending.choicetype == ChoiceType.LOG_PAUSE
        )

    def _pause_mark(self) -> tuple:
        pending = self.engine.pending_choice()
        if pending is None:
            return ("none", len(self.engine.messages))
        return (
            int(pending.choicetype),
            pending.player_id,
            pending.description,
            len(self.engine.messages),
        )

    def _drain_multi_log_pause(self) -> None:
        """Step log pauses once per distinct state.

        Polls used to enter this on every refresh and copy the whole log
        again even when the engine could not move.
        """
        if not (self._several_humans() and self._pending_is_log_pause()):
            self._pause_drain_mark = None
            return
        mark = self._pause_mark()
        if mark == self._pause_drain_mark:
            return
        self._run_bots()
        after = self._pause_mark()
        if after != mark:
            self.revision += 1
        # Progress may have stopped on the next pause; let a later poll
        # continue. No progress means retrying would only repeat the work.
        self._pause_drain_mark = after if after == mark else None

    def _should_pause(self, log_len_before: int) -> bool:
        if self._several_humans():
            # Log clicks are per viewer. The engine keeps moving to the next human.
            return False
        if not self.pause_after_actions:
            return False
        if self.engine.terminal:
            return False
        if len(self.engine.messages) <= log_len_before:
            return False
        # Engine already yielded LOG_PAUSE for this event; UI maps that to continue.
        if self._pending_is_log_pause():
            return False
        # Pause so the new log line is shown before the next human choice / bots.
        return True

    def continue_block_reason(self, player_id: str | None = None) -> str | None:
        """Why a real choice cannot be applied yet, or None if one can."""
        pending = self.engine.pending_choice()
        last = self.engine.messages[-1] if self.engine.messages else ""
        log_pause = (
            pending is not None
            and pending.choicetype == ChoiceType.LOG_PAUSE
            and (player_id is None or pending.player_id == player_id)
        )
        if self.awaiting_continue or log_pause:
            parts = ["Press Jatka before the next choice."]
            if self.awaiting_continue:
                parts.append("The game is paused after a logged action.")
            if log_pause and pending is not None:
                parts.append(
                    "A continue pause is still open"
                    + (f": {pending.description}" if pending.description else ".")
                )
            if last:
                parts.append(f"Last log line: {last}")
            return " ".join(parts)
        return None

    def _waiting_assign_units(self, player_id: str) -> list[Any]:
        player = self.engine._player_by_id(player_id)
        return [
            unit
            for unit in self.engine.convoy.units
            if unit.player is player and not unit.actioncard
        ]

    def _apply_assign_batch(self, player_id: str, cards: list[int]) -> dict[str, Any]:
        """Place one hand card on each waiting unit, front to back, in one click."""
        pending = self.engine.pending_choice()
        if (
            pending is None
            or pending.player_id != player_id
            or pending.choicetype != ChoiceType.CHOOSE_CARD
            or (pending.payload or {}).get("reason") != "assign"
        ):
            raise ValueError("Not your turn")
        waiting = self._waiting_assign_units(player_id)
        if len(cards) != len(waiting):
            raise ValueError(
                f"Illegal choice {cards}: expected {len(waiting)} cards"
            )
        hand = list(self.engine._player_by_id(player_id).action_cards)
        for card in cards:
            if card not in hand:
                raise ValueError(f"Illegal choice {[card]}")
            hand.remove(card)
        before = len(self.engine.messages)
        for card in cards:
            pending = self.engine.pending_choice()
            if (
                pending is None
                or pending.player_id != player_id
                or pending.choicetype != ChoiceType.CHOOSE_CARD
                or (pending.payload or {}).get("reason") != "assign"
                or card not in pending.options
            ):
                raise ValueError(f"Illegal choice {[card]}")
            picked = [int(card)]
            self.human_choices.append(picked)
            self.engine.step(picked)
        if self._should_pause(before):
            self.awaiting_continue = True
            self.revision += 1
            return self.snapshot(player_id)
        self._run_bots()
        self.revision += 1
        return self.snapshot(player_id)

    def apply_human_choice(self, player_id: str, choice: list[int]) -> dict[str, Any]:
        if self.placement_answers is not None:
            return self._accept_placement(player_id, choice)
        pending = self.engine.pending_choice()
        blocked = self.continue_block_reason(player_id)
        if blocked:
            raise ValueError(blocked)
        if pending is None or pending.player_id != player_id:
            raise ValueError("Not your turn")
        if (
            len(choice) > 1
            and pending.choicetype == ChoiceType.CHOOSE_CARD
            and (pending.payload or {}).get("reason") == "assign"
        ):
            return self._apply_assign_batch(player_id, [int(card) for card in choice])
        legal = self.engine.legal_actions()

        is_ordered = pending.choicetype in (
            ChoiceType.CHOOSE_CARD,
            ChoiceType.CHOOSE_ACTION,
            ChoiceType.PLACE_UNITS,
            ChoiceType.REORDER_SCOUTED_CARDS,
        )

        matched_vector = None
        if is_ordered:
            if choice in legal:
                matched_vector = choice
        else:
            # Unordered: compare as sorted lists
            choice_sorted = sorted(choice)
            for leg in legal:
                if sorted(leg) == choice_sorted:
                    matched_vector = leg
                    break

        if matched_vector is None:
            if len(choice) == 1 and 0 <= choice[0] < len(legal):
                choice = list(legal[choice[0]])
            else:
                raise ValueError(f"Illegal choice {choice}")
        else:
            choice = matched_vector

        self.human_choices.append(choice)
        before = len(self.engine.messages)
        self.engine.step(choice)
        if self._should_pause(before):
            self.awaiting_continue = True
            self.revision += 1
            return self.snapshot(player_id)
        self._run_bots()
        self.revision += 1
        return self.snapshot(player_id)

    def continue_play(self, player_id: str) -> dict[str, Any]:
        """Resume after a pause (or no-op if not paused)."""
        if self._several_humans():
            # Jatka only turns this viewer's log page, unless the engine is
            # actually parked on a log pause. That pause is not their turn.
            if self._pending_is_log_pause():
                self._run_bots()
                self.revision += 1
            seen = self.log_seen.get(player_id, 0)
            if seen < len(self.engine.messages):
                self.log_seen[player_id] = seen + 1
            return self.snapshot(player_id)
        self.awaiting_continue = False
        self.engine.clear_hit_draws()
        if self.engine.terminal:
            return self.snapshot(player_id)

        pending = self.engine.pending_choice()
        if (
            pending is not None
            and pending.choicetype == ChoiceType.LOG_PAUSE
            and pending.player_id == player_id
        ):
            before = len(self.engine.messages)
            legal = self.engine.legal_actions()
            self.engine.step(legal[0] if legal else [0])
            self.revision += 1
            if self._should_pause(before):
                self.awaiting_continue = True
                return self.snapshot(player_id)

        if self._human_must_act() and not self._pending_is_log_pause():
            return self.snapshot(player_id)
        self._run_bots()
        self.revision += 1
        return self.snapshot(player_id)

    def _run_bots(self) -> None:
        self.awaiting_continue = False
        steps = 0
        while not self.engine.terminal:
            steps += 1
            if steps > 400:
                break
            pending = self.engine.pending_choice()
            if pending is None:
                break
            if pending.choicetype == ChoiceType.LOG_PAUSE:
                if self._several_humans():
                    # The pause names one human seat, but the next unit may be a
                    # bot. Step it and keep going so that bot acts before we ask
                    # the following human.
                    self.engine.clear_hit_draws()
                    self.engine.step([0])
                    continue
                break
            if pending.player_id in self.human_seats:
                break
            bot = self.bots[pending.player_id]
            before = len(self.engine.messages)
            legal = self.engine.legal_actions()
            seat = int(pending.player_id.split("_")[1])
            obs = self.engine.observe(pending.player_id)
            choice = bot.choose(
                legal,
                observation=obs,
                agent_index=seat,
                num_players=len(self.engine.players),
                raw_choice=obs.get("choice"),
            )
            self.engine.step(choice)
            if self._should_pause(before):
                self.awaiting_continue = True
                break
            # A bot step often ends on LOG_PAUSE. Loop and consume it.


def _waiting_sentence(players, verb: str) -> str:
    if not players:
        return ""
    bits = []
    for player in players:
        color = _COLOR_PARTITIVE[player.number % len(_COLOR_PARTITIVE)]
        bits.append(f"{color} pelaajaa {player.name}")
    if len(bits) == 1:
        names = bits[0]
    elif len(bits) == 2:
        names = f"{bits[0]} ja {bits[1]}"
    else:
        names = ", ".join(bits[:-1]) + " ja " + bits[-1]
    return f"Odotetaan {names} {verb}"


def _require_player_name(name: str | None) -> str:
    text = " ".join((name or "").split())
    if not text:
        raise ValueError("Anna nimi.")
    return text[:32]


@dataclass
class OpenTable:
    table_id: str
    num_players: int
    seed: int | None
    max_rounds: int
    pause_after_actions: bool
    bot_kind: str
    bot_id: str | None
    league_path: str | None
    seats: dict[int, str]
    started_game_id: str | None = None

    def public(self) -> dict[str, Any]:
        rows = []
        for seat in range(self.num_players):
            rows.append(
                {
                    "seat": seat,
                    "name": self.seats.get(seat),
                    "open": seat not in self.seats,
                    "color": _COLOR_NOMINATIVE[seat % len(_COLOR_NOMINATIVE)],
                }
            )
        return {
            "table_id": self.table_id,
            "num_players": self.num_players,
            "seed": self.seed,
            "pause_after_actions": self.pause_after_actions,
            "bot_kind": self.bot_kind,
            "host_seat": 0,
            "started_game_id": self.started_game_id,
            "open_count": sum(1 for row in rows if row["open"]),
            "seats": rows,
        }


class SessionManager:
    def __init__(self, max_games: int = 3) -> None:
        self.max_games = max(1, int(max_games))
        self.sessions: dict[str, GameSession] = {}
        self.tables: dict[str, OpenTable] = {}
        self._lock = threading.Lock()

    def _occupancy_unlocked(self) -> int:
        live = sum(1 for s in self.sessions.values() if not s.engine.terminal)
        waiting = sum(1 for t in self.tables.values() if t.started_game_id is None)
        return live + waiting

    def _require_room(self) -> None:
        if self._occupancy_unlocked() >= self.max_games:
            raise RuntimeError(
                f"Pelejä on jo {self.max_games}. Lopeta yksi ennen uutta."
            )

    def lobby_status(self) -> dict[str, Any]:
        with self._lock:
            tables = [
                t.public()
                for t in self.tables.values()
                if t.started_game_id is None
            ]
            return {
                "max_games": self.max_games,
                "games_in_use": self._occupancy_unlocked(),
                "tables": tables,
            }

    def create_table(
        self,
        *,
        num_players: int = 3,
        name: str | None = None,
        seed: int | None = None,
        max_rounds: int = 200,
        pause_after_actions: bool = True,
        bot_kind: str = "random",
        bot_id: str | None = None,
        league_path: str | None = None,
    ) -> OpenTable:
        with self._lock:
            self._require_room()
            table = OpenTable(
                table_id=uuid.uuid4().hex[:10],
                num_players=num_players,
                seed=seed,
                max_rounds=max_rounds,
                pause_after_actions=pause_after_actions,
                bot_kind=bot_kind,
                bot_id=bot_id,
                league_path=league_path,
                seats={0: _require_player_name(name)},
            )
            self.tables[table.table_id] = table
            return table

    def get_table(self, table_id: str) -> OpenTable:
        try:
            return self.tables[table_id]
        except KeyError:
            raise KeyError(table_id) from None

    def join_table(self, table_id: str, name: str | None) -> tuple[OpenTable, int]:
        with self._lock:
            table = self.tables.get(table_id)
            if table is None:
                raise KeyError(table_id)
            if table.started_game_id is not None:
                raise ValueError("Peli on jo alkanut")
            open_seats = [i for i in range(table.num_players) if i not in table.seats]
            if not open_seats:
                raise ValueError("Pöytä on täynnä")
            seat = open_seats[0]
            table.seats[seat] = _require_player_name(name)
            return table, seat

    def start_table(
        self,
        table_id: str,
        seat: int = 0,
        external_bots: dict[str, Any] | None = None,
    ) -> tuple[GameSession, str]:
        with self._lock:
            table = self.tables.get(table_id)
            if table is None:
                raise KeyError(table_id)
            if seat != 0 or 0 not in table.seats:
                raise ValueError("Vain pelin avaaja voi aloittaa")
            if table.started_game_id is not None:
                session = self.sessions[table.started_game_id]
                return session, f"player_{seat}"
            # The waiting table already counts toward the cap. Starting it
            # replaces that slot with a live game, so don't require a new one.
            session = self._create_unlocked(
                num_players=table.num_players,
                human_seats=dict(table.seats),
                seed=table.seed,
                max_rounds=table.max_rounds,
                pause_after_actions=table.pause_after_actions,
                bot_kind=table.bot_kind,
                bot_id=table.bot_id,
                league_path=table.league_path,
                count_against_cap=False,
                external_bots=external_bots,
            )
            table.started_game_id = session.game_id
            return session, "player_0"

    def create(
        self,
        num_players: int = 3,
        human_seat: int = 0,
        seed: int | None = None,
        max_rounds: int = 200,
        pause_after_actions: bool = True,
        *,
        bot_kind: str = "random",
        bot_id: str | None = None,
        league_path: str | None = None,
    ) -> GameSession:
        with self._lock:
            return self._create_unlocked(
                num_players=num_players,
                human_seats={human_seat: f"player_{human_seat}"},
                seed=seed,
                max_rounds=max_rounds,
                pause_after_actions=pause_after_actions,
                bot_kind=bot_kind,
                bot_id=bot_id,
                league_path=league_path,
            )

    def _create_unlocked(
        self,
        *,
        num_players: int,
        human_seats: dict[int, str],
        seed: int | None,
        max_rounds: int,
        pause_after_actions: bool,
        bot_kind: str,
        bot_id: str | None,
        league_path: str | None,
        count_against_cap: bool = True,
        external_bots: dict[str, Any] | None = None,
    ) -> GameSession:
        if count_against_cap:
            self._require_room()
        if not human_seats:
            raise ValueError("at least one human seat")
        engine = GameEngine()
        human_seat = min(human_seats)
        engine.human_seat = human_seat
        engine.pause_after_actions = pause_after_actions
        engine.reset(num_players=num_players, seed=seed, max_rounds=max_rounds)
        for seat, name in human_seats.items():
            engine.players[seat].name = name
        for player in engine.players:
            if player.number not in human_seats:
                player.name = "Botti"
        game_id = uuid.uuid4().hex[:10]
        human_ids = {f"player_{seat}" for seat in human_seats}
        if external_bots is not None:
            bots = external_bots
            bot_meta = {
                "bot_kind": bot_kind,
                "bot_id": bot_id,
                "bot_name": bot_id,
                "league": league_path,
            }
        else:
            bots, bot_meta = make_seat_bots(
                engine.agent_ids(),
                human_id=f"player_{human_seat}",
                human_ids=human_ids,
                seed=seed if seed is not None else engine.seed,
                bot_kind=bot_kind,
                bot_id=bot_id,
                league_path=league_path,
            )
        for bot in bots.values():
            reset = getattr(bot, "reset_memory", None)
            if callable(reset):
                reset()
        session = GameSession(
            game_id=game_id,
            engine=engine,
            human_seats=set(human_ids),
            bots=bots,
            bot_meta=bot_meta,
            pause_after_actions=pause_after_actions,
        )
        session._remember_bot_placements()
        session.log_seen = {pid: len(engine.messages) for pid in human_ids}
        if session.placement_answers is not None and all(
            p.agent_id() in session.placement_answers for p in engine.players
        ):
            session._commit_placements()
        elif session.placement_answers is None:
            session._run_bots()
        self.sessions[game_id] = session
        return session

    def create_from_state_string(self, state_string: str) -> GameSession:
        import json
        import zlib
        import base64

        with self._lock:
            self._require_room()
            try:
                compressed = base64.urlsafe_b64decode(state_string.encode("utf-8"))
                json_bytes = zlib.decompress(compressed)
                data = json.loads(json_bytes.decode("utf-8"))
            except Exception as exc:
                raise ValueError(f"Invalid state string: {exc}")

            num_players = data.get("p", 3)
            seed = data.get("s")
            human_seat = data.get("h", 0)
            pause_after_actions = data.get("pa", True)
            choices = data.get("c", [])
            bot_kind = data.get("bk") or "random"
            bot_id = data.get("bid")
            league_path = data.get("bl")

            engine = GameEngine()
            engine.human_seat = human_seat
            engine.pause_after_actions = pause_after_actions
            engine.reset(num_players=num_players, seed=seed)
            game_id = uuid.uuid4().hex[:10]
            human_id = f"player_{human_seat}"
            engine.players[human_seat].name = human_id
            bots, bot_meta = make_seat_bots(
                engine.agent_ids(),
                human_id=human_id,
                seed=engine.seed,
                bot_kind=bot_kind,
                bot_id=bot_id,
                league_path=league_path,
            )
            for bot in bots.values():
                reset = getattr(bot, "reset_memory", None)
                if callable(reset):
                    reset()
            for player in engine.players:
                if player.number != human_seat:
                    player.name = "Botti"
            session = GameSession(
                game_id=game_id,
                engine=engine,
                human_seats={human_id},
                bots=bots,
                bot_meta=bot_meta,
                pause_after_actions=pause_after_actions,
            )

            session._remember_bot_placements()
            session.log_seen = {human_id: len(engine.messages)}
        for index, choice in enumerate(choices, start=1):
            hops = 0
            while session.continue_block_reason(human_id):
                hops += 1
                if hops > 40:
                    raise ValueError(
                        f"Saved choice {index}/{len(choices)} {choice} was not reached. "
                        f"{session.continue_block_reason(human_id)}"
                    )
                session.continue_play(human_id)
            try:
                session.apply_human_choice(human_id, choice)
            except ValueError as exc:
                pending = session.engine.pending_choice()
                pending_bit = ""
                if pending is not None:
                    pending_bit = (
                        f" Game is waiting on {pending.choicetype.name} "
                        f"for {pending.player_id}"
                        + (f": {pending.description}" if pending.description else ".")
                    )
                raise ValueError(
                    f"Saved choice {index}/{len(choices)} {choice} does not match this game. "
                    f"{exc}.{pending_bit}"
                ) from exc

        self.sessions[game_id] = session
        return session

    def get(self, game_id: str) -> GameSession:
        return self.sessions[game_id]
