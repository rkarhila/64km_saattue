"""
Default game-balance profile.

RL / bot training should pin a profile name (see CONVOY_CONFIG) so trained
weights stay tied to the same reward and deal parameters.
"""

CONFIG_NAME = "default"

# Cards dealt to each player at round start.
CARDS_TO_DEAL_FIRST_ROUND = 7
CARDS_TO_DEAL = 3

# Defence soak rewards (per attack type soaked: A=air, G=ground, S=sabotage).
SOAK_AIR_CASH = 2
SOAK_AIR_ATROCITIES = 1
SOAK_GROUND_CASH = 2
SOAK_GROUND_ATROCITIES = 0
SOAK_SABOTAGE_CASH = 2
SOAK_SABOTAGE_ATROCITIES = 0

# Action cash incentives (shown on action faces in the UI).
SERVICE_CASH = 1
ATTACK_CASH = 2
SCOUT_CASH = 3
FIRST_UNIT_ADVANCE_CASH = 1

# Cash granted when a resistance hit does not destroy (status==1 from take_damage).
RESISTANCE_HIT_CASH = 1

# Instant / race victory thresholds (≤0 disables that condition).
# First sole player to PROMOTION_POINTS_TO_WIN wins at bookkeeping.
# If several hit the threshold on the same round → sudden death until one leads in PP.
PROMOTION_POINTS_TO_WIN = 6
# First player whose total_cash reaches this wins immediately (mid-round OK).
CASH_TO_WIN = 50

# Backward-compatible aliases (older imports / tests).
INCENTIVE_SERVICE_CASH = SERVICE_CASH
INCENTIVE_ATTACK_CASH = ATTACK_CASH
INCENTIVE_SCOUT_CASH = SCOUT_CASH
INCENTIVE_FIRST_UNIT_ADVANCE_CASH = FIRST_UNIT_ADVANCE_CASH
