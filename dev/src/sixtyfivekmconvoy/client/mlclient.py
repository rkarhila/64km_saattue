#! /usr/bin/env python3

"""
This is a placeholder for a MLClient class for a machine learning client.
"""

import random
from .socketclient import SocketClient


class MLClient(SocketClient):
    
  def __init__(self, conf):
    super().__init__(conf)
    
  def push_info(self, game_state):
    if 'choice' in game_state:
      
      #print(game_state['choice']['description'])
      options=game_state['choice']['options']
      choicecount=game_state['choice']['num_choice']
      random.shuffle(options)
      choice = options[:choicecount]
      return { 'choicetype' : game_state['choice']['choicetype'],
               'choice' : choice }
      
  def await_choice(self, candidates=None):
    """Handle choice selection from candidates."""
    if candidates is None:
      candidates = self._receive_json()
    
    # Extract options from candidates dict
    if isinstance(candidates, dict):
      if 'options' in candidates:
        options = candidates['options']
        num_choices = candidates.get('num_choice', 1)
        random.shuffle(options)
        choice = options[:num_choices]
        # Send back the choice as a list of integers
        self._send_json(choice)
        return choice
    # If candidates is a list, treat as options
    elif isinstance(candidates, list) and len(candidates) > 0:
      choice = [random.choice(candidates)]
      self._send_json(choice)
      return choice
    
    # Default: send empty choice
    choice = []
    self._send_json(choice)
    return choice