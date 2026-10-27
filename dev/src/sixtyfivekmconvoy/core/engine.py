"""Pure game engine with ChoiceRequest yield protocol."""

from __future__ import annotations

import itertools
import random
from dataclasses import dataclass, field
from typing import Any, Generator

# card_display imported lazily in choice builders to avoid cycles

from . import actions as action_mod
from .cards import (
    ACTION_CATALOG,
    HIT_CATALOG,
    MAULING_CATALOG,
    OFFICER_CATALOG,
    PILLAGE_CATALOG,
    RESISTANCE_CATALOG,
    CardDeck,
    CardQueue,
    select_resistance_deck,
)
from .constants import (
    ActionName,
    CARDS_TO_DEAL,
    CARD_TO_POINTS_RATIO,
    ChoiceType,
    MIN_PLAYER_CARD_LIMIT,
    UNIT_TYPE_STR,
)
from .i18n import t, unit_type_label
from .models import Convoy, Player, Resistance, Unit, UnitType
from .setup_layouts import pick_setup_pattern, slots_for_player
from .stats import EpisodeStats
from .view import player_view


@dataclass
class ChoiceRequest:
    player_id: str
    choicetype: ChoiceType
    options: list[Any]
    num_choices: int = 1
    description: str = ""
    payload: dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> dict:
        data = {
            "choicetype": int(self.choicetype),
            "options": self.options,
            "num_choice": self.num_choices,
            "description": self.description,
            "player_id": self.player_id,
        }
        if self.payload:
            data["payload"] = self.payload
        return data

    def legal_action_vectors(self) -> list[list[int]]:
        """Enumerate valid choice vectors for the PettingZoo action mask."""
        opts = list(self.options)
        n = self.num_choices
        if n <= 0:
            return [[]]
        if n == 1:
            return [[o] for o in opts]
        indices = range(len(opts))
        # Place-units: options are troop types; choice is a permutation onto slots.
        if self.choicetype == ChoiceType.PLACE_UNITS:
            return [list(p) for p in itertools.permutations(opts)]
        # Card-to-unit assignment is ordered; discards/cash-in are unordered.
        ordered = self.choicetype in (ChoiceType.CHOOSE_CARD, ChoiceType.CHOOSE_ACTION)
        vectors: list[list[int]] = []
        if ordered:
            for perm in itertools.permutations(indices, n):
                vectors.append([opts[i] for i in perm])
        else:
            for combo in itertools.combinations(indices, n):
                vectors.append([opts[i] for i in combo])
        # Cap explosion for large hands (RL mask size)
        if len(vectors) > 256:
            vectors = vectors[:256]
        return vectors or [[]]


@dataclass
class StepResult:
    terminal: bool = False
    message: str | None = None
    ranking: list[dict] | None = None


@dataclass
class Rounds:
    stages = {
        0: "Deal cards",
        1: "Place actions",
        2: "Actions round",
        3: "Advance convoy",
        4: "Mauling",
        5: "Bookkeeping",
    }

    count: int = 0
    stage: int = -1

    def next_round(self) -> None:
        self.count += 1
        self.stage = -1

    def next_stage(self) -> str | None:
        self.stage += 1
        return self.stages.get(self.stage)


