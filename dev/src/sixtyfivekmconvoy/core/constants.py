"""Shared vocabulary for choices, actions, and effect parsing."""

from __future__ import annotations

from enum import IntEnum


class ChoiceType(IntEnum):
    CHOOSE_CARD = 0
    CHOOSE_ACTION = 1
    CHOOSE_CARDS_TO_DISCARD = 2
    CASH_IN_CARDS = 3
    CHOOSE_QUEUE_TO_SCOUT = 4
    CHOOSE_PILLAGE_CARD = 5
    CHOOSE_OFFICER = 6
    CHOOSE_SERVICE = 7
    YES_NO = 8
    PLACE_UNITS = 9
    CHOOSE_CARDS_TO_SCOUT = 10
    REORDER_SCOUTED_CARDS = 11
    LOG_PAUSE = 12


class ActionName:
    ATTACK = "attack"
    ASSAULT = "assault"
    BYPASS = "bypass"
    DEFEND = "defend"  # ground defence ("Puolustusasemiin!")
    EXIT = "exit"
    HUMAN_SHIELDS = "human shields"  # air defence ("Ihmiskilpiä")
    ORDER = "order"
    PATROL = "patrol"  # sabotage defence ("Partioi"); not "guard"
    PILLAGE = "pillage"
    PROMOTE = "promote"
    REST = "rest"
    RETREAT = "retreat"
    SCOUT = "scout"
    SEARCH = "search"
    SERVICE = "service"
    SIGINT = "sigint"
    SOBER_UP = "sober_up"
    WAIT = "wait"
    SUICIDAL_ATTACK = "suicidal_attack"
    SEARCH_PILLAGE_COMBO = "search_pillage_combo"
    PILLAGE_WITH_EXTRA_ATROCITY = "pillage_with_extra_atrocity"
    EXIT_FROM_C_WITH_COST = "exit_from_c_with_cost"

    # Not fully implemented — excluded from legal play until rules exist.
    UNIMPLEMENTED = frozenset()

    @classmethod
    def normalize(cls, action_name: str | None) -> str | None:
        if not action_name:
            return None
        return action_name.lower().strip()


class AttackType:
    """
    Mauling (and similar) attack letters stored on cards / unit.defending.

    Attack letter  | Defence action          | Action CSV name
    ---------------|-------------------------|------------------
    A (air)        | human shields           | Human shields
    G (ground)     | defend                  | Defend
    S (sabotage)   | patrol                  | Patrol

    A matching defence lowers this category one step on ATTACK_CATEGORIES
    (10→5→3→1→0) for the defender and for a neighbour in the same stance.
    Rewards come from config (SOAK_*_CASH / SOAK_*_ATROCITIES).
    """

    AIR = "A"
    GROUND = "G"
    SABOTAGE = "S"
    RESISTANCE = "R"
    ALL = frozenset({AIR, GROUND, SABOTAGE, RESISTANCE})


# Hit-table ranks. Each rank is its own deck; the card's reverse is that many dollars.
ATTACK_CATEGORIES = (1, 3, 5, 10)


def lower_attack_category(category: int, steps: int) -> int:
    """Step down the 10 → 5 → 3 → 1 ladder. Zero means the attack draws nothing."""
    if steps <= 0:
        return category
    ladder = (0,) + ATTACK_CATEGORIES
    if category not in ladder:
        raise ValueError(f"Attack category must be one of {ladder}, got {category}")
    index = ladder.index(category)
    return ladder[max(0, index - steps)]


# Defence action → attack letter it lowers.
ATTACK_TYPE_BY_DEFENCE_ACTION = {
    ActionName.HUMAN_SHIELDS: AttackType.AIR,
    ActionName.DEFEND: AttackType.GROUND,
    ActionName.PATROL: AttackType.SABOTAGE,
}

MIN_PLAYER_CARD_LIMIT = 2
CARD_TO_POINTS_RATIO = 4
PLAYER_COLORS = ["red", "green", "blue", "orange", "purple"]

# Random resistance cards drawn into the play deck (excluding the fixed starter).
# Tunable; remaining eligible cards are left out of the game.
RESISTANCE_POOL_SIZE = {
    2: 6,
    3: 8,
    4: 10,
    5: 12,
}

UNIT_TYPE_LETTER = {0: "P", 1: "I", 2: "L"}
# Stable English codes for RL / logic (display labels live in i18n).
UNIT_TYPE_STR = {0: "panzer", 1: "infantry", 2: "logistics"}
# Short codes kept for legacy comparisons in engine bookkeeping.
UNIT_TYPE_SHORT = {0: "Pnz", 1: "Inf", 2: "Log"}
