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
          modifier=int(modifier[1])
        elif modifier[0] == '-':
          modifier=int(modifier)  
        else:
          raise ValueError(f'  Bad modifier for overtake action: {modifier}')
        if not self.acting_unit.can_overtake(modifier, messager):
          return False
                           
      elif actionstr[0] == 'P':
        # Require pillage queue to have cards:
        print("CHECKING PILLAGE POSSIBLE:", len(self.gamestate.pillage_queue.cards_and_visibilities))
        mod = int(actionstr[2])        
        if len(self.gamestate.pillage_queue.cards_and_visibilities) < 1:
          if messager: messager('  Nothing to pillage')
          return False
                           
      elif actionstr[0] == 'S':
        # Scout action: Require something to be scoutable:
        can_scout = any([
          self.gamestate.pillage_queue.contains_hidden_cards(),
          self.gamestate.mauling_queue.contains_hidden_cards(),
          self.gamestate.resistance_queue.contains_hidden_cards() ])
        
        if not can_scout:
          if messager: messager('Nothing to scout')
          print("could not scout")
          return False
        else:
          print("could scout")
          
      elif actionstr[0] == 'Z':
        if actionstr[0:3] == 'Z=0':
          if not self.acting_unit.can_rest():
            if messager: messager('  Not tired enough to rest')            
            return False
        elif actionstr[0:3] == 'Z=2':
          if not self.acting_unit.can_rest_with_cards():
            if messager: messager('  Not tired enough to rest with extra cards')            
            return False
        else:
          print(f"WARNING: bad options for rest {actionstr[0:3]}")
          
      actionstr=actionstr[3:] 

    if messager: messager('  Action possible')
    return True
  
  def resolve(self, messager=None):
    actionstr = self.effect
    resolve_arr = [f'Unit {self.actor} (Player {self.player.number}/{self.player.name}) resolved action {self.name}:']
    while len(actionstr)>0:
      #print("  Resolving actionstring ",actionstr)      
      if actionstr[0] == 'A':
        # require active resistance:
        modifier = actionstr[1:3]
        # Reward: 1 for damage done and another 1 if target destroyed.
        reward, msg = self.gamestate.resistance.take_damage(self.acting_unit_type, modifier)
        self.player.get_cash(reward)
        self.acting_unit.tire()
        resolve_arr.append(f"{msg}")
        #return True
      elif actionstr[0] == 'B':
        # require position of the acting unit to allow bypass
        modifier=actionstr[1:3]
        if modifier == '=1' or modifier == '=2':
          #print(f"check if {self.actor} < {int(modifier[1])}")
          move=int(modifier[1])
          if self.actor < int(modifier[1]):
            if messager: messager('  Cannot overtake')
            return False
        elif modifier == '-1':
          # If unit is last in convoy, it cannot reverse:
          move=int(modifier)
          if self.actor == len(self.convoy.units):
            if messager: messager('  Cannot reverse')
            return False
        else:
          raise ValueError(f'  Bad modifier for overtake action: {modifier}')
        old_position=self.actor

        new_position = self.convoy.move_unit(self.actor, move)
        resolve_arr.append(f"overtook from position {old_position} to position {new_position}")

        
      elif actionstr[0] == 'E':
        # escape!
        self.acting_unit.player.this_round_cash += sum(self.acting_unit.carry)
        self.convoy.units.pop(self.actor)
        resolve_arr.append(f"escaped with {sum(self.acting_unit.carry)} worth loot")
        
      elif actionstr[0] == 'P':
        
        # Require pillage queue to have cards:
        if actionstr[1] in ['+', '-']:
          mod = int(actionstr[2]) 
        else:
          mod = 1
        if len(self.gamestate.pillage_queue.cards_and_visibilities) < 2 + mod:
          if messager: messager('  Not enough to pillage')
          return False
        rewards = self.resolve_pillage(self.acting_unit, mod)
        for r in rewards:
          self.acting_unit.player.this_round_cash += r['reward']['cash']
          self.acting_unit.gain_loot(r['reward']['loot'])
          self.acting_unit.gain_atrocities(r['reward']['atrocities'])
          resolve_arr.append(f"pillaged {r['name']} and gained {r['reward']['cash']} cash and {r['reward']['loot']} loot while committing {r['reward']['atrocities']} atrocities.")

      elif actionstr[0] == 'S':
        # Scout action: Require something to be scoutable:
        can_scout = any( [
          self.gamestate.pillage_queue.contains_hidden_cards(),
          self.gamestate.mauling_queue.contains_hidden_cards(),
          self.gamestate.resistance_queue.contains_hidden_cards() ] )
        if not can_scout:
          if messager: messager('Nothing to scout')
          return False

        print("WARNING: scouting implementation is not finished yet")
        modifier=actionstr[1:3]

        # restriction can be "M" for mauling, "R" for resistance, "P" for pillage, "E" for everything
        restrictions=modifier[0]
        count=modifier[1]
        scouted = self.resolve_scout( restrictions, count )
        resolve_arr = []
        
        
        
      elif actionstr[0] == 'D':
        modifier=actionstr[1:3]
        defense_type = modifier[0]
         self.acting_unit.resolve_defend(defense_type)
        
      elif actionstr[0] == 'W':
        # You can always wait as your first action!
        dummy=1
      
      elif actionstr[0] == 'O':
        # Ordering requires neighbouring unit to be waiting:
        print("WARNING: ordering not yet implemented")
        # or the following unit's orders to be unknown!
        
      elif actionstr[0] == 'Z':
        if actionstr[0:3] == 'Z=0':
          if not self.acting_unit.can_rest():
            if messager: messager('  Not tired enough to rest')            
            return False
          u = self.acting_unit.under_influence
          old_t = self.acting_unit.tired
          self.acting_unit.rest()
          new_t = self.acting_unit.tired
          if u:
            resolve_arr.append(f"resting (No longer under influence)")
          else:
            resolve_arr.append(f"resting (from {old_t} to {new_t})")
        elif actionstr[0:3] == 'Z=2':
          if not self.acting_unit.can_rest_with_cards():
            if messager: messager('  Not tired enough to rest with extra cards')            
            return False
          old_t = self.acting_unit.tired
          self.acting_unit.rest_with_cards()
          new_t = self.acting_unit.tired
          resolve_arr.append(f"resting (from {old_t} to {new_t})")
        else:
          print(f"WARNING: Rest {actionstr[0:3]} not implemented") 
      else:
        print(f"WARNING: Action {actionstr[0:3]} not implemented") 
      actionstr=actionstr[3:]
      #if len(actionstr)> 0:
        #print(actionstr)
        #breakpoint()

    # Broadcast message:
    self.gamestate.broadcast(','.join(resolve_arr))

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



  def resolve_pillage(self, acting_unit, modifier=0):
    # in basic case, show player 2 cards to choose from.
    
    # Draw two + modifier cards from pillage deck:
    
    count = 2+modifier
    pillage_cards = []
    for c in range(count):
      pillage_cards.append(        
        self.gamestate.pillage_queue.remove_card(0)
      )

    

    if len(pillage_cards) == 0:
      raise(ValueError, 'No pillage cards for pillage action, some check has failed!')
    description='Choose one pillage card:'  
    for pc, vis in pillage_cards:
      #  print(self.action_deck.describe(c))
      #breakpoint()
      description+= f'\n  {pc}: {self.gamestate.pillage_deck.describe(pc)}'
    choicetaken = self.gamestate.demand_choice(self.acting_unit.player,
                                       self.gamestate.choose_pillage_card_choice_type,
                                       pillage_cards,
                                       description=description,
                                       num_choices=1)


    pillaged = choicetaken
    for p in pillaged:
      pillage_cards.remove(p)
    
    for pc in pillage_cards:
      self.gamestate.pillage_queue.return_card( pc[0], visible=pc[1] )
    
    return [self.gamestate.pillage_deck.describe(p) for p,vis in pillaged]
  

  def resolve_scout(self, restrictions, count):

    scouted = []
    
    if restrictions != "E":
      raise NotImplementedError("Only unrestricted scouting implemented for now!")

    for c in range(int(count)):
      description = "Choose card deck to scout:"
      options = []
      for card_and_vis in self.gamestate.pillage_queue.cards_and_visibilities:
        if not card_and_vis[1]:
          options.append(0)
          description+= f'\n  0: pillage'
          break
      for card_and_vis in self.gamestate.mauling_queue.cards_and_visibilities:
        if not card_and_vis[1]:
          options.append(1)
          description+= f'\n  1: mauling'
          break

      for card_and_vis in self.gamestate.resistance_queue.cards_and_visibilities:
        if not card_and_vis[1]:
          options.append(2)
          description+= f'\n  2: resistance'
          break

      if len(options) > 1: 
        choicetaken = self.gamestate.demand_choice(self.acting_unit.player,
                                                   self.gamestate.choose_queue_to_scout_choice_type,
                                                   options,
                                                   description=description,
                                                   num_choices=1)
      else:
        choicetaken=options

      if choicetaken[0] == 0:
        print("revealing pillage")
        self.gamestate.pillage_queue.reveal_next_hidden()
      elif choicetaken[0] == 1:
        print("revealing mauling")
        self.gamestate.mauling_queue.reveal_next_hidden()
      elif choicetaken[0] == 2:
        print("revealing resistance")
        self.gamestate.resistance_queue.reveal_next_hidden()

      
            
      scouted.append(choicetaken)

    return scouted
