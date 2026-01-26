#! /usr/bin/env python3

"""
This module contains the DisplayMixin class for displaying game state in ASCII format.

This mixin provides ASCII conversion and display functionality that can be shared
by multiple client types.
"""


class DisplayMixin:
  """Mixin class for ASCII display functionality."""

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
      
      # Append officer names if present
      officers = unit.get('officers', [])
      if officers:
        # Format: " [Officer1, Officer2]"
        officer_list = ','.join(officers)
        unit_str += f' [{officer_list}]'
      
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
    for deck_name in ['action', 'resistance', 'pillage', 'mauling', 'officer']:
      if deck_name in decks:
        deck_info = decks[deck_name]
        deck_size = deck_info.get('deck', 0)
        discard_size = deck_info.get('discard', 0)
        deck_parts.append(f'{deck_name.capitalize()}: {deck_size}D{discard_size}')
    
    deck_state_str = 'Decks: ' + ' '.join(deck_parts)
    
    # Queue states
    queue_state_str = []
    if queues:
      queue_names = ['resistance', 'pillage', 'mauling', 'officer']
      queue_list = [queues.get(q, []) for q in queue_names]
      max_len = max(len(q) for q in queue_list) if queue_list else 0
      
      # Calculate a fixed column width based on the longest item across all queues
      # This ensures all columns have the same width for better alignment
      max_item_width = 0
      for q_name in queue_names:
        queue_data = queues.get(q_name, [])
        if queue_data:
          max_item_width = max(max_item_width, max(len(str(item)) for item in queue_data))
        # Also check header width
        max_item_width = max(max_item_width, len(q_name))
      
      # Set minimum width and round up to ensure even number for better centering
      fixed_column_width = max(max_item_width, 20)
      fixed_column_width = ((fixed_column_width + 1) // 2) * 2  # Round up to even number
      
      if max_len > 0:
        # Build header row with consistent spacing
        header_parts = ['  ']  # Start with indent
        for q_name in queue_names:
          header_parts.append(q_name.center(fixed_column_width))
        que_state_str = [' '.join(header_parts)]
        
        # Build data rows (in reverse order for correct display: newest on top)
        for i in range(max_len - 1, -1, -1):
          row_parts = [str(i+1)+':']
          for q_name in queue_names:
            queue_data = queues.get(q_name, [])
            if len(queue_data) > i:
              card_str = str(queue_data[i])
              row_parts.append(card_str.center(fixed_column_width))
            else:
              row_parts.append(''.center(fixed_column_width))
          que_state_str.append(' '.join(row_parts))
        
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

