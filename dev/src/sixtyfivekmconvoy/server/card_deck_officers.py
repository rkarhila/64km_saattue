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
    
    def __init__(self, officer_id, name, passive_effect, discard_effect, passive_description, discard_description,
                 troop_type=None, zone=None, action_type=None, action_modifier=None, cost=None, tire=None, intoxicate=None):
        """
        Initialize an OfficerCard.
        
        Args:
            officer_id: the unique ID of the officer (int)
            name: the name of the officer (string)
            passive_effect: the passive ability type (string)
            discard_effect: the discard ability type (string)
            passive_description: description of the passive ability (string)
            discard_description: description of the discard ability (string)
            troop_type: troop type restriction for discard effect (string, e.g., 'A', 'I', 'P', 'L')
            zone: zone restriction for discard effect (string, e.g., 'A', 'B', 'C', 'E')
            action_type: action name for discard effect (string)
            action_modifier: modifier value for discard effect (int or None)
            cost: cost for discard effect (string, e.g., 'T', '0', '1')
            tire: tire effect for discard effect (int or None)
            intoxicate: intoxicate effect for discard effect (int or None)
        """
        self.officer_id = officer_id
        self.name = name
        self.passive_effect = passive_effect
        self.discard_effect = discard_effect
        self.passive_description = passive_description
        self.discard_description = discard_description
        self.troop_type = troop_type
        self.zone = zone
        self.action_type = action_type
        self.action_modifier = action_modifier
        self.cost = cost
        self.tire = tire
        self.intoxicate = intoxicate
    
    def __str__(self):
        return f"OfficerCard({self.officer_id}): {self.name}"
    
    def __repr__(self):
        return self.__str__()
    
    def describe(self):
        """Return a dictionary describing this officer card."""
        return {
            'officer_id': self.officer_id,
            'name': self.name,
            'passive_effect': self.passive_effect,
            'discard_effect': self.discard_effect,
            'passive_description': self.passive_description,
            'discard_description': self.discard_description,
            'troop_type': self.troop_type,
            'zone': self.zone,
            'action_type': self.action_type,
            'action_modifier': self.action_modifier,
            'cost': self.cost,
            'tire': self.tire,
            'intoxicate': self.intoxicate
        }
    
    def get_discard_action_description(self):
        """Return an action description dictionary for the discard effect, if it exists."""
        if not self.discard_effect or not self.action_type:
            return None
        
        return {
            'name': self.action_type,
            'action_name': self.action_type,
            'action_modifier': self.action_modifier if self.action_modifier is not None else 0,
            'zone': self.zone if self.zone else '',
            'troop_type': self.troop_type if self.troop_type else 'A',
            'cost': self.cost if self.cost else '0',
            'tire': self.tire if self.tire is not None else 0,
            'intoxicate': self.intoxicate if self.intoxicate is not None else 0,
            'is_officer_discard': True,
            'officer': self
        }


def _load_deck_from_csv():
    """
    Load the officer deck from the CSV file.
    
    The CSV format has:
        - officer_id: the officer ID (integer)
        - name: the name of the officer
        - passive_effect: the passive ability type (string)
        - discard_effect: the discard ability type (string)
        - passive_description: description of the passive ability (string)
        - discard_description: description of the discard ability (string)
    
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
            passive_effect = row['passive_effect'].strip() if row['passive_effect'].strip() else None
            discard_effect = row['discard_effect'].strip() if row['discard_effect'].strip() else None
            passive_description = row['passive_description'].strip() if row['passive_description'].strip() else ''
            discard_description = row['discard_description'].strip() if row['discard_description'].strip() else ''
            
            # Parse action-related fields for discard effects
            troop_type = row.get('troop_type', '').strip() if row.get('troop_type', '').strip() else None
            zone = row.get('zone', '').strip() if row.get('zone', '').strip() else None
            action_type = row.get('action_type', '').strip() if row.get('action_type', '').strip() else None
            action_modifier = int(row['action_modifier'].strip()) if row.get('action_modifier', '').strip() else None
            cost = row.get('cost', '').strip() if row.get('cost', '').strip() else None
            tire = int(row['tire'].strip()) if row.get('tire', '').strip() else None
            intoxicate = int(row['intoxicate'].strip()) if row.get('intoxicate', '').strip() else None
            
            deck[officer_id] = OfficerCard(
                officer_id=officer_id,
                name=name,
                passive_effect=passive_effect,
                discard_effect=discard_effect,
                passive_description=passive_description,
                discard_description=discard_description,
                troop_type=troop_type,
                zone=zone,
                action_type=action_type,
                action_modifier=action_modifier,
                cost=cost,
                tire=tire,
                intoxicate=intoxicate
            )
    
    return deck


class OfficerCardDeck:
    """
    Class containing the officer card deck.
    
    The deck is loaded from the CSV file when the class is defined.
    """
    
    deck = _load_deck_from_csv()


