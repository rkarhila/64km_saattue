"""Pure game engine with ChoiceRequest yield protocol."""

from __future__ import annotations

import itertools
import random
from dataclasses import dataclass, field
from typing import Any, Generator

from . import actions as action_mod
from .cards import (
    ACTION_CATALOG,
    MAULING_CATALOG,
    OFFICER_CATALOG,
    PILLAGE_CATALOG,
    RESISTANCE_CATALOG,
    CardDeck,
    CardQueue,
)
from .constants import (
    ActionName,
    CARDS_TO_DEAL,
    CARD_TO_POINTS_RATIO,
    ChoiceType,
    MIN_PLAYER_CARD_LIMIT,
    UNIT_TYPE_STR,
)
from .models import Convoy, Player, Resistance, Unit
from .stats import EpisodeStats
from .view import player_view


@dataclass
class ChoiceRequest:
    player_id: str
    choicetype: ChoiceType
    options: list[Any]
    num_choices: int = 1
    description: str = ""

    def to_json(self) -> dict:
        return {
            "choicetype": int(self.choicetype),
            "options": self.options,
            "num_choice": self.num_choices,
            "description": self.description,
            "player_id": self.player_id,
        }

    def legal_action_vectors(self) -> list[list[int]]:
        """Enumerate valid choice vectors for the PettingZoo action mask."""
        opts = list(self.options)
        n = self.num_choices
        if n <= 0:
            return [[]]
        if n == 1:
            return [[o] for o in opts]
        indices = range(len(opts))
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
        self.ranking: list[dict] | None = None

        # decks/queues filled in reset()
        self.action_deck: CardDeck
        self.resistance_deck: CardDeck
        self.pillage_deck: CardDeck
        self.mauling_deck: CardDeck
        self.officer_deck: CardDeck
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
        self.round_action_summaries = []
        self.max_rounds = max_rounds
        self.stats = EpisodeStats(seed=seed, num_players=num_players)

        self.players = [Player(i) for i in range(num_players)]
        self._init_decks()
        self.convoy = Convoy(self.players, engine=self)
        self.rng.shuffle(self.convoy.units)

        for _ in range(3):
            self.resistance_queue.put_card(self.resistance_deck.get_card())
        for _ in range(3):
            self.mauling_queue.put_card(self.mauling_deck.get_card())
        self.resistance_queue.reveal_card(0)
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

        self.resistance_deck = CardDeck(
            list(RESISTANCE_CATALOG.keys()),
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

    def _broadcast(self, message: str) -> None:
        self.messages.append(message)

    def _run_game(self) -> Generator[ChoiceRequest, list[int], StepResult]:
        assert self.rounds is not None and self.convoy is not None
        initial_units = len(self.convoy.units)

        while not self.terminal:
            self.rounds.stage = -1
            self.round_action_summaries = []
            self.round_resistance_damage = 0
            self.round_unit_damage = []
            for pl in self.players:
                pl.this_round_cash = 0

            self._broadcast(f"============ Round {self.rounds.count} ==========")

            # Fill officer queue
            while len(self.officer_queue) < len(self.players):
                self.officer_queue.put_card(self.officer_deck.get_card(), visible=True)

            # Deal
            self.rounds.next_stage()
            for _ in range(CARDS_TO_DEAL):
                for player in self.players:
                    player.draw_card(1)

            # Assign actions
            self.rounds.next_stage()
            for player in self.players:
                units = [u for u in self.convoy.units if u.player is player]
                if not units:
                    continue
                desc = "Choose one action card per unit: " + ",".join(
                    UNIT_TYPE_STR[u.unittype] for u in units
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
                    player.place_action_card(card)

            # Execute actions by index
            self.rounds.next_stage()
            action_index = 0
            while True:
                units_with_action = [
                    idx
                    for idx, unit in enumerate(self.convoy.units)
                    if action_index < len(unit.actioncard)
                    and (
                        action_index >= len(unit.actiontaken)
                        or unit.actiontaken[action_index] is None
                    )
                ]
                if not units_with_action:
                    break

                for unit_idx in list(units_with_action):
                    if unit_idx >= len(self.convoy.units):
                        continue
                    unit = self.convoy.units[unit_idx]
                    actioncard = unit.actioncard[action_index]
                    while len(unit.actiontaken) <= action_index:
                        unit.actiontaken.append(None)

                    descriptions = unit.player.action_deck.describe(actioncard)
                    possible: list[tuple[int, dict]] = []
                    for e, desc in enumerate(descriptions):
                        if action_mod.is_action_possible(self, unit_idx, desc):
                            possible.append((e, desc))

                    # Officer discard actions
                    for officer in list(unit.officers):
                        od = officer.get_discard_action_description()
                        if not od:
                            continue
                        if od["action_name"] in ActionName.UNIMPLEMENTED:
                            continue
                        if action_mod.is_action_possible(self, unit.index(), od):
                            possible.append((len(possible), od))

                    if len(possible) > 1:
                        labels = list(range(len(possible)))
                        d = "Choose action: " + " ".join(
                            f'{i}:"{possible[i][1].get("name")}"' for i in labels
                        )
                        pick = yield ChoiceRequest(
                            player_id=unit.player.agent_id(),
                            choicetype=ChoiceType.CHOOSE_ACTION,
                            options=labels,
                            num_choices=1,
                            description=d,
                        )
                        choice_i = pick[0]
                    elif len(possible) == 1:
                        choice_i = 0
                    else:
                        choice_i = -1

                    unit.actiontaken[action_index] = choice_i
                    if choice_i < 0:
                        unit.become_frustrated()
                        self.round_action_summaries.append(
                            f"Unit {unit_idx} frustrated on card {actioncard}"
                        )
                    else:
                        # Refresh index in case prior actions moved units
                        unit_idx = unit.index()
                        summary = yield from action_mod.resolve_action(
                            self, unit_idx, possible[choice_i][1], actioncard
                        )
                        self._broadcast(summary)

                action_index += 1

            # Advance
            self.rounds.next_stage()
            if not self.resistance.active:
                self.convoy.move_resting_and_damaged_units()
                if self.resistance_queue:
                    self.resistance_queue.remove_card(0)
                self.resistance_queue.put_card(self.resistance_deck.get_card())
                if self.resistance_queue.cards_and_visibilities and not self.resistance_queue.cards_and_visibilities[0][1]:
                    self.resistance_queue.reveal_card(0)
                    self.resistance = Resistance(self.resistance_queue.describe(0), self)
                    ambush = self.resistance.attack()
                    self._broadcast(f"Ambush: {ambush}")
                else:
                    self.resistance = Resistance(self.resistance_queue.describe(0), self)
                self._broadcast(f'New resistance "{self.resistance.name}"')
            else:
                self._broadcast("Convoy stuck because of resistance.")

            # Mauling
            self.rounds.next_stage()
            maul_id, _ = self.mauling_queue.remove_card(0)
            mauling = self.mauling_deck.describe(maul_id)
            target = mauling["effect"]["target"]
            damage = mauling["effect"]["damage"][0]
            atype = mauling["effect"]["type"][0]
            if target in "ABCE":
                msg = self.convoy.apply_damage(damage, zone=target, attack_type=atype)
            else:
                zone = target[0]
                rel = int(target[1:]) if len(target) > 1 else 1
                msg = self.convoy.apply_damage(
                    damage, unit=rel, zone=zone, attack_type=atype
                )
            self._broadcast(f"Mauling {mauling['name']}: {msg}")
            self.mauling_queue.put_card(self.mauling_deck.get_card())

            # Bookkeeping
            self.rounds.next_stage()
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
                    if u.player is pl and UNIT_TYPE_STR[u.unittype] == "Log":
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

            self.rounds.next_round()

        ranking = self._compute_ranking()
        return StepResult(terminal=True, ranking=ranking)

    def _compute_ranking(self) -> list[dict]:
        rows = [p.to_json() for p in self.players]
        return sorted(rows, key=lambda k: (-k["promotion_points"], -k["total_cash"]))
