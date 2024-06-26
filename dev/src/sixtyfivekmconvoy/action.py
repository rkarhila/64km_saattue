#!/usr/bin/env python3

class Action:

  def __init__(self, gamestate, convoy, actor, action, cardnumber):
    self.gamestate = gamestate
    self.convoy = convoy
    self.actor = actor
    self.player = self.convoy.units[self.actor].player
    self.effect = action['effect']
    self.cost = action['cost']
    self.limits = action['limits']
    self.name = action['name']
    self.cardnumber = cardnumber
    self.acting_unit = self.convoy.units[self.actor]
    self.acting_unit_type = self.acting_unit.type_to_str[self.acting_unit.unittype][0]
    self.player = self.acting_unit.player

    self.possible = self.is_possible()
    self.cost = self.get_cost()
    
  def is_possible(self,messager=None):
    
    #messager = print
    if messager: messager(f'  Check if action {self.name} is possible')
    # Start with the easy check:

    # (1) Does the player have enough cards to pay for the action?

    required_cards = self.get_cost()
    if len(self.acting_unit.player.action_cards) < required_cards:
      if messager: messager(f'  Not enough cards to pay for action, requires {required_cards} but player has {len(self.acting_unit.player.action_cards)}' )
      return False
    
    # (2) Are there unit and place limitations for the action?
    
    if self.acting_unit_type not in self.limits:
      if messager: messager(f'  Action not available for unit type {self.acting_unit_type}, requires {",".join(self.limits.keys())}')
      return False
    acting_unit_zone = []
    if self.actor+1 in self.convoy.zones['A']:
      acting_unit_zone.append('A')
    elif self.actor+1 in self.convoy.zones['B']:
      acting_unit_zone.append('B')
    elif self.actor+1 in self.convoy.zones['C']:
      acting_unit_zone.append('C')
    if self.actor - len(self.convoy.units) in self.convoy.zones['E']:
      acting_unit_zone.append('E')
    # Check if any of the acting unit's zones (up to 2) are in the
    # string of allowed zones for the action:
    if not [i for i in acting_unit_zone if i in self.limits[self.acting_unit_type]]:
      if messager: messager("  Action not available in unit's zone")
      return False
            
    # (3) Is there a target for the action?
    # Actions string:
    #   B=1 bypass : move forward 1
    #   B=2 bypass : move forward 2
    #   P+0  pillage
    #   P+1 pillage, with extra card
    #   A+2  attack with +2 damage
    #   A+1  attack with +1 damage
    #   A+0    normal attack
    #   A-1  attack with -1 damage
    #   A=4  fixed 4 damage (independent of troop type)
    #   R=1  reverse : move backward 1
    #   S+1 scout, reveal and reorder 1-4 card
    #   S+0   scout, reveal and reorder 1-3 cards
    #   S-1 scout, reveal and reorder 1-2 cards
    #   Z..  rest ('zzz')
    #   Dr. defend against resistance
    #   Da. defend against aerial attacks
    #   Dg. defend against ground attack
    #   Dt. defend against traps
    #   Dg. defend against guerilla activity
    actionstr = self.effect
    while len(actionstr)>0:
      if actionstr[0] == 'A':
        # require active resistance:
        if not self.gamestate.resistance.active:
          if messager: messager('  No target for attack')
          return False
      elif actionstr[0] == 'B':
        # require position of the acting unit to allow bypass
        modifier=actionstr[1:3]
        if modifier == '=1' or modifier == '=2':
          #print(f"check if {self.actor} < {int(modifier[1])}")
          if self.actor < int(modifier[1]):
            if messager: messager('  Cannot overtake')
            return False
        elif modifier == '-1':
          # If unit is last in convoy, it cannot reverse:
          if self.actor == len(self.convoy.units):
            if messager: messager('  Cannot reverse')
            return False
        else:
          raise ValueError(f'  Bad modifier for overtake action: {modifier}')
      elif actionstr[0] == 'P':
        # Require pillage queue to have cards:
        mod = int(actionstr[2])
        if len(self.gamestate.pillage_queue.cards_and_visibilities) < mod:
          if messager: messager('  Nothing to pillage')
          return False
      elif actionstr[0] == 'S':
        # Scout action: Require something to be scoutable:
        can_scout = False
        for queue in [ self.gamestate.pillage_queue.cards_and_visibilities,
                       self.gamestate.mauling_queue.cards_and_visibilities,
                       self.gamestate.resistance_queue.cards_and_visibilities ]:
          if not can_scout:
            for card_and_vis in queue:
              if not card_and_vis[1]:
                can_scout=True
                break
        if not can_scout:
          if messager: messager('Nothing to scout')
          return False
      elif actionstr[0] == 'Z':
        if actionstr[0:2] == 'Z--':
          if not self.acting_unit.can_rest():
            if messager: messager('  Not tired enough to rest')            
            return False
        elif actionstr[0:2] == 'Z2c':
          if not self.acting_unit.can_rest_with_cards():
            if messager: messager('  Not tired enough to rest with extra cards')            
            return False
      actionstr=actionstr[3:] 

    if messager: messager('  Action possible')
    return True
  
  def resolve(self):
    actionstr = self.effect
    while len(actionstr)>0:
      print("  Resolving actionstring ",actionstr)
      if actionstr[0] == 'A':
        # require active resistance:
        modifier = actionstr[1:3]
        # Reward: 1 for damage done and another 1 if target destroyed.
        reward, msg = self.gamestate.resistance.take_damage(self.acting_unit_type, modifier)
        self.player.get_cash(reward)
        self.acting_unit.tire()
        # Broadcast message:
        self.gamestate.broadcast(f"Unit {self.actor} (Player {self.player.number}/{self.player.name}) resolved action {self.name}: {msg}")
        return True
      if actionstr[0] == 'B':
        # require position of the acting unit to allow bypass
        modifier=actionstr[1:3]
        if modifier == '=1' or modifier == '=2':
          #print(f"check if {self.actor} < {int(modifier[1])}")
          if self.actor < int(modifier[1]):
            if messager: messager('  Cannot overtake')
            return False
        elif modifier == '-1':
          # If unit is last in convoy, it cannot reverse:
          if self.actor == len(self.convoy.units):
            if messager: messager('  Cannot reverse')
            return False
        else:
          raise ValueError(f'  Bad modifier for overtake action: {modifier}')
        self.actor
      if actionstr[0] == 'E':
        # escape!
        self.acting_unit.player.this_round_cash += sum(self.acting_unit.carry)
        self.convoy.units.pop(self.actor)
        self.gamestate.broadcast(f"Unit {self.actor} (Player {self.player.number}/{self.player.name}) escaped with {sum(self.acting_unit.carry)} worth loot")
        
      elif actionstr[0] == 'P':
        # Require pillage queue to have cards:
        mod = int(actionstr[2])
        if len(self.gamestate.pillage_queue.cards_and_visibilities) < mod:
          if messager: messager('  Nothing to pillage')
          return False
      elif actionstr[0] == 'S':
        # Scout action: Require something to be scoutable:
        can_scout = False
        for queue in [ self.gamestate.pillage_queue.cards_and_visibilities,
                       self.gamestate.mauling_queue.cards_and_visibilities,
                       self.gamestate.resistance_queue.cards_and_visibilities ]:
          if not can_scout:
            for card_and_vis in queue:
              if not card_and_vis[1]:
                can_scout=True
                break
        if not can_scout:
          if messager: messager('Nothing to scout')
          return False
      elif actionstr[0] == 'Z':
        if actionstr[0:2] == 'Z--':
          if not self.acting_unit.can_rest():
            if messager: messager('  Not tired enough to rest')            
            return False
        elif actionstr[0:2] == 'Z2c':
          if not self.acting_unit.can_rest_with_cards():
            if messager: messager('  Not tired enough to rest with extra cards')            
            return False
      actionstr=actionstr[3:] 



    return True

  def get_cost(self):
    cost = 0
    for c in self.cost:
      if c == 'T':
        # As many cards as acting unit has tired markers:
        cost += self.acting_unit.tired
      if c == 'U':
        # extra cost for being under the influence:
        if self.acting_unit.under_influence:
          cost += 1
      if c in '0123456789':
        cost += int(c)
    return cost
