#! /usr/bin/env python3

"""
This module contains the deck of action cards for the game.

The card information is read from a separare csv file and converted into a dictionary of lists.

The deck is a dictionary of actioncards, where the key is the card number and the value is actioncard object.

Actioncard is a holding class for a list of action class objects.

Each action is a class with following variables:
  - cost: the cost of the action in cards
  - effect: the effect of the action
  - limits: the limits of the action
  - name: the name of the action

The deck is used to generate the action cards for each player.

"""

import csv
import os
from .constants import ActionName


"""
Action is a class for an action card.

Each action is a class with following variables:
  - cost: the cost of the action in cards (string like 'T' or '0' or '1')
  - action_name: the normalized action name (string)
  - action_modifier: the numeric modifier value (int)
  - zone: the zone where the action can be used (string like 'AB', 'ABCE')
  - troop_type: the troop type this action is for ('P', 'I', 'L', or 'A' for all)
  - tire: whether the action causes the unit to tire (0 or 1)
  - intoxicate: whether the action causes the unit to become intoxicated (0 or 1)
  - limits: dictionary with keys 'I', 'P', 'L' for unit type limits (derived from troop_type)
  - name: the display name of the action
"""

class CardAction:
  def __init__(self, cost, action_name, action_modifier, zone, troop_type, tire, intoxicate, name):
    """
    Initialize a CardAction.
    
    Args:
      cost: the cost of the action (string 'T', '0', '1', etc.)
      action_name: the normalized action name (string)
      action_modifier: the numeric modifier value (int)
      zone: the zone where the action can be used (string)
      troop_type: the troop type this action is for ('P', 'I', 'L', or 'A')
      tire: whether the action causes the unit to tire (0 or 1)
      intoxicate: whether the action causes the unit to become intoxicated (0 or 1)
      name: the display name of the action
    """
    self.cost = cost
    self.action_name = action_name
    self.action_modifier = action_modifier
    self.zone = zone
    self.troop_type = troop_type
    self.tire = tire
    self.intoxicate = intoxicate
    self.name = name
    
    # Build limits dictionary from troop_type
    # If troop_type is 'A', action is available to all troop types
    self.limits = {}
    if troop_type == 'A':
      self.limits = {'I': zone, 'P': zone, 'L': zone}
    else:
      self.limits = {troop_type: zone}

  def __str__(self):
    return f"{self.name} (cost:{self.cost}, {self.action_name}={self.action_modifier}, zone:{self.zone}, troop:{self.troop_type}, tire:{self.tire}, intox:{self.intoxicate})"

  def __repr__(self):
    return self.__str__()
  
  def describe(self):
    """Return a dictionary describing this action."""
    return {
      'name': self.name,
      'cost': self.cost,
      'action_name': self.action_name,
      'action_modifier': self.action_modifier,
      'zone': self.zone,
      'troop_type': self.troop_type,
      'tire': self.tire,
      'intoxicate': self.intoxicate,
      'limits': self.limits
    }


"""
Actioncard is a holding class for a list of action class objects.

Each actioncard has a list of actions.

"""
class ActionCard():

  def __init__(self, id, actions):
    self.id = id
    self.actions = actions

  def get_actions(self):
      return self.actions

  def __str__(self):
      action_names = '/'.join([action.name for action in self.actions])
      return f"ActionCard({self.id}): {action_names}"

  def __repr__(self):
      return self.__str__()
  
  def describe(self):
    """Return a list of action dictionaries describing this card."""
    return [action.describe() for action in self.actions]






    # Actions string:
    #   B=1 bypass : move forward 1
    #   B=2 bypass : move forward 2
    #   B-1  reverse : move backward 1
    #   P+0  pillage
    #   P+1 pillage, with extra card
    #   A+2  attack with +2 damage
    #   A+1  attack with +1 damage
    #   A+0    normal attack
    #   A-1  attack with -1 damage
    #   A=4  fixed 4 damage (independent of troop type)
    #   S+1 scout, reveal and reorder 1-4 card
    #   S+0   scout, reveal and reorder 1-3 cards
    #   S-1 scout, reveal and reorder 1-2 cards
    #   Z..  rest ('zzz')
    #   W..  wait
    #   O..  order (waiting troop)
    #   Dr. defend against resistance
    #   Da. defend against aerial attacks
    #   Dg. defend against ground attack
    #   Dt. defend against traps
    #   Ds. defend against saboteur activity



def _load_deck_from_csv():
  """
  Load the action deck from the CSV file.
  
  The CSV format has:
    - card_id: the card ID
    - action_index: the index of the action within the card (0, 1, 2, 3)
    - troop_type: 'P' (Pioneer/Panzer), 'I' (Infantry), 'L' (Logistics), or 'A' (All)
    - zone: the zone where the action can be used (e.g., 'AB', 'ABCE', 'E')
    - action_type: the action name (e.g., 'Attack', 'Rest', 'Pillage')
    - action_modifier: numeric modifier value
    - cost: 'T' (tiredness + under_influence) or numeric string like '0', '1'
    - tire: 0 or 1 (whether action causes unit to tire)
    - intoxicate: 0 or 1 (whether action causes unit to become intoxicated)
    - name: display name for the action
  
  If zone is empty, the action is null and should be ignored.
  
  Returns a dictionary where keys are card IDs and values are ActionCard objects.
  """
  # Get the directory where this module is located
  module_dir = os.path.dirname(os.path.abspath(__file__))
  csv_path = os.path.join(module_dir, 'cards', 'action.csv')
  
  deck = {}
  
  with open(csv_path, 'r', encoding='utf-8') as f:
    reader = csv.DictReader(f)
    for row in reader:
      card_id = int(row['card_id'])
      action_index = int(row['action_index'])
      
      # Skip null actions (zone is empty)
      zone = row['zone'].strip() if 'zone' in row else ''
      if not zone:
        continue
      
      # Get and normalize action name
      action_type = row['action_type'].strip()
      if not action_type:
        continue
      action_name = ActionName.normalize(action_type)
      
      # Get modifier (numeric value, acts as "=" in old system)
      action_modifier = int(row['action_modifier'].strip()) if row['action_modifier'].strip() else 0
      
      # Get troop type
      troop_type = row['troop_type'].strip()
      
      # Get cost (default to '0' if not present)
      cost = row.get('cost', '0').strip()
      if not cost:
        cost = '0'
      
      # Get tire and intoxicate
      tire = int(row['tire'].strip()) if row['tire'].strip() else 0
      intoxicate = int(row['intoxicate'].strip()) if row['intoxicate'].strip() else 0
      
      # Get name
      name = row['name'].strip() if row['name'].strip() else action_type
      
      # Create the CardAction object
      action = CardAction(
        cost=cost,
        action_name=action_name,
        action_modifier=action_modifier,
        zone=zone,
        troop_type=troop_type,
        tire=tire,
        intoxicate=intoxicate,
        name=name
      )
      
      # Initialize the card's action list if needed
      if card_id not in deck:
        deck[card_id] = {}
      
      # Store actions by action_index (we'll collect all actions for each card)
      deck[card_id][action_index] = action
  
  # Convert to ActionCard objects
  result = {}
  for card_id in sorted(deck.keys()):
    # Get all actions sorted by action_index
    actions = [deck[card_id][idx] for idx in sorted(deck[card_id].keys())]
    result[card_id] = ActionCard(id=card_id, actions=actions)
  
  return result


class CardDeckActions:
  """
  Class containing the action card deck.
  
  The deck is loaded from the CSV file when the class is defined.
  """
  
  deck = _load_deck_from_csv()
