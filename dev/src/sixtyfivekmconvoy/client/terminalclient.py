#!/usr/bin/env python3

"""
This module contains the TerminalClient class for terminal-based local gameplay.
"""

import re
from .socketclient import SocketClient


class TerminalClient(SocketClient):
  def __init__(self, conf):
    super().__init__(conf)

  def push_info(self, game_state):
    #print(game_state)
    #breakpoint()
    if 'ascii' in game_state:
      if 'players' in game_state['ascii']:
        print(game_state['ascii']['players'])
      if 'decks' in game_state['ascii']:
        print(game_state['ascii']['decks'])
      if 'resistance' in game_state['ascii']:
        print(game_state['ascii']['resistance'])
        
    choice = None
    if 'convoy' in game_state['ascii']:
      print(game_state['ascii']['convoy'])
    if 'message' in game_state:
      print('BROADCAST:', game_state['message'])
    if 'choice' in game_state:
      print(game_state['choice']['description'])
      options=game_state['choice']['options']
      choicecount=game_state['choice']['num_choice']
      choice = None
      while not self.verify_input(choice,options, choicecount):
        print(f"Choose {choicecount} values from:", ','.join([str(c) for c in options]))
        choice = self.get_choice(input())
      return { 'choicetype' : game_state['choice']['choicetype'],
               'choice' : choice }
      
      print("press return to continue")
      input()
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
    
