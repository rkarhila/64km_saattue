#!/usr/bin/env python3

"""
Constants and type definitions for the game.

This module contains:
- Emoji constants for display
- Choice type constants
- Action type and modifier type constants
"""


# ============================================================================
# Emoji Constants
# ============================================================================

EMOJI_LOOT_1 = u'\u2460'
EMOJI_LOOT_2 = u'\u2461'
EMOJI_LOOT_3 = u'\u2462'
EMOJI_LOOT_4 = u'\u2463'
EMOJI_LOOT_5 = u'\u2464'
EMOJI_LOOT_6 = u'\u2465'

EMOJI_LUGGAGE = u'\u1F9F3'

# EMOJI_DAMAGE = u'\u1F4A5'
EMOJI_DAMAGE = u'\u2B59'


# ============================================================================
# Choice Type Constants
# ============================================================================

class ChoiceType:
    """Constants for different choice types in the game."""
    CHOOSE_CARD = 0
    CHOOSE_ACTION = 1
    CHOOSE_CARDS_TO_DISCARD = 2
    CASH_IN_CARDS = 3
    CHOOSE_QUEUE_TO_SCOUT = 4
    CHOOSE_PILLAGE_CARD = 5
    
    # Legacy names (for backward compatibility)
    choose_card_choice_type = 0
    choose_action_choice_type = 1
    choose_cards_to_discard = 2
    cash_in_cards_choice_type = 3
    choose_queue_to_scout_choice_type = 4
    choose_pillage_card_choice_type = 5


# ============================================================================
# Action Name Constants (case-insensitive)
# ============================================================================

class ActionName:
    """Action name constants (case-insensitive string matching)."""
    # All action names from action.csv - each is a separate action
    ATTACK = 'attack'
    ASSAULT = 'assault'
    BYPASS = 'bypass'
    DEFEND = 'defend'
    EXIT = 'exit'
    HUMAN_SHIELDS = 'human shields'
    ORDER = 'order'
    PATROL = 'patrol'
    PILLAGE = 'pillage'
    PROMOTE = 'promote'
    REST = 'rest'
    RETREAT = 'retreat'
    SCOUT = 'scout'
    SEARCH = 'search'
    SERVICE = 'service'
    SIGINT = 'sigint'
    SOBER_UP = 'sober_up'
    WAIT = 'wait'
    
    @classmethod
    def normalize(cls, action_name):
        """Normalize an action name to lowercase (case-insensitive matching)."""
        if not action_name:
            return None
        return action_name.lower().strip()


# ============================================================================
# Modifier Type Constants
# ============================================================================

class ModifierType:
    """Modifier type constants for different action types."""
    # For attacks: damage modifiers
    DAMAGE_ADD = '+'  # Add damage (+0, +1, +2, -1)
    DAMAGE_FIXED = '='  # Fixed damage (=4)
    
    # For overtake: move distance
    MOVE_FIXED = '='  # Fixed move (=1, =2)
    MOVE_REVERSE = '-'  # Reverse move (-1)
    
    # For pillage: extra cards
    PILLAGE_EXTRA = '+'  # Extra cards (+0, +1)
    PILLAGE_COUNT = '='  # Specific count (=3)
    
    # For scout: restriction and count
    SCOUT_RESTRICTION = 'E'  # Scout restriction (E for everything)
    SCOUT_COUNT = None  # Count is a number (e.g., 2 in SE2)
    
    # For defend: defense type and reward
    DEFEND_SABOTEUR = 'S'
    DEFEND_GROUND = 'G'
    DEFEND_AERIAL = 'A'
    DEFEND_RESISTANCE = 'R'
    DEFEND_TRAP = 'T'
    DEFEND_REWARD = '_'  # Reward indicator (A)trocities, (C)ash or (B)oth
    
    # For rest: rest type
    REST_BASIC = '=0'
    REST_WITH_CARDS = '=2'
    
    # For wait/order: no modifier
    NONE = '..'


# ============================================================================
# Utility Functions
# ============================================================================

def parse_effect_string(effect_str):
    """
    Parse an effect string into a list of (action_type, modifier) tuples.
    
    Examples:
        "A+0" -> [('A', '+0')]
        "B=1A+0" -> [('B', '=1'), ('A', '+0')]
        "DS_" -> [('D', 'S_')]
        "SE2" -> [('S', 'E2')]
        "Z=0" -> [('Z', '=0')]
        "W.." -> [('W', '..')]
    
    Args:
        effect_str: The effect string to parse
        
    Returns:
        List of tuples: [(action_type_char, modifier_str), ...]
    """
    if not effect_str:
        return []
    
    actions = []
    i = 0
    while i < len(effect_str):
        # Get action type (single character)
        action_type = effect_str[i]
        i += 1
        
        # Get modifier (next 2 characters, or rest if less)
        if i < len(effect_str):
            if action_type == 'D':
                # Defend actions: modifier is 2 chars (type + reward)
                modifier = effect_str[i:i+2] if i+2 <= len(effect_str) else effect_str[i:]
                i += 2
            elif action_type == 'S':
                # Scout actions: modifier can be 2 chars (restriction + count)
                if i+1 < len(effect_str) and effect_str[i+1].isdigit():
                    modifier = effect_str[i:i+2]
                    i += 2
                else:
                    modifier = effect_str[i:i+2] if i+2 <= len(effect_str) else effect_str[i:]
                    i += 2
            elif action_type == 'Z':
                # Rest actions: modifier is =0 or =2
                modifier = effect_str[i:i+2] if i+2 <= len(effect_str) else effect_str[i:]
                i += 2
            elif action_type == 'W':
                # Wait actions: modifier is ..
                modifier = effect_str[i:i+2] if i+2 <= len(effect_str) else effect_str[i:]
                i += 2
            elif action_type == 'O':
                # Order actions: modifier is =0
                modifier = effect_str[i:i+2] if i+2 <= len(effect_str) else effect_str[i:]
                i += 2
            elif action_type == 'E':
                # Escape actions: can have SC or just be E
                if i+1 < len(effect_str) and effect_str[i:i+2] == 'SC':
                    modifier = 'SC'
                    i += 2
                else:
                    modifier = ''
                    # Don't increment i, next iteration will handle next action
            else:
                # Other actions (A, B, P): modifier is typically 2 chars (+0, =1, etc.)
                modifier = effect_str[i:i+2] if i+2 <= len(effect_str) else effect_str[i:]
                i += 2
        else:
            modifier = ''
        
        actions.append((action_type, modifier))
    
    return actions
