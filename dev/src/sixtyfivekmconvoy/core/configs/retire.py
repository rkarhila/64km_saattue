"""Cash-in alternative: four cards leave the game and pay 1.

The cards are not discarded. They never return to the draw pile.
Everything else matches the default profile.
"""

from .default import *  # noqa: F403

CONFIG_NAME = "retire"
CASH_IN_CARDS = 4
CASH_IN_REWARD = 1
CASH_IN_REMOVES_FROM_PLAY = True
