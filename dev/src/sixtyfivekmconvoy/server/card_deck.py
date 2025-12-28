#! /usr/bin/env python3

"""
This module contains the CardDeck class for managing a deck of cards with shuffle, draw, and discard functionality.
"""

import random


class CardDeck:
  NO_CARD=0

  def __init__(self, number_of_cards, shuffled=True, names_and_effects=None):
    self.number_of_cards = number_of_cards
    #self.deck =  list(range(1,number_of_cards+1))
    self.deck =  list(range(number_of_cards))
    self.discard = []
    if shuffled:
      random.shuffle(self.deck)
    self.names_and_effects = names_and_effects
                      
  def get_card(self,shuffle_if_necessary = True):
    if len(self.deck) == 0:
      print("Shuffling deck")
      self.reshuffle()
    card = self.deck.pop(0)
    return card
  
  def return_card(self, card):
    self.deck = [card] + self.deck
                      
  def discard(self,card):
    self.discard.append(card)

  def reshuffle(self):
    assert (len(self.deck) == 0)
    self.deck = self.discard
    print(f"Reshuffling, deck size is {len(self.deck)}")
    random.shuffle(self.deck)
    self.discard = []

  def get_sizes(self):
    return len(self.deck), len(self.discard)

  def to_json(self):
    deckjson = { 'deck' : len(self.deck),
                 'discard' : len(self.discard) }
    return deckjson
  
  def to_str(self):
    deckstr = f"{len(self.deck)}D{len(self.discard)}"
    return deckstr

  def get_name(self, card):
    if self.names_and_effects:
      return self.names_and_effects[card]['name']

  def get_effect(self,card):
    if self.names_and_effects:
      return self.names_and_effects[card]['effect']

  def describe(self, card):
    return self.names_and_effects[card]
    
