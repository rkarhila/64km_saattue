"""Domain models: Player, Unit, Convoy, Resistance."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .constants import UNIT_TYPE_STR, PLAYER_COLORS
from .cards import CardDeck, OfficerCard
from .i18n import unit_type_label

if TYPE_CHECKING:
    from .engine import GameEngine


class UnitType:
    PANZER = 0
    INFANTRY = 1
    LOGISTICS = 2


class Player:
    def __init__(self, number: int, name: str | None = None):
        self.number = number
        self.name = name or f"player_{number}"
        self.this_round_cash = 0
        self.total_cash = 0
        self.promotion_points = 0
        self.action_cards: list[int] = []
        self.action_deck: CardDeck | None = None

    def agent_id(self) -> str:
        return f"player_{self.number}"

    def get_cash(self, cash: int) -> None:
        self.this_round_cash += cash
        self.total_cash += cash

    def can_discard(self, count: int) -> bool:
        return len(self.action_cards) >= count

    def discard(self, cards: list[int]) -> None:
        assert self.action_deck is not None
        for card in cards:
            self.action_cards.remove(card)
            self.action_deck.discard_card(card)

    def place_action_card(self, card: int) -> None:
        self.action_cards.remove(card)

    def draw_card(self, count: int = 1) -> None:
        assert self.action_deck is not None
        for _ in range(count):
            self.action_cards.append(self.action_deck.get_card())
        self.action_cards.sort()

    def to_json(self, playerview: Player | None = None) -> dict:
        data = {
            "number": self.number,
            "name": self.name,
            "cash_this_round": self.this_round_cash,
            "total_cash": self.total_cash,
            "promotion_points": self.promotion_points,
            "card_count": len(self.action_cards),
        }
        if playerview is None or playerview is self:
            data["cards"] = list(self.action_cards)
        return data


class Unit:
    type_to_str = UNIT_TYPE_STR

    def __init__(self, player: Player, unittype: int):
        self.player = player
        self.unittype = unittype
        self.carry: list[int] = [0, 0, 0]
        self.tired = 0
        self.under_influence = 0
        self.atrocities = 0
        self.actioncard: list[int] = []
        self.actiontaken: list[int | None] = []
        # Parallel to actiontaken: how the choice resolved (for UI reveal / highlight).
        self.action_resolution: list[dict | None] = []
        self.convoy: Convoy | None = None
        self.engine: GameEngine | None = None
        self.defending: str | None = None
        self.had_defended = False
        self.defending_reward: str | None = None
        self.current_action_type: str | None = None
        self.officers: list[OfficerCard] = []

    def clear_state(self) -> None:
        self.actioncard = []
        self.actiontaken = []
        self.action_resolution = []
        self.current_action_type = None
        self.defending = None
        self.defending_reward = None

    def is_defending(self) -> bool:
        return self.current_action_type == "defending"

    def is_resting(self) -> bool:
        return self.current_action_type == "resting"

    def is_damaged(self) -> bool:
        return len(self.carry) == 0

    def index(self) -> int:
        assert self.convoy is not None
        return self.convoy.get_unit_index(self)

    def position(self) -> int:
        return self.index() + 1

    def zone(self) -> str:
        assert self.convoy is not None
        return self.convoy.get_unit_zone(self)

    def get_neighbours(self) -> list[Unit | None]:
        assert self.convoy is not None
        idx = self.index()
        preceding = self.convoy.units[idx - 1] if idx > 0 else None
        following = (
            self.convoy.units[idx + 1] if idx < len(self.convoy.units) - 1 else None
        )
        return [preceding, following]

    def apply_damage(
        self,
        damage: int,
        discards: int = 0,
        damage_for_not_discarding: int = 1,
        discard_choice: list[int] | None = None,
        cards_to_discard: list[int] | None = None,
    ) -> int:
        """Apply damage. Optional discard-to-soak handled by engine via ChoiceRequest."""
        if discards > 0 and len(self.player.action_cards) >= discards:
            if discard_choice is not None and discard_choice[0] == 1:
                assert cards_to_discard is not None
                self.player.discard(cards_to_discard)
            else:
                damage += damage_for_not_discarding
        if damage >= len(self.carry):
            self.carry = []
            return -1
        for _ in range(damage):
            self.carry.pop()
        return len(self.carry)

    def gain_loot(self, loot: int | list | str) -> list[int]:
        if isinstance(loot, int):
            loot = [loot]
        elif isinstance(loot, str):
            loot = [int(loot)]
        self.carry.extend(loot)
        self.carry.sort(reverse=True)
        capacity = 3
        for officer in self.officers:
            if officer.passive_effect == "extra_carry_capacity":
                capacity = 4
                break
        dropped = self.carry[capacity:]
        self.carry = self.carry[:capacity]
        return [d for d in dropped if d > 0]

    def gain_atrocities(self, atrocity: int) -> None:
        self.atrocities += atrocity

    def tire(self) -> None:
        self.tired += 1

    def become_frustrated(self) -> None:
        if self.under_influence == 0:
            self.under_influence = 1
        else:
            self.tired += 1

    def can_rest(self) -> bool:
        return self.tired > 0 or self.under_influence > 0

    def can_rest_with_cards(self) -> bool:
        return self.under_influence == 0 and self.tired > 2

    def can_overtake(self, modifier: int = 1) -> bool:
        if modifier > 0:
            return self.position() > modifier
        if modifier < 0:
            assert self.convoy is not None
            return self.index() < len(self.convoy.units) + modifier
        raise ValueError("Overtaking modifier cannot be 0")

    def rest(self) -> None:
        if self.under_influence > 0:
            self.under_influence = 0
        else:
            self.tired = max(0, self.tired - 2)
        self.current_action_type = "resting"

    def rest_with_cards(self) -> None:
        self.tired = 0
        self.current_action_type = "resting"

    def resolve_defend(self, defense_type: str, defense_reward: str) -> bool:
        """
        Set this unit's defence stance. `defense_type` is an AttackType letter
        (A/G/S) that will soak matching mauling attack_type hits.
        """
        from .constants import AttackType

        if defense_type not in AttackType.ALL:
            raise NotImplementedError(
                f"Defense type {defense_type} not implemented "
                f"(expected one of {sorted(AttackType.ALL)})"
            )
        self.defending = defense_type
        self.had_defended = False
        self.defending_reward = defense_reward
        self.current_action_type = "defending"
        return True

    def reward_defending(self) -> None:
        assert self.defending_reward is not None
        r = self.defending_reward
        if r.lower() == "a":
            self.atrocities += 1
            self.player.this_round_cash += 1
        elif r.lower() == "c":
            self.player.this_round_cash += 1
        elif r == "_":
            pass
        else:
            raise NotImplementedError(f"defense reward type {r} not implemented")

    def to_json(self, playerview: Player | None = None) -> dict:
        officer_names = [o.name for o in self.officers]
        return {
            "player": self.player.number,
            "unit_type": self.type_to_str[self.unittype],
            "unit_type_label": unit_type_label(self.unittype),
            "tiredness": self.tired,
            "under_influence": self.under_influence,
            "atrocities": self.atrocities,
            "carry": list(self.carry),
            "action": self._action_json(playerview),
            "officers": officer_names,
            "zone": self.zone() if self.convoy else None,
        }

    def _action_json(self, playerview: Player | None) -> dict:
        if not self.actioncard:
            return {"card": None, "face_up": False, "has_card": False, "cards": []}
        is_owner = playerview is None or playerview is self.player
        stack: list[dict] = []
        for i, card_id in enumerate(self.actioncard):
            resolution = None
            if i < len(self.action_resolution) and self.action_resolution[i] is not None:
                resolution = self.action_resolution[i]
            elif i < len(self.actiontaken) and self.actiontaken[i] is not None:
                resolution = {
                    "option": self.actiontaken[i],
                    "kind": "card",
                    "face_index": None,
                }
            resolved = resolution is not None
            face_up = is_owner or resolved
            entry: dict = {
                "index": i,
                "has_card": True,
                "face_up": face_up,
                "card": card_id if face_up else None,
                "resolved": resolved,
                "actiontaken": self.actiontaken[i] if i < len(self.actiontaken) else None,
            }
            if resolved and resolution:
                entry["chosen_face_index"] = resolution.get("face_index")
                entry["chosen_kind"] = resolution.get("kind")
                entry["chosen_name"] = resolution.get("name")
                entry["frustrated"] = resolution.get("kind") == "frustrated"
            stack.append(entry)

        top = stack[0]
        # Compat fields describe the first (bottom) card; UI prefers `cards` stack.
        data: dict = {
            "has_card": True,
            "face_up": top["face_up"],
            "card": top["card"],
            "cards": stack,
            "actiontaken": top.get("actiontaken"),
            "resolved": top.get("resolved", False),
        }
        if top.get("resolved"):
            data["chosen_face_index"] = top.get("chosen_face_index")
            data["chosen_kind"] = top.get("chosen_kind")
            data["chosen_name"] = top.get("chosen_name")
            data["frustrated"] = top.get("frustrated", False)
        return data


def _zones_for_players(num_players: int) -> dict[str, list[int]]:
    tables = {
        2: {"A": [1], "B": [2, 3], "C": [4, 5], "E": [-1]},
        3: {"A": [1, 2], "B": [3, 4, 5], "C": [6, 7], "E": [-2, -1]},
        4: {"A": [1, 2, 3], "B": [4, 5, 6], "C": [7, 8, 9], "E": [-3, -2, -1]},
        5: {"A": [1, 2, 3, 4], "B": [5, 6, 7, 8], "C": [9, 10, 11, 12], "E": [-3, -2, -1]},
    }
    if num_players not in tables:
        raise ValueError(f"Unsupported player count: {num_players}")
    zones = tables[num_players]
    return {k: [v - 1 for v in vals] for k, vals in zones.items()}


class Convoy:
    def __init__(self, players: list[Player], engine: GameEngine | None = None):
        self.players = players
        self.engine = engine
        self.units: list[Unit] = []
        for player in players:
            for ut in (UnitType.PANZER, UnitType.INFANTRY, UnitType.LOGISTICS):
                unit = Unit(player, ut)
                unit.convoy = self
                unit.engine = engine
                self.units.append(unit)
        self.zones = _zones_for_players(len(players))
        self.current_actor: int | None = None

    def get_unit_index(self, unit: Unit) -> int:
        return self.units.index(unit)

    def get_unit_position(self, unit: Unit) -> int:
        return self.get_unit_index(unit) + 1

    def get_unit_zone(self, unit: Unit) -> str:
        position = self.get_unit_position(unit)
        exit_positions = [len(self.units) + e + 1 for e in self.zones["E"]]
        # zones['E'] stored 0-based offsets from end (-2,-1) -> convert carefully
        n = len(self.units)
        for e in self.zones["E"]:
            # e is already 0-based relative like -2,-1 after conversion from 1-based
            # Original: zones E = [-2,-1] meaning last two 1-based positions
            # After -1: still negative indices conceptually
            pass
        # Match original logic: position in [len + e for e in zones['E']]
        # where zones['E'] were converted by subtracting 1 from 1-based negatives
        # e.g. 3p: E=[-2,-1] -> after -1: [-3,-2]. len+e: for 9 units -> 6,7 — WRONG
        # Looking at original again:
        # zones start 1-based then subtract 1: E [-2,-1] -> [-3,-2]
        # check: position in [len(units)+e for e in zones['E']]
        # for 9 units: [9-3, 9-2] = [6,7] — that's wrong for "last two"
        # Actually for 3p original before convert: E=[-2,-1]
        # after convert: [v-1 for v in [-2,-1]] = [-3,-2]
        # len+e: 9-3=6, 9-2=7 — still not last two (8,9)...
        # Wait get_unit_zone uses:
        # if position in [ len(self.units) + e for e in self.zones['E'] ]:
        # For 3p with E still as [-2,-1] BEFORE convert... but they convert ALL zones including E.
        # There may be a bug in original. Let's use sensible zone logic:
        # A/B/C by 0-based index membership; E = last |E| positions.
        idx = self.get_unit_index(unit)
        e_count = len(self.zones["E"])
        if idx >= n - e_count:
            return "E"
        for zone in "ABC":
            if idx in self.zones[zone]:
                return zone
        # Fallback: find nearest zone by index
        for zone in "ABC":
            if self.zones[zone] and idx <= max(self.zones[zone]):
                return zone
        return "E"

    def get_unit_at(self, place: int) -> Unit:
        return self.units[place - 1]

    def get_units_in_zone(self, zone: str) -> list[Unit]:
        assert zone in "ABCE"
        if zone == "E":
            e_count = len(self.zones["E"])
            return self.units[max(0, len(self.units) - e_count) :]
        return [self.units[i] for i in self.zones[zone] if i < len(self.units)]

    def apply_damage(
        self,
        damage: int,
        cards: int = 0,
        damage_for_not_discarding: int = 1,
        unit: Unit | int | None = None,
        zone: str | None = None,
        attack_type: str | None = None,
    ) -> str:
        assert unit is not None or zone is not None
        msg = ""
        if zone is not None and not isinstance(unit, Unit) and unit is None:
            for u in self.get_units_in_zone(zone):
                msg += self.apply_damage(
                    damage,
                    cards=cards,
                    damage_for_not_discarding=damage_for_not_discarding,
                    unit=u,
                    attack_type=attack_type,
                )
            return msg

        if zone is not None and isinstance(unit, int):
            units_in_zone = self.get_units_in_zone(zone)
            if not units_in_zone:
                return msg
            target_rel = unit
            while len(units_in_zone) < abs(target_rel) and target_rel != 0:
                if target_rel < 0:
                    target_rel += 1
                else:
                    target_rel -= 1
            # Map 1-based / negative relative to 0-based index
            if target_rel > 0:
                zi = min(target_rel - 1, len(units_in_zone) - 1)
            else:
                zi = max(target_rel, -len(units_in_zone))
            unit = units_in_zone[zi]

        if isinstance(unit, int):
            unit = self.get_unit_at(unit)
        if not isinstance(unit, Unit):
            raise ValueError(f"Target unit needs to be int or Unit, got {type(unit)}")

        defend_soak = 0
        for u in [unit] + unit.get_neighbours():
            if u is not None and u.defending is not None and u.defending == attack_type:
                defend_soak += 1
                u.reward_defending()

        if defend_soak > 0:
            if damage + cards <= defend_soak:
                return "Defense soaks up all damage."
            while damage > 0 and defend_soak > 0:
                damage -= 1
                defend_soak -= 1
            while cards > 0 and defend_soak > 0:
                cards -= 1
                defend_soak -= 1
            msg += f"Defense soaks some damage; "

        if self.engine is not None and damage > 0:
            self.engine.round_unit_damage.append((unit.index(), damage))

        pos_1based = unit.position()
        u_idx = unit.index()
        color = PLAYER_COLORS[unit.player.number % len(PLAYER_COLORS)]
        troop = unit_type_label(unit.unittype)

        status = unit.apply_damage(damage, discards=cards, damage_for_not_discarding=damage_for_not_discarding)
        msg += f"Unit at position {pos_1based} ({color} {troop}, index {u_idx}) takes {damage} damage"
        if status < 0:
            msg += " and is removed from convoy"
            self.units.pop(unit.index())
        else:
            msg += f" and is left with {status} capacity"
        return msg

    def move_unit(self, position: int, move: int) -> int:
        new_position = position - move
        moving = self.units.pop(position)
        self.units.insert(new_position, moving)
        return new_position

    def move_resting_and_damaged_units(self) -> None:
        # Drop trailing destroyed/damaged (empty carry) off the back
        while self.units and self.units[-1].is_damaged():
            self.units.pop()

        damaged: list[Unit] = []
        remaining: list[Unit] = []
        for u in self.units:
            if u.is_damaged():
                damaged.append(u)
            else:
                remaining.append(u)

        new_order: dict[float, Unit] = {}
        for i, u in enumerate(remaining):
            if u.is_resting():
                new_order[i + len(self.players) + 0.5] = u
            else:
                new_order[i] = u
        self.units = [u for _, u in sorted(new_order.items())] + damaged

    def to_json(self, playerview: Player | None = None) -> list[dict]:
        return [u.to_json(playerview=playerview) for u in self.units]


class Resistance:
    def __init__(self, description: dict | None, engine: GameEngine | None = None):
        self.engine = engine
        self.active = False
        self.name: str | None = None
        # `attack` on the card is a hit-table category (1–4), or 0 = no attack.
        self.attack_category = 0
        self.damage_to_convoy = 0  # kept as alias of attack_category for JSON compat
        self.target = ""
        self.loot = 0
        self.durability = 0
        self.damage_from_convoy: dict[str, int] = {}
        self.status = "inactive"
        if description is not None:
            self.name = description["name"]
            effect = description["effect"]
            self.attack_category = int(effect["attack"])
            self.damage_to_convoy = self.attack_category
            self.target = effect["target"]
            self.loot = effect["loot"]
            self.durability = effect["durability"]
            self.damage_from_convoy = effect["damage"]
            self.active = True
            self.status = "active"

    def take_damage(self, damagetype: str, modifier: int | str) -> tuple[int, str]:
        if isinstance(modifier, int):
            damage = modifier
        elif isinstance(modifier, str):
            if modifier.startswith("="):
                damage = int(modifier[1:])
            elif modifier.startswith("+"):
                damage = self.damage_from_convoy[damagetype] + int(modifier[1:])
            elif modifier.startswith("-"):
                damage = self.damage_from_convoy[damagetype] - int(modifier[1:])
            else:
                damage = int(modifier)
        else:
            damage = int(modifier)

        if damage <= 0:
            return 0, "No damage dealt"
        self.durability -= damage
        if self.engine is not None:
            self.engine.round_resistance_damage += damage
        if self.durability <= 0:
            self.status = "destroyed"
            self.active = False
            self.distribute_loot()
            return 2, f"Resistance took {damage} damage and is destroyed"
        return 1, f"Resistance took {damage} damage, durability {self.durability}"

    def attack(self) -> str:
        """
        Ambush the convoy using the hit table.

        Card `attack` is a hit category (1–4). Category 0 means no attack.
        """
        assert self.engine is not None
        if self.attack_category <= 0:
            return f"{self.name} does not attack (attack 0)"
        damage = self.engine.draw_hit_damage(self.attack_category)
        if damage <= 0:
            return f"{self.name} attacks (cat {self.attack_category}) for 0 damage"
        msg = self.engine.convoy.apply_damage(damage, unit=1)
        return f"{self.name} attacks (cat {self.attack_category}) for {damage}: {msg}"

    def distribute_loot(self) -> None:
        if self.engine is None:
            return
        for _ in range(self.loot):
            if self.engine.pillage_deck.deck:
                self.engine.pillage_queue.put_card(self.engine.pillage_deck.get_card())

    def to_json(self) -> dict:
        if not self.name:
            return {"active": False}
        return {
            "in_progress": (
                f"{self.name},attacks{self.target}with{self.damage_to_convoy},"
                f"{self.loot}loot,status{self.durability}"
            ),
            "name": self.name,
            "active": self.active,
            "status": self.status,
            "durability": self.durability,
            "attack": self.damage_to_convoy,
            "target": self.target,
            "loot": self.loot,
            "damage": dict(self.damage_from_convoy),
        }
