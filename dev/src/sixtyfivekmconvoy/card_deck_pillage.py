
import random

class CardDeckPillage:

  deck = {}

  for i in range(40):
    deck[i] = { 'name' : f'pillage_{i}',
                'reward' : {
                  'cash' : random.choice([0,1,2]),
                  'loot' : random.choice([ [], [],[1], [1,1], [1,1,1], [3], [3,1], [5]]),
                  'atrocities' : random.choice([0,1]) } }
    
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
           9 : { 'name' : 'leipomo', 'effect' : [] },
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
