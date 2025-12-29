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


"""
Action is a class for an action card.

Each action is a class with following variables:
  - cost: the cost of the action in cards
  - effect: the effect of the action
  - limits: the limits of the action
  - name: the name of the action
"""

class CardAction:
  def __init__(self, cost, effect, limits, name):
    self.cost = cost
    self.effect = effect
    self.limits = limits
    self.name = name

  def __str__(self):
    return f"{self.name} ({self.cost}) {self.effect} {self.limits}"

  def __repr__(self):
    return self.__str__()
  
  def describe(self):
    """Return a dictionary describing this action."""
    return {
      'name': self.name,
      'cost': self.cost,
      'effect': self.effect,
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
  
  Returns a dictionary where keys are card IDs and values are lists of action dictionaries.
  Each action dictionary has the keys: 'cost', 'effect', 'limits', 'name'
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
      
      # Build the limits dictionary from separate I, P, L columns
      # Only include keys that have non-empty values
      limits = {}
      if row['I'].strip():
        limits['I'] = row['I'].strip()
      if row['P'].strip():
        limits['P'] = row['P'].strip()
      if row['L'].strip():
        limits['L'] = row['L'].strip()
      
      # Create the action dictionary
      action = CardAction(
        cost=row['cost'],
        effect=row['effect'],
        limits=limits,
        name=row['name']
      )
      
      # Initialize the card's action list if needed
      if card_id not in deck:
        deck[card_id] = []
      
      # Append actions in order (they should be sorted by action_index in the CSV)
      # For safety, ensure we insert at the correct index
      while len(deck[card_id]) <= action_index:
        deck[card_id].append(None)
      deck[card_id][action_index] = action
  
  # Clean up: remove None placeholders and convert to list of actions
  result = {}
  for card_id in sorted(deck.keys()):
    result[card_id] = ActionCard(actions=[action for action in deck[card_id] if action is not None], id=card_id)
  
  return result


class CardDeckActions:
  """
  Class containing the action card deck.
  
  The deck is loaded from the CSV file when the class is defined.
  """
  
  deck = _load_deck_from_csv()
