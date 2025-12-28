#!/usr/bin/env python3

"""
This module contains the TerminalClient class for terminal-based local gameplay.
"""

import re
from .socketclient import SocketClient


class TerminalClient(SocketClient):
  def __init__(self, conf):
    super().__init__(conf)

  def _json_to_ascii_convoy(self, convoy_json):
    """Convert convoy JSON to ASCII string representation."""
    if not convoy_json:
      return ""
    
    # Unicode damage emoji (same as in constants.py)
    EMOJI_DAMAGE = u'\u2B59'
    
    unit_strs = []
    for unit in convoy_json:
      # Format: player + unit_type + tired + carry + atrocities + action
      unit_str = str(unit.get('player', ''))
      
      # Unit type mapping: 'Pnz', 'Inf', 'Log'
      unit_type = unit.get('unit_type', '')
      unit_str += unit_type
      
      # Tiredness: T + tiredness + (U if under_influence)
      tiredness = unit.get('tiredness', 0)
      unit_str += f'T{tiredness}'
      if unit.get('under_influence', False):
        unit_str += 'U'
      
      # Carry: L + positive values, then damage emoji for empty slots
      carry = unit.get('carry', [0, 0, 0])
      if carry and max(carry) > 0:
        unit_str += 'L'
        for c in carry:
          if c > 0:
            unit_str += str(c)
      # Add damage emoji for empty slots (from len(carry) to 3)
      for d in range(len(carry), 3):
        unit_str += EMOJI_DAMAGE
      
      # Atrocities: A + atrocities (if > 0)
      atrocities = unit.get('atrocities', 0)
      if atrocities > 0:
        unit_str += f'A{atrocities}'
      
      # Action card
      action = unit.get('action', {})
      if action:
        card = action.get('card')
        if card is None:
          unit_str += ' A-'
        elif 'actiontaken' in action:
          unit_str += f' A{card}/{action["actiontaken"]}'
        elif card == '?':
          unit_str += ' A?'
        else:
          unit_str += f' A{card}'
      else:
        unit_str += ' A-'
      
      unit_strs.append(unit_str)
    
    return '\n'.join(unit_strs)

  def _json_to_ascii_players(self, players_json):
    """Convert players JSON to ASCII string representation."""
    if not players_json:
      return ""
    
    player_strs = []
    for player in players_json:
      player_str = f"Player{player.get('number', '')} ${player.get('cash_this_round', 0)}/{player.get('total_cash', 0)} VP${player.get('promotion_points', 0)}"
      
      # Card count or cards list
      if 'cards' in player:
        cards_str = ','.join([str(c) for c in player['cards']])
        player_str += f' cards:{cards_str}'
      else:
        card_count = player.get('card_count', 0)
        player_str += f' cards:({card_count})'
      
      player_strs.append(player_str)
    
    return '\n'.join(player_strs)

  def _json_to_ascii_decks(self, decks_json):
    """Convert decks JSON to ASCII string representation."""
    if not decks_json:
      return ""
    
    decks = decks_json.get('decks', {})
    queues = decks_json.get('queues', {})
    
    # Deck sizes: "Action: XD Y, Resistance: XD Y, ..."
    deck_parts = []
    for deck_name in ['action', 'resistance', 'pillage', 'mauling']:
      if deck_name in decks:
        deck_info = decks[deck_name]
        deck_size = deck_info.get('deck', 0)
        discard_size = deck_info.get('discard', 0)
        deck_parts.append(f'{deck_name.capitalize()}: {deck_size}D{discard_size}')
    
    deck_state_str = 'Decks: ' + ' '.join(deck_parts)
    
    # Queue states
    queue_state_str = []
    if queues:
      queue_list = queues.get('resistance', []), queues.get('pillage', []), queues.get('mauling', [])
      max_len = max(len(q) for q in queue_list)
      
      for i in range(max_len):
        q_linearr = [str(i+1)+':']
        for q in ['resistance', 'pillage', 'mauling']:
          queue_data = queues.get(q, [])
          if len(queue_data) > i:
            q_linearr.append(str(queue_data[i]).center(20))
          else:
            q_linearr.append(''.center(20))
        queue_state_str = [' '.join(q_linearr)] + queue_state_str
      
      que_state_str = ['  '+' '.join([q.center(20) for q in ['resistance', 'pillage', 'mauling']])] + queue_state_str
      deck_state_str += '\n' + '\n'.join(que_state_str)
    
    return deck_state_str

  def _json_to_ascii_resistance(self, resistance_json):
    """Convert resistance JSON to ASCII string representation."""
    if not resistance_json:
      return ""
    
    if 'in_progress' in resistance_json:
      return resistance_json['in_progress']
    return ""

  def _json_to_ascii(self, game_state_json):
    """Convert game state JSON to ASCII representation dictionary."""
    ascii_state = {}
    
    if 'convoy' in game_state_json:
      ascii_state['convoy'] = self._json_to_ascii_convoy(game_state_json['convoy'])
    
    if 'players' in game_state_json:
      ascii_state['players'] = self._json_to_ascii_players(game_state_json['players'])
    
    if 'decks' in game_state_json:
      ascii_state['decks'] = self._json_to_ascii_decks(game_state_json['decks'])
    
    if 'resistance' in game_state_json:
      ascii_state['resistance'] = self._json_to_ascii_resistance(game_state_json['resistance'])
    
    return ascii_state

  def push_info(self, game_state):
    # Convert JSON game state to ASCII for display
    ascii_state = self._json_to_ascii(game_state)
    
    # Display ASCII representation
    if 'players' in ascii_state:
      print(ascii_state['players'])
    if 'decks' in ascii_state:
      print(ascii_state['decks'])
    if 'resistance' in ascii_state:
      print(ascii_state['resistance'])
    if 'convoy' in ascii_state:
      print(ascii_state['convoy'])
    
    if 'message' in game_state:
      print('BROADCAST:', game_state['message'])
    
    if 'choice' in game_state:
      print(game_state['choice']['description'])
      options = game_state['choice']['options']
      choicecount = game_state['choice']['num_choice']
      choice = None
      while not self.verify_input(choice, options, choicecount):
        print(f"Choose {choicecount} values from:", ','.join([str(c) for c in options]))
        choice = self.get_choice(input())
      return { 'choicetype' : game_state['choice']['choicetype'],
               'choice' : choice }
    
    return None
    
  def get_choice(self, input):
    if input and len(input) > 0 and input[0] in '0123456789':
      return [int(c) for c in re.split(r'\D+', input)]
    else:
      return None
    
  def verify_input(self, choice, options, num_choices=1):
    if choice is None:
      return False
    else:
      if len(choice) != num_choices:
        if num_choices == 1:
          print(f"You choce {','.join([str(c) for c in choice])}. You must select a single option")
        else:
          print(f"You choce {','.join([str(c) for c in choice])}. You must select {num_choices} options (separate with non-digit)")
        return False
      if len(choice) != len(list(set(choice))):
        print("You choce {','.join(choice)}. You cannot choose the same option twice")
        return False
      for op in choice:
        if op not in options:
          print(f"You choce {','.join([str(c) for c in choice])}. Value {op} not in options!")
          return False
      return True

  def await_choice(self, candidates=None):
    """Handle choice selection from candidates.
    
    This method is called when a choice needs to be made. For TerminalClient,
    it prompts the user via push_info instead, so this method should not be
    called directly. If called, it would need to extract options and prompt.
    """
    # For TerminalClient, choices are handled within push_info when game_state
    # contains a 'choice' field. This method is provided for interface compatibility.
    # If candidates is provided as a dict with 'options', extract and handle it.
    if isinstance(candidates, dict):
      if 'options' in candidates:
        options = candidates['options']
        num_choices = candidates.get('num_choice', 1)
        choice = None
        while not self.verify_input(choice, options, num_choices):
          print(f"Choose {num_choices} values from:", ','.join([str(c) for c in options]))
          choice = self.get_choice(input())
        return choice
    # If candidates is a list, treat as options
    elif isinstance(candidates, list) and len(candidates) > 0:
      choice = None
      while not self.verify_input(choice, candidates, 1):
        print(f"Choose 1 value from:", ','.join([str(c) for c in candidates]))
        choice = self.get_choice(input())
      return choice
    return None
    
