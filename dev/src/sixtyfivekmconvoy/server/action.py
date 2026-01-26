#!/usr/bin/env python3

from .constants import ActionName
from .card_deck_officers import OfficerCardDeck, OfficerCard
from .unit import Unit

# Player color mapping for broadcasts
PLAYER_COLORS = ['red', 'green', 'blue', 'orange', 'purple']

def get_player_color(player_number):
    """Get color name for a player number."""
    if 0 <= player_number < len(PLAYER_COLORS):
        return PLAYER_COLORS[player_number]
    return 'unknown'

class Action:

  def __init__(self, gamestate, convoy, actor, action, cardnumber, action_index=None):
    self.gamestate = gamestate
    self.convoy = convoy
    self.actor = actor
    self.player = self.convoy.units[self.actor].player
    self.cardnumber = cardnumber
    self.acting_unit = self.convoy.units[self.actor]
    self.acting_unit_type = self.acting_unit.type_to_str[self.acting_unit.unittype][0]
    self.player = self.acting_unit.player
    self.action_index = action_index  # Store the action index for this action (used by WAIT action)
    
    # New format: action_name, action_modifier, zone, tire, intoxicate
    if 'action_name' in action:
      self.action_name = action['action_name']
      self.action_modifier = action['action_modifier']  # Numeric value
      self.zone = action.get('zone', '')
      self.tire = action.get('tire', 0)
      self.intoxicate = action.get('intoxicate', 0)
    # Backward compatibility: old format
    elif 'actions' in action:
      # Old format: list of (action_type, modifier) tuples
      # Convert to new format (take first action)
      if len(action['actions']) > 0:
        old_action_type, old_modifier = action['actions'][0]
        # Map old ActionType to new ActionName (this is a transition helper)
        # For now, we'll assume it's already normalized
        self.action_name = old_action_type if isinstance(old_action_type, str) else ActionName.normalize(str(old_action_type))
        # Convert modifier string to numeric
        if isinstance(old_modifier, str):
          if old_modifier.startswith('='):
            self.action_modifier = int(old_modifier[1:])
          elif old_modifier.startswith('+'):
            self.action_modifier = int(old_modifier[1:])
          elif old_modifier.startswith('-'):
            self.action_modifier = int(old_modifier)
          else:
            self.action_modifier = 0
        else:
          self.action_modifier = old_modifier
      else:
        raise ValueError("Actions list is empty")
      self.zone = action.get('zone', '')
      self.tire = action.get('tire', 0)
      self.intoxicate = action.get('intoxicate', 0)
    else:
      raise ValueError("Action must have 'action_name' or 'actions' field")
    
    self.cost = action['cost']
    self.limits = action['limits']
    self.name = action['name']

    self.possible = self.is_possible()
    self.cost = self.get_cost()
    
  def is_possible(self, messager=None):
    
    if messager: messager(f'  Check if action {self.name} is possible')
    
    # (1) Does the player have enough cards to pay for the action?
    required_cards = self.get_cost()
    if len(self.acting_unit.player.action_cards) < required_cards:
      if messager: messager(f'  Not enough cards to pay for action, requires {required_cards} but player has {len(self.acting_unit.player.action_cards)}')
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
    action_name_lower = self.action_name.lower()
    
    if action_name_lower == ActionName.ATTACK:
      # require active resistance:
      if not self.gamestate.resistance.active:
        if messager: messager('  No target for attack')
        return False
        
    elif action_name_lower == ActionName.ASSAULT:
      # Assault is similar to attack
      if not self.gamestate.resistance.active:
        if messager: messager('  No target for assault')
        return False
        
    elif action_name_lower == ActionName.BYPASS:
      # require position of the acting unit to allow bypass
      # Modifier is numeric, positive = forward, negative = backward
      if not self.acting_unit.can_overtake(self.action_modifier, messager):
        return False

                        
    elif action_name_lower == ActionName.PILLAGE:
      # Require pillage queue to have cards:
      # Modifier is extra cards (numeric)
      if len(self.gamestate.pillage_queue.cards_and_visibilities) < 1:
        if messager: messager('  Nothing to pillage')
        return False
                        
    elif action_name_lower == ActionName.SCOUT:
      # Scout action: Require something to be scoutable:
      can_scout = any([
        self.gamestate.pillage_queue.contains_hidden_cards(),
        self.gamestate.mauling_queue.contains_hidden_cards(),
        self.gamestate.resistance_queue.contains_hidden_cards()])
      
      if not can_scout:
        if messager: messager('Nothing to scout')
        return False
        
    elif action_name_lower == ActionName.SEARCH:
      # Search action: Require something to be scoutable (similar to scout)
      can_search = any([
        self.gamestate.pillage_queue.contains_hidden_cards(),
        self.gamestate.mauling_queue.contains_hidden_cards(),
        self.gamestate.resistance_queue.contains_hidden_cards()])
      
      if not can_search:
        if messager: messager('Nothing to search')
        return False
        
    elif action_name_lower == ActionName.PATROL:
      # Patrol action: Require something to be scoutable (similar to scout)
      can_patrol = any([
        self.gamestate.pillage_queue.contains_hidden_cards(),
        self.gamestate.mauling_queue.contains_hidden_cards(),
        self.gamestate.resistance_queue.contains_hidden_cards()])
      
      if not can_patrol:
        if messager: messager('Nothing to patrol')
        return False
          
    elif action_name_lower == ActionName.REST:
      # Modifier: 0 = basic rest, 2 = rest with cards
      if self.action_modifier == 0:
        if not self.acting_unit.can_rest():
          if messager: messager('  Not tired enough to rest')
          return False
      elif self.action_modifier == 2:
        if not self.acting_unit.can_rest_with_cards():
          if messager: messager('  Not tired enough to rest with extra cards')
          return False
      else:
        print(f"WARNING: bad modifier for rest {self.action_modifier}")

    elif action_name_lower == ActionName.ASSAULT:
      # Assault is a combination of bypass by one and attack
      if not self.acting_unit.can_overtake(1, messager):
        if messager: messager('  Not enough space to assault')
        return False
      if not self.gamestate.resistance.active:
        if messager: messager('  No target for assault')
        return False

    elif action_name_lower == ActionName.RETREAT:
      # Retreat is a combination of bypass backwards by one and attack
      if not self.acting_unit.can_overtake(-1, messager):
        if messager: messager('  Not enough space to retreat')
        return False
      if not self.gamestate.resistance.active:
        if messager: messager('  No target for retreat')
        return False

    elif action_name_lower == ActionName.SERVICE:
      # Service action: require neighbouring unit to be tired
      preceding_unit, following_unit = self.acting_unit.get_neighbours()
      if (preceding_unit is None or preceding_unit.tired == 0) and (following_unit is None or following_unit.tired == 0):
        if messager: messager('  No neighbouring units in need of service')
        return False

    elif action_name_lower == ActionName.DEFEND:
      # you can always defend
      pass
    elif action_name_lower == ActionName.PROMOTE:
      # you can always promote
      pass
    elif action_name_lower == ActionName.SOBER_UP:
      # Sober up requires Officer 1
      if not self._has_officer('sober_up'):
        if messager: messager('  No sober up officer available')
        return False
      if self.acting_unit.under_influence == 0:
        if messager: messager('  Unit is not under influence')
        return False
    elif action_name_lower == ActionName.ORDER:
      # you can always try to order (unless you're the last in the convoy)
      if self.actor == len(self.convoy.units) - 1:
        if messager: messager('  You are the last unit in the convoy, you cannot order')
        return False
    elif action_name_lower == ActionName.WAIT:
      # you can always wait
      pass
    if messager: messager('  Action possible')
    return True
  
  def resolve(self, messager=None):
    # Get unit type string (lowercase: pnz, inf, log)
    unit_type_str = Unit.type_to_str.get(self.acting_unit.unittype, 'unknown').lower()
    # Get player color
    player_color = get_player_color(self.player.number)
    resolve_arr = [f'Unit {self.actor} {player_color} {unit_type_str} resolved card ${self.cardnumber} action {self.name}:']
    action_name_lower = self.action_name.lower()
    
    if action_name_lower == ActionName.ATTACK:
      # Reward: 1 for damage done and another 1 if target destroyed.
      # Convert numeric modifier to string format for take_damage (which expects '=N' format)
      # User said modifiers act as "=" (fixed value), so use '=N' format
      damage_modifier = self.action_modifier
      
      # Check for Officer 2 (enhanced attack)
      officer2 = self._has_officer('enhanced_attack')
      if officer2:
        description = f"Use {officer2.name} for +3 damage (but unit takes 1 damage)? 0: No, 1: Yes"
        choicetaken = self.gamestate.demand_choice(self.acting_unit.player,
                                                   self.gamestate.choose_cards_to_discard,
                                                   [0, 1],
                                                   description=description,
                                                   num_choices=1)
        if choicetaken[0] == 1:
          damage_modifier += 3
          self._discard_officer(officer2)
          # Unit takes 1 damage
          if len(self.acting_unit.carry) > 0:
            self.acting_unit.carry.pop()
          resolve_arr.append(f"used {officer2.name}: +3 damage but unit took 1 damage")
      
      modifier_str = f'={damage_modifier}'
      # Calculate actual damage before applying
      if isinstance(modifier_str, int):
        actual_damage = modifier_str
      elif modifier_str.startswith('='):
        actual_damage = int(modifier_str[1:])
      elif modifier_str.startswith('+'):
        actual_damage = self.gamestate.resistance.damage_from_convoy[self.acting_unit_type] + int(modifier_str[1:])
      elif modifier_str.startswith('-'):
        actual_damage = self.gamestate.resistance.damage_from_convoy[self.acting_unit_type] - int(modifier_str[1:])
      else:
        actual_damage = int(modifier_str) if modifier_str.isdigit() else damage_modifier
      
      result = self.gamestate.resistance.take_damage(self.acting_unit_type, modifier_str)
      if isinstance(result, tuple):
        reward, msg = result
      else:
        reward = result
        msg = f'Resistance took {damage_modifier} damage'
      # Track actual resistance damage
      if actual_damage > 0:
        self.gamestate.round_resistance_damage += actual_damage
      self.player.get_cash(reward)
      resolve_arr.append(f"{msg}")
      
    elif action_name_lower == ActionName.ASSAULT:
      # Assault is a combination of bypass by one and attack
      old_position = self.actor
      new_position = self.convoy.move_unit(self.actor, 1)
      resolve_arr.append(f"overtook from position {old_position} to position {new_position}")
      modifier_str = f'={self.action_modifier}'
      result = self.gamestate.resistance.take_damage(self.acting_unit_type, modifier_str)
      if isinstance(result, tuple):
        reward, msg = result
      else:
        reward = result
        msg = f'Resistance took {self.action_modifier} damage from assault'
      self.player.get_cash(reward)
      resolve_arr.append(f"{msg}")

    elif action_name_lower == ActionName.RETREAT:
      # Retreat is a combination of bypass backwards by one and attack
      old_position = self.actor
      new_position = self.convoy.move_unit(self.actor, -1)
      resolve_arr.append(f"overtook from position {old_position} to position {new_position}")
      result = self.gamestate.resistance.take_damage(self.acting_unit_type, self.action_modifier)
      if isinstance(result, tuple):
        reward, msg = result
      else:
        reward = result
        msg = f'Resistance took {self.action_modifier} damage from retreat'
      self.player.get_cash(reward)
      resolve_arr.append(f"{msg}")

    elif action_name_lower == ActionName.BYPASS:
      # Modifier is numeric: positive = forward, negative = backward
      old_position = self.actor
      new_position = self.convoy.move_unit(self.actor, self.action_modifier)
      resolve_arr.append(f"overtook from position {old_position} to position {new_position}")
        
    elif action_name_lower == ActionName.EXIT:
      # Exit (escape): unit leaves convoy
      self.acting_unit.player.this_round_cash += sum(self.acting_unit.carry)
      self.convoy.units.pop(self.actor)
      resolve_arr.append(f"exited with {sum(self.acting_unit.carry)} worth loot")
      
    elif action_name_lower == ActionName.PILLAGE:
      # Modifier is extra cards (numeric)
      if len(self.gamestate.pillage_queue.cards_and_visibilities) < 2 + self.action_modifier:
        if messager: messager('  Not enough to pillage')
        return False
      rewards = self.resolve_pillage(self.acting_unit, self.action_modifier)
      total_atrocities = 0
      for r in rewards:
        self.acting_unit.player.this_round_cash += r['reward']['cash']
        self.acting_unit.gain_loot(r['reward']['loot'])
        self.acting_unit.gain_atrocities(r['reward']['atrocities'])
        total_atrocities += r['reward']['atrocities']
        resolve_arr.append(f"pillaged {r['name']} and gained {r['reward']['cash']} cash and {r['reward']['loot']} loot while committing {r['reward']['atrocities']} atrocities.")
      
      # Check for Officer 4 (atrocity conversion) after pillage
      officer4 = self._has_officer('atrocity_conversion')
      if officer4 and total_atrocities > 0 and self.acting_unit.atrocities > 0:
        description = f"Use {officer4.name} to convert 1 atrocity to 1 cash? 0: No, 1: Yes"
        choicetaken = self.gamestate.demand_choice(self.acting_unit.player,
                                                   self.gamestate.choose_cards_to_discard,
                                                   [0, 1],
                                                   description=description,
                                                   num_choices=1)
        if choicetaken[0] == 1:
          self.acting_unit.atrocities -= 1
          self.acting_unit.player.this_round_cash += 1
          self._discard_officer(officer4)
          resolve_arr.append(f"used {officer4.name}: converted 1 atrocity to 1 cash")

    elif action_name_lower == ActionName.SCOUT:
      # Scout action: modifier is count (numeric)
      print("WARNING: scouting implementation is not finished yet")
      restrictions = 'E'  # Default to everything
      count = self.action_modifier if self.action_modifier > 0 else 2
      scouted = self.resolve_scout(restrictions, count)
      resolve_arr = []
      
    elif action_name_lower == ActionName.SEARCH:
      # Search action: similar to scout
      print("WARNING: search implementation is not finished yet")
      restrictions = 'E'  # Default to everything
      count = self.action_modifier if self.action_modifier > 0 else 2
      scouted = self.resolve_scout(restrictions, count)
      resolve_arr = []
      
      # Check for Officer 3 (search + pillage combo)
      officer3 = self._has_officer('search_pillage_combo')
      if officer3:
        description = f"Use {officer3.name} to also pillage after search? 0: No, 1: Yes"
        choicetaken = self.gamestate.demand_choice(self.acting_unit.player,
                                                   self.gamestate.choose_cards_to_discard,
                                                   [0, 1],
                                                   description=description,
                                                   num_choices=1)
        if choicetaken[0] == 1:
          # Perform pillage
          if len(self.gamestate.pillage_queue.cards_and_visibilities) >= 2:
            rewards = self.resolve_pillage(self.acting_unit, 0)
            for r in rewards:
              self.acting_unit.player.this_round_cash += r['reward']['cash']
              self.acting_unit.gain_loot(r['reward']['loot'])
              self.acting_unit.gain_atrocities(r['reward']['atrocities'])
              resolve_arr.append(f"also pillaged {r['name']} and gained {r['reward']['cash']} cash and {r['reward']['loot']} loot while committing {r['reward']['atrocities']} atrocities.")
            self._discard_officer(officer3)
            resolve_arr.append(f"used {officer3.name}: combined search with pillage")
      
    elif action_name_lower == ActionName.PATROL:
      # Patrol action: similar to scout
      print("WARNING: patrol implementation is not finished yet")
      restrictions = 'E'  # Default to everything
      count = self.action_modifier if self.action_modifier > 0 else 2
      scouted = self.resolve_scout(restrictions, count)
      resolve_arr = []
      
    elif action_name_lower == ActionName.DEFEND:
      # Defend: modifier is defense type (numeric, but we'll need to map it)
      # For now, assume modifier 1 means basic defend
      defense_type = 'S'  # Default
      defense_reward = '_'
      self.acting_unit.resolve_defend(defense_type, defense_reward)
      
    elif action_name_lower == ActionName.WAIT:
      # Wait: player chooses a new action card to append to unit's actioncard list
      if not self.acting_unit.player.action_cards:
        if messager: messager('  No action cards available to wait with')
        return False
      
      # Let player choose an action card
      description = 'Choose an action card to add to this unit (WAIT action):'
      for c in self.acting_unit.player.action_cards:
        card_desc = self.acting_unit.player.action_deck.describe(c)
        if isinstance(card_desc, list):
          description += f'\n  {c}: ' + '/'.join([f['name'] for f in card_desc if isinstance(f, dict) and 'name' in f])
        elif isinstance(card_desc, dict) and 'name' in card_desc:
          description += f'\n  {c}: {card_desc["name"]}'
        else:
          description += f'\n  {c}: {str(card_desc)}'
      
      choicetaken = self.gamestate.demand_choice(
        self.acting_unit.player,
        self.gamestate.choose_card_choice_type,
        self.acting_unit.player.action_cards,
        description=description,
        num_choices=1
      )
      
      chosen_card = choicetaken[0]
      # Append the chosen card to the unit's actioncard list
      self.acting_unit.actioncard.append(chosen_card)
      self.acting_unit.actiontaken.append(None)  # Will be set when this action is resolved
      self.acting_unit.player.place_action_card(chosen_card)
      
      resolve_arr.append(f"waited and added card ${chosen_card} to action queue")
      
    elif action_name_lower == ActionName.SOBER_UP:
      # Sober up: remove under_influence (requires Officer 1)
      officer1 = self._has_officer('sober_up')
      if not officer1:
        if messager: messager('  No sober up officer available')
        return False
      self.acting_unit.under_influence = 0
      self._discard_officer(officer1)
      resolve_arr.append(f"used {officer1.name}: removed under_influence condition")

    elif action_name_lower == ActionName.PROMOTE:
      # Promote: let player choose which officer to attach from the officer queue
      officer_queue = self.gamestate.officer_queue
      if len(officer_queue.cards_and_visibilities) == 0:
        if messager: messager('  No officers available in the officer queue')
        return
      
      # Build list of available officer indices and descriptions
      available_indices = list(range(len(officer_queue.cards_and_visibilities)))
      description = "Choose an officer from the queue to promote this unit:"
      for index in available_indices:
        officer_id, visibility = officer_queue.cards_and_visibilities[index]
        officer = OfficerCardDeck.deck[officer_id]
        desc_parts = []
        if officer.passive_description:
          desc_parts.append(f"Passive: {officer.passive_description}")
        if officer.discard_description:
          desc_parts.append(f"Discard: {officer.discard_description}")
        desc_text = ' | '.join(desc_parts) if desc_parts else ''
        description += f'\n  {index}: {officer.name}'
        if desc_text:
          description += f' - {desc_text}'
      
      choicetaken = self.gamestate.demand_choice(self.acting_unit.player,
                                                 self.gamestate.choose_cards_to_discard,  # Reuse choice type
                                                 available_indices,
                                                 description=description,
                                                 num_choices=1)
      # Get the selected officer from the queue and remove it
      selected_index = choicetaken[0]

      officer_description = officer_queue.describe(selected_index)
      officer = OfficerCard(**officer_description)

      officer_queue.remove_card(selected_index)
      
      # Attach officer to unit
      self.acting_unit.officers.append(officer)
      
      desc_parts = []
      if officer.passive_description:
        desc_parts.append(f"Passive: {officer.passive_description}")
      if officer.discard_description:
        desc_parts.append(f"Discard: {officer.discard_description}")
      desc_text = ' | '.join(desc_parts) if desc_parts else ''
      resolve_arr.append(f"promoted unit with {officer.name}" + (f": {desc_text}" if desc_text else ""))

    elif action_name_lower == ActionName.SERVICE:
      resolve_arr.append(self.resolve_service())
      
    elif action_name_lower == ActionName.ORDER:
      # Ordering requires neighbouring unit to be waiting:
      print("WARNING: ordering not yet implemented")
      
    elif action_name_lower == ActionName.REST:
      if self.action_modifier == 0:
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
      elif self.action_modifier == 2:
        if not self.acting_unit.can_rest_with_cards():
          if messager: messager('  Not tired enough to rest with extra cards')
          return False
        old_t = self.acting_unit.tired
        self.acting_unit.rest_with_cards()
        new_t = self.acting_unit.tired
        resolve_arr.append(f"resting (from {old_t} to {new_t})")
      else:
        print(f"WARNING: Rest modifier {self.action_modifier} not implemented")
    else:
      print(f"WARNING: Action {self.action_name} not implemented")

    # Apply tire and intoxicate effects after action resolution
    if self.tire:
      self.acting_unit.tire()
    if self.intoxicate:
      self.acting_unit.under_influence = 1

    # Broadcast message:
    # Collect action summary instead of broadcasting immediately
    action_summary = ','.join(resolve_arr)
    self.gamestate.round_action_summaries.append(action_summary)

    return True

  def get_cost(self):
    if self.cost == 'T':
      # Cost is sum of tiredness and under_influence
      return self.acting_unit.tired + (1 if self.acting_unit.under_influence else 0)
    else:
      # Numeric cost
      return int(self.cost)



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
        choicetaken = options if options else [0]  # Default to 0 if no options

      if choicetaken and len(choicetaken) > 0 and choicetaken[0] == 0:
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

  def _has_officer(self, effect_type, effect_kind='discard_effect'):
    """
    Check if the acting unit has an officer with the given effect type.
    
    Args:
        effect_type: the effect type to search for (string)
        effect_kind: either 'passive_effect' or 'discard_effect' (default: 'discard_effect')
    
    Returns:
        The officer card if found, None otherwise
    """
    for officer in self.acting_unit.officers:
      if effect_kind == 'passive_effect' and officer.passive_effect == effect_type:
        return officer
      elif effect_kind == 'discard_effect' and officer.discard_effect == effect_type:
        return officer
    return None
  
  def _discard_officer(self, officer):
    """Discard an officer from the acting unit."""
    if officer in self.acting_unit.officers:
      self.acting_unit.officers.remove(officer)
      return True
    return False

  def resolve_service(self, modifier=1):
    # service action removes one point of tiredness from a neighbouring unit

    # get neighbouring units:
    preceding_unit, following_unit = self.acting_unit.get_neighbours()


    # check if they can be serviced:
    if preceding_unit is not None and preceding_unit.tired > 0 and following_unit is not None and following_unit.tired > 0:
      choice = self.gamestate.demand_choice(self.acting_unit.player,
                                            self.gamestate.choose_service_choice_type,
                                            [0, 1],
                                            description=f"Choose neighbouring unit to service: 0 for preceding, 1 for following",
                                            num_choices=1)

      if choice[0] == 0:
        neighbouring_unit = preceding_unit
      else:
        neighbouring_unit = following_unit
    else:
      if preceding_unit.tired > 0:
        neighbouring_unit = preceding_unit
      else:
        neighbouring_unit = following_unit

    neighbouring_unit.tired -= min(modifier, neighbouring_unit.tired)

    return f"unit {self.actor} (player {self.player.number}/{self.player.name}) serviced neighbouring unit {neighbouring_unit.index()} (player {neighbouring_unit.player.number}/{neighbouring_unit.player.name})"

    