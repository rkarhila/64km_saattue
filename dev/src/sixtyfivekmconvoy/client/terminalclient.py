#!/usr/bin/env python3

"""
This module contains terminal client classes for human and random terminal interaction.
"""

import re
import argparse
from .directclient import DirectClient
from .socketclient import SocketClient
from .displaymixin import DisplayMixin


class TerminalHumanClient(DirectClient, DisplayMixin):
    """
    A terminal client for human players with ASCII output.
    Used for direct/local communication.
    """
    
    def __init__(self, conf):
        DirectClient.__init__(self, conf)

    def push_info(self, game_state):
        """Receive game state, display it, and prompt for human input."""
        if game_state is None:
            raise ValueError("TerminalHumanClient.push_info() requires game_state parameter")
        
        # Display game state
        ascii_state = self._json_to_ascii(game_state)
        
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
        
        # If there's a choice, handle it
        if 'choice' in game_state:
            print(game_state['choice']['description'])
            options = game_state['choice']['options']
            choicecount = game_state['choice']['num_choice']
            choice = None
            while not self.verify_input(choice, options, choicecount):
                print(f"Choose {choicecount} values from:", ','.join([str(c) for c in options]))
                choice = self.get_choice(input())
            
            # Return choice dict for direct client
            return {
                'choicetype': game_state['choice']['choicetype'],
                'choice': choice
            }
        
        return None
    
    def await_choice(self, candidates):
        """Handle choice selection from candidates by prompting user."""
        # Extract options from candidates dict
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
        
        return []
    
    def get_choice(self, input_str):
        """Parse input string into a list of integers."""
        if input_str and len(input_str) > 0 and input_str[0] in '0123456789':
            return [int(c) for c in re.split(r'\D+', input_str)]
        else:
            return None
    
    def verify_input(self, choice, options, num_choices=1):
        """Verify that a choice is valid."""
        if choice is None:
            return False
        if len(choice) != num_choices:
            if num_choices == 1:
                print(f"You chose {','.join([str(c) for c in choice])}. You must select a single option")
            else:
                print(f"You chose {','.join([str(c) for c in choice])}. You must select {num_choices} options (separate with non-digit)")
            return False
        if len(choice) != len(list(set(choice))):
            print(f"You chose {','.join([str(c) for c in choice])}. You cannot choose the same option twice")
            return False
        for op in choice:
            if op not in options:
                print(f"You chose {','.join([str(c) for c in choice])}. Value {op} not in options!")
                return False
        return True


class TerminalHumanSocketClient(SocketClient, DisplayMixin):
    """
    A terminal client for human players with ASCII output.
    Used for socket/network communication.
    """
    
    def __init__(self, conf):
        SocketClient.__init__(self, conf)
    
    def push_info(self, state=None):
        """Receive game state from socket, display it. Returns True if there was a choice."""
        # In socket mode, read from socket
        if state is None:
            state = self._receive_json()
        
        # Display game state
        ascii_state = self._json_to_ascii(state)
        
        if 'players' in ascii_state:
            print(ascii_state['players'])
        if 'decks' in ascii_state:
            print(ascii_state['decks'])
        if 'resistance' in ascii_state:
            print(ascii_state['resistance'])
        if 'convoy' in ascii_state:
            print(ascii_state['convoy'])
        
        if 'message' in state:
            print('BROADCAST:', state['message'])
        
        # Store whether there was a choice
        has_choice = 'choice' in state
        
        if has_choice:
            print(state['choice']['description'])
        
        # In socket mode, return True if there was a choice (handle in await_choice)
        return has_choice
    
    def await_choice(self, candidates=None):
        """Receive candidates from socket and prompt user for choice."""
        if candidates is None:
            candidates = self._receive_json()
        
        # Extract options from candidates dict and prompt user
        if isinstance(candidates, dict):
            if 'options' in candidates:
                options = candidates['options']
                num_choices = candidates.get('num_choice', 1)
                choice = None
                while not self.verify_input(choice, options, num_choices):
                    print(f"Choose {num_choices} values from:", ','.join([str(c) for c in options]))
                    choice = self.get_choice(input())
                self._send_json(choice)
                return choice
        # If candidates is a list, treat as options
        elif isinstance(candidates, list) and len(candidates) > 0:
            choice = None
            while not self.verify_input(choice, candidates, 1):
                print(f"Choose 1 value from:", ','.join([str(c) for c in candidates]))
                choice = self.get_choice(input())
            self._send_json(choice)
            return choice
        
        # Default: send empty choice
        choice = []
        self._send_json(choice)
        return choice
    
    def get_choice(self, input_str):
        """Parse input string into a list of integers."""
        if input_str and len(input_str) > 0 and input_str[0] in '0123456789':
            return [int(c) for c in re.split(r'\D+', input_str)]
        else:
            return None
    
    def verify_input(self, choice, options, num_choices=1):
        """Verify that a choice is valid."""
        if choice is None:
            return False
        if len(choice) != num_choices:
            if num_choices == 1:
                print(f"You chose {','.join([str(c) for c in choice])}. You must select a single option")
            else:
                print(f"You chose {','.join([str(c) for c in choice])}. You must select {num_choices} options (separate with non-digit)")
            return False
        if len(choice) != len(list(set(choice))):
            print(f"You chose {','.join([str(c) for c in choice])}. You cannot choose the same option twice")
            return False
        for op in choice:
            if op not in options:
                print(f"You chose {','.join([str(c) for c in choice])}. Value {op} not in options!")
                return False
        return True        
    

# Factory function to choose between DirectClient and SocketClient versions
def create_terminal_human_client(conf, use_socket=False):
    """Factory function to create a TerminalHumanClient (direct or socket)."""
    if use_socket:
        return TerminalHumanSocketClient(conf)
    else:
        return TerminalHumanClient(conf)


def main():
    """Main function to connect to a game server and play via terminal."""
    parser = argparse.ArgumentParser(description='Connect to a game server and play via terminal')
    parser.add_argument('--host', type=str, default='localhost', help='Server hostname (default: localhost)')
    parser.add_argument('--port', type=int, required=True, help='Server port number')
    
    args = parser.parse_args()
    
    # Create socket-based client for network connection
    client = TerminalHumanSocketClient({'playertype': 'terminal'})
    
    try:
        # Connect to server
        print(f"Connecting to server at {args.host}:{args.port}...")
        client.connect(args.host, args.port)
        print("Connected successfully!")
        
        # Main game loop: receive game state, respond to choices
        while True:
            try:
                # Receive game state from server
                # push_info returns True if there was a choice in the game state
                has_choice = client.push_info()  # Returns True/False in socket mode
                
                # If there was a choice, the server will send the choice candidates separately
                if has_choice:
                    try:
                        candidates = client._receive_json()
                        # Prompt user for choice and send it back
                        client.await_choice(candidates)
                    except (ConnectionError, EOFError, OSError, BrokenPipeError) as e:
                        print(f"\nConnection closed while receiving choice: {e}")
                        break
                    
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
