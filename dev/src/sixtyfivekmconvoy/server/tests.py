#!/usr/bin/env python3

"""
Test module for running game tests with direct clients.
"""

from .playerconnector import PlayerConnector
from .gamestate import GameState


def main():
    """Start a game with 3 quiet random direct clients."""
    # Create player configuration:
    # - 3 quiet random clients (playertype: 'computer' -> QuietRandomClient)
    playerconf = [
        {'playertype': 'computer'},      # Quiet random client (no output)
        {'playertype': 'computer'},      # Quiet random client (no output)
        {'playertype': 'computer'}       # Quiet random client (no output)
    ]
    
    # Create PlayerConnector with port=None for direct clients
    connector = PlayerConnector(playerconf, port=None)
    
    # Create GameState with the connector
    game = GameState(connector, seed=None)
    
    # Run the game
    game.finalize_setup()
    game.play()


if __name__ == '__main__':
    main()
