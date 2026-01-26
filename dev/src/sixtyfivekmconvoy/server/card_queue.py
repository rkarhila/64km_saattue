#! /usr/bin/env python3

"""
This module contains the CardQueue class for managing a queue of cards with visibility control.
"""


class CardQueue:
  
  def __init__(self, number_of_cards, deck=None):
    self.cards_and_visibilities = []
    self.deck = deck

  def remove_card(self, index=0):
    card, visibility = self.cards_and_visibilities.pop(index)
    return card, visibility
  
  def put_card(self, card, visible=False):
    self.cards_and_visibilities.append([card, visible])
    
  def return_card(self, card, visible=False):
    self.cards_and_visibilities = [[card,visible]] + self.cards_and_visibilities 
  def contains_hidden_cards(self):
    for card, visible in self.cards_and_visibilities:
      if not visible:
        return True
    return False

    
  def reveal_card(self, index=0):
    self.cards_and_visibilities[index][1] = True
 
  def reveal_next_hidden(self):
    for index, card_and_visible in enumerate(self.cards_and_visibilities):
      if not card_and_visible[1]:        
        self.cards_and_visibilities[index][1] = True
        break
    
  def to_arr(self):
    if self.deck is not None and self.deck.names_and_effects is not None:
      # Use the card ID (c[0]) to get the name, not the enumeration index
      queuearr = [ self.deck.get_name(c[0]) if c[1] else '?' for c in self.cards_and_visibilities]
    else:
      queuearr = [ c[0] if c[1] else '?' for c in self.cards_and_visibilities]

    return queuearr

  def describe(self, index):
    if self.deck is not None:
      return self.deck.describe(self.cards_and_visibilities[index][0])
    

