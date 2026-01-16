#!/usr/bin/env python3

"""
End-to-end test that starts a game server and connects clients to it.
"""

import threading
import time
import sys
import os

# Add the src directory to the path so we can import from sixtyfivekmconvoy
# The tests directory is at dev/src/sixtyfivekmconvoy/tests
# So we need to go up to dev/src
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..'))

from sixtyfivekmconvoy.client import SocketClient, TerminalClient, VerboseRandomClient, MLClient
from sixtyfivekmconvoy.client.randomclient import QuietRandomClient
from sixtyfivekmconvoy.server import gamestate, playerconnector


def run_client(client, host, port):
    """Run a client that connects to the server and handles game communication."""
    client.connect(host, port)
    try:
        # Main client loop: receive game state, respond to choices
        while True:
            # Receive game state from server (push_info reads from socket)
            game_state = client.push_info()
            
            # If there's a choice in the game state, handle it
            # await_choice will read candidates from socket and send back choice
            if game_state and 'choice' in game_state:
                # await_choice expects to read from socket, but we already have the choice
                # So we need to call it with the choice dict, which will send it back
                client.await_choice(game_state['choice'])
    except (ConnectionError, EOFError, OSError, BrokenPipeError):
        # Server closed connection or game ended
        pass
    finally:
        try:
            client.disconnect()
        except:
            pass


def test_end_to_end():
    """Start a game server and connect clients to it."""
    host = 'localhost'
    port = 8888
    num_players = 3
    
    # Create player configuration for socket-based players
    playerconf = [{'playertype': 'socket'} for _ in range(num_players)]
    
    # Create PlayerConnector which will start SocketServer and wait for connections
    # We'll run this in a thread since it blocks until all clients connect
    connector = None
    connector_ready = threading.Event()
    
    def start_server():
        nonlocal connector
        connector = playerconnector.PlayerConnector(playerconf, port)
        connector_ready.set()
    
    server_thread = threading.Thread(target=start_server, daemon=False)
    server_thread.start()
    
    # Give server a moment to start listening
    time.sleep(0.2)
    
    # Create and connect clients
    clients = []
    client_threads = []
    
    # 1 random-terminal client
    random_client = VerboseRandomClient({'playertype': 'random-terminal'})
    clients.append(random_client)
    t = threading.Thread(target=run_client, args=(random_client, host, port), daemon=True)
    t.start()
    client_threads.append(t)
    
    # 2 computer (ML) clients
    for i in range(2):
        ml_client = MLClient({'playertype': 'computer'})
        clients.append(ml_client)
        t = threading.Thread(target=run_client, args=(ml_client, host, port), daemon=True)
        t.start()
        client_threads.append(t)
    
    # Wait for all clients to connect (SocketServer.__init__ blocks until all connect)
    connector_ready.wait(timeout=10)
    
    if connector is None:
        raise RuntimeError("Server failed to start or accept connections")
    
    # Now create GameState with the connector (PlayerConnector now handles socket communication)
    game = gamestate.GameState(connector, seed=None)
    
    game.finalize_setup()
    game.play()


if __name__ == '__main__':
    test_end_to_end()

