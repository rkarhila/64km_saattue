#!/usr/bin/env python3

import re

class TerminalClient:
  def __init__(self, conf):
    self.conf = conf

  def push_info(self, game_state):
    #print(game_state)
    #breakpoint()
    if 'ascii' in game_state:
      if 'players' in game_state['ascii']:
        print(game_state['ascii']['players'])
      if 'decks' in game_state['ascii']:
        print(game_state['ascii']['decks'])
      if 'resistance' in game_state['ascii']:
        print(game_state['ascii']['resistance'])
        
    choice = None
    if 'convoy' in game_state['ascii']:
      print(game_state['ascii']['convoy'])
    if 'message' in game_state:
      print('BROADCAST:', game_state['message'])
    if 'choice' in game_state:
      print(game_state['choice']['description'])
      options=game_state['choice']['options']
      choicecount=game_state['choice']['num_choice']
      choice = None
      while not self.verify_input(choice,options, choicecount):
        print(f"Choose {choicecount} values from:", ','.join([str(c) for c in options]))
        choice = self.get_choice(input())
      return { 'choicetype' : game_state['choice']['choicetype'],
               'choice' : choice }
      
      print("press return to continue")
      input()
      return None
    
  def get_choice(self, input):
    if input[0] in '0123456789':
      return [int(c) for c in re.split('\D+', input)]
    else:
      return None
    
  def verify_input(self, choice, options, num_choices=1):
    if choice is None:
      return False
    else:
      if len(choice) != num_choices:
        if num_choices == 1:
          print(f"You choce {','.join([str(c) for c in choice])}. You must select a single option")
        else:
          print(f"You choce {','.join([str(c) for c in choice])}. You must select {num_choices} options (separate with non-digit)")
        return False
      if len(choice) != len(list(set(choice))):
        print("You choce {','.join(choice)}. You cannot choose the same option twice")
        return False
      for op in choice:
        if op not in options:
          print(f"You choce {','.join([str(c) for c in choice])}. Value {op} not in options!")
          return False
      return True        
    

import random

class VerboseRandomClient:
    
  def __init__(self, conf):
    self.conf = conf
    
  def push_info(self, game_state):
    if 'choice' in game_state:
      if 'ascii' in game_state:
        if 'players' in game_state['ascii']:
          print(game_state['ascii']['players'])
        if 'decks' in game_state['ascii']:
          print(game_state['ascii']['decks'])
        if 'resistance' in game_state['ascii']:
          print(game_state['ascii']['resistance'])

      if 'convoy' in game_state['ascii']:
        print(game_state['ascii']['convoy'])
    if 'message' in game_state:
      print('BROADCAST:', game_state['message'])

      
    if 'choice' in game_state:
      
      #print(game_state['choice']['description'])
      options=game_state['choice']['options']
      choicecount=game_state['choice']['num_choice']
      random.shuffle(options)
      choice = options[:choicecount]
      print(game_state['choice']['description'])
      print(f"You choce {','.join([str(c) for c in choice])}")

      #print("press return to continue")
      #input()

      return { 'choicetype' : game_state['choice']['choicetype'],
               'choice' : choice }
    #else:
      #print("press return to continue")
      #input()

  def await_choice(self, candidates):
    choice = random.choice(candidates.options)
    return choice

    
class SocketClient:

  socket = None

  def __init__(self, conf):
    self.conf = conf
    self.socket = None 

  def push_info(self, state):
    self.socket.send(state)

  def await_choice(self, candidates):
    self.socket.send(candidates)
    choice = self.socket.wait()
    return choice 



class MLClient:
    
  def __init__(self, conf):
    self.conf = conf
    
  def push_info(self, game_state):
    if 'choice' in game_state:
      
      #print(game_state['choice']['description'])
      options=game_state['choice']['options']
      choicecount=game_state['choice']['num_choice']
      random.shuffle(options)
      choice = options[:choicecount]
      return { 'choicetype' : game_state['choice']['choicetype'],
               'choice' : choice }
      
  def await_choice(self, candidates):
    choice = random.choice(candidates.options)
    return choice
