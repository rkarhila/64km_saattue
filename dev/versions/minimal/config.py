"""Short path through place, assign, move, attack, and pillage.

Five cost-free cards are dealt each round. Attack pays 1; destroying
resistance pays the card's own cash_for_destroying. Service, scout reveals,
and first-unit advance each pay 1. Win at 15 $ or 3 promotion points
(cash checked at end of round; conflicting PP/cash winners → tie).
"""

from sixtyfivekmconvoy.core.configs.retire import *  # noqa: F403

CONFIG_NAME = "minimal"

CARDS_TO_DEAL_FIRST_ROUND = 5
CARDS_TO_DEAL = 5
ATTACK_CASH = 1
INCENTIVE_ATTACK_CASH = ATTACK_CASH
FIRST_UNIT_ADVANCE_CASH = 1
INCENTIVE_FIRST_UNIT_ADVANCE_CASH = FIRST_UNIT_ADVANCE_CASH
REVEAL_MAULING_CASH = 1
REVEAL_RESISTANCE_CASH = 1
INCENTIVE_SCOUT_CASH = REVEAL_RESISTANCE_CASH
SERVICE_CASH = 1
INCENTIVE_SERVICE_CASH = SERVICE_CASH
PROMOTION_POINTS_TO_WIN = 3
CASH_TO_WIN = 15
CASH_WIN_AT_END_OF_ROUND = True
USE_OFFICER_QUEUE = False
MAULING_QUEUE_FACE_UP = True
PILLAGE_QUEUE_FACE_UP = True
RESISTANCE_QUEUE_LENGTH = 1
SCOUT_RESISTANCE_DRAW = 1
