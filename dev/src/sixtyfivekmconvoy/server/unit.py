#!/usr/bin/env python3

from .constants import *


class UnitType:
  PANZER     = 0
  INFANTRY   = 1
  LOGISTICS  = 2


class Unit:

  player=-1
  unittype = -1
  tired = -1
  under_influence = -1
  # Carry can be loot (positive integer)
  # or damage (negative -1)
  carry = [0,0,0]
  atrocities = -1
  actioncard = None
  actiontaken = None

  secondactioncard = None
  secondactiontaken = None
  
  type_to_str = { 0 : 'Pnz',
                  1 : 'Inf',
                  2 : 'Log' }
  carry_to_str = {0 : '',
                  -1 : EMOJI_DAMAGE,
                  1 : EMOJI_LUGGAGE + '1'}

  playercolors = [ '\033[93m'
                   '\033[95m',
                   '\033[94m',
                   '\033[96m',
                   '\033[92m' ]
  resetfont = '\033[0m'
    # WARNING = 
    # FAIL = '\033[91m'
    # ENDC = '\033[0m'
    # BOLD = '\033[1m'
    # UNDERLINE = '\033[4m'

  
  def __init__(self, player, unittype):
    self.player = player
    self.unittype = unittype
    self.carry = [0,0,0]
    self.tired = 0
    self.under_influence = 0
    self.atrocities = 0
    self.actioncard = None
    self.actiontaken = None
    self.secondactioncard = None
    self.secondactiontaken = None
    self.convoy = None

    self.defending=None
    self.had_defended = False
    self.defending_reward = None
    
    self.current_action_type = None

    
  def __str__(self):
    return (self.player_to_str() \
              + self.unit_type_to_str() \
              + self.tired_to_str() \
              + self.carry_to_str() \
              + self.atrocities_to_str() )

  def to_str(self, playerview=None):
    return (self.player_to_str() \
              + self.unit_type_to_str() \
              + self.tired_to_str() \
              + self.carry_to_str() \
              + self.atrocities_to_str() \
              + self.actioncard_to_str(playerview=playerview))

  def to_json(self, playerview=None):
    return {'player' : self.player.number,
            'unit_type' : self.unit_type_to_str(),
            'tiredness' : self.tired,
            'under_influence' : self.under_influence,
            'atrocities' : self.atrocities,
            'carry' : self.carry,
            'action' : self.actioncard_to_json(playerview=playerview)}
            
            
  def state(self):
    return self.unit_to_state() \
           + self.tired_to_state() \
           + self.carry_to_state() \
           + self.atrocities_to_state()
            
  def player_to_str(self, colorize=False):
    if colorize:
      return Unit.playercolors[self.player.number]+ str(self.player.number) + Unit.resetfont
    return str(self.player.number)

  def player_to_state(self):
    pl = [0,0,0,0,0]
    pl[self.player.number-1] = 1
    return pl

  def carry_to_str(self):
    cs = ''
    if len(self.carry)>0 and max(self.carry) > 0:
      cs += 'L'
      for l in self.carry:
        if l > 0:
          cs += str(l)  
    for d in range(len(self.carry), 3):
      cs += EMOJI_DAMAGE
    return cs
        
  def carry_to_state(self):
    cs = self.carry
    for d in range(len(cs), 3):
      cs.append(-1)
    return cs
            
  def unit_type_to_str(self):
    return Unit.type_to_str[self.unittype]

  def unit_type_to_state(self):
    uts = [0,0,0]
    uts[self.unittype] = 1
    return uts

  def tired_to_str(self): 
    ts = 'T' + str(self.tired)
    if self.under_influence:
      ts += 'U'
    return ts

  def tired_to_state(self):
    return [ self.tired, self.under_influence ]

  def atrocities_to_str(self):
    if self.atrocities > 0:
      return 'A'+str(self.atrocities)
    else:
      return ''

  def atrocities_to_state(self):
    return [self.atrocities]


  def actioncard_to_str(self, playerview=None):
    if self.actioncard is None:
      return ' A-'
    if self.actiontaken is not None:
      return ' A' + str(self.actioncard) + '/' + str(self.actiontaken)
    if playerview is None or playerview.number == self.player:
      return ' A' + str(self.actioncard)
    else:
      return ' A?'

  def actioncard_to_json(self, playerview=None):
    if self.actioncard is None:
      return { 'card' : None}
    if self.actiontaken:
      return { 'card' : self.actioncard, 'actiontaken' : self.actiontaken }
    if playerview is None or playerview.number == self.player:
      return { 'card' : self.actioncard}
    else:
      return { 'card' : '?'}


  ### /state related methods

  def clear_state(self):
    
    self.actioncard = None
    self.actiontaken = None
    self.secondactioncard = None
    self.secondactiontaken = None
    self.current_action_type = None

  
  def is_defending(self):
    if self.current_action_type == 'defending':
      return True
    else:
      return False

  
  def is_resting(self):
    if self.current_action_type == 'resting':
      return True
    else:
      return False
    
  def is_damaged(self):
    if len(self.carry) == 0:
      return True
    return False


  def position(self):
    return self.convoy.get_unit_position(self)

  def index(self):
    return self.convoy.get_unit_index(self)

  def zone(self):
    return self.convoy.get_unit_zone(self)
  
  def get_neighbours(self):
    index=self.convoy.get_unit_index(self)
    if self.position() > 0:
      preceeding=self.convoy.units[index-1]
    else:
      preceeding=None

    if self.position() < len(self.convoy.units)-1:
      following = self.convoy.units[index+1]
    else:
      following = None
    return [ preceeding, following ]
      
  ### /state related methods
  
  def apply_damage(self, damage, discards=0, damage_for_not_discarding=1):
    if discards > 0 and len(self.player.action_cards) >= discards:
      # Choose to discard or not:
      description=f'Do you want to discard {discards} cards to avoid {damage_for_not_discarding} damage?'
      description += f'\n 0: No'
      description += f'\n 1: Yes'
      choose_to_discard = self.gamestate.demand_choice(
        self.player,
        self.gamestate.choose_cards_to_discard,
        [0,1],
        description=description,
        num_choices=1
      )
      if choose_to_discard[0] == 1:
        choicetaken = self.gamestate.demand_choice(self.player,
                                                   self.gamestate.choose_cards_to_discard,
                                                   self.player.action_cards,
                                                   description=description,
                                                   num_choices=discards)
        self.player.discard(self.gamestate.action_deck,
                            choicetaken)
        
      else:
        damage += damage_for_not_discarding
    if damage > len(self.carry):
      self.carry == None
      # Unit destroyed, return -1
      return -1
    for d in range(damage):
      r = self.carry.pop()
    return len(self.carry)

  def gain_loot(self, loot):
    # Handle loot as arrays:
    if type(loot) == int:
      loot=[loot]
    elif type(loot) == str:
      loot = [int(loot)]
    self.carry += loot
    # Loop with highest loot first:
    self.carry.sort(reverse=True)
    dropped = self.carry[3:]
    self.carry = self.carry[:3]

    return [ d for d in dropped if d > 0 ]
    #for i,l in enumerate(loot):
    #  if l > self.carry[-1]:
    #    self.carry[-1] = l
    #    # sort loot array (highest first):
    #    self.carry.sort(reverse=True)
    #  else:
    #    # These loot items could not be placed:
    #    return loot[i:]
    #return []

  def gain_atrocities(self, atrocity):
    self.atrocities += atrocity
  
  def tire(self):
    self.tired += 1
  
  def become_frustrated(self):
    if self.under_influence == 0:
      self.under_influence = 1
    else:
      self.tired += 1


  #
  #  Are actions possible?
  # 

  def can_rest(self):
    if self.tired > 0 or self.under_influence > 0:
      return True
    return False

  def can_rest_with_cards(self):
    if self.under_influence == 0 and self.tired > 2:
      return True
    else:
      return False

  def can_overtake(self, modifier=1, messager=None):
    if modifier > 0:
      if self.position() > modifier:
        return True
      return False
    elif modifier < 0:
      if self.index() < len(self.convoy.units)+modifier:
        return True
      return False
    else:
      raise ValueError("Overtaking modifier cannot be 0")
    
  #
  #  Doing actions
  #
      
  def rest(self):
    if self.under_influence > 0:
      self.under_influence = 0
    else:
      self.tired = max(0, self.tired - 2)

  def rest_with_cards(self):
    self.tired = 0


  #
  # Resolving actions:
  #


  
  """
  def can_attack(self):
    dummy = 1

  def resolve_attack(self, modifier=0):
    if self.can_attack:
      # if player can pay for action:
      # 1. select discard cards (if needed)
      # 2. do damage
      # 3. get benefit
      dummy = 1
    else:
      # unit is intoxicated
      dummy = 1
  """  
             

  def resolve_rest(self, modifier=0):
    if self.can_rest():
      self.rest()
      return True
    else:
      return False
    
  def resolve_scout(self, modifier=0):
    dummy = 1

  def resolve_defend(self, defense_type=None, defense_reward=None):
    if defense_type in 'AGS':
      self.defending = defense_type
      self.has_defended = False
    else:
      raise NotImplementedError("Defense type "+defense_type+ " not implemented")
    self.defending_reward = defense_reward
    return True


  def reward_defending(self):
    assert self.defending_reward is not None, "Defending reward is None"
    r = self.defending_reward
    if r.lower() == 'a':
      self.atrocities += 1
      self.player.cash_this_round += 1
    elif r.lower() == 'c':
      self.player.cash_this_round += 1
    else:
      raise NotImplementedError("defense reward type " + r + " not implemented")
    
  # This should be convoy level operation:
  #def resolve_bypass(self, modifier=0):
  #      dummy = 1

  def resolve_reverse(self, modifier=0):
    dummy = 1

