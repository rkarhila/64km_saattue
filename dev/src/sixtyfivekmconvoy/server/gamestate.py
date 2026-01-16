#!/usr/bin/env python3

"""
This module contains the main game loop and tracks the state for the game.

The stateof the game is tracked in the GameState class. The game state can be
- saved and loaded from a file.

The game states is broadcasted to the players. The players can then send their actions to the game state.

The players can be either human players or AI players.


"""

import random

import sys
from copy import deepcopy

from .constants import ChoiceType
from .card_deck_pillage import CardDeckPillage
from .card_deck_resistance import CardDeckResistance
from .card_deck_actions import CardDeckActions
from .card_deck_mauling import CardDeckMauling
from .card_deck_officers import OfficerCardDeck
from .card_deck import CardDeck
from .card_queue import CardQueue


NUM_ACTION_CARDS = 50
NUM_MAULING_CARDS = 24
NUM_PILLAGE_CARDS = 36
NUM_RESISTANCE_CARDS = 24


MIN_PLAYER_CARD_LIMIT = 2
CARD_TO_POINTS_RATIO = 4

CARDS_TO_DEAL=5

class Phase:
  PRE_START       = -1
  DEAL_CARDS      = 0
  ASSIGN_ACTIONS  = 1
  EXECUTE_ACTIONS = 2
  MAUL            = 3
  ADVANCE         = 4
  



from .unit import Unit, UnitType
from .convoy import Convoy
from .resistance import Resistance

from .action import Action


class Rounds:

  stages= { 0 : 'Deal cards',
            1 : 'Place actions',
            2 : 'Actions round',
            3 : 'Advance convoy',
            4 : 'Mauling',
            5 : 'Bookkeeping' }
  
  def __init__(self, count=0, stage=-1):
    self.count = count
    self.stage = stage

  def next_round(self):
    self.count += 1
    self.stage = -1

  def next_stage(self):
    self.stage += 1
    if self.stage not in Rounds.stages:
      return None
    else:
      return Rounds.stages[self.stage]

  def current_stage(self):
    return self.stage, Rounds.stages[self.stage]
    
