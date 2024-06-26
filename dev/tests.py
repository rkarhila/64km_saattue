#!/usr/bin/env python3

from src.sixtyfivekmconvoy import playerconnector, gamestate, convoyclients

def test_game_init():
  playerconf = [ { 'playertype': 'random-terminal' },
                 { 'playertype': 'computer' },
                 { 'playertype': 'computer' } ]
  game = gamestate.GameState(playerconf, seed=None)
  game.finalize_setup()
  game.play()

"""
def test_game_init():
  playerconf = [ { 'playertype': 'terminal' },
                 { 'playertype': 'computer' },
                 { 'playertype': 'computer' } ]
  players = playerconnector.PlayerConnector(playerconf)
  game = gamestate.GameState(playerconnector)
  game.setup()
  game.play()


from src.sixyfivekmconvoy import convoyengine, gamestate, convoyclients


def test_game_init():
  playerconf = [ { 'playertype': 'terminal' },
                 { 'playertype': 'computer' },
                 { 'playertype': 'computer' } ]
  game = convoyengine.ConvoyEngine(playerconf)
  
if __name__ == 'main':
  test_game_init()

"""  

  
if __name__ == '__main__':
  test_game_init()
  
