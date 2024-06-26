#!/usr/bin/env python3


class Actions:  
  ATTACK   = 0
  OVERTAKE = 1
  SCOUT    = 2
  PILLAGE  = 3
  ESCAPE   = 4
  WAIT     = 5
  REST     = 6  

  def __init__():
    dummy = 1

class Modifiers:
   DAMAGE   = 0
   

class CardEffect:
  def __init__(actions, modifiers):
    self.actions = actions
    self.mod = modifiers  


class ActionCard:
  def __init__(base, special, effect):
    self.base = base
    self.special = special
    self.effect = effect

class ActionCards:
  cards = { 0 : ActionCard(Actions.ATTACK,
                           'koukkaa oikealta', 
                           CardEffect(action=Actions.ATTACK,
                                      modifiers={Modifiers.DAMAGE = '+2'} ) ) }
