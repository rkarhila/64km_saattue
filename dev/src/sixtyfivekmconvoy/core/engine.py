"""Pure game engine with ChoiceRequest yield protocol."""

from __future__ import annotations

import itertools
import random
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Generator

from sixtyfivekmconvoy.rl.events import EVENT_WINDOW, event_from_detail

# card_display imported lazily in choice builders to avoid cycles

from . import actions as action_mod
from .cards import (
    ACTION_CATALOG,
    HIT_DECKS,
    MAULING_CATALOG,
    OFFICER_CATALOG,
    PILLAGE_CATALOG,
    RESISTANCE_CATALOG,
    CardDeck,
    CardQueue,
    select_resistance_deck,
)
from .config import CARDS_TO_DEAL, CARDS_TO_DEAL_FIRST_ROUND
from .constants import (
    ActionName,
    CARD_TO_POINTS_RATIO,
    ChoiceType,
    MIN_PLAYER_CARD_LIMIT,
    UNIT_TYPE_STR,
    PLAYER_COLORS,
)
from .i18n import t, unit_type_label
from .models import Convoy, Player, Resistance, Unit, UnitType
from .setup_layouts import pattern_for_players, slots_for_player
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
        ordered = self.choicetype in (
            ChoiceType.CHOOSE_CARD,
            ChoiceType.CHOOSE_ACTION,
            ChoiceType.REORDER_SCOUTED_CARDS,
        )
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
        self.human_seat = 0
        self.pause_after_actions = True
        self.current_action_index = 0
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
        self.event_rows: deque[list[int]] = deque(maxlen=EVENT_WINDOW)
        # Training turns this off so log strings are not stored.
        self.record_text_log = True
        self.ranking: list[dict] | None = None

        # decks/queues filled in reset()
        self.action_deck: CardDeck
        self.resistance_deck: CardDeck
        self.pillage_deck: CardDeck
        self.mauling_deck: CardDeck
        self.officer_deck: CardDeck
        self.hit_decks: dict[int, CardDeck]
        self.hit_draws: list[dict[str, int]] = []
        self.struck_units: list[Unit] = []
        self.resistance_struck = False
        self._consolidating: set[int] = set()
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
        if seed is None:
            seed = random.Random().randint(0, 999999)
        self.seed = seed
        self.rng = random.Random(seed)
        self.terminal = False
        self.ranking = None
        self._end_message: str | None = None
        # True after ≥2 players hit PROMOTION_POINTS_TO_WIN on the same round.
        self.sudden_death_pp = False
        self.messages = []
        self.hit_draws = []
        self.struck_units = []
        self.resistance_struck = False
        self.event_log = []
        self.event_rows = deque(maxlen=EVENT_WINDOW)
        self.round_action_summaries = []
        self.max_rounds = max_rounds
        self.stats = EpisodeStats(seed=seed, num_players=num_players)

        self.players = [Player(i) for i in range(num_players)]
        for pl in self.players:
            pl.engine = self
        self._init_decks()
        self.convoy = Convoy(self.players, engine=self)
        self.setup_complete = False
        self._table_open = False
        # Keep created units aside until players place them into the pattern.
        self._unit_pool: list[Unit] = list(self.convoy.units)
        self.convoy.units = []
        # Queues open after placement: the order card is shown first.
        self.resistance = Resistance(None, self)
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
            shuffled=False,
            names_and_effects=ACTION_CATALOG,
            rng=self.rng,
        )
        for player in self.players:
            player.action_deck = CardDeck(
                list(ACTION_CATALOG.keys()),
                shuffled=False,
                names_and_effects=ACTION_CATALOG,
                rng=self.rng,
            )

        # Mauling is drawn before anything else is shuffled. The order card
        # stays out of the pile until placement finishes.
        self.mauling_deck = CardDeck(
            list(MAULING_CATALOG.keys()),
            shuffled=False,
            names_and_effects=MAULING_CATALOG,
            rng=self.rng,
        )
        self._draw_setup_order_card()
        starter_id, pool_ids = select_resistance_deck(
            len(self.players), self.rng, shuffle=False
        )
        self._resistance_starter_id = starter_id
        # Catalog stays full for lookups; only the sampled ids are in the draw pile.
        self.resistance_deck = CardDeck(
            pool_ids,
            shuffled=False,
            names_and_effects=RESISTANCE_CATALOG,
            rng=self.rng,
        )
        self.pillage_deck = CardDeck(
            list(PILLAGE_CATALOG.keys()),
            shuffled=False,
            names_and_effects=PILLAGE_CATALOG,
            rng=self.rng,
        )
        self.hit_decks = {
            category: CardDeck(
                list(cards.keys()),
                shuffled=False,
                names_and_effects=cards,
                rng=self.rng,
            )
            for category, cards in HIT_DECKS.items()
        }

        officer_ids = sorted(OFFICER_CATALOG.keys())
        sequential = {i: OFFICER_CATALOG[oid] for i, oid in enumerate(officer_ids)}
        self.officer_id_mapping = {i: oid for i, oid in enumerate(officer_ids)}
        self.officer_deck = CardDeck(
            list(sequential.keys()),
            shuffled=False,
            names_and_effects=sequential,
            rng=self.rng,
        )

        self.resistance_queue = CardQueue(self.resistance_deck)
        self.mauling_queue = CardQueue(self.mauling_deck)
        self.pillage_queue = CardQueue(self.pillage_deck)
        self.officer_queue = CardQueue(self.officer_deck)

    def _draw_setup_order_card(self) -> None:
        """Pull one mauling card. Its formation is the convoy order."""
        deck = self.mauling_deck
        if not deck.deck:
            raise RuntimeError("Mauling deck is empty before setup")
        card_id = deck.deck.pop(self.rng.randrange(len(deck.deck)))
        card = deck.names_and_effects[card_id]
        self.setup_order_card_id = card_id
        self.setup_pattern = pattern_for_players(
            card.formations["5"], len(self.players)
        )

    def _shuffle_all_decks(self) -> None:
        decks = [
            self.action_deck,
            self.resistance_deck,
            self.pillage_deck,
            self.mauling_deck,
            self.officer_deck,
            *self.hit_decks.values(),
            *(player.action_deck for player in self.players),
        ]
        for deck in decks:
            self.rng.shuffle(deck.deck)

    def _open_table(self) -> None:
        """Discard the order card, shuffle every deck, then deal the queues."""
        if self._table_open:
            return
        self.mauling_deck.discard_card(self.setup_order_card_id)
        self._shuffle_all_decks()
        self.resistance_queue.put_card(self._resistance_starter_id, visible=True)
        for _ in range(2):
            if self.resistance_deck.deck:
                self.resistance_queue.put_card(self.resistance_deck.get_card())
        for _ in range(3):
            self.mauling_queue.put_card(self.mauling_deck.get_card())
        self.mauling_queue.reveal_card(0)
        self.resistance = Resistance(self.resistance_queue.describe(0), self)
        self._table_open = True

    def draw_hit_damage(self, category: int) -> int:
        """
        Draw one card from that category's deck and return its damage.

        The card stays out of the deck while it is a damage marker. Unclaimed
        draws and markers on a destroyed unit or resistance go back to discard.
        """
        deck = self.hit_decks.get(category)
        if deck is None:
            raise ValueError(
                f"Hit category must be one of {sorted(self.hit_decks)}, got {category}"
            )
        if not deck.deck and not deck.discard:
            self.consolidate_empty_pile(category)
        card_id = deck.get_card()
        card = deck.names_and_effects[card_id]
        damage = card.damage
        self.hit_draws.append(
            {
                "category": category,
                "id": card_id,
                "damage": damage,
                "cash": card.cash,
                "claimed": False,
            }
        )
        return damage

    def _claim_hit_card(self, category: int) -> int | None:
        for entry in reversed(self.hit_draws):
            if entry.get("category") == category and not entry.get("claimed"):
                entry["claimed"] = True
                return int(entry["id"])
        return None

    def discard_unclaimed_hits(self) -> None:
        """Return drawn hit cards that were not stuck to a target."""
        for entry in self.hit_draws:
            if entry.get("claimed"):
                continue
            deck = self.hit_decks.get(int(entry["category"]))
            if deck is not None:
                deck.discard_card(int(entry["id"]))
            entry["claimed"] = True

    def _pile_empty(self, value: int) -> bool:
        deck = self.hit_decks.get(value)
        return deck is None or (not deck.deck and not deck.discard)

    def _can_draw_many(self, values: list[int]) -> bool:
        from collections import Counter

        for value, count in Counter(values).items():
            deck = self.hit_decks.get(value)
            if deck is None or len(deck.deck) + len(deck.discard) < count:
                return False
        return True

    def _exchange_counters(
        self, pile: list[dict], take_value: int, take_n: int, give: list[int]
    ) -> None:
        """Trade ``take_n`` counters for larger chips, returning the small cards."""
        while True:
            held = [c for c in pile if int(c["value"]) == take_value]
            if len(held) < take_n or not self._can_draw_many(give):
                return
            for _ in range(take_n):
                index = next(
                    i for i, counter in enumerate(pile) if int(counter["value"]) == take_value
                )
                self.release_money_counter(pile.pop(index))
            for value in give:
                card_id = self._draw_money_card(value)
                if card_id is None:
                    return
                pile.append({"value": value, "id": card_id, "fresh": True})

    def consolidate_empty_pile(self, value: int) -> None:
        """
        When a money/damage pile is empty, trade players' counters of that
        value up to $5 and $10 so the small cards return to the pile.
        """
        if value not in (1, 3, 5) or not self._pile_empty(value):
            return
        if value in self._consolidating:
            return
        self._consolidating.add(value)
        try:
            exchanges = {
                1: [(10, [10]), (5, [5])],
                3: [(10, [10, 10, 10]), (5, [10, 5])],
                5: [(2, [10])],
            }
            for player in self.players:
                for pile in (player.round_counters, player.bank_counters):
                    for take_n, give in exchanges[value]:
                        self._exchange_counters(pile, value, take_n, give)
        finally:
            self._consolidating.discard(value)

    def _draw_money_card(self, value: int) -> int | None:
        deck = self.hit_decks.get(value)
        if deck is None:
            return None
        if not deck.deck and not deck.discard:
            self.consolidate_empty_pile(value)
        if not deck.deck and not deck.discard:
            return None
        return deck.get_card()

    def draw_money(self, amount: int) -> list[dict]:
        """Take 10/5/3/1 counters from the money decks that sum to ``amount``."""
        if amount <= 0:
            return []
        drawn: list[dict] = []
        remaining = amount
        for value in (10, 5, 3, 1):
            while remaining >= value:
                card_id = self._draw_money_card(value)
                if card_id is None:
                    break
                drawn.append({"value": value, "id": card_id, "fresh": True})
                remaining -= value
        return drawn

    def release_money_counter(self, counter: dict) -> None:
        deck = self.hit_decks.get(int(counter["value"]))
        if deck is not None:
            deck.discard_card(int(counter["id"]))

    def pay_counters(self, pile: list[dict], amount: int) -> int:
        """Remove counters worth up to ``amount``. Break one larger chip if needed."""
        if amount <= 0:
            return 0
        paid = 0
        for value in (10, 5, 3, 1):
            index = 0
            while paid + value <= amount and index < len(pile):
                if int(pile[index]["value"]) == value:
                    counter = pile.pop(index)
                    self.release_money_counter(counter)
                    paid += value
                else:
                    index += 1
        if paid < amount:
            bigger = [c for c in pile if int(c["value"]) > amount - paid]
            if bigger:
                chip = min(bigger, key=lambda c: int(c["value"]))
                pile.remove(chip)
                change = int(chip["value"]) - (amount - paid)
                self.release_money_counter(chip)
                pile.extend(self.draw_money(change))
                paid = amount
        return paid

    def attach_damage_marker(
        self, target: Any, damage: int, category: int | None = None
    ) -> None:
        """Stick the dealt damage card on a unit or the resistance."""
        if damage <= 0:
            return
        card_id = self._claim_hit_card(category) if category is not None else None
        target.damage_markers.append(
            {
                "damage": int(damage),
                "category": category,
                "id": card_id,
                "fresh": True,
            }
        )

    def recycle_damage_markers(self, target: Any) -> None:
        """Return damage cards to their decks when the target is destroyed."""
        for marker in target.damage_markers:
            card_id = marker.get("id")
            category = marker.get("category")
            deck = self.hit_decks.get(category) if category is not None else None
            if card_id is not None and deck is not None:
                deck.discard_card(int(card_id))
                marker["id"] = None
        target.damage_markers.clear()

    def _settle_damage_markers(self) -> None:
        targets: list[Any] = []
        if self.convoy is not None:
            targets.extend(self.convoy.units)
        targets.extend(getattr(self, "_unit_pool", []) or [])
        if self.resistance is not None:
            targets.append(self.resistance)
        for target in targets:
            for marker in getattr(target, "damage_markers", []):
                marker["fresh"] = False
        for player in getattr(self, "players", []) or []:
            for pile in (player.round_counters, player.bank_counters):
                for counter in pile:
                    counter["fresh"] = False

    def note_struck_unit(self, unit: Unit) -> None:
        if unit not in self.struck_units:
            self.struck_units.append(unit)

    def clear_hit_draws(self) -> None:
        self._settle_damage_markers()
        self.hit_draws.clear()
        self.struck_units.clear()
        self.resistance_struck = False

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
        """Append a log line. Training keeps only the fixed event-row ring."""
        row = event_from_detail(
            detail,
            round_n=self.rounds.count if self.rounds else 0,
            stage=self.rounds.stage if self.rounds else -1,
        )
        if row is not None:
            self.event_rows.append(row)
        if not self.record_text_log:
            return
        self.messages.append(message)
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
        order_name = self.mauling_deck.get_name(self.setup_order_card_id) or str(
            self.setup_order_card_id
        )
        self._broadcast(
            f"Muodostelma kortista {order_name}: "
            f"{''.join(str(p + 1) for p in self.setup_pattern)}"
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
        self._open_table()
        self._broadcast("Saattue muodostettu.")

        initial_units = len(self.convoy.units)

        while not self.terminal:
            self.rounds.stage = -1
            self.round_action_summaries = []
            self.round_resistance_damage = 0
            self.round_unit_damage = []
            for pl in self.players:
                pl.bank_round_cash()

            self._broadcast(f"—— Kierros {self.rounds.count} alkaa ——")

            # Fill officer queue
            while len(self.officer_queue) < len(self.players):
                if not self.officer_deck.deck and not self.officer_deck.discard:
                    break
                self.officer_queue.put_card(self.officer_deck.get_card(), visible=True)

            # Deal
            self.rounds.next_stage()
            deal_n = (
                CARDS_TO_DEAL_FIRST_ROUND
                if self.rounds.count == 0
                else CARDS_TO_DEAL
            )
            for _ in range(deal_n):
                for player in self.players:
                    player.draw_card(1)
            self._broadcast(f"Kortit jaettu ({deal_n}).")

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
                self.current_action_index = action_index
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
                            clues = []
                            from .card_display import passive_clues_for

                            if not desc.get("is_officer_discard"):
                                clues = passive_clues_for(
                                    unit.officers, desc.get("action_name")
                                )
                            if clues:
                                face = {**face, "passive_clues": clues}
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
                        yield from action_mod.pause_after_action(self, msg)
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
                            "action_name": desc.get("action_name"),
                        }
                        unit_idx = unit.index()
                        summary = yield from action_mod.resolve_action(
                            self, unit_idx, desc, actioncard
                        )
                        self._broadcast(
                            summary,
                            event_type=1,
                            actor=unit.player.number,
                            card_id=actioncard,
                            card_visible=True,
                            amount=choice_i,
                        )
                        early = self._finished_result()
                        if early is not None:
                            return early
                        yield from action_mod.pause_after_action(self, summary)

                action_index += 1

            # Advance
            self.rounds.next_stage()
            has_advance_log = False
            if not self.resistance.active:
                self.convoy.move_resting_and_damaged_units()
                if self.convoy.units:
                    from .config import FIRST_UNIT_ADVANCE_CASH
                    if FIRST_UNIT_ADVANCE_CASH > 0:
                        first_unit = self.convoy.units[0]
                        first_unit.player.get_cash(
                            FIRST_UNIT_ADVANCE_CASH, source="lead the advance"
                        )
                        self._broadcast(
                            f"{first_unit.player.agent_id()} rewarded {FIRST_UNIT_ADVANCE_CASH} cash for having the first unit when the convoy advanced"
                        )
                        early = self._finished_result()
                        if early is not None:
                            return early
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
                has_advance_log = True
            else:
                self._broadcast("Convoy stuck because of resistance.")
                has_advance_log = True

            if getattr(self, "pause_after_actions", True) and has_advance_log:
                yield ChoiceRequest(
                    player_id=f"player_{getattr(self, 'human_seat', 0)}",
                    choicetype=ChoiceType.LOG_PAUSE,
                    options=[0],
                    num_choices=1,
                    description="Jatka peliä (Continue)"
                )

            # Mauling (hit-table damage and/or forced discard)
            self.rounds.next_stage()
            from .actions import resolve_mauling

            maul_id, _ = self.mauling_queue.remove_card(0)
            mauling = self.mauling_deck.describe(maul_id)
            msg = yield from resolve_mauling(self, mauling)
            maul_line = f"Mauling {mauling['name']}: {msg}"
            self._broadcast(
                maul_line,
                event_type=3,
                queue=1,
                card_id=maul_id,
                card_visible=True,
            )
            early = self._finished_result()
            if early is not None:
                return early
            self.mauling_deck.discard_card(maul_id)
            self.mauling_queue.put_card(self.mauling_deck.get_card())

            if getattr(self, "pause_after_actions", True):
                yield ChoiceRequest(
                    player_id=f"player_{getattr(self, 'human_seat', 0)}",
                    choicetype=ChoiceType.LOG_PAUSE,
                    options=[0],
                    num_choices=1,
                    description=maul_line,
                    payload={"reason": "mauling_pause"},
                )

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
                        pl.get_cash(1, source="cash in cards")
                        self._broadcast(f"{PLAYER_COLORS[pl.number % len(PLAYER_COLORS)]} player cashed in cards")
                        early = self._finished_result()
                        if early is not None:
                            return early

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
                        self._broadcast(f"{PLAYER_COLORS[pl.number % len(PLAYER_COLORS)]} player gets promotion point")

            early = self._check_promotion_victory()
            if early is not None:
                return early

            if not self.resistance.active and self.round_resistance_damage > 0:
                # count kills when resistance was destroyed this round
                if self.resistance.status == "destroyed":
                    self.stats.record_resistance_kill()

            if len(self.convoy.units) <= len(self.players):
                return self._end_game(
                    None,
                    "Game finished (convoy collapsed).",
                )

            if self.rounds.count + 1 >= self.max_rounds:
                return self._end_game(
                    None,
                    "Max rounds reached.",
                )

            for unit in self.convoy.units:
                if unit.actioncard and unit.player.action_deck:
                    for card in unit.actioncard:
                        unit.player.action_deck.discard_card(card)
                unit.clear_state()

            score_parts = []
            for pl in self.players:
                color_name = PLAYER_COLORS[pl.number % len(PLAYER_COLORS)].capitalize()
                score_parts.append(f"{color_name} {pl.promotion_points} PP, {pl.total_cash} total cash")
            self._broadcast("Current score: " + ", ".join(score_parts))

            self._broadcast(f"—— Kierros {self.rounds.count} päättyy ——")
            if getattr(self, "pause_after_actions", True):
                yield ChoiceRequest(
                    player_id=f"player_{getattr(self, 'human_seat', 0)}",
                    choicetype=ChoiceType.LOG_PAUSE,
                    options=[0],
                    num_choices=1,
                    description="Jatka peliä (Continue)"
                )
            self.rounds.next_round()

        return self._end_game(None, "Game finished.")

    def _compute_ranking(self) -> list[dict]:
        rows = [p.to_json() for p in self.players]
        return sorted(rows, key=lambda k: (-k["promotion_points"], -k["total_cash"]))

    def _ranking_with_winner(self, winner: Player) -> list[dict]:
        """Force ``winner`` to 1st; others by normal PP then cash."""
        rest = [p.to_json() for p in self.players if p is not winner]
        rest.sort(key=lambda k: (-k["promotion_points"], -k["total_cash"]))
        return [winner.to_json()] + rest

    def _end_game(
        self, winner: Player | None, message: str
    ) -> StepResult:
        """Mark terminal. If ``winner`` is set, they are ranked first."""
        if winner is not None:
            ranking = self._ranking_with_winner(winner)
        else:
            ranking = self._compute_ranking()
        self.terminal = True
        self.ranking = ranking
        self._end_message = message
        rounds = self.rounds.count if self.rounds else 0
        self.stats.finalize(ranking, rounds)
        self._broadcast(message)
        return StepResult(terminal=True, ranking=ranking, message=message)

    def _finished_result(self) -> StepResult | None:
        if not self.terminal:
            return None
        return StepResult(
            terminal=True,
            ranking=self.ranking,
            message=self._end_message or "Game finished.",
        )

    def _on_cash_gained(self, player: Player, before: int) -> None:
        """Instant win when total_cash first crosses CASH_TO_WIN (mid-round OK)."""
        if self.terminal:
            return
        from .config import CASH_TO_WIN

        if CASH_TO_WIN <= 0:
            return
        if before < CASH_TO_WIN <= player.total_cash:
            color = PLAYER_COLORS[player.number % len(PLAYER_COLORS)]
            self._end_game(
                player,
                f"{color} wins with {player.total_cash} cash "
                f"(target {CASH_TO_WIN}).",
            )

    def _check_promotion_victory(self) -> StepResult | None:
        """
        First sole player to PROMOTION_POINTS_TO_WIN wins.

        If several reach the threshold on the same award, enter sudden death
        until one player has strictly more PP than every other.
        """
        if self.terminal:
            return self._finished_result()
        from .config import PROMOTION_POINTS_TO_WIN

        if PROMOTION_POINTS_TO_WIN <= 0:
            return None

        at_target = [
            p
            for p in self.players
            if p.promotion_points >= PROMOTION_POINTS_TO_WIN
        ]

        if not self.sudden_death_pp:
            if len(at_target) == 1:
                color = PLAYER_COLORS[at_target[0].number % len(PLAYER_COLORS)]
                return self._end_game(
                    at_target[0],
                    f"{color} wins with {at_target[0].promotion_points} PP "
                    f"(target {PROMOTION_POINTS_TO_WIN}).",
                )
            if len(at_target) >= 2:
                self.sudden_death_pp = True
                names = ", ".join(
                    PLAYER_COLORS[p.number % len(PLAYER_COLORS)] for p in at_target
                )
                self._broadcast(
                    f"Sudden death: {names} reached {PROMOTION_POINTS_TO_WIN} PP "
                    f"together — first sole PP lead wins."
                )
                return None
            return None

        # Sudden death: sole leader (any PP) wins.
        max_pp = max(p.promotion_points for p in self.players)
        leaders = [p for p in self.players if p.promotion_points == max_pp]
        if len(leaders) == 1:
            color = PLAYER_COLORS[leaders[0].number % len(PLAYER_COLORS)]
            return self._end_game(
                leaders[0],
                f"{color} wins sudden death with {max_pp} PP.",
            )
        return None
