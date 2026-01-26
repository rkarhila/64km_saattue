#! /usr/bin/env python3

"""
This module contains the deck of pillage cards for the game.

The card information is read from a separate CSV file and converted into a dictionary.
"""

import csv
import os


class PillageCard:
  """A pillage card."""
  
  def __init__(self, id, name, reward):
    self.id = id
    self.name = name
    self.reward = reward
  
  def __str__(self):
    return f"PillageCard({self.id}): {self.name}"
  
  def __repr__(self):
    return self.__str__()
  
  def describe(self):
    """Return a dictionary describing this pillage card."""
    return {
      'name': self.name,
      'reward': self.reward
    }


def _load_deck_from_csv():
  """
  Load the pillage deck from the CSV file.
  
  The CSV format has:
    - card_id: the card ID (integer)
    - name: the name of the pillage location
    - cash: cash reward (integer)
    - loot: loot reward (comma-separated list of integers, or empty string)
    - atrocities: atrocity points (integer)
  
  Returns a dictionary where keys are card IDs and values are PillageCard objects.
  """
  # Get the directory where this module is located
  module_dir = os.path.dirname(os.path.abspath(__file__))
  csv_path = os.path.join(module_dir, 'cards', 'pillage.csv')
  
  deck = {}
  
  with open(csv_path, 'r', encoding='utf-8') as f:
    reader = csv.DictReader(f)
    for row in reader:
      card_id = int(row['card_id'].strip())
      name = row['name'].strip()
      cash = int(row['cash'].strip())
      loot_str = row['loot'].strip()
      atrocities = int(row['atrocities'].strip())
      
      # Parse loot: empty string means empty list, otherwise parse comma-separated integers
      if not loot_str:
        loot = []
      else:
        loot = [int(x.strip()) for x in loot_str.split(',') if x.strip()]
      
      reward = {
        'cash': cash,
        'loot': loot,
        'atrocities': atrocities
      }
      
      deck[card_id] = PillageCard(
        id=card_id,
        name=name,
        reward=reward
      )
  
  return deck


class CardDeckPillage:
  """
  Class containing the pillage card deck.
  
  The deck is loaded from the CSV file when the class is defined.
  """
  
  deck = _load_deck_from_csv()
    
  """
  deck = { 0 : { 'name' : 'ruokala', 'effect' : [] },
           1 : { 'name' : 'sairaala', 'effect' : [] },
           2 : { 'name' : 'kauppa', 'effect' : [] },
           3 : { 'name' : 'paviljonki', 'effect' : [] },
           4 : { 'name' : 'ravintola', 'effect' : [] },
           5 : { 'name' : 'eteinen', 'effect' : [] },
           6 : { 'name' : 'patsas', 'effect' : [] },
           7 : { 'name' : 'verstas', 'effect' : [] },
           8 : { 'name' : 'hääjuhlat', 'effect' : [] },
           9 : { 'name' : 'leipamo', 'effect' : [] },
           10 : { 'name' : 'hautajaiset', 'effect' : [] },
           11 : { 'name' : 'työmaa', 'effect' : [] },
           12 : { 'name' : 'hautausmaa', 'effect' : [] },
           13 : { 'name' : 'kaatopaikka', 'effect' : [] },
           14 : { 'name' : 'maatalo', 'effect' : [] },
           15 : { 'name' : 'maatila', 'effect' : [] },
           16 : { 'name' : 'huvila', 'effect' : [] },
           17 : { 'name' : 'koulu', 'effect' : [] },
           18 : { 'name' : 'lautapelikauppa', 'effect' : [] },
           19 : { 'name' : 'tatuointiliike', 'effect' : [] },
           20 : { 'name' : 'hotelli', 'effect' : [] },
           21 : { 'name' : 'majatalo', 'effect' : [] },
           22 : { 'name' : 'kaupungintalo', 'effect' : [] },
           23 : { 'name' : 'kirkko', 'effect' : [] } } 
  """
