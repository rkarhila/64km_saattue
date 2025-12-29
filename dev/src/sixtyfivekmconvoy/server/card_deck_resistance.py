#! /usr/bin/env python3

"""
This module contains the deck of resistance cards for the game.
"""


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


class CardDeckResistance:

  deck = {
    0: ResistanceCard(
      id=0,
      name='Peltoja ja PST-sissejä (1)',
      effect={
        'attack': 3,
        'target': 'A1',
        'loot': 3,
        'durability': 3,
        'damage': {'I': 1, 'P': 2}
      }
    ),
    1: ResistanceCard(
      id=1,
      name='Peltoja ja PST-sissejä (2)',
      effect={
        'attack': 3,
        'target': 'A1',
        'loot': 3,
        'durability': 3,
        'damage': {'I': 1, 'P': 2}
      }
    ),
    2: ResistanceCard(
      id=2,
      name='Metsää ja metsäsissejä (1)',
      effect={
        'attack': 3,
        'target': 'A1',
        'loot': 3,
        'durability': 3,
        'damage': {'I': 1, 'P': 2}
      }
    ),
    3: ResistanceCard(
      id=3,
      name='Metsää ja metsäsissejä (2)',
      effect={
        'attack': 3,
        'target': 'A1',
        'loot': 3,
        'durability': 3,
        'damage': {'I': 1, 'P': 2}
      }
    ),
    4: ResistanceCard(
      id=4,
      name='Käännetty kyltti ja jalkaväkeä (1)',
      effect={
        'attack': 3,
        'target': 'A1',
        'loot': 3,
        'durability': 3,
        'damage': {'I': 1, 'P': 2}
      }
    ),
    5: ResistanceCard(
      id=5,
      name='Käännetty kyltti ja jalkaväkeä (2)',
      effect={
        'attack': 3,
        'target': 'A1',
        'loot': 3,
        'durability': 3,
        'damage': {'I': 1, 'P': 2}
      }
    ),
    6: ResistanceCard(
      id=6,
      name='Käännetty kyltti ja jalkaväkeä (3)',
      effect={
        'attack': 3,
        'target': 'A1',
        'loot': 3,
        'durability': 3,
        'damage': {'I': 1, 'P': 2}
      }
    ),
    7: ResistanceCard(
      id=7,
      name='Pieni kylä',
      effect={
        'attack': 3,
        'target': 'A1',
        'loot': 3,
        'durability': 3,
        'damage': {'I': 1, 'P': 2}
      }
    ),
    8: ResistanceCard(
      id=8,
      name='Pieni kylä',
      effect={
        'attack': 3,
        'target': 'A1',
        'loot': 3,
        'durability': 3,
        'damage': {'I': 1, 'P': 2}
      }
    ),
    9: ResistanceCard(
      id=9,
      name='Kirkonkylä',
      effect={
        'attack': 3,
        'target': 'A1',
        'loot': 3,
        'durability': 3,
        'damage': {'I': 1, 'P': 2}
      }
    ),
    10: ResistanceCard(
      id=10,
      name='Kirkonkylä',
      effect={
        'attack': 3,
        'target': 'A1',
        'loot': 3,
        'durability': 3,
        'damage': {'I': 1, 'P': 2}
      }
    ),
    11: ResistanceCard(
      id=11,
      name='Kirkonkylä',
      effect={
        'attack': 3,
        'target': 'A1',
        'loot': 3,
        'durability': 3,
        'damage': {'I': 1, 'P': 2}
      }
    ),
    12: ResistanceCard(
      id=12,
      name="Käännetty kyltti ja tark'ampujia (1)",
      effect={
        'attack': 3,
        'target': 'A1',
        'loot': 3,
        'durability': 3,
        'damage': {'I': 1, 'P': 2}
      }
    ),
    13: ResistanceCard(
      id=13,
      name="Käännetty kyltti ja tark'ampujia (2)",
      effect={
        'attack': 3,
        'target': 'A1',
        'loot': 3,
        'durability': 3,
        'damage': {'I': 1, 'P': 2}
      }
    ),
    14: ResistanceCard(
      id=14,
      name="Käännetty kyltti ja tark'ampujia (3)",
      effect={
        'attack': 3,
        'target': 'A1',
        'loot': 3,
        'durability': 3,
        'damage': {'I': 1, 'P': 2}
      }
    ),
    15: ResistanceCard(
      id=15,
      name='Kaupunki',
      effect={
        'attack': 3,
        'target': 'A1',
        'loot': 3,
        'durability': 3,
        'damage': {'I': 1, 'P': 2}
      }
    ),
    16: ResistanceCard(
      id=16,
      name='Kaupunki',
      effect={
        'attack': 3,
        'target': 'A1',
        'loot': 3,
        'durability': 3,
        'damage': {'I': 1, 'P': 2}
      }
    ),
    17: ResistanceCard(
      id=17,
      name='Kaupunki',
      effect={
        'attack': 3,
        'target': 'A1',
        'loot': 3,
        'durability': 3,
        'damage': {'I': 1, 'P': 2}
      }
    ),
    18: ResistanceCard(
      id=18,
      name='Kasarmi',
      effect={
        'attack': 3,
        'target': 'A1',
        'loot': 3,
        'durability': 3,
        'damage': {'I': 1, 'P': 2}
      }
    ),
  }


  # deck = { 0 : { 'name' : 'kaupunki',
  #                'effect' :
  #                {'attack': 3,
  #                 'target': 'A1',
  #                 'loot': 3,
  #                 'durability' : 3,
  #                 'damage' : {'I': 1, 'P':2  }}
  #               },
  #          1 : { 'name' : 'kylä', 'effect' : {'attack': 3, 'target': 'A1', 'loot': 3, 'durability' : 3, 'damage' : {'I': 1, 'P':2  }} },
  #          2 : { 'name' : 'kaupunki', 'effect' : {'attack': 3, 'target': 'A1', 'loot': 3, 'durability' : 3, 'damage' : {'I': 1, 'P':2  }} },
  #          3 : { 'name' : 'peltoja', 'effect' : {'attack': 3, 'target': 'A1', 'loot': 3, 'durability' : 3, 'damage' : {'I': 1, 'P':2  }} },
  #          4 : { 'name' : 'metsää', 'effect' : {'attack': 3, 'target': 'A1', 'loot': 3, 'durability' : 3, 'damage' : {'I': 1, 'P':2  }} },
  #          5 : { 'name' : 'metsää', 'effect' : {'attack': 3, 'target': 'A1', 'loot': 3, 'durability' : 3, 'damage' : {'I': 1, 'P':2  }} },
  #          6 : { 'name' : 'peltoja', 'effect' : {'attack': 3, 'target': 'A1', 'loot': 3, 'durability' : 3, 'damage' : {'I': 1, 'P':2  }} },
  #          7 : { 'name' : 'kaupunki', 'effect' : {'attack': 3, 'target': 'A1', 'loot': 3, 'durability' : 3, 'damage' : {'I': 1, 'P':2  }} },
  #          8 : { 'name' : 'peltoja', 'effect' : {'attack': 3, 'target': 'A1', 'loot': 3, 'durability' : 3, 'damage' : {'I': 1, 'P':2  }} },
  #          9 : { 'name' : 'metsää', 'effect' : {'attack': 3, 'target': 'A1', 'loot': 3, 'durability' : 3, 'damage' : {'I': 1, 'P':2  }} },
  #          10 : { 'name' : 'kirkonkylä', 'effect' : {'attack': 3, 'target': 'A1', 'loot': 3, 'durability' : 3, 'damage' : {'I': 1, 'P':2  }} },
  #          11 : { 'name' : 'silta', 'effect' : {'attack': 3, 'target': 'A1', 'loot': 3, 'durability' : 3, 'damage' : {'I': 1, 'P':2  }} } }
