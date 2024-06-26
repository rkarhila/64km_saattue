#!/usr/bin/env python3


EMOJI_LOOT_1 = u'\u2460'
EMOJI_LOOT_2 = u'\u2461'
EMOJI_LOOT_3 = u'\u2462'
EMOJI_LOOT_4 = u'\u2463'
EMOJI_LOOT_5 = u'\u2464'
EMOJI_LOOT_6 = u'\u2465'

EMOJI_LUGGAGE = u'\u1F9F3'

#EMOJI_DAMAGE = u'\u1F4A5'
EMOJI_DAMAGE = u'\u2B59'



class Resistance:
  
  def __init__(self, name_and_description, gamestate):
    print("Initialising resisintace")
    if name_and_description is None:
      self.name = None
    else:
      self.name = name_and_description['name']
      self.damage_to_convoy = name_and_description['effect']['attack']
      self.target = name_and_description['effect']['target']
      self.loot = name_and_description['effect']['loot']
      self.durability = name_and_description['effect']['durability']
      self.damage_from_convoy = name_and_description['effect']['damage']

      self.active = True
      self.damage_status = self.durability
    self.gamestate = gamestate

      
  def take_damage(self, damagetype, modifier):
    if modifier[0] == '=':
      damage = int(modifier[1])
    elif modifier[0] == '+':
      damage = self.damage_from_convoy[damagetype] + int(modifier[1])
    elif modifier[0] == '-':
      damage = self.damage_from_convoy[damagetype] - int(modifier[1])
    # elif type(damagetype) == int:
    #   self.durability -= damagetype
    # elif damagetype in '0123456789':
    #   self.durability -= int(damagetype)
    # else:
    #   raise ValueError(f'Cannot interpret "{damagetype}" as damage')

    print(f"Resistance takes {damage} damage from attack") 
    if damage <= 0:
      return 0
    else:
      self.durability -= damage
    
      if self.durability <= 0:
        self.status = 'destroyed'
        self.active = False
        self.distribute_loot()
        return 2, f'Resistance took {damage} damage and is destroyed! Player gains 2 money'
      else:
        return 1, f'Resistance took {damage} damage and is left with {self.durability}. Player gains 1 money.'

  def attack(self):
    print("New resistance attacks!")
    msg = self.gamestate.convoy.apply_damage(3, unit=1)
    return msg #self.gamestate.broadcast(msg)
    
  def distribute_loot(self):
    for i in range(self.loot):
      if len(self.gamestate.pillage_deck.deck) > 0:
        self.gamestate.pillage_queue.put_card(self.gamestate.pillage_deck.get_card())

  def __str__(self):
    return (self.name \
            + f',attacks{self.target}' \
            + f'with{self.damage_to_convoy}' \
            + f',{self.loot}loot' \
            + f',status{self.damage_status}/{self.durability}')


  def to_str(self):
    if self.name:
      return (self.name \
            + f',attacks{self.target}' \
            + f'with{self.damage_to_convoy}' \
            + f',{self.loot}loot' \
            + f',status{self.damage_status}/{self.durability}')


  def to_json(self):
    if self.name:
      return {'in_progress' : self.to_str() }
            
