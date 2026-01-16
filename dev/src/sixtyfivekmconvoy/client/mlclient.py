#! /usr/bin/env python3

"""
This is a placeholder for a MLClient class for a machine learning client.
"""

import random
from .directclient import DirectClient
from .socketclient import SocketClient


class MLClient(DirectClient):
    """
    ML client for direct/local communication.
    Currently a placeholder that makes random choices.
    """
    
  def __init__(self, conf):
        DirectClient.__init__(self, conf)
    
  def push_info(self, game_state):
        """Receive game state and handle choices."""
        if game_state is None:
            raise ValueError("MLClient.push_info() requires game_state parameter")
        
    if 'choice' in game_state:
            options = list(game_state['choice']['options'])  # Don't modify original
            choicecount = game_state['choice']['num_choice']
      random.shuffle(options)
      choice = options[:choicecount]
            return {
                'choicetype': game_state['choice']['choicetype'],
                'choice': choice
            }
        
        return None
      
  def await_choice(self, candidates):
        """Handle choice selection from candidates."""
        # Extract options from candidates dict
        if isinstance(candidates, dict):
            if 'options' in candidates:
                options = list(candidates['options'])  # Don't modify original
                num_choices = candidates.get('num_choice', 1)
                random.shuffle(options)
                return options[:num_choices]
        # If candidates is a list, treat as options
        elif isinstance(candidates, list) and len(candidates) > 0:
            options_copy = list(candidates)  # Don't modify original
            random.shuffle(options_copy)
            return [random.choice(options_copy)]
        
        # Default: return empty choice
        return []


class MLSocketClient(SocketClient):
    """
    ML client for socket/network communication.
    Currently a placeholder that makes random choices.
    """
    
    def __init__(self, conf):
        SocketClient.__init__(self, conf)
    
    def push_info(self, state=None):
        """Receive game state from socket. Returns True if there was a choice."""
        if state is None:
            state = self._receive_json()
        
        # Return True if there was a choice (don't handle it here in socket mode)
        return 'choice' in state
    
    def await_choice(self, candidates=None):
        """Receive candidates from socket and send random choice back."""
        if candidates is None:
            candidates = self._receive_json()
        
        # Extract options from candidates dict
        if isinstance(candidates, dict):
            if 'options' in candidates:
                options = list(candidates['options'])  # Don't modify original
                num_choices = candidates.get('num_choice', 1)
                random.shuffle(options)
                choice = options[:num_choices]
                self._send_json(choice)
                return choice
        # If candidates is a list, treat as options
        elif isinstance(candidates, list) and len(candidates) > 0:
            options_copy = list(candidates)  # Don't modify original
            random.shuffle(options_copy)
            choice = [random.choice(options_copy)]
            self._send_json(choice)
            return choice
        
        # Default: send empty choice
        choice = []
        self._send_json(choice)
    return choice