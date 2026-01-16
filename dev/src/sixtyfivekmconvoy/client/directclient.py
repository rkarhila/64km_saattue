#! /usr/bin/env python3

"""
This module contains the DirectClient class for direct/backend communication.

DirectClient is used for local clients that are called directly by the PlayerConnector,
without going through socket communication.
"""


class DirectClient:
  """
  Base class for clients that communicate directly (no sockets).
  
  This is used when clients are instantiated locally and called directly
  by the PlayerConnector, rather than connecting over a network.
  """

  def __init__(self, conf):
    self.conf = conf

  def connect(self, host=None, port=None):
    """No-op for direct clients (no connection needed)."""
    pass

  def disconnect(self):
    """No-op for direct clients (no disconnection needed)."""
    pass

  def push_info(self, game_state):
    """
    Receive and handle game state information.
    
    Args:
        game_state: The game state dictionary (required for direct clients)
    
    Returns:
        If there's a choice in the game state, returns a choice dict with
        'choicetype' and 'choice' keys. Otherwise returns None.
    """
    # Direct clients must be called with game_state
    if game_state is None:
      raise ValueError("DirectClient.push_info() requires game_state parameter")
    # This should be overridden by subclasses
    return None

  def await_choice(self, candidates):
    """
    Handle choice selection from candidates.
    
    Args:
        candidates: Dictionary with 'options' and 'num_choice' keys, or a list
    
    Returns:
        List of integers representing the choice
    """
    # This should be overridden by subclasses
    return []

