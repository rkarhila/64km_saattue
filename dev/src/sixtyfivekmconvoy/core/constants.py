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


class ActionName:
    ATTACK = "attack"
    ASSAULT = "assault"
    BYPASS = "bypass"
    DEFEND = "defend"
    EXIT = "exit"
    HUMAN_SHIELDS = "human shields"
    ORDER = "order"
    PATROL = "patrol"
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
    UNIMPLEMENTED = frozenset(
        {
            HUMAN_SHIELDS,
            ORDER,
            PATROL,
            SCOUT,
            SEARCH,
            SIGINT,
            SEARCH_PILLAGE_COMBO,
        }
    )

    @classmethod
    def normalize(cls, action_name: str | None) -> str | None:
        if not action_name:
            return None
        return action_name.lower().strip()


CARDS_TO_DEAL = 5
MIN_PLAYER_CARD_LIMIT = 2
CARD_TO_POINTS_RATIO = 4
PLAYER_COLORS = ["red", "green", "blue", "orange", "purple"]

UNIT_TYPE_LETTER = {0: "P", 1: "I", 2: "L"}
UNIT_TYPE_STR = {0: "Pnz", 1: "Inf", 2: "Log"}
