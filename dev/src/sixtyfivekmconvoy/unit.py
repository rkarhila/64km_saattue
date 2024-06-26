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


  ### /state related methods
  
  def apply_damage(self, damage):
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
    # Loop with highest loot first:
    loot.sort(reverse=True)
    for i,l in enumerate(loot):
      if l > self.carry[-1]:
        self.carry[-1] = l
        # sort loot array (highest first):
        self.carry.sort(reverse=True)
      else:
        # These loot items could not be placed:
        return loot[i:]
    return []

  def tire(self):
    self.tired += 1
  
  def become_frustrated(self):
    if self.under_influence == 0:
      self.under_influence = 1
    else:
      self.tired += 1
      
  def rest(self):
    if self.under_influence > 0:
      self.under_influence = 0
    else:
      self.tired = max(0, self.tired - 2)

  def rest_with_cards(self):
    self.tired = 0

  def can_rest(self):
    if self.tired > 0 or self.under_influence > 0:
      return True
    return False

  def can_rest_with_cards(self):
    if self.under_influence == 0 and self.tired > 2:
      return True
    else:
      return False

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

  def resolve_pillage(self, modifier=0):
    dummy = 1

  def resolve_rest(self, modifier=0):
    if self.can_rest():
      self.rest()
      return True
    else:
      return False
    
  def resolve_scout(self, modifier=0):
    dummy = 1

  def resolve_defend(self, modifier=0):
    dummy = 1

  def resolve_bypass(self, modifier=0):
    dummy = 1

  def resolve_reverse(self, modifier=0):
    dummy = 1