class GameState:

  setup_complete = False
  game_ended = False
  
  phase = Phase.PRE_START
  action_phase_counter = -1

  treasury = [0] * 5
  victory_points = [0] * 5

  units = [0] * 15
  
  selected_actions = [0] * 30

  player_hands = [[0] * 10 for _ in range(5)]

  players = None
  
  active_resistance = [0]

  history = []

  # Choice type constants (from constants.ChoiceType, kept for backward compatibility)
  choose_card_choice_type = ChoiceType.choose_card_choice_type
  choose_action_choice_type = ChoiceType.choose_action_choice_type
  choose_cards_to_discard = ChoiceType.choose_cards_to_discard
  cash_in_cards_choice_type = ChoiceType.cash_in_cards_choice_type
  choose_queue_to_scout_choice_type = ChoiceType.choose_queue_to_scout_choice_type
  choose_pillage_card_choice_type = ChoiceType.choose_pillage_card_choice_type

  
  def __init__(self, playerconnector, seed=3):
    """
    Initialize GameState with a PlayerConnector.
    
    Args:
        playerconnector: PlayerConnector instance that manages player connections
        seed: Random seed for game initialization (optional)
    """
    self.playerconnector = playerconnector
    self.players = self.playerconnector.players
    
    self.rounds = None
    
    # Shuffle decks
    if seed is not None:
      random.seed(seed)

    self.action_deck = CardDeck(len(CardDeckActions.deck),
                                names_and_effects = CardDeckActions.deck)
    self.resistance_deck = CardDeck(len(CardDeckResistance.deck),
                                 names_and_effects = CardDeckResistance.deck)
    self.pillage_deck = CardDeck(len(CardDeckPillage.deck),
                                 names_and_effects = CardDeckPillage.deck)
    self.mauling_deck = CardDeck(len(CardDeckMauling.deck),
                                 names_and_effects = CardDeckMauling.deck)
    # Initialise queues:
    self.resistance_queue = CardQueue(3, deck=self.resistance_deck)    
    self.mauling_queue = CardQueue(3, deck=self.mauling_deck)    
    self.pillage_queue = CardQueue(20, deck=self.pillage_deck)

    self.convoy = Convoy(self.players)
    
    self.scores = [0] * len(self.players)

    #self.resistance = Resistance(None)

  def setup(self):
    self.finalize_setup()


  def broadcast(self, message):
    for pl in self.players:
      game_state  = self.get_game_state(player=pl)
      game_state['message'] = message
      self.playerconnector.send_game_state(pl,game_state)
      
    
  def demand_choice(self,player, choicetype, options, description=None, num_choices=1):
    game_state  = self.get_game_state(player=player)
    game_state['choice'] = {'choicetype' : choicetype, 
                            'options' : options,
                            'num_choice' : num_choices}
    if description is not None:
      game_state['choice']['description'] = description
    choice_json = self.playerconnector.send_game_state(player,game_state)
    return choice_json['choice']
    
  def play(self):
    while not self.game_ended:
      # Loop through the round:

      # 0 Deal cards:
      #self.phase = Phase.DEAL_CARDS
      self.broadcast(f"============ Starting round {self.rounds.count} ==========")

      
      for i in range(CARDS_TO_DEAL):
        for player in self.players:
          player.draw_card(self.action_deck, 1)
      next_stage = self.rounds.next_stage()
      print(f"Everyone got their cards, move on to {next_stage}")

          
      # 1 assign actions:
      
      #self.phase = Phase.ASSIGN_ACTIONS

      game_states  = self.get_game_state()
      #choice = self.playerconnector.broadcast_game_states(game_state)
      #self.update_game_state(choice)
      print(f"stage {self.rounds.stage} == 1; Choose actions")
      for i,player in enumerate(self.players):
        #breakpoint()
        units = [Unit.type_to_str[u.unittype] for u in self.convoy.units if u.player == player ]
        #print("player", i, units)
        if len(units) > 0:
          description='Choose one action card for each troop '+','.join(units)
          for c in player.action_cards:
            #  print(self.action_deck.describe(c))
            card_desc = self.action_deck.describe(c)
            # card_desc is a list of action dictionaries when using action_deck
            if isinstance(card_desc, list):
              description+= f'\n  {c}: '+ '/'.join([f['name'] for f in card_desc if isinstance(f, dict) and 'name' in f])
            elif isinstance(card_desc, dict) and 'name' in card_desc:
              # Single action dictionary
              description+= f'\n  {c}: {card_desc["name"]}'
            else:
              description+= f'\n  {c}: {str(card_desc)}'
          choicetaken = self.demand_choice(player,
                                           GameState.choose_card_choice_type,
                                           player.action_cards,
                                           description=description,
                                           num_choices=len(units))

          units = [u for u in self.convoy.units if u.player == player ]
          for i, choice in enumerate(choicetaken):
            units[i].actioncard = choice
            player.place_action_card(choice)
              
      next_stage = self.rounds.next_stage()
      print(f"Everyone chose their actions, move on to {next_stage}")
      self.convoy.current_actor= 0
          
      # 2 play actions:
      
      while self.convoy.current_actor is not None:
        actor = self.convoy.units[self.convoy.current_actor]
        if self.convoy.units[self.convoy.current_actor].actiontaken is None:
          actioncard = self.convoy.units[self.convoy.current_actor].actioncard
        elif self.convoy.units[self.convoy.current_actor].secondactiontaken is None:
          actioncard = self.convoy.units[self.convoy.current_actor].secondactioncard
        else:
          raise ValueError('All actions taken already')

        descriptions = self.action_deck.describe(actioncard)
        possible_choices = []
        for e,desc in enumerate(descriptions):
          action = Action(self, self.convoy, self.convoy.current_actor, desc, actioncard)
          if action.possible:
            possible_choices.append([e,desc,action])
        if len(possible_choices) > 1:
          choicetaken = self.demand_choice(actor.player,
                                           GameState.choose_action_choice_type,
                                           [0,1],
                                           description='Choose action for '+Unit.type_to_str[actor.unittype] + '  0:"' +  descriptions[0]['name'] + '" 1:"' +descriptions[1]['name']+'"',
                                           num_choices=1)
        elif len(possible_choices) == 1:
          choicetaken = [0] #possible_choices[0]
        else:
          choicetaken = [-1]  # become frustrated!
        
        if choicetaken[0] == -1:
          if self.convoy.units[self.convoy.current_actor].actiontaken is None:
            self.convoy.units[self.convoy.current_actor].actiontaken = choicetaken[0]
          elif self.convoy.units[self.convoy.current_actor].secondactiontaken is None:
            self.convoy.units[self.convoy.current_actor].secondactiontaken = choicetaken[0]
          self.broadcast(f"Unit {actor} (Player {actor.player.number}/{actor.player.name}) becomes frustrated ")

          self.convoy.resolve_action(None)
        else:
          if self.convoy.units[self.convoy.current_actor].actiontaken is None:
            self.convoy.units[self.convoy.current_actor].actiontaken = choicetaken[0]
            action = possible_choices[choicetaken[0]][2]
            self.convoy.resolve_action(action)
          elif self.convoy.units[self.convoy.current_actor].secondactiontaken is None:
            self.convoy.units[self.convoy.current_actor].secondactiontaken = choicetaken[0]
            action = possible_choices[choicetaken[0]][2]
            self.convoy.resolve_action(action, second=True)

      # 3 advance convoy
      advance_msg = ''
      if not self.resistance.active:
        # Advance: All resting units are moved back in the convoy:
        self.convoy.move_resting_and_damaged_units()
        # Reveal new resistance:
        self.resistance_queue.remove_card(0)
        # TODO: safety check if there is less than 3 cards in resistance queue!
        self.resistance_queue.put_card(self.resistance_deck.get_card())
        if self.resistance_queue.cards_and_visibilities[0][1] == False:
          self.resistance_queue.reveal_card(0)
          self.resistance = Resistance(self.resistance_queue.describe(0), self)
          advance_msg += ". Convoy advances into ambush: "+self.resistance.attack()
        else:
          self.resistance = Resistance(self.resistance_queue.describe(0), self)
        advance_msg = f'Convoy moves, new active resistance "{self.resistance.name}"' + advance_msg
      else:
        advance_msg = 'Convoy stuck because of resistance.'
      self.broadcast(advance_msg)
        
      next_stage = self.rounds.next_stage()
      #print(f"Advance done, move on to {next_stage}")


      # 4 Mauling

      mauling = self.mauling_deck.describe(self.mauling_queue.remove_card()[0])
      mauling_target= mauling['effect']['target']
      if mauling_target in 'ABCE':
        mauled_zone = mauling_target[0]
        mauled_unit = None
        atrocities = sum([ self.convoy.units[u].atrocities for u in self.convoy.zones[mauled_zone] ])
      else:
        mauled_zone = mauling_target[0]
        mauled_unit = int(mauling_target[1:])
        atrocities = self.convoy.units[self.convoy.zones[mauled_zone][mauled_unit]].atrocities 
      mauling_damage = mauling['effect']['damage']
      mauling_type = mauling['effect']['type'][0]
      mauling_threshold = mauling['effect']['atrocity_threshold']
      
      # TODO: All damage under atrocity threshold for now
      mauling_msg = f"Convoy attacked by {mauling['name']}: "
      mauling_msg += self.convoy.apply_damage(mauling_damage[0], unit=mauled_unit, zone=mauled_zone, attack_type=mauling_type)
      self.broadcast(mauling_msg)
      self.mauling_queue.put_card(self.mauling_deck.get_card())
      
      next_stage = self.rounds.next_stage()
      print(f"Mauling done, move on to {next_stage}")


      # 5 bookkkeeping
      for pl in self.players:
        if len(pl.action_cards) > CARD_TO_POINTS_RATIO:
          description = f"Do you want to exchange {CARD_TO_POINTS_RATIO} to 1 point (1=yes,0=no)"
          choicetaken = self.demand_choice(player,
                                           GameState.cash_in_cards_choice_type,
                                           [0,1],
                                           description=description,
                                           num_choices=1)
          if choicetaken == 1:
            if len(pl.action_cards) == CARD_TO_POINTS_RATIO:
              pl.discard(pl.action_cards, choicetaken)
            else:
              description = f"Choose {CARDS_TO_POINTS_RATIO} cards to discard in exchange for a point"
              choicetaken = self.demand_choice(pl,
                                             self.choose_cards_to_discard,
                                             pl.action_cards,
                                             description=description,
                                             num_choices=CARDS_TO_POINTS_RATIO)
              pl.discard(self.action_deck, choicetaken)

            pl.get_cash(1)
            self.broadcast(f"Player {pl.number}/{pl.name} cashed in cards")
        
        player_card_limit = MIN_PLAYER_CARD_LIMIT
        for u in [u for u in self.convoy.units if u.player == pl]:
          if Unit.type_to_str[u.unittype] == 'Log':
            player_card_limit += sum([c == 0 for c in u.carry])
            break
        if len(pl.action_cards) > player_card_limit:
          to_discard = len(pl.action_cards) - player_card_limit
          description = f"You can only keep {player_card_limit} cards in your hand. Choose {to_discard} cards to discard."
          choicetaken = self.demand_choice(pl,
                                           self.choose_cards_to_discard,
                                           pl.action_cards,
                                           description=description,
                                           num_choices=to_discard)
          pl.discard(self.action_deck, choicetaken)
          
      # Who gets promotion points?

      max_score = max([ pl.this_round_cash for pl in self.players ])
      if max_score > 0:
        for pl in self.players:
          if  pl.this_round_cash == max_score:
            pl.promotion_points += 1
            self.broadcast(f"Player {pl.number}/{pl.name} gets promotion point")


      if len(self.convoy.units) <= len(self.players):
        self.broadcast("Game finished.")
        pls = self.players_to_json()
        sorted_pl = sorted(pls, key=lambda k:(-k['promotion_points'], -k['total_cash']))
        from pprint import pprint
        #pprint( [ pl.  sorted_pl)
        print( '\n'.join([f"Player {pl['number']}: {pl['promotion_points']} promotion points, {pl['total_cash']} total cash" for pl in sorted_pl])  )  
        sys.exit()
        
      #print(f"Bookkeeping done, move on to next round")
      for unit in self.convoy.units:
        if unit.actioncard:
          self.action_deck.discard.append(unit.actioncard)
          unit.actioncard = None
        unit.actiontaken = None
        if unit.secondactioncard:
          self.action_deck.discard.append(unit.secondactioncard)
          unit.secondactiontaken = None

      
      for pl in self.players:
        pl.this_round_cash = 0

      
      self.rounds.next_round()
    
      
  def get_setup_state(self):
    # In setup, players choose position for their troops
    setup_states = []
    for player in self.players:
      setup_states.append({})
    return setup_states
  
    
  def update_setup_state(self,choice):
    self.setup_complete=True

  def finalize_setup(self):
    # organize convoy:
    import random
    random.shuffle(self.convoy.units)
    
    for i in range(3):
      self.resistance_queue.put_card(self.resistance_deck.get_card())
    for i in range(3):
      self.mauling_queue.put_card(self.resistance_deck.get_card())

    self.resistance_queue.reveal_card(0)
    self.mauling_queue.reveal_card(0)
    self.rounds = Rounds(stage=0)
    self.resistance = Resistance(self.resistance_queue.describe(0), self)
    
  """
  def next_actions(self):
    choices = [None]*len(self.players)
    
    if self.rounds is None:
      return choices
    
    if self.rounds.stage == 0:
      print(f"stage {self.rounds.stage} == 0; Deal cards")
      # Deal cards: No action from players required:
      for i in range(CARDS_TO_DEAL):
        for player in self.players:
          player.draw_card(self.action_deck, 1)
    elif self.rounds.stage == 1:
      print(f"stage {self.rounds.stage} == 1; Choose actions")
      for i,player in enumerate(self.players):
        #breakpoint()
        units = [Unit.type_to_str[u.unittype] for u in self.convoy.units if u.player == player.number ]
        #print("player", i, units)
        if len(units) > 0:
          choices[i] = {'description' : 'Choose one action card for each troop '+','.join(units),
                        'choicetype' : GameState.choose_card_choice_type,
                        'options' : player.action_cards,
                        'num_choice' : len(units)}
    elif self.rounds.stage == 2:
      print(f"stage {self.rounds.stage} == 1; Play actions:")
      choices = [None]*len(self.players)
      if self.convoy.current_actor is not None:
        actor = self.convoy.units[self.convoy.current_actor]
        choices[actor.player-1] = {'description' : 'Choose action for '+Unit.type_to_str[actor.unittype],
                                   'choicetype' : GameState.choose_action_choice_type,
                                   'options' : [0,1],
                                   'num_choice' : 1}
      
    #print("choices",choices)
    return choices

  def update_game_state(self,choices):
    # A player has made a decision, mark its effects on the game stage
    #dummy = 1
    #self.game_ended = True
    
    for i, choice in enumerate(choices):
      if choice == None:
        continue
      player = self.players[i]
      choicetype = choice['choicetype']
      choicetaken = choice['choice']
      if choicetype == GameState.choose_card_choice_type:
        units = [u for u in self.convoy.units if u.player == player.number ]
        #breakpoint()
        for i,ch in enumerate(choicetaken):
          units[i].actioncard = ch
          player.place_action_card(ch)
      elif choicetype == GameState.choose_action_choice_type:
        if self.convoy.units[self.convoy.current_actor].actiontaken is None:
          self.convoy.units[self.convoy.current_actor].actiontaken = choicetaken[0]
          self.convoy.resolve_action(self.convoy.current_actor)
        elif self.convoy.units[self.convoy.current_actor].secondactiontaken is None:
          self.convoy.units[self.convoy.current_actor].secondactiontaken = choicetaken[0]
          self.convoy.resolve_action(self.convoy.current_actor, second=True)
          
    if self.rounds.stage == 0:
      
    elif self.rounds.stage == 1:

    elif self.rounds.stage == 2 and self.convoy.current_actor is None:

      
    print(f"current game round and stage {self.rounds.count},{self.rounds.stage}")
    

  """
  def get_game_state(self, player=None):
    # Returns a dictionary of game states:
    # A unique game view for each player and possibly
    # a choice for one player

    
    await_actions = [None,None,None,None,None] #self.next_actions()

    deck_state = self.get_deck_state()

    if player is None:
      game_states = []
      for i,player in enumerate(self.players):
        game_state = { 'convoy' : self.convoy.to_json(playerview=player),
                                  'players' : self.players_to_json(playerview=player),
                      'decks': deck_state,
                      'resistance' : self.resistance.to_json() }
        if await_actions[i] is not None:
          game_state['choice'] = { 'options' : await_actions[i]['options'],
                                   'choicetype' : await_actions[i]['choicetype'],
                                   'description' : await_actions[i]['description'],
                                   'num_choice' : await_actions[i]['num_choice']}
        game_states.append(game_state)
      return game_states
    else:
        game_state = { 'convoy' : self.convoy.to_json(playerview=player),
                                  'players' : self.players_to_json(playerview=player),
                      'decks': deck_state,
                      'resistance' : self.resistance.to_json() }
        return game_state
        
  def get_deck_state(self):
    
    deck_state_json =  { 'action' : self.action_deck.to_json(),
                         'resistance' : self.resistance_deck.to_json(),
                         'pillage' : self.pillage_deck.to_json(),
                         'mauling' : self.mauling_deck.to_json() }
    queue_state_json = { 'resistance' : self.resistance_queue.to_arr(),
                         'pillage' : self.pillage_queue.to_arr(),
                         'mauling' : self.mauling_queue.to_arr() }

    return {'decks' : deck_state_json,
            'queues' : queue_state_json }
    
  def finalize_score(self):
    dummy = 1
  
  def save(self):
    dummy = 1

  def load(self):
    dummy = 1

  def players_to_json(self,playerview=None):
    return [player.to_json(playerview=playerview) for player in self.players]

  def players_to_str(self,playerview=None):
    return '\n'.join([player.to_str(playerview=playerview) for player in self.players])  
