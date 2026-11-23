"""Short path through place, assign, move, attack, and pillage.

Three cost-free cards are dealt. One attack of 1 destroys the roadblock
(1 cash) and also pays the attack reward (1). The roadblock drops the cash
box (3). Together that reaches CASH_TO_WIN. Promotion points are off.
"""

from sixtyfivekmconvoy.core.configs.retire import *  # noqa: F403

CONFIG_NAME = "minimal"

CARDS_TO_DEAL_FIRST_ROUND = 3
CARDS_TO_DEAL = 3
ATTACK_CASH = 1
INCENTIVE_ATTACK_CASH = ATTACK_CASH
FIRST_UNIT_ADVANCE_CASH = 0
INCENTIVE_FIRST_UNIT_ADVANCE_CASH = FIRST_UNIT_ADVANCE_CASH
REVEAL_MAULING_CASH = 0
REVEAL_RESISTANCE_CASH = 0
SERVICE_CASH = 0
INCENTIVE_SERVICE_CASH = SERVICE_CASH
PROMOTION_POINTS_TO_WIN = 0
CASH_TO_WIN = 5
USE_OFFICER_QUEUE = False
MAULING_QUEUE_FACE_UP = True
PILLAGE_QUEUE_FACE_UP = True
RESISTANCE_QUEUE_LENGTH = 1
SCOUT_RESISTANCE_DRAW = 1
