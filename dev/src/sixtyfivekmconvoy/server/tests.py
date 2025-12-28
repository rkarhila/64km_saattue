#!/usr/bin/env python3

from src.sixyfivekmconvoy import convoyengine, gamestate, convoyclients


def test_game_init():
  playerconf = [ { 'playertype': 'randomterminal' },
                 { 'playertype': 'computer' },
                 { 'playertype': 'computer' } ]
  game = convoyengine.ConvoyEngine(playerconf)
  
if __name__ == 'main':
  test_game_init()
  
