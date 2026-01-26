#! /usr/bin/env python3

"""
This module contains the deck of mauling cards for the game.

The card information is read from a separate CSV file and converted into a dictionary.
"""

import csv
import os


class CardMauling:
  """A single mauling action/effect."""
  
  def __init__(self, name, effect):
    self.name = name
    self.effect = effect
  
  def __str__(self):
    return f"{self.name}: {self.effect}"
  
  def __repr__(self):
    return self.__str__()
  
  def describe(self):
    """Return a dictionary describing this mauling action."""
    return {
      'name': self.name,
      'effect': self.effect
    }


class MaulingCard:
  """A mauling card containing mauling actions (currently just one effect)."""
  
  def __init__(self, id, name, effect):
    self.id = id
    self.name = name
    self.effect = effect
    # Store as a list of CardMauling for consistency with ActionCard pattern
    self.maulings = [CardMauling(name, effect)]
  
  def __str__(self):
    return f"MaulingCard({self.id}): {self.name}"
  
  def __repr__(self):
    return self.__str__()
  
  def describe(self):
    """Return a dictionary describing this mauling card."""
    return {
      'name': self.name,
      'effect': self.effect
    }


def _load_deck_from_csv():
  """
  Load the mauling deck from the CSV file.
  
  The CSV format has:
    - card_id: the card ID (integer)
    - name: the name of the mauling
    - damage_min: minimum damage (integer)
    - damage_max: maximum damage (integer)
    - target: target zone/unit (string)
    - atrocity_threshold: atrocity threshold (integer)
    - type: attack type (string: Ground, Aerial, Saboteur, Trap)
  
  Returns a dictionary where keys are card IDs and values are MaulingCard objects.
  """
  # Get the directory where this module is located
  module_dir = os.path.dirname(os.path.abspath(__file__))
  csv_path = os.path.join(module_dir, 'cards', 'mauling.csv')
  
  deck = {}
  
  with open(csv_path, 'r', encoding='utf-8') as f:
    reader = csv.DictReader(f)
    for row in reader:
      card_id = int(row['card_id'].strip())
      name = row['name'].strip()
      damage_min = int(row['damage_min'].strip())
      damage_max = int(row['damage_max'].strip())
      target = row['target'].strip()
      atrocity_threshold = int(row['atrocity_threshold'].strip())
      attack_type = row['type'].strip()
      
      effect = {
        'damage': [damage_min, damage_max],
        'target': target,
        'atrocity_threshold': atrocity_threshold,
        'type': attack_type
      }
      
      deck[card_id] = MaulingCard(
        id=card_id,
        name=name,
        effect=effect
      )
  
  return deck


class CardDeckMauling:
  """
  Class containing the mauling card deck.
  
  The deck is loaded from the CSV file when the class is defined.
  """
  
  deck = _load_deck_from_csv()
  
  """
  deck = { 0 : { 'name' : 'Kiväärihenkilöitä/Panssarirynnäkkö',
                 'effect' : { 'type' : 'G',
                              'damage' : ['D1', 'D3'] } },
           1 : { 'name' : 'Satunnaista ammuskelua /Tykistöisku',
                 'effect' : { 'type' : 'G',
                              'damage' : ['D1', 'D3'] } },
           2 : { 'name' : 'Kiväärihenkilöitä/Sinkohenkilöitä',
                 'effect' : { 'type' : 'G',
                              'damage' : ['D1', 'D3'] } },
           3 : { 'name' : 'Satunnaista ammuskelua/Raketinheittimiä',
                 'effect' : { 'type' : 'G',
                              'damage' : ['D1', 'D3'] } },
           4 : { 'name' : 'Nelikoptereita/Lennokki-isku',
                 'effect' : { 'type' : 'A',
                              'damage' : ['D1', 'D3'] } },
           5 : { 'name' : 'Nelikoptereita/Lennokki-isku',
                 'effect' : { 'type' : 'A',
                              'damage' : ['D1', 'D3'] } },
           6 : { 'name' : 'Räjähtäviä lepakoita/Napalmia',
                 'effect' : { 'type' : 'A',
                              'damage' : ['D1', 'D3'] } },
           7 : { 'name' : 'Nelikoptereita/Risteilyohjus',
                 'effect' : { 'type' : 'A',
                              'damage' : ['D1', 'D3'] } },
           8 : { 'name' : 'Räjähtäviä lepakoita/Napalmia',
                 'effect' : { 'type' : 'A',
                              'damage' : ['D1', 'D3'] } },
           9 : { 'name' : 'Nelikoptereita/Kiertoratapommitus',
                 'effect' : { 'type' : 'A',
                              'damage' : ['D1', 'D3'] } },
           10 : { 'name' : 'Räjähtäviä lepakoita/Lennokki-isku',
                 'effect' : { 'type' : 'A',
                              'damage' : ['D1', 'D3'] } },
           11 : { 'name' : 'Räjähtäviä lepakoita/Lennokki-isku',
                 'effect' : { 'type' : 'A',
                              'damage' : ['D1', 'D3'] } },
           12 : { 'name' : 'Varkaita/Robottininjoja',
                 'effect' : { 'type' : 'S',
                              'damage' : ['D1', 'D3'] } },
           13 : { 'name' : 'Kaukopartiolaisia/Desantteja',
                 'effect' : { 'type' : 'S',
                              'damage' : ['D1', 'D3'] } },
           14 : { 'name' : 'Varkaita/Kommunisteja',
                 'effect' : { 'type' : 'S',
                              'damage' : ['D1', 'D3'] } },
           15 : { 'name' : 'Maanalainen armeija/Desantteja',
                 'effect' : { 'type' : 'S',
                              'damage' : ['D1', 'D3'] } },
           16 : { 'name' : 'Kaukopartiolaisia/Robottininjoja',
                 'effect' : { 'type' : 'S',
                              'damage' : ['D1', 'D3'] } },
           17 : { 'name' : 'Tienvarsiräjähde/telamiinoja',
                 'effect' : { 'type' : 'T',
                              'damage' : ['D1', 'D3'] } },
           18 : { 'name' : 'Tienvarsiräjähde/viuhkamiinoja',
                 'effect' : { 'type' : 'T',
                              'damage' : ['D1', 'D3'] } },
           19 : { 'name' : 'Tienvarsiräjähde/???',
                 'effect' : { 'type' : 'T',
                              'damage' : ['D1', 'D3'] } },
           20 : { 'name' : '',
                 'effect' : { 'type' : 'G',
                              'damage' : ['D1', 'D3'] } },
           21 : { 'name' : '',
                 'effect' : { 'type' : 'G',
                              'damage' : ['D1', 'D3'] } },
           17 : { 'name' : '',
                 'effect' : { 'type' : 'G',
                              'damage' : ['D1', 'D3'] } },
           18 : { 'name' : '',
                 'effect' : { 'type' : 'G',
                              'damage' : ['D1', 'D3'] } },
           19 : { 'name' : '',
                 'effect' : { 'type' : 'G',
                              'damage' : ['D1', 'D3'] } },

          }
"""
