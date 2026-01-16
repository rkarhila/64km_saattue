#! /usr/bin/env python3

"""
This module contains the deck of officer cards for the game.

The card information is read from a separate CSV file and converted into a dictionary.

The deck is a dictionary of OfficerCard objects, where the key is the officer ID and the value is the OfficerCard object.

OfficerCard is a class representing a single officer card that can be attached to a unit.
"""

import csv
import os


class OfficerCard:
    """Represents an officer card that can be attached to a unit."""
    
    def __init__(self, officer_id, name, description, ability_type):
        """
        Initialize an OfficerCard.
        
        Args:
            officer_id: the unique ID of the officer (int)
            name: the name of the officer (string)
            description: description of the officer's ability (string)
            ability_type: the type of ability this officer grants (string)
        """
        self.officer_id = officer_id
        self.name = name
        self.description = description
        self.ability_type = ability_type
    
    def __str__(self):
        return f"OfficerCard({self.officer_id}): {self.name} - {self.description}"
    
    def __repr__(self):
        return self.__str__()
    
    def describe(self):
        """Return a dictionary describing this officer card."""
        return {
            'officer_id': self.officer_id,
            'name': self.name,
            'description': self.description,
            'ability_type': self.ability_type
        }


def _load_deck_from_csv():
    """
    Load the officer deck from the CSV file.
    
    The CSV format has:
        - officer_id: the officer ID (integer)
        - name: the name of the officer
        - description: description of the officer's ability
        - ability_type: the type of ability (sober_up, enhanced_attack, search_pillage_combo, atrocity_conversion, extra_carry_capacity)
    
    Returns a dictionary where keys are officer IDs and values are OfficerCard objects.
    """
    # Get the directory where this module is located
    module_dir = os.path.dirname(os.path.abspath(__file__))
    csv_path = os.path.join(module_dir, 'cards', 'officer.csv')
    
    deck = {}
    
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            officer_id = int(row['officer_id'].strip())
            name = row['name'].strip()
            description = row['description'].strip()
            ability_type = row['ability_type'].strip()
            
            deck[officer_id] = OfficerCard(
                officer_id=officer_id,
                name=name,
                description=description,
                ability_type=ability_type
            )
    
    return deck


class OfficerCardDeck:
    """
    Class containing the officer card deck.
    
    The deck is loaded from the CSV file when the class is defined.
    """
    
    deck = _load_deck_from_csv()

