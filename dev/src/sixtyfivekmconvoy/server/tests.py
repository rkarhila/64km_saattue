#!/usr/bin/env python3

"""
Test module for running game tests with direct clients.
"""

from .playerconnector import PlayerConnector
from .gamestate import GameState


def main():
    """Start a game with 2 quiet random direct clients and 1 verbose random direct client."""
    # Create player configuration:
    # - 2 quiet random clients (playertype: 'computer' -> QuietRandomClient)
    # - 1 verbose random client (playertype: 'random-terminal' -> TerminalRandomClient)
    playerconf = [
        {'playertype': 'computer'},      # Quiet random client (no output)
        {'playertype': 'computer'},      # Quiet random client (no output)
        {'playertype': 'random-terminal'}  # Verbose random client (with ASCII output)
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
