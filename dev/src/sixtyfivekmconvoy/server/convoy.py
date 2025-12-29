#!/usr/bin/env python3

from .constants import *

from .unit import Unit, UnitType



class Convoy:
  base_units = {
    1:  Unit( player=1, unittype=UnitType.PANZER),
    2:  Unit( player=1, unittype=UnitType.INFANTRY),
    3:  Unit( player=1, unittype=UnitType.LOGISTICS),
    4:  Unit( player=2, unittype=UnitType.PANZER),
    5:  Unit( player=2, unittype=UnitType.INFANTRY),
    6:  Unit( player=2, unittype=UnitType.LOGISTICS),
    7:  Unit( player=3, unittype=UnitType.PANZER),
    8:  Unit( player=3, unittype=UnitType.INFANTRY),
    9:  Unit( player=3, unittype=UnitType.LOGISTICS),
    10:  Unit( player=4, unittype=UnitType.PANZER),
    11:  Unit( player=4, unittype=UnitType.INFANTRY),
    12:  Unit( player=4, unittype=UnitType.LOGISTICS),
    13:  Unit( player=5, unittype=UnitType.PANZER),
    14:  Unit( player=5, unittype=UnitType.INFANTRY),
    15:  Unit( player=5, unittype=UnitType.LOGISTICS),
  }

  def __init__(self, players, state=None):
    if state is None:
      num_players = len(players)
      num_units = num_players * 3
      self.units = [
        Convoy.base_units[i] for i in range(1,num_units+1)
      ]
      for u in self.units:
        u.player = players[u.player-1]
        u.convoy = self
    else:
      self.units = state

    self.current_actor = None


    #
    # Set the action zones according to number of players:
    #
    if num_players == 2:
      self.zones = {'A':[1], 'B': [2,3], 'C': [4,5], 'E': [-1]}
    elif num_players == 3:
      self.zones = {'A':[1,2], 'B': [3,4,5], 'C': [6,7], 'E': [-2,-1]}
    elif num_players == 4:
      self.zones = {'A':[1,2,3], 'B': [4,5,6], 'C': [7,8,9], 'E': [-3,-2,-1]}
    elif num_players == 5:
      self.zones = {'A':[1,2,3,4], 'B': [5,6,7,8], 'C': [9,10,11,12], 'E': [-3,-2,-1]}

    # The zone count of course should match with arrays starting from 0!

    for k,v in self.zones.items():
      self.zones[k] = [ v-1 for v in self.zones[k]]
                    
  def __str__(self):
    return '\n'.join([str(u) for u in self.units])

  def to_str(self, playerview=None):
    return '\n'.join([u.to_str(playerview=playerview) for u in self.units])

  def to_json(self, playerview=None):
    return [ u.to_json(playerview=playerview) for u in self.units ]

  #
  # Accessing unit position and unit itself:
  #
  
  def get_unit_position(self, unit):
    return self.units.index(unit)+1
  
  def get_unit_index(self, unit):
    return self.units.index(unit)  

  def get_unit_zone(self, unit):
    position = self.get_unit_position(unit)
    if position in [ len(self.units) + e for e in self.zones['E'] ]:
      return 'E'
    for zone in 'ABC':
      if position in self.zones[zone]:
        return zone
    raise NotImplementedError('Unit has no zone!')
  
  def get_unit_at(self, place):
    # Game uses indexing starting at 1;
    # Arrays use indexing starting at 0.
    return self.units[place-1]
  
  def get_units_in_zone(self, zone):
    assert( zone in 'ABCE')
    zone_units = [ u for u in self.zones[zone] if u < len(self.units) ]
    #return [self.units[u] for u in zone_units ]
    #list(range(1,len(self.units)+1))[u] for u in zone_units ]
    return [ self.get_unit_at(u) for u in zone_units ]


  #
  #   Apply damage to convoy:
  #
  #
                   
  def apply_damage(self, damage, cards=0, damage_for_not_discarding=1, unit=None, zone=None, attack_type=None):
    assert(unit is not None or zone is not None)
    msg = ''
    if zone is not None and unit is None:            
      # Apply damage to all unit is zone:
      print(self.get_units_in_zone(zone))
      for unit in self.get_units_in_zone(zone):
        msg += self.apply_damage(damage,
                                 cards=cards,
                                 damage_for_not_discarding=damage_for_not_discarding,
                                 unit=unit, attack_type=attack_type)
        
    elif zone is not None and unit is not None:
      units_in_zone = self.get_units_in_zone(zone)
      # In zone targeting, unit can be -2, -1, 1 or 2
      # These are mapped for zone size
      #        1   2   3   4 
      #      ----------------
      # -2   | 1   1   2   3
      # -1   | 1   2   3   4      
      #  1   | 1   1   1   1
      #  2   | 1   2   2   2
      while len(units_in_zone) < abs(unit):
        if unit < 0: unit +=1
        else: unit -= 1
      unit_in_zone = units_in_zone[unit]
      # TODO: Figure out what to do if zone C is empty!
      msg += self.apply_damage(damage,
                               cards=cards,
                               damage_for_not_discarding=damage_for_not_discarding,
                               unit=unit_in_zone,
                               attack_type=attack_type)
      
    else:

      
      # let's say target is index in unit list:
      if type(unit) == int:
        unit = self.get_unit_at(unit)
      elif type(unit) != Unit:
        raise ValueError("Target unit needs to be int or unit: Got "+type(unit))
      msg = ""
      # Is there a defender to lessen the damage?
      defend_soak=0
      for u in [unit] + unit.get_neighbours():
        if u.defending is not None and u.defending == attack_type:
          defend_soak +1
          u.reward_defending()

      if defend_soak > 0:
        if damage + cards <= defend_soak:
          msg = f"Defense soaks up all damage."
          return msg
        else:
          soaked_damage = 0
          soaked_cards = 0
          while damage > 0 and defend_soak > 0:
            damage -= 1
            soaked_damage += 1
          while cards > 0 and defend_soak > 0:
            cards -= 1
            soaked_cards += 1
          msg += f"Defense soaks {damage} damage and {cards} discards"
      
      new_unit_status = unit.apply_damage(damage, discards=cards,damage_for_not_discarding=damage_for_not_discarding)
      
      msg += f"Unit {unit} takes {damage} damage, player loses {cards} cards"
      if new_unit_status < 0:
        msg += " and is removed from convoy"
        self.units.pop( unit.index() )
      else:
        msg += f" and is left with {new_unit_status} capacity"
    return msg

  def gain_loot(self,unit,loot):
    player = self.units[unit].player
    if 'cash' in loot:
      player.get_cash(loot['cash'])
    if 'cards' in loot:
      if loot['cards'] > 0:
        player.get_cards(loots['cards'])
    # Deal damage first to see if there is a reason to discard:
    if 'damage' in loot:
      status = self.apply_damage(loot['damage'], unit=unit)
      if status < 0:
        return
    if 'discard' in loot:
        if player.can_discard(loot['discard']):
          player.discard[loot[cards]]
        else:
          status = self.apply_damage(loot['damage'], unit=unit)
    if status > 0:
      if 'stuff' in loot:
        self.units[unit].gain_loot(loot['stuff'])
    
  def state(self):
    state = []
    for u in self.units:
      unit_state = u.state()
      state.append(unit_state)
    for not_u in range(len(self.units), 15):
        state.append([0]*len(unit_state))
    return np.array(state)


  def move_resting_and_damaged_units(self):
    # Remove damaged units from the back of the queue:
    removed_units = []
    for e,u in reversed(list(enumerate(self.units))):
      if u.is_damaged():
        removed_units.append(self.units.pop(e))
      else:
        break
    
    # Collect damaged units to the back of the queue:
    damaged_units = []
    for e,u in enumerate(self.units):
      if u.is_damaged():
        damaged_units.append(self.units.pop(e))

    # two player game, resting units move back 2 spaces
    # keeping their order:
    # 1R  2N  3R  4R  5R => 2N 1R 3R 4R 5R
    # 3.5  2 5.5 6.5 7.5
    # 1R  2N 3N  4R  5N => 
    # 3.5  2  3 6.5 7.5
    new_order = {}
    for i,u in enumerate(self.units):
      if u.is_resting():
        new_order[i + len(self.players) + 0.5]=u
      else:
        new_order[i] = u

    self.units = [ u for i,u in sorted(new_order.items()) ]
    
    # Add damaged units to the back of the convoy:
    self.units = self.units + damaged_units
    
    # Move resting units back as many places as there are players:
        
    return True

  #def resolve_action(self, unitnumber, actionstr, second=False):
  #  unit = self.units[unitnumber]

  def move_unit(self, position, move):
    new_position=position - move

    # Simple but I'm writing it down:
    # convoy is: 0 1 2 3 4
    # move 2 forward:
    # pop item at 2:  0 1 3 4 then insert item at 2-1: 0 2 1 3 4
    # move 2 backward:
    # pop item at 2:  0 1 3 4 then insert item at 2+1: 0 1 3 2 4
    moving_unit = self.units.pop(position)
    self.units.insert(new_position, moving_unit)
    return new_position
  
  def resolve_action(self, action, second=False):

    if action is None:
      #print(f"{self.units[self.current_actor].to_str()} becomes frustrated")
      self.units[self.current_actor].become_frustrated()
      self.set_next_actor()
      return True


    #print("Resolve action", action.name, "for unit", action.actor)
    

    # We know the action was possible since is was vetted before;

    action_cost = action.cost
    #print(f"  Action cost {action_cost}")
    if action_cost > 0:
      if action_cost == len(action.acting_unit.player.action_cards):
        # Discard all cards to play the action:
        action.acting_unit.player.discard(action.gamestate.action_deck,
                                          action.acting_unit.player.action_cards)
      else:
        description=f'Choose {action_cost} action cards to discard for action {action.name}'
        for c in action.acting_unit.player.action_cards:
          card_desc = action.gamestate.action_deck.describe(c)
          # card_desc is a list of action dictionaries when using action_deck
          if isinstance(card_desc, list):
            description+= f'\n  {c}: '+ '/'.join([f['name'] for f in card_desc if isinstance(f, dict) and 'name' in f])
          elif isinstance(card_desc, dict) and 'name' in card_desc:
            # Single action dictionary
            description+= f'\n  {c}: {card_desc["name"]}'
          else:
            description+= f'\n  {c}: {str(card_desc)}'
        choicetaken = action.gamestate.demand_choice(action.acting_unit.player,
                                           action.gamestate.choose_cards_to_discard,
                                           action.acting_unit.player.action_cards,
                                           description=description,
                                           num_choices=action_cost)
        action.acting_unit.player.discard(action.gamestate.action_deck,
                                          choicetaken)

    # Cost has been paid, it's time to resolve:
    action.resolve()
        
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
    # while len(actionstr)>0:
    #   if actionstr[0] == 'A':
    #     unit.resolve_attack(modifier=actionstr[1:3])
    #   if actionstr[0] == 'B':
    #     unit.resolve_bypass(modifier=actionstr[1:3])
    #   elif actionstr[0] == 'P':
    #     unit.resolve_pillage(modifier=actionstr[1:3])
    #   elif actionstr[0] == 'R':
    #     unit.resolve_reverse(modifier=actionstr[1:3])
    #   elif actionstr[0] == 'S':
    #     unit.resolve_scout(modifier=actionstr[1:3])
    #   elif actionstr[0] == 'Z':
    #     unit.resolve_rest(modifier=actionstr[1:3])
    #   elif actionstr[0] == 'D':
    #     unit.resolve_defend(modifier=actionstr[1:3])
    #   actionstr=actionstr[3:] 
        
    # Action resolved, now take set the next unit in convoy to
    # be active.
    self.set_next_actor()

  def set_next_actor(self):
    set_next_actor = None
    
    # Was the next actor specified in the action taken?
    if set_next_actor:
      self.current_actor = set_next_actor
    else:
      self.current_actor = None
      # Check from the beginning which unit is the first one not
      # to have taken action:
      for i,u in enumerate(self.units):
        if u.actiontaken is None:
          self.current_actor = i
          break
      # If all units have acted, check if there is a second round
      # of actions:
      if self.current_actor is None:
        for i,u in enumerate(self.units):
          if u.secondactioncard is not None and u.secondactiontaken is None:
            self.current_actor = i
            break
