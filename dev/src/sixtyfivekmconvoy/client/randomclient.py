#!/usr/bin/env python3

"""
This module contains the RandomClient class for a random client.
"""

import random
from .terminalclient import TerminalClient
from .socketclient import SocketClient


class RandomClient(TerminalClient):
    """
    A random client that makes random choices in the game.
    Can operate in quiet mode (no output) or verbose mode (displays game state).
    """
    
    def __init__(self, conf, verbose=False):
        """
        Initialize the RandomClient.
        
        Args:
            conf: Configuration dictionary
            verbose: If True, displays game state. If False, operates silently.
        """
        super().__init__(conf)
        self.verbose = verbose
    
    @classmethod
    def quiet(cls, conf):
        """Create a quiet RandomClient (no output)."""
        return cls(conf, verbose=False)
    
    @classmethod
    def verbose(cls, conf):
        """Create a verbose RandomClient (displays game state)."""
        return cls(conf, verbose=True)
    
    def push_info(self, game_state=None):
        """Receive and optionally display game state, making random choices."""
        # If game_state is None, read from socket (socket client mode)
        read_from_socket = (game_state is None)
        if read_from_socket:
            game_state = self._receive_json()
        
        # Display game state if in verbose mode
        if self.verbose:
            # Convert JSON game state to ASCII for display (using parent's method)
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
        
        # If there's a choice, make a random choice
        if 'choice' in game_state:
            if self.verbose:
                print(game_state['choice']['description'])
            
            options = game_state['choice']['options']
            choicecount = game_state['choice']['num_choice']
            # Make random choice
            random.shuffle(options)
            choice = options[:choicecount]
            
            if self.verbose:
                print(f"You chose {','.join([str(c) for c in choice])}")
            
            # If we read from socket, send choice back via socket
            if read_from_socket:
                self._send_json(choice)
                return None  # Don't return choice dict in socket mode
            
            # For local mode, return choice dict
            return { 'choicetype' : game_state['choice']['choicetype'],
                     'choice' : choice }
        
        return None
    
    def await_choice(self, candidates=None):
        """Handle choice selection from candidates by making random choices."""
        if candidates is None:
            candidates = self._receive_json()
        
        # Extract options from candidates dict and make random choice
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


# Backward compatibility aliases
QuietRandomClient = lambda conf: RandomClient.quiet(conf)
VerboseRandomClient = lambda conf: RandomClient.verbose(conf)


def main():
    """Main function to connect to a game server and play with a random client."""
    import argparse
    
    parser = argparse.ArgumentParser(description='Connect to a game server and play with a random client')
    parser.add_argument('--host', type=str, default='localhost', help='Server hostname (default: localhost)')
    parser.add_argument('--port', type=int, required=True, help='Server port number')
    parser.add_argument('--verbose', action='store_true', help='Use verbose random client (displays game state)')
    
    args = parser.parse_args()
    
    # Create client based on verbose flag
    if args.verbose:
        client = RandomClient.verbose({'playertype': 'random-terminal'})
    else:
        client = RandomClient.quiet({'playertype': 'computer'})
    
    try:
        # Connect to server
        print(f"Connecting to server at {args.host}:{args.port}...")
        client.connect(args.host, args.port)
        print("Connected successfully!")
        
        if args.verbose:
            print("Using verbose random client (game state will be displayed)")
        else:
            print("Using quiet random client (no output)")
        
        # Main game loop: receive game state, respond to choices
        while True:
            try:
                # Receive game state from server and display it (for verbose client)
                # push_info handles reading from socket, displaying, and sending choices back
                client.push_info()  # None means read from socket
                    
            except (ConnectionError, EOFError, OSError, BrokenPipeError) as e:
                print(f"\nConnection closed: {e}")
                break
            except KeyboardInterrupt:
                print("\n\nGame interrupted by user.")
                break
                
    except ConnectionRefusedError:
        print(f"Error: Could not connect to server at {args.host}:{args.port}")
        print("Make sure the server is running and the port is correct.")
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        try:
            client.disconnect()
        except:
            pass


if __name__ == '__main__':
    main()
