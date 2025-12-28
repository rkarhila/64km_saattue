#!/usr/bin/env python3


class ActionCards:
  cards = { 0 : ActionCard(Actions.ATTACK,
                           'koukkaa oikealta', 
                           CardEffect(action=Actions.ATTACK,
                                      modifiers={Modifiers.DAMAGE = {Modifiers.ADD = 2 }} ) ), 
            1 : ActionCard(Actions.ATTACK,
                           'koukkaa vasemmalta', 
                           CardEffect(action=Actions.ATTACK,
                                      modifiers={Modifiers.DAMAGE = {Modifiers.ADD = 1 }} ) ), 
           }
