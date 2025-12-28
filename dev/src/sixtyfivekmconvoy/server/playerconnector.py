#!/usr/bin/env python3
"""
This module contains the PlayerConnector class for connecting players to the game.

It starts a tcp server and listens for connections from players. 
It waits for a connection from each player and then creates a Player object for each player.

The SocketServer class is responsible for sending and receiving messages to and from the player.
"""


import socket
import json

class Player:
  number = -1
  name = None
  this_round_cash = 0
  cash_in_bank = 0
  promotion_points = 0
  action_cards = []

  client='terminal'
  
  def __init__(self, number, conf):
    self.number = number
    if 'name' in conf:
      self.name = conf['name']
    self.this_round_cash = 0
    self.total_cash = 0
    self.promotion_points = 0
    self.action_cards = []

    if conf['playertype'] == 'terminal':
      self.client = TerminalClient(conf)
    elif conf['playertype'] == 'random-terminal':
      self.client = VerboseRandomClient(conf)
      
    elif conf['playertype'] == 'computer':
      self.client = MLClient(conf)

    
  def get_cash(self, cash):
    self.this_round_cash += cash
    self.total_cash += cash

  def count_this_round_cash(self):
    promotion_point_cash = self.this_round_cash
    self.this_round_cash = 0
    return promotion_point_cash

  def can_discard(self, count):
    if len(self.action_cards) >= count:
      return True
    else:
      return False

  def discard(self, pack, cards):
    for card in cards:
      self.action_cards.remove(card)
      pack.discard.append(card)
    
  def place_action_card(self, card):
    self.action_cards.remove(card)
      
  def draw_card(self, pack, count):
    for c in range(count):
      self.action_cards.append(pack.get_card(shuffle_if_necessary=True))
    self.action_cards.sort()
      
  def to_str(self, playerview=None):
    playerstr = f"Player{self.number} ${self.this_round_cash}/{self.total_cash} VP${self.promotion_points}"
    if playerview is None or playerview == self:
      playerstr += f' cards:{",".join([str(c) for c in self.action_cards])}'
    else:
      playerstr += f' cards:({len(self.action_cards)})'
    return playerstr
      
  def to_json(self, playerview=None):
    playerjson = { 'number' : self.number,
                   'cash_this_round' : self.this_round_cash,
                   'total_cash' : self.total_cash,
                   'promotion_points' : self.promotion_points,
                   'card_count' : len(self.action_cards) }
    
    if playerview is None or playerview == self:
      playerjson['cards'] = self.action_cards
    return playerjson
  

class SocketPlayer:
  def __init__(self, client_socket):
    self.client_socket = client_socket
    # Make socket non-blocking and set timeout for receive operations
    self.client_socket.settimeout(None)

  def _send_json(self, data):
    """Send JSON-encoded data over the socket."""
    json_str = json.dumps(data) + '\n'
    self.client_socket.sendall(json_str.encode('utf-8'))

  def _receive_json(self):
    """Receive and parse JSON data from the socket."""
    # Read line-by-line to handle JSON messages
    buffer = ''
    while True:
      data = self.client_socket.recv(4096)
      if not data:
        raise ConnectionError("Socket connection closed")
      buffer += data.decode('utf-8')
      if '\n' in buffer:
        line, buffer = buffer.split('\n', 1)
        return json.loads(line)

  def push_info(self, info):
    """Send game state information as JSON to the client."""
    self._send_json(info)
    
  def await_choice(self, candidates):
    """Send candidates as JSON and receive a list of integers as the choice."""
    self._send_json(candidates)
    choice = self._receive_json()
    # Ensure the response is a list of integers
    if isinstance(choice, list):
      return [int(x) for x in choice]
    elif isinstance(choice, int):
      return [choice]
    else:
      raise ValueError(f"Expected list of integers, got {type(choice)}: {choice}")

class SocketServer:
  def __init__(self, port, num_players):
    self.port = port
    self.players = []
    self.num_players = num_players
    self.server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    self.server.bind(('0.0.0.0', port))
    self.server.listen(5)
    
    while len(self.players) < self.num_players:
      client, address = self.server.accept()
      self.players.append(SocketPlayer(client))

  def get_players(self):
    return self.players

  def push_info(self, player, info):
    self.players[player].push_info(info)

  def await_choice(self, player, candidates):
    return self.players[player].await_choice(candidates)

  def get_choice(self, player, choice):
    return self.players[player].get_choice(choice)



class PlayerConnector:

  def __init__(self,playerconf2, port):

    assert(type(playerconf2) == list),('conf should be list, but is', type(playerconf2))
    assert(len(playerconf2)>=1)
    assert(len(playerconf2)<=5)

    self.num_players = len(playerconf2)

    self.server = SocketServer(port, self.num_players)


    self.players = []
    for i,pl in enumerate(playerconf2):
      self.players.append(Player(i+1,pl))

    """
    self.state = GameState(self.players)

    # Do setup: Query each player

    while not self.state.setup_complete:
      setup_state = self.state.get_setup_state()      
      choice = self.send_game_states(setup_state)
      self.state.update_setup_state(choice)

    self.state.finalize_setup()
    #breakpoint()
    while not self.state.game_ended:
      game_state  = self.state.get_game_state()
      choice = self.send_game_states(game_state)
      self.state.update_game_state(choice)

    self.state.finalize_score()
    
    self.send_scores(self.state.scores)
    """
  def send_game_state(self, player, game_state):
    for p in self.players:
      if player == p or player == player.number:
        choice = p.client.push_info(game_state)
        return choice
        
    
  def broadcast_game_states(self, game_states):
    #dummy = 1
        
    # Send to each player the state
    # And to one player send a choice (if necessary)

    choices = []
    #breakpoint()
    for i,player in enumerate(self.players):
      choice = player.client.push_info(game_states[i])
      choices.append(choice)
      
    return choices
    

  def send_scores(self, scores):
    dummy = 1