class GameEngine:
    """Authoritative rules engine. No I/O — adapters drive choices via step()."""

    def __init__(self) -> None:
        self.players: list[Player] = []
        self.convoy: Convoy | None = None  # type: ignore[assignment]
        self.resistance = Resistance(None)
        self.rounds: Rounds | None = None
        self.terminal = False
        self.stats = EpisodeStats()
        self.rng = random.Random()
        self._pending: ChoiceRequest | None = None
        self._gen: Generator[ChoiceRequest, list[int], StepResult] | None = None
        self._last_result = StepResult()
        self.round_action_summaries: list[str] = []
        self.round_resistance_damage = 0
        self.round_unit_damage: list[tuple[int, int]] = []
        self.messages: list[str] = []
        self.event_log: list[dict[str, Any]] = []
        self.ranking: list[dict] | None = None

        # decks/queues filled in reset()
        self.action_deck: CardDeck
        self.resistance_deck: CardDeck
        self.pillage_deck: CardDeck
        self.mauling_deck: CardDeck
        self.officer_deck: CardDeck
        self.hit_deck: CardDeck
        self.officer_id_mapping: dict[int, int] = {}
        self.resistance_queue: CardQueue
        self.mauling_queue: CardQueue
        self.pillage_queue: CardQueue
        self.officer_queue: CardQueue

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def reset(
        self,
        num_players: int = 3,
        seed: int | None = None,
        max_rounds: int = 200,
    ) -> None:
        self.rng = random.Random(seed)
        self.terminal = False
        self.ranking = None
        self.messages = []
        self.event_log: list[dict[str, Any]] = []
        self.round_action_summaries = []
        self.max_rounds = max_rounds
        self.stats = EpisodeStats(seed=seed, num_players=num_players)

        self.players = [Player(i) for i in range(num_players)]
        self._init_decks()
        self.convoy = Convoy(self.players, engine=self)
        self.setup_pattern: tuple[int, ...] = pick_setup_pattern(num_players, self.rng)
        self.setup_complete = False
        # Keep created units aside until players place them into the pattern.
        self._unit_pool: list[Unit] = list(self.convoy.units)
        self.convoy.units = []

        # Fixed starting resistance, then fill the queue from the sampled deck.
        self.resistance_queue.put_card(self._resistance_starter_id, visible=True)
        for _ in range(2):
            if self.resistance_deck.deck:
                self.resistance_queue.put_card(self.resistance_deck.get_card())
        for _ in range(3):
            self.mauling_queue.put_card(self.mauling_deck.get_card())
        self.mauling_queue.reveal_card(0)
        self.resistance = Resistance(self.resistance_queue.describe(0), self)
        self.rounds = Rounds(count=0, stage=0)

        self._gen = self._run_game()
        self._pending = None
        self._prime()

    def current_agent(self) -> str | None:
        if self.terminal or self._pending is None:
            return None
        return self._pending.player_id

    def pending_choice(self) -> ChoiceRequest | None:
        return self._pending

    def legal_actions(self) -> list[list[int]]:
        if self._pending is None:
            return []
        return self._pending.legal_action_vectors()

    def observe(self, player_id: str) -> dict:
        player = self._player_by_id(player_id)
        return player_view(
            self,
            player,
            choice=self._pending if self._pending and self._pending.player_id == player_id else None,
            message=self.messages[-1] if self.messages else None,
        )

    def step(self, choice: list[int]) -> StepResult:
        if self.terminal:
            return StepResult(terminal=True, ranking=self.ranking)
        if self._gen is None:
            raise RuntimeError("Call reset() before step()")
        try:
            self._pending = self._gen.send(choice)
            return StepResult(terminal=False, message=self.messages[-1] if self.messages else None)
        except StopIteration as stop:
            result = stop.value if isinstance(stop.value, StepResult) else StepResult(terminal=True)
            self.terminal = True
            self._pending = None
            self._last_result = result
            self.ranking = result.ranking
            return result

    def winner_ranking(self) -> list[dict] | None:
        return self.ranking

    def agent_ids(self) -> list[str]:
        return [p.agent_id() for p in self.players]

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _player_by_id(self, player_id: str) -> Player:
        for p in self.players:
            if p.agent_id() == player_id:
                return p
        raise KeyError(player_id)

    def _init_decks(self) -> None:
        self.action_deck = CardDeck(
            list(ACTION_CATALOG.keys()),
            names_and_effects=ACTION_CATALOG,
            rng=self.rng,
        )
        for player in self.players:
            player.action_deck = CardDeck(
                list(ACTION_CATALOG.keys()),
                names_and_effects=ACTION_CATALOG,
                rng=self.rng,
            )

        starter_id, pool_ids = select_resistance_deck(len(self.players), self.rng)
        self._resistance_starter_id = starter_id
        # Catalog stays full for lookups; only the sampled ids are in the draw pile.
        self.resistance_deck = CardDeck(
            pool_ids,
            shuffled=False,  # already shuffled by select_resistance_deck
            names_and_effects=RESISTANCE_CATALOG,
            rng=self.rng,
        )
        self.pillage_deck = CardDeck(
            list(PILLAGE_CATALOG.keys()),
            names_and_effects=PILLAGE_CATALOG,
            rng=self.rng,
        )
        self.mauling_deck = CardDeck(
            list(MAULING_CATALOG.keys()),
            names_and_effects=MAULING_CATALOG,
            rng=self.rng,
        )
        self.hit_deck = CardDeck(
            list(HIT_CATALOG.keys()),
            names_and_effects=HIT_CATALOG,
            rng=self.rng,
        )

        officer_ids = sorted(OFFICER_CATALOG.keys())
        sequential = {i: OFFICER_CATALOG[oid] for i, oid in enumerate(officer_ids)}
        self.officer_id_mapping = {i: oid for i, oid in enumerate(officer_ids)}
        self.officer_deck = CardDeck(
            list(sequential.keys()),
            names_and_effects=sequential,
            rng=self.rng,
        )

        self.resistance_queue = CardQueue(self.resistance_deck)
        self.mauling_queue = CardQueue(self.mauling_deck)
        self.pillage_queue = CardQueue(self.pillage_deck)
        self.officer_queue = CardQueue(self.officer_deck)

    def draw_hit_damage(self, category: int) -> int:
        """
        Draw one hit-table card and return damage for attack `category` (1–4).

        Drawn cards go to the hit discard pile (reshuffled when the deck empties).
        """
        if category not in (1, 2, 3, 4):
            raise ValueError(f"Hit category must be 1–4, got {category}")
        card_id = self.hit_deck.get_card()
        damage = HIT_CATALOG[card_id].damage_for(category)
        self.hit_deck.discard_card(card_id)
        return damage

    def _prime(self) -> None:
        assert self._gen is not None
        try:
            self._pending = next(self._gen)
        except StopIteration as stop:
            self.terminal = True
            self._pending = None
            if isinstance(stop.value, StepResult):
                self._last_result = stop.value
                self.ranking = stop.value.ranking

    def _broadcast(self, message: str, **detail: Any) -> None:
        """Append a player-visible log line; optional structured detail for debugging."""
        self.messages.append(message)
        if not hasattr(self, "event_log") or self.event_log is None:
            self.event_log: list[dict[str, Any]] = []
        entry: dict[str, Any] = {
            "i": len(self.event_log),
            "round": self.rounds.count if self.rounds else 0,
            "stage": self.rounds.stage if self.rounds else -1,
            "msg": message,
        }
        if detail:
            entry["detail"] = detail
        self.event_log.append(entry)

    def _apply_unit_placements(self, placements: dict[int, list[int]]) -> None:
        """Build convoy order from ownership pattern + per-player troop permutations."""
        pool: dict[int, dict[int, Unit]] = {}
        for u in self._unit_pool:
            pool.setdefault(u.player.number, {})[u.unittype] = u
        ordered: list[Unit] = []
        cursor = {p: 0 for p in range(len(self.players))}
        for owner in self.setup_pattern:
            ut = placements[owner][cursor[owner]]
            cursor[owner] += 1
            ordered.append(pool[owner][ut])
        self.convoy.units = ordered
        self.setup_complete = True

    def _run_game(self) -> Generator[ChoiceRequest, list[int], StepResult]:
        assert self.rounds is not None and self.convoy is not None

        # ---- Setup: place units into a balanced ownership pattern ----
        self._broadcast("—— Asento: sijoita joukot saattueeseen ——")
        self._broadcast(
            f"Muodostelma: {''.join(str(p + 1) for p in self.setup_pattern)}"
        )
        placements: dict[int, list[int]] = {}
        troop_meta = [
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
        for player in self.players:
            slots = slots_for_player(self.setup_pattern, player.number)
            desc = (
                f"Sijoita panssarit, jalkaväki ja huolto paikkoihin "
                f"{', '.join(str(s) for s in slots)}"
            )
            chosen = yield ChoiceRequest(
                player_id=player.agent_id(),
                choicetype=ChoiceType.PLACE_UNITS,
                options=[UnitType.PANZER, UnitType.INFANTRY, UnitType.LOGISTICS],
                num_choices=3,
                description=desc,
                payload={
                    "slots": slots,
                    "pattern": list(self.setup_pattern),
                    "troops": troop_meta,
                },
            )
            if sorted(chosen) != [0, 1, 2]:
                raise ValueError(f"Invalid unit placement: {chosen}")
            placements[player.number] = list(chosen)
            self._broadcast(
                f"Pelaaja {player.number} sijoitti joukkonsa paikkoihin {slots}."
            )

        self._apply_unit_placements(placements)
        self._broadcast("Saattue muodostettu.")

        initial_units = len(self.convoy.units)

        while not self.terminal:
            self.rounds.stage = -1
            self.round_action_summaries = []
            self.round_resistance_damage = 0
            self.round_unit_damage = []
            for pl in self.players:
                pl.this_round_cash = 0

            self._broadcast(f"—— Kierros {self.rounds.count} alkaa ——")

            # Fill officer queue
            while len(self.officer_queue) < len(self.players):
                if not self.officer_deck.deck and not self.officer_deck.discard:
                    break
                self.officer_queue.put_card(self.officer_deck.get_card(), visible=True)

            # Deal
            self.rounds.next_stage()
            for _ in range(CARDS_TO_DEAL):
                for player in self.players:
                    player.draw_card(1)
            self._broadcast("Kortit jaettu.")

            # Assign actions
            self.rounds.next_stage()
            for player in self.players:
                units = [u for u in self.convoy.units if u.player is player]
                if not units:
                    continue
                desc = t("ui.choose_cards_for_units") + ": " + ", ".join(
                    unit_type_label(u.unittype) for u in units
                )
                for c in player.action_cards:
                    desc += f"\n  {c}"
                chosen = yield ChoiceRequest(
                    player_id=player.agent_id(),
                    choicetype=ChoiceType.CHOOSE_CARD,
                    options=list(player.action_cards),
                    num_choices=len(units),
                    description=desc,
                )
                # Deduplicate-safe: remove as we assign
                for i, card in enumerate(chosen):
                    units[i].actioncard = [card]
                    units[i].actiontaken = []
                    units[i].action_resolution = []
                    player.place_action_card(card)
            self._broadcast("Toimintakortit asetettu.")

            # Execute actions by index.
            # Track units by object identity — retreat/assault/bypass reorder the
            # convoy, so iterating stale indices double-resolves some units and
            # skips others.
            self.rounds.next_stage()
            action_index = 0
            while True:
                units_with_action = [
                    unit
                    for unit in self.convoy.units
                    if action_index < len(unit.actioncard)
                    and (
                        action_index >= len(unit.actiontaken)
                        or unit.actiontaken[action_index] is None
                    )
                ]
                if not units_with_action:
                    break

                for unit in units_with_action:
                    if unit.convoy is not self.convoy or unit not in self.convoy.units:
                        continue
                    unit_idx = unit.index()
                    actioncard = unit.actioncard[action_index]
                    while len(unit.actiontaken) <= action_index:
                        unit.actiontaken.append(None)

                    descriptions = unit.player.action_deck.describe(actioncard)
                    possible: list[tuple[int, dict]] = []
                    blocked_faces: list[dict[str, Any]] = []
                    for e, desc in enumerate(descriptions):
                        why = action_mod.why_action_impossible(self, unit_idx, desc)
                        if not why:
                            possible.append((e, desc))
                        else:
                            blocked_faces.append(
                                {
                                    "face_index": e,
                                    "action_name": desc.get("action_name"),
                                    "name": desc.get("name"),
                                    "reasons": why,
                                }
                            )

                    # Officer discard actions
                    for officer in list(unit.officers):
                        od = officer.get_discard_action_description()
                        if not od:
                            continue
                        if od["action_name"] in ActionName.UNIMPLEMENTED:
                            continue
                        why = action_mod.why_action_impossible(self, unit.index(), od)
                        if not why:
                            possible.append((len(possible), od))
                        else:
                            blocked_faces.append(
                                {
                                    "face_index": None,
                                    "action_name": od.get("action_name"),
                                    "name": od.get("name"),
                                    "reasons": why,
                                    "officer": True,
                                }
                            )

                    if len(possible) > 1:
                        from .card_display import format_face

                        labels = list(range(len(possible)))
                        action_choices = []
                        for opt_i, (face_i, desc) in enumerate(possible):
                            face = format_face(desc)
                            action_choices.append(
                                {
                                    "option": opt_i,
                                    "face_index": face_i,
                                    "kind": "officer" if desc.get("is_officer_discard") else "card",
                                    "face": face,
                                }
                            )
                        d = (
                            f"Choose action for {action_mod.unit_log_label(unit)}: "
                            + " ".join(
                                f'{i}:"{possible[i][1].get("name")}"' for i in labels
                            )
                        )
                        pick = yield ChoiceRequest(
                            player_id=unit.player.agent_id(),
                            choicetype=ChoiceType.CHOOSE_ACTION,
                            options=labels,
                            num_choices=1,
                            description=d,
                            payload={
                                "unit_index": unit.index(),
                                "unit_type_label": unit_type_label(unit.unittype),
                                "card_id": actioncard,
                                "actions": action_choices,
                            },
                        )
                        choice_i = pick[0]
                    elif len(possible) == 1:
                        choice_i = 0
                    else:
                        choice_i = -1

                    unit.actiontaken[action_index] = choice_i
                    while len(unit.action_resolution) <= action_index:
                        unit.action_resolution.append(None)
                    if choice_i < 0:
                        unit.action_resolution[action_index] = {
                            "kind": "frustrated",
                            "face_index": None,
                            "option": -1,
                            "name": None,
                        }
                        unit.become_frustrated()
                        label = action_mod.unit_log_label(unit)
                        face_bits = []
                        for blocked in blocked_faces:
                            face_bits.append(
                                f"{blocked.get('action_name') or '?'}:"
                                + ",".join(blocked["reasons"])
                            )
                        reason_txt = "; ".join(face_bits) if face_bits else "no faces"
                        msg = (
                            f"{label} frustrated on card {actioncard} "
                            f"(unit#{unit_idx} zone={unit.zone()} "
                            f"type={unit_type_label(unit.unittype)}; "
                            f"{action_mod.hidden_queue_summary(self)}): {reason_txt}"
                        )
                        self.round_action_summaries.append(msg)
                        self._broadcast(
                            msg,
                            kind="frustrated",
                            unit_index=unit_idx,
                            card_id=actioncard,
                            zone=unit.zone(),
                            blocked=blocked_faces,
                            queues=action_mod.hidden_queue_summary(self),
                        )
                    else:
                        face_i, desc = possible[choice_i]
                        kind = (
                            "officer"
                            if desc.get("is_officer_discard")
                            else "card"
                        )
                        unit.action_resolution[action_index] = {
                            "kind": kind,
                            "face_index": face_i if kind == "card" else None,
                            "option": choice_i,
                            "name": desc.get("name"),
                        }
                        unit_idx = unit.index()
                        summary = yield from action_mod.resolve_action(
                            self, unit_idx, desc, actioncard
                        )
                        self._broadcast(summary)

                action_index += 1

            # Advance
            self.rounds.next_stage()
            if not self.resistance.active:
                self.convoy.move_resting_and_damaged_units()
                if self.resistance_queue:
                    res_id, _ = self.resistance_queue.remove_card(0)
                    self.resistance_deck.discard_card(res_id)
                self.resistance_queue.put_card(self.resistance_deck.get_card())
                if self.resistance_queue.cards_and_visibilities and not self.resistance_queue.cards_and_visibilities[0][1]:
                    self.resistance_queue.reveal_card(0)
                    self.resistance = Resistance(self.resistance_queue.describe(0), self)
                    ambush = self.resistance.attack()
                    if self.resistance.attack_category > 0:
                        self._broadcast(f"Ambush: {ambush}")
                    else:
                        self._broadcast(ambush)
                else:
                    self.resistance = Resistance(self.resistance_queue.describe(0), self)
                self._broadcast(f'New resistance "{self.resistance.name}"')
            else:
                self._broadcast("Convoy stuck because of resistance.")

            # Mauling (hit-table damage and/or forced discard)
            self.rounds.next_stage()
            from .actions import resolve_mauling

            maul_id, _ = self.mauling_queue.remove_card(0)
            mauling = self.mauling_deck.describe(maul_id)
            msg = yield from resolve_mauling(self, mauling)
            self._broadcast(f"Mauling {mauling['name']}: {msg}")
            self.mauling_deck.discard_card(maul_id)
            self.mauling_queue.put_card(self.mauling_deck.get_card())

            # Bookkeeping
            self.rounds.next_stage()
            self._broadcast("Kirjanpito.")
            lost = initial_units - len(self.convoy.units)
            self.stats.units_lost = max(self.stats.units_lost, lost)

            for pl in self.players:
                if len(pl.action_cards) >= CARD_TO_POINTS_RATIO:
                    yes = yield ChoiceRequest(
                        player_id=pl.agent_id(),
                        choicetype=ChoiceType.CASH_IN_CARDS,
                        options=[0, 1],
                        num_choices=1,
                        description=f"Exchange {CARD_TO_POINTS_RATIO} cards for 1 cash? 0=no 1=yes",
                    )
                    if yes[0] == 1:
                        if len(pl.action_cards) == CARD_TO_POINTS_RATIO:
                            pl.discard(list(pl.action_cards))
                        else:
                            discard = yield ChoiceRequest(
                                player_id=pl.agent_id(),
                                choicetype=ChoiceType.CHOOSE_CARDS_TO_DISCARD,
                                options=list(pl.action_cards),
                                num_choices=CARD_TO_POINTS_RATIO,
                                description=f"Choose {CARD_TO_POINTS_RATIO} cards to cash in",
                            )
                            pl.discard(list(discard))
                        pl.get_cash(1)
                        self._broadcast(f"Player {pl.number} cashed in cards")

                card_limit = MIN_PLAYER_CARD_LIMIT
                for u in self.convoy.units:
                    if u.player is pl and UNIT_TYPE_STR[u.unittype] == "logistics":
                        card_limit += sum(1 for c in u.carry if c == 0)
                        break
                if len(pl.action_cards) > card_limit:
                    to_discard = len(pl.action_cards) - card_limit
                    discard = yield ChoiceRequest(
                        player_id=pl.agent_id(),
                        choicetype=ChoiceType.CHOOSE_CARDS_TO_DISCARD,
                        options=list(pl.action_cards),
                        num_choices=to_discard,
                        description=f"Hand limit {card_limit}; discard {to_discard}",
                    )
                    pl.discard(list(discard))

            max_score = max(pl.this_round_cash for pl in self.players)
            if max_score > 0:
                for pl in self.players:
                    if pl.this_round_cash == max_score:
                        pl.promotion_points += 1
                        self._broadcast(f"Player {pl.number} gets promotion point")

            if not self.resistance.active and self.round_resistance_damage > 0:
                # count kills when resistance was destroyed this round
                if self.resistance.status == "destroyed":
                    self.stats.record_resistance_kill()

            if len(self.convoy.units) <= len(self.players):
                ranking = self._compute_ranking()
                self.stats.finalize(ranking, self.rounds.count)
                self._broadcast("Game finished.")
                self.terminal = True
                return StepResult(terminal=True, ranking=ranking, message="Game finished.")

            if self.rounds.count + 1 >= self.max_rounds:
                ranking = self._compute_ranking()
                self.stats.finalize(ranking, self.rounds.count)
                self._broadcast("Max rounds reached.")
                self.terminal = True
                return StepResult(
                    terminal=True,
                    ranking=ranking,
                    message="Max rounds reached.",
                )

            for unit in self.convoy.units:
                if unit.actioncard and unit.player.action_deck:
                    for card in unit.actioncard:
                        unit.player.action_deck.discard_card(card)
                unit.clear_state()

            self._broadcast(f"—— Kierros {self.rounds.count} päättyy ——")
            self.rounds.next_round()

        ranking = self._compute_ranking()
        return StepResult(terminal=True, ranking=ranking)

    def _compute_ranking(self) -> list[dict]:
        rows = [p.to_json() for p in self.players]
        return sorted(rows, key=lambda k: (-k["promotion_points"], -k["total_cash"]))
