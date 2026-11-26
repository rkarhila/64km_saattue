"""
Default game-balance profile.

RL / bot training should pin a profile name (see CONVOY_CONFIG) so trained
weights stay tied to the same reward and deal parameters.
"""

CONFIG_NAME = "default"

# Cards dealt to each player at round start.
CARDS_TO_DEAL_FIRST_ROUND = 5
CARDS_TO_DEAL = 5

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
# Sober rest removes this many tiredness. A drunk rest clears influence instead.
REST_TIREDNESS = 2
# Service removes this many tiredness from one tired neighbour.
SERVICE_TIREDNESS = 1
# Scout and sigint. Pillage reveals pay nothing.
# False: each amount once per action when at least one card of that type
# was turned face up. True: that amount for every such card.
REVEAL_CASH_PER_CARD = False
REVEAL_MAULING_CASH = 1
REVEAL_RESISTANCE_CASH = 1
# Kept so older imports still resolve. Scout no longer pays this flat amount.
SCOUT_CASH = 0
FIRST_UNIT_ADVANCE_CASH = 1

# Cash granted when a resistance hit does not destroy (status==1 from take_damage).
RESISTANCE_HIT_CASH = 1

# Instant / race victory thresholds (≤0 disables that condition).
# First sole player to PROMOTION_POINTS_TO_WIN wins at bookkeeping.
# If several hit the threshold on the same round → sudden death until one leads in PP.
PROMOTION_POINTS_TO_WIN = 6
# True: a promotion point is awarded only when exactly one player earned
# strictly more cash this round than every other player.
# False: every player tied for the highest cash this round (above 0) gets a point.
SOLE_CASH_LEAD_FOR_PROMOTION = True
# Cash race threshold (≤0 disables). Default: first to reach wins mid-round.
CASH_TO_WIN = 25
# True: check cash at end of round bookkeeping instead. Then the richest
# player wins if anyone is at/above CASH_TO_WIN. Same round as a sole
# promotion win for a different player → tie.
CASH_WIN_AT_END_OF_ROUND = False

# Sell (Myy varusteita) pays CASH_IN_REWARD for the card's printed cost.
# CASH_IN_CARDS is the count shown in the rules; the printed cost is what play uses.
# When CASH_IN_REMOVES_FROM_PLAY is false the cards go to that player's
# discard and can be drawn again. The retire profile removes them.
CASH_IN_CARDS = 4
CASH_IN_REWARD = 1
CASH_IN_REMOVES_FROM_PLAY = False

# Officer queue is dealt and shown. A version can turn the queue off.
USE_OFFICER_QUEUE = True
# Queue cards behind the front stay face down unless a version turns these on.
MAULING_QUEUE_FACE_UP = False
PILLAGE_QUEUE_FACE_UP = False
# Resistance queue at the start. The front card is face up and is the active resistance.
RESISTANCE_QUEUE_LENGTH = 3
# 1: a scout draws the action's printed number of resistance cards and keeps one
# face up in the queue. 0 leaves resistance on the ordinary scout rules.
SCOUT_RESISTANCE_DRAW = 0

# Backward-compatible aliases (older imports / tests).
INCENTIVE_SERVICE_CASH = SERVICE_CASH
INCENTIVE_ATTACK_CASH = ATTACK_CASH
INCENTIVE_SCOUT_CASH = REVEAL_RESISTANCE_CASH
INCENTIVE_FIRST_UNIT_ADVANCE_CASH = FIRST_UNIT_ADVANCE_CASH
