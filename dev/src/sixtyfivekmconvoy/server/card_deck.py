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
      card_data = self.names_and_effects[card]
      # If it's a card object with a name attribute, return it
      if hasattr(card_data, 'name'):
        return card_data.name
      # Otherwise assume it's a dictionary
      elif isinstance(card_data, dict) and 'name' in card_data:
        return card_data['name']
    return None

  def get_effect(self, card):
    if self.names_and_effects:
      card_data = self.names_and_effects[card]
      # If it's a card object with an effect attribute, return it
      if hasattr(card_data, 'effect'):
        return card_data.effect
      # Otherwise assume it's a dictionary
      elif isinstance(card_data, dict) and 'effect' in card_data:
        return card_data['effect']
      # For ActionCard, get effect from actions
      elif hasattr(card_data, 'get_actions'):
        return None  # ActionCard doesn't have a single effect
    return None

  def describe(self, card):
    """Describe a card by calling its describe() method if available, otherwise return the card data."""
    card_data = self.names_and_effects[card]
    
    # If the card has a describe() method, call it
    if hasattr(card_data, 'describe'):
      return card_data.describe()

    
    # Otherwise return as-is (should be a dict or list for backward compatibility)
    return card_data
    
