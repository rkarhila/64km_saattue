#!/usr/bin/env python3

"""
This module contains server logic for starting a game server and managing client connections.
"""

from .playerconnector import PlayerConnector
from .gamestate import GameState


def serve(port, num_players, seed=None):
    """
    Start a game server that accepts socket connections from clients.
    
    Args:
        port: Port number to listen on
        num_players: Number of players to wait for
        seed: Random seed for game (optional)
    
    Returns:
        None (runs until game ends)
    """
    # Create player configuration (for socket mode, we just need the count)
    playerconf = [{'playertype': 'socket'} for _ in range(num_players)]
    
    # Create PlayerConnector which will start SocketServer and wait for connections
    connector = PlayerConnector(playerconf, port)
    
    
    # Create GameState with the connector
    game = GameState(connector, seed=seed)
    
    # Run the game
    game.finalize_setup()
    game.play()


if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='Start a game server')
    parser.add_argument('--port', type=int, required=True, help='Port number to listen on')
    parser.add_argument('--players', type=int, required=True, help='Number of players')
    parser.add_argument('--seed', type=int, default=None, help='Random seed for the game')
    
    args = parser.parse_args()
    
    serve(args.port, args.players, seed=args.seed)

