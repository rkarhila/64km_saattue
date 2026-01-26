#! /usr/bin/env python3

"""
This module contains the deck of resistance cards for the game.

The card information is read from a separate CSV file and converted into a dictionary.
"""

import csv
import os


class ResistanceCard:
  """A resistance card."""
  
  def __init__(self, id, name, effect):
    self.id = id
    self.name = name
    self.effect = effect
  
  def __str__(self):
    return f"ResistanceCard({self.id}): {self.name}"
  
  def __repr__(self):
    return self.__str__()
  
  def describe(self):
    """Return a dictionary describing this resistance card."""
    return {
      'name': self.name,
      'effect': self.effect
    }


def _load_deck_from_csv():
  """
  Load the resistance deck from the CSV file.
  
  The CSV format has:
    - card_id: the card ID (integer)
    - name: the name of the resistance
    - attack: attack value (integer)
    - target: target zone/unit (string)
    - loot: loot value (integer)
    - durability: durability value (integer)
    - damage_I: damage to Infantry (integer)
    - damage_P: damage to Panzer (integer)
  
  Returns a dictionary where keys are card IDs and values are ResistanceCard objects.
  """
  # Get the directory where this module is located
  module_dir = os.path.dirname(os.path.abspath(__file__))
  csv_path = os.path.join(module_dir, 'cards', 'resistance.csv')
  
  deck = {}
  
  with open(csv_path, 'r', encoding='utf-8') as f:
    reader = csv.DictReader(f)
    for row in reader:
      card_id = int(row['card_id'].strip())
      name = row['name'].strip()
      attack = int(row['attack'].strip())
      target = row['target'].strip()
      loot = int(row['loot'].strip())
      durability = int(row['durability'].strip())
      damage_I = int(row['damage_I'].strip())
      damage_P = int(row['damage_P'].strip())
      
      effect = {
        'attack': attack,
        'target': target,
        'loot': loot,
        'durability': durability,
        'damage': {'I': damage_I, 'P': damage_P}
      }
      
      deck[card_id] = ResistanceCard(
        id=card_id,
        name=name,
        effect=effect
      )
  
  return deck


class CardDeckResistance:
  """
  Class containing the resistance card deck.
  
  The deck is loaded from the CSV file when the class is defined.
  """
  
  deck = _load_deck_from_csv()
