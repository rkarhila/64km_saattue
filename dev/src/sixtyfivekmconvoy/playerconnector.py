#!/usr/bin/env python3


from .convoyclients import TerminalClient, MLClient, VerboseRandomClient



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
  

    
class PlayerConnector:

  def __init__(self,playerconf2):
    assert(type(playerconf2) == list),('conf should be list, but is', type(playerconf2))
    assert(len(playerconf2)>=1)
    assert(len(playerconf2)<=5)

    self.num_players = len(playerconf2)

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
