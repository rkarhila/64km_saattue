
    # Actions string:
    #   B=1 bypass : move forward 1
    #   B=2 bypass : move forward 2
    #   P+0  pillage
    #   P+1 pillage, with extra card
    #   A+2  attack with +2 damage
    #   A+1  attack with +1 damage
    #   A+0    normal attack
    #   A-1  attack with -1 damage
    #   A=4  fixed 4 damage (independent of troop type)
    #   R=1  reverse : move backward 1
    #   S+1 scout, reveal and reorder 1-4 card
    #   S+0   scout, reveal and reorder 1-3 cards
    #   S-1 scout, reveal and reorder 1-2 cards
    #   Z..  rest ('zzz')
    #   Dr. defend against resistance
    #   Da. defend against aerial attacks
    #   Dg. defend against ground attack
    #   Dt. defend against traps
    #   Dg. defend against guerilla activity



class CardDeckActions:

  basic_attack_action = {'cost': 'TUU',
                         'effect': 'A+0',
                         'limits': {'I': 'A', 'P': 'AB'},
                         'name': 'Hyökkää'}

  basic_overtake_action = {'cost': 'TU',
                           'effect': 'B=1',
                           'limits': {'I': 'ABCE', 'P': 'ABCE', 'L':'ABCE'},
                           'name': 'Ohita'}

  basic_scout_action = {'cost': 'TUUU',
                        'effect': 'S+0',
                        'limits': {'I': 'A'},
                        'name': 'Tiedustele'}

  basic_pillage_action = {'cost': 'T',
                          'effect': 'P+0',
                          'limits': {'I': 'ABCE', 'P': 'ABCE', 'L':'ABCE'},
                          'name': 'Ryöstele'}
  
  deck = {0: [{'cost': 'T2UU',
               'effect': 'A+2',
               'limits': {'I': 'A'},
               'name': 'Koukkaa vasemmalta'},
              basic_attack_action],
          1: [{'cost': 'T1UU',
               'effect': 'A+1',
               'limits': {'I': 'A'},
               'name': 'Koukkaa oikealta'},
              basic_attack_action],
          2: [{'cost': 'T',
               'effect': 'A-1',
               'limits': {'I': 'A'},
               'name': 'Ei nuoret henkilöt, ei sotaa noin käydä'},
              basic_attack_action],
          3: [{'cost': 'T2UU',
               'effect': 'A+2',
               'limits': {'P': 'AB'},
               'name': 'Patton olisi ylpeä'},
              basic_attack_action],
          4: [{'cost': 'T1UU',
               'effect': 'A+2',
               'limits': {'P': 'AB'},
               'name': 'Rommel olisi ylpeä'},
              basic_attack_action],
          5: [{'cost': 'T',
               'effect': '',
               'limits': {'P': 'AB'},
               'name': 'Todistakaa! Keskinkertaista panssarisodankäyntiä'},
              basic_attack_action],
          6: [{'cost': '4',
               'effect': 'A=4',
               'limits': {'I': 'ABCE', 'L': 'ABCE', 'P': 'ABCE'},
               'name': 'Ilmaiskuja'},
              basic_attack_action],
          7: [{'cost': 'TUU',
               'effect': 'A=4',
               'limits': {'I': 'ABCE', 'L': 'ABCE', 'P': 'ABCE'},
               'name': 'Ilmahyökkäys'},
              basic_attack_action],
          8: [{'cost': 'T1U',
               'effect': 'B=2',
               'limits': {'I': 'ABCE', 'L': 'ABCE', 'P': 'ABCE'},
               'name': 'Latua prkl!'},
              basic_overtake_action],
          9: [{'cost': 'T1U',
               'effect': 'B-1',
               'limits': {'I': 'ABCE', 'L': 'ABCE', 'P': 'ABCE'},
               'name': 'Peruuta'},
              basic_overtake_action],
          10: [{'cost': 'T1U',
                'effect': 'B-1',
                'limits': {'I': 'ABCE', 'L': 'ABCE', 'P': 'ABCE'},
                'name': 'Sekaannus etenemissuunnasta'},
               basic_overtake_action],
          11: [{'cost': 'T1U',
                'effect': 'B=2',
                'limits': {'I': 'ABCE', 'L': 'ABCE', 'P': 'ABCE'},
                'name': 'Törkeä liikenteen vaarantaminen'},
               basic_overtake_action],
          12: [{'cost': 'TUU',
                'effect': 'B=2',
                'limits': {'I': 'ABCE', 'L': 'ABCE', 'P': 'ABCE'},
                'name': 'Vaarallinen käytös liikenteessä'},
               basic_overtake_action],
          13: [{'cost': 'T2U',
                'effect': 'ESC',
                'limits': {'I': 'E', 'L': 'E', 'P': 'E'},
                'name': 'Ei vain kertakaikkiaan jaksa enää'},
               basic_overtake_action],
          14: [{'cost': 'T2U',
                'effect': 'ESC',
                'limits': {'I': 'E', 'L': 'E', 'P': 'E'},
                'name': 'Reippain mielin kotimatkalle'},
               basic_overtake_action],
          15: [{'cost': 'T2U',
                'effect': 'ESC',
                'limits': {'I': 'E', 'L': 'E', 'P': 'E'},
                'name': 'Sayonara, suckers!'},
               basic_overtake_action],
          16: [{'cost': 'TUU',
                'effect': 'A=4',
                'limits': {'I': 'ABCE', 'L': 'ABCE', 'P': 'ABCE'},
                'name': 'Haukansilmillä'},
               basic_scout_action],
          17: [{'cost': 'TUU',
                'effect': 'A=4',
                'limits': {'I': 'ABCE', 'L': 'ABCE', 'P': 'ABCE'},
                'name': 'Samoilla silmillä'},
               basic_scout_action],
          18: [{'cost': 'TUU',
                'effect': 'A=4',
                'limits': {'I': 'ABCE', 'L': 'ABCE', 'P': 'ABCE'},
                'name': 'Neuvoa-antava'},
               basic_scout_action],
          19: [{'cost': 'TUU',
                'effect': 'A=4',
                'limits': {'I': 'ABCE', 'L': 'ABCE', 'P': 'ABCE'},
                'name': 'Toinen aamiainen'},
               basic_scout_action],
          20: [{'cost': 'TUU',
                'effect': 'A=4',
                'limits': {'I': 'ABCE', 'L': 'ABCE', 'P': 'ABCE'},
                'name': 'Körssitauko'},
               basic_scout_action],
          21: [{'cost': 'TUU',
                'effect': 'A=4',
                'limits': {'I': 'ABCE', 'L': 'ABCE', 'P': 'ABCE'},
                'name': 'Jahtiryyppy'},
               basic_scout_action],
          22: [{'cost': 'TUU',
                'effect': 'A=4',
                'limits': {'I': 'ABCE', 'L': 'ABCE', 'P': 'ABCE'},
                'name': 'Vartioi'},
               basic_scout_action],
          23: [{'cost': 'TUU',
                'effect': 'A=4',
                'limits': {'I': 'ABCE', 'L': 'ABCE', 'P': 'ABCE'},
                'name': 'Partioi'},
               basic_scout_action],
          24: [{'cost': 'TUU',
                'effect': 'A=4',
                'limits': {'I': 'ABCE', 'L': 'ABCE', 'P': 'ABCE'},
                'name': 'Jalkaväkirynnäkkö!'},
               basic_attack_action],
          25: [{'cost': 'TUU',
                'effect': 'A=4',
                'limits': {'I': 'ABCE', 'L': 'ABCE', 'P': 'ABCE'},
                'name': 'Panssarirynnäkkö!'},
               basic_attack_action],
          26: [{'cost': 'TUU',
                'effect': 'A=4',
                'limits': {'I': 'ABCE', 'L': 'ABCE', 'P': 'ABCE'},
                'name': 'Miinaharavointia ja muita klassikoita'},
               basic_scout_action],
          27: [{'cost': 'TUU',
                'effect': 'A=4',
                'limits': {'I': 'ABCE', 'L': 'ABCE', 'P': 'ABCE'},
                'name': 'Suojatulta'},
               basic_overtake_action],
          28: [{'cost': 'TUU',
                'effect': 'A=4',
                'limits': {'I': 'ABCE', 'L': 'ABCE', 'P': 'ABCE'},
                'name': 'Iloinen kotimatka'},
               basic_overtake_action],
          29: [{'cost': 'TUU',
                'effect': 'A=4',
                'limits': {'I': 'ABCE', 'L': 'ABCE', 'P': 'ABCE'},
                'name': 'Maalita'},
               basic_scout_action],
          30: [{'cost': 'TUU',
                'effect': 'A=4',
                'limits': {'I': 'ABCE', 'L': 'ABCE', 'P': 'ABCE'},
                'name': 'Enemmän kuin irti lähtee'},
               basic_pillage_action],
          31: [{'cost': 'TUU',
                'effect': 'A=4',
                'limits': {'I': 'ABCE', 'L': 'ABCE', 'P': 'ABCE'},
                'name': 'Kapasiteetin rajoilla'},
               basic_pillage_action],
          32: [{'cost': 'TUU',
                'effect': 'A=4',
                'limits': {'I': 'ABCE', 'L': 'ABCE', 'P': 'ABCE'},
                'name': 'Miinoita'},
               basic_pillage_action],
          33: [{'cost': 'TUU',
                'effect': 'A=4',
                'limits': {'I': 'ABCE', 'L': 'ABCE', 'P': 'ABCE'},
                'name': 'Ihmiskilpiä'},
               basic_pillage_action],
          34: [{'cost': 'TUU',
                'effect': 'A=4',
                'limits': {'I': 'ABCE', 'L': 'ABCE', 'P': 'ABCE'},
                'name': 'Erikoisen kurinalaista toimintaa'},
               basic_pillage_action],
          35: [{'cost': 'TUU',
                'effect': 'A=4',
                'limits': {'I': 'ABCE', 'L': 'ABCE', 'P': 'ABCE'},
                'name': 'Kohteliaasti kännissä'},
               basic_pillage_action],
          36: [{'cost': 'TUU',
                'effect': 'A=4',
                'limits': {'I': 'ABCE', 'L': 'ABCE', 'P': 'ABCE'},
                'name': 'Sivutie'},
               basic_pillage_action],
          37: [{'cost': 'TUU',
                'effect': 'A=4',
                'limits': {'I': 'ABCE', 'L': 'ABCE', 'P': 'ABCE'},
                'name': 'Väärä risteys'},
               basic_pillage_action],
          38: [{'cost': '',
                'effect': 'Z--',
                'limits': {'I': 'ABCE', 'L': 'ABCE', 'P': 'ABCE'},
                'name': 'Telttaretki'},
               {'cost': '2',
                'effect': 'Z2c',
                'limits': {'I': 'A', 'P': 'AB'},
                'name': 'tuplalepo'}],
          39: [{'cost': '',
                'effect': 'Z--',
                'limits': {'I': 'ABCE', 'L': 'ABCE', 'P': 'ABCE'},
                'name': 'Juomatauko'},
               {'cost': '2',
                'effect': 'Z2c',
                'limits': {'I': 'ABCE', 'L': 'ABCE', 'P': 'ABCE'},
                'name': 'tuplalepo'}],
          40: [{'cost': '',
                'effect': 'Z--',
                'limits': {'I': 'ABCE', 'L': 'ABCE', 'P': 'ABCE'},
                'name': 'Unilinna'},
               {'cost': '2',
                'effect': 'Z2c',
                'limits': {'I': 'ABCE', 'L': 'ABCE', 'P': 'ABCE'},
                'name': 'tuplalepo'}],
          41: [{'cost': '',
                'effect': 'Z--',
                'limits': {'I': 'ABCE', 'L': 'ABCE', 'P': 'ABCE'},
                'name': 'Lomamatka'},
               {'cost': '2',
                'effect': 'Z2c',
                'limits': {'I': 'ABCE', 'L': 'ABCE', 'P': 'ABCE'},
                'name': 'tuplalepo'}],
          42: [{'cost': '',
                'effect': 'Z--',
                'limits': {'I': 'ABCE', 'L': 'ABCE', 'P': 'ABCE'},
                'name': 'Kesäolympialaiset'},
               {'cost': '2',
                'effect': 'Z2c',
                'limits': {'I': 'ABCE', 'L': 'ABCE', 'P': 'ABCE'},
                'name': 'tuplalepo'}],
          43: [{'cost': '',
                'effect': 'Z--',
                'limits': {'I': 'ABCE', 'L': 'ABCE', 'P': 'ABCE'},
                'name': 'Virkisty radalla'},
               {'cost': '2',
                'effect': 'Z2c',
                'limits': {'I': 'ABCE', 'L': 'ABCE', 'P': 'ABCE'},
                'name': 'tuplalepo'}],
          44: [{'cost': '',
                'effect': 'Z--',
                'limits': {'I': 'ABCE', 'L': 'ABCE', 'P': 'ABCE'},
                'name': 'Suunnistuskilpailu'},
               {'cost': '2',
                'effect': 'Z2c',
                'limits': {'I': 'ABCE', 'L': 'ABCE', 'P': 'ABCE'},
                'name': 'tuplalepo'}],
          45: [{'cost': '',
                'effect': 'Z--',
                'limits': {'I': 'ABCE', 'L': 'ABCE', 'P': 'ABCE'},
                'name': 'Lootusasentoon'},
               {'cost': '2',
                'effect': 'Z2c',
                'limits': {'I': 'ABCE', 'L': 'ABCE', 'P': 'ABCE'},
                'name': 'tuplalepo'}],
          46: [{'cost': '',
                'effect': 'Z--',
                'limits': {'I': 'ABCE', 'L': 'ABCE', 'P': 'ABCE'},
                'name': 'Työkykypäivä'},
               {'cost': '2',
                'effect': 'Z2c',
                'limits': {'I': 'ABCE', 'L': 'ABCE', 'P': 'ABCE'},
                'name': 'tuplalepo'}],
          47: [{'cost': '',
                'effect': 'Z--',
                'limits': {'I': 'ABCE', 'L': 'ABCE', 'P': 'ABCE'},
                'name': 'Palaututtavat'},
               {'cost': '2',
                'effect': 'Z2c',
                'limits': {'I': 'ABCE', 'L': 'ABCE', 'P': 'ABCE'},
                'name': 'tuplalepo'}],
          48: [{'cost': 'TUU',
                'effect': 'A=4',
                'limits': {'I': 'ABCE', 'L': 'ABCE', 'P': 'ABCE'},
                'name': 'Pikku piipahdus'},
               basic_pillage_action],
          49: [{'cost': 'TUU',
                'effect': 'A=4',
                'limits': {'I': 'ABCE', 'L': 'ABCE', 'P': 'ABCE'},
                'name': 'Kohteliaasti kylässä'},
               basic_pillage_action]}

  
  deck_old = { 0 : {'name' : ['Koukkaa vasemmalta','Hyökkää'],
                'effect' : ['A+2', 'A+0'] ,
                'limits' : [{'I':'A'}, {'I':'A', 'P':'AB'}],
                'cost' : ['T2UU','TUU'] },
           1 : {'name' : ['Koukkaa oikealta','Hyökkää'],
                'effect' : ['A+1', 'A+0'],
                'limits' : [{'I':'A'}, {'I':'A', 'P':'AB'}],
                'cost' : ['T1UU','TUU'] },
           2 : {'name' : ['Ei nuoret henkilöt, ei sotaa noin käydä','Hyökkää'],
                'effect' : ['A-1', 'A+0'],
                'limits' : [{'I':'A'}, {'I':'A', 'P':'AB'}],
                'cost' : ['T','TUU']},
           3 : {'name' : ['Patton olisi ylpeä','Hyökkää'],
                'effect' : ['A+2', 'A+0'],
                'limits' : [{'P':'AB'}, {'I':'A', 'P':'AB'}],
                'cost' : ['T2UU','TUU'] },
           4 : {'name' : ['Rommel olisi ylpeä','Hyökkää'],
                'effect' : ['A+2', 'A+0'],
                'limits' : [{'P':'AB'}, {'I':'A', 'P':'AB'}],
                'cost' : ['T1UU','TUU'] },
           5 : {'name' : ['Todistakaa! Keskinkertaista panssarisodankäyntiä','Hyökkää'],
                'effect' : ['', ''],
                'limits' : [{'P':'AB'}, {'I':'A', 'P':'AB'}],
                'cost' : ['T','TUU'] },
           6 : {'name' : ['Ilmaiskuja','Hyökkää'],
                'effect' : ['A=4', 'A+0'],
                'limits' : [{'P':'ABCE', 'I':'ABCE', 'L': 'ABCE'}, {'I':'A', 'P':'AB'}],
                'cost' : ['TUU','TUU'] },
           7 : {'name' : ['Ilmahyökkäys','Hyökkää'],
                'effect' : ['A=4', 'A+0'],
                'limits' : [{'P':'ABCE', 'I':'ABCE', 'L': 'ABCE'}, {'I':'A', 'P':'AB'}],
                'cost' : ['TUU','TUU'] },
           8 : {'name' : ['Latua prkl!','Ohita'],
                'effect' : ['A=4', 'A+0'],
                'limits' : [{'P':'ABCE', 'I':'ABCE', 'L': 'ABCE'}, {'I':'A', 'P':'AB'}],
                'cost' : ['TUU','TUU'] },
           9 : {'name' : ['Peruuta','Ohita'],
                'effect' : ['A=4', 'A+0'],
                'limits' : [{'P':'ABCE', 'I':'ABCE', 'L': 'ABCE'}, {'I':'A', 'P':'AB'}],
                'cost' : ['TUU','TUU'] },
           10: {'name' : ['Sekaannus etenemissuunnasta','Ohita'],
                'effect' : ['A=4', 'A+0'],
                'limits' : [{'P':'ABCE', 'I':'ABCE', 'L': 'ABCE'}, {'I':'A', 'P':'AB'}],
                'cost' : ['TUU','TUU'] },
           11 : {'name' : ['Törkeä liikenteen vaarantaminen','Ohita'],
                'effect' : ['A=4', 'A+0'],
                'limits' : [{'P':'ABCE', 'I':'ABCE', 'L': 'ABCE'}, {'I':'A', 'P':'AB'}],
                'cost' : ['TUU','TUU'] },
           12 : {'name' : ['Vaarallinen käytös liikenteessä','Ohita'],
                'effect' : ['A=4', 'A+0'],
                'limits' : [{'P':'ABCE', 'I':'ABCE', 'L': 'ABCE'}, {'I':'A', 'P':'AB'}],
                'cost' : ['TUU','TUU'] },
           13 : {'name' : ['Ei vain kertakaikkiaan jaksa enää','Ohita'],
                'effect' : ['A=4', 'A+0'],
                'limits' : [{'P':'ABCE', 'I':'ABCE', 'L': 'ABCE'}, {'I':'A', 'P':'AB'}],
                'cost' : ['TUU','TUU'] },
           14 : {'name' : ['Reippain mielin kotimatkalle',''],
                'effect' : ['A=4', 'A+0'],
                'limits' : [{'P':'ABCE', 'I':'ABCE', 'L': 'ABCE'}, {'I':'A', 'P':'AB'}],
                'cost' : ['TUU','TUU'] },
           15 : {'name' : ['Sayonara, suckers!','Ohita'],
                'effect' : ['A=4', 'A+0'],
                'limits' : [{'P':'ABCE', 'I':'ABCE', 'L': 'ABCE'}, {'I':'A', 'P':'AB'}],
                'cost' : ['TUU','TUU'] },
           16 : {'name' : ['Haukansilmillä','Tiedustele'],
                'effect' : ['A=4', 'A+0'],
                'limits' : [{'P':'ABCE', 'I':'ABCE', 'L': 'ABCE'}, {'I':'A', 'P':'AB'}],
                'cost' : ['TUU','TUU'] },
           17 : {'name' : ['Samoilla silmillä','Tiedustele'],
                'effect' : ['A=4', 'A+0'],
                'limits' : [{'P':'ABCE', 'I':'ABCE', 'L': 'ABCE'}, {'I':'A', 'P':'AB'}],
                'cost' : ['TUU','TUU'] },
           18 : {'name' : ['Neuvoa-antava','Tiedustele'],
                'effect' : ['A=4', 'A+0'],
                'limits' : [{'P':'ABCE', 'I':'ABCE', 'L': 'ABCE'}, {'I':'A', 'P':'AB'}],
                'cost' : ['TUU','TUU'] },
           19 : {'name' : ['Toinen aamiainen','Tiedustele'],
                'effect' : ['A=4', 'A+0'],
                'limits' : [{'P':'ABCE', 'I':'ABCE', 'L': 'ABCE'}, {'I':'A', 'P':'AB'}],
                'cost' : ['TUU','TUU'] },
           20:  {'name' : ['Körssitauko','Tiedustele'],
                'effect' : ['A=4', 'A+0'],
                'limits' : [{'P':'ABCE', 'I':'ABCE', 'L': 'ABCE'}, {'I':'A', 'P':'AB'}],
                'cost' : ['TUU','TUU'] },
           21 : {'name' : ['Jahtiryyppy','Tiedustele'],
                'effect' : ['A=4', 'A+0'],
                'limits' : [{'P':'ABCE', 'I':'ABCE', 'L': 'ABCE'}, {'I':'A', 'P':'AB'}],
                'cost' : ['TUU','TUU'] },
           22 : {'name' : ['Vartioi','Tiedustele'],
                'effect' : ['A=4', 'A+0'],
                'limits' : [{'P':'ABCE', 'I':'ABCE', 'L': 'ABCE'}, {'I':'A', 'P':'AB'}],
                'cost' : ['TUU','TUU'] },
           23 : {'name' : ['Partioi','Tiedustele'],
                'effect' : ['A=4', 'A+0'],
                'limits' : [{'P':'ABCE', 'I':'ABCE', 'L': 'ABCE'}, {'I':'A', 'P':'AB'}],
                'cost' : ['TUU','TUU'] },
           24 : {'name' : ['Jalkaväkirynnäkkö!','Hyökkää'],
                'effect' : ['A=4', 'A+0'],
                'limits' : [{'P':'ABCE', 'I':'ABCE', 'L': 'ABCE'}, {'I':'A', 'P':'AB'}],
                'cost' : ['TUU','TUU'] },
           25 : {'name' : ['Panssarirynnäkkö!','Hyökkää'],
                'effect' : ['A=4', 'A+0'],
                'limits' : [{'P':'ABCE', 'I':'ABCE', 'L': 'ABCE'}, {'I':'A', 'P':'AB'}],
                'cost' : ['TUU','TUU'] },
           26 : {'name' : ['Miinaharavointia ja muita klassikoita','Tiedustele'],
                'effect' : ['A=4', 'A+0'],
                'limits' : [{'P':'ABCE', 'I':'ABCE', 'L': 'ABCE'}, {'I':'A', 'P':'AB'}],
                'cost' : ['TUU','TUU'] },
           27 : {'name' : ['Suojatulta','Ohita'],
                'effect' : ['A=4', 'A+0'],
                'limits' : [{'P':'ABCE', 'I':'ABCE', 'L': 'ABCE'}, {'I':'A', 'P':'AB'}],
                'cost' : ['TUU','TUU'] },
           28 : {'name' : ['Iloinen kotimatka','Ohita'],
                'effect' : ['A=4', 'A+0'],
                'limits' : [{'P':'ABCE', 'I':'ABCE', 'L': 'ABCE'}, {'I':'A', 'P':'AB'}],
                'cost' : ['TUU','TUU'] },
           29 : {'name' : ['Maalita','Tiedustele'],
                'effect' : ['A=4', 'A+0'],
                'limits' : [{'P':'ABCE', 'I':'ABCE', 'L': 'ABCE'}, {'I':'A', 'P':'AB'}],
                'cost' : ['TUU','TUU'] },
           30 : {'name' : ['Enemmän kuin irti lähtee','Ryöstele'],
                'effect' : ['A=4', 'A+0'],
                'limits' : [{'P':'ABCE', 'I':'ABCE', 'L': 'ABCE'}, {'I':'A', 'P':'AB'}],
                'cost' : ['TUU','TUU'] },
           31 : {'name' : ['Kapasiteetin rajoilla','Ryöstele'],
                'effect' : ['A=4', 'A+0'],
                'limits' : [{'P':'ABCE', 'I':'ABCE', 'L': 'ABCE'}, {'I':'A', 'P':'AB'}],
                'cost' : ['TUU','TUU'] },
           32 : {'name' : ['Miinoita','Ryöstele'],
                'effect' : ['A=4', 'A+0'],
                'limits' : [{'P':'ABCE', 'I':'ABCE', 'L': 'ABCE'}, {'I':'A', 'P':'AB'}],
                'cost' : ['TUU','TUU'] },
           33 : {'name' : ['Ihmiskilpiä','Ryöstele'],
                'effect' : ['A=4', 'A+0'],
                'limits' : [{'P':'ABCE', 'I':'ABCE', 'L': 'ABCE'}, {'I':'A', 'P':'AB'}],
                'cost' : ['TUU','TUU'] },
           34 : {'name' : ['Erikoisen kurinalaista toimintaa','Ryöstele'],
                'effect' : ['A=4', 'A+0'],
                'limits' : [{'P':'ABCE', 'I':'ABCE', 'L': 'ABCE'}, {'I':'A', 'P':'AB'}],
                'cost' : ['TUU','TUU'] },
           35 : {'name' : ['Kohteliaasti kännissä','Ryöstele'],
                'effect' : ['A=4', 'A+0'],
                'limits' : [{'P':'ABCE', 'I':'ABCE', 'L': 'ABCE'}, {'I':'A', 'P':'AB'}],
                'cost' : ['TUU','TUU'] },
           36 : {'name' : ['Sivutie','Ryöstele'],
                'effect' : ['A=4', 'A+0'],
                'limits' : [{'P':'ABCE', 'I':'ABCE', 'L': 'ABCE'}, {'I':'A', 'P':'AB'}],
                'cost' : ['TUU','TUU'] },
           37 : {'name' : ['Väärä risteys','Ryöstele'],
                'effect' : ['A=4', 'A+0'],
                'limits' : [{'P':'ABCE', 'I':'ABCE', 'L': 'ABCE'}, {'I':'A', 'P':'AB'}],
                'cost' : ['TUU','TUU'] },
           38 : {'name' : ['Telttaretki', 'tuplalepo'], 'effect' : ['Z--', 'Z2c'], 'limits' : [{'P':'ABCE', 'I':'ABCE', 'L': 'ABCE'}, {'I':'A', 'P':'AB'}],
                'cost' : ['TUU','TUU'] },
           39 : {'name' : ['Juomatauko', 'tuplalepo'], 'effect' : [ 'Z--', 'Z2c'], 'limits' : [{'P':'ABCE', 'I':'ABCE', 'L': 'ABCE'}, {'I':'A', 'P':'AB'}],
                'cost' : ['TUU','TUU'] },
           40 : {'name' : ['Unilinna', 'tuplalepo'], 'effect' : [ 'Z--', 'Z2c'], 'limits' : [{'P':'ABCE', 'I':'ABCE', 'L': 'ABCE'}, {'I':'A', 'P':'AB'}],
                'cost' : ['TUU','TUU'] },
           41 : {'name' : ['Lomamatka', 'tuplalepo'], 'effect' : [ 'Z--', 'Z2c'], 'limits' : [{'P':'ABCE', 'I':'ABCE', 'L': 'ABCE'}, {'I':'A', 'P':'AB'}],
                'cost' : ['TUU','TUU'] },
           42 : {'name' : ['Kesäolympialaiset', 'tuplalepo'], 'effect' : [ 'Z--', 'Z2c'], 'cost' : ['0','2'], 'limits' : [{'P':'ABCE', 'I':'ABCE', 'L': 'ABCE'}, {'I':'A', 'P':'AB'}],
                'cost' : ['TUU','TUU'] },
           43 : {'name' : ['Virkisty radalla', 'tuplalepo'], 'effect' : [ 'Z--', 'Z2c'], 'cost' : ['0','2'], 'limits' : [{'P':'ABCE', 'I':'ABCE', 'L': 'ABCE'}, {'I':'A', 'P':'AB'}],
                'cost' : ['TUU','TUU'] },
           44 : {'name' : ['Suunnistuskilpailu', 'tuplalepo'], 'effect' : [ 'Z--', 'Z2c'], 'cost' : ['0','2'], 'limits' : [{'P':'ABCE', 'I':'ABCE', 'L': 'ABCE'}, {'I':'A', 'P':'AB'}],
                'cost' : ['TUU','TUU'] },
           45 : {'name' : ['Lootusasentoon', 'tuplalepo'], 'effect' : [ 'Z--', 'Z2c'], 'cost' : ['0','2'], 'limits' : [{'P':'ABCE', 'I':'ABCE', 'L': 'ABCE'}, {'I':'A', 'P':'AB'}],
                'cost' : ['TUU','TUU'] },
           46 : {'name' : ['Työkykypäivä', 'tuplalepo'], 'effect' : [ 'Z--', 'Z2c'], 'cost' : ['0','2'], 'limits' : [{'P':'ABCE', 'I':'ABCE', 'L': 'ABCE'}, {'I':'A', 'P':'AB'}],
                'cost' : ['TUU','TUU'] },
           47 : {'name' : ['Palaututtavat', 'tuplalepo'], 'effect' : [ 'Z--', 'Z2c'], 'cost' : ['0','2'], 'limits' : [{'P':'ABCE', 'I':'ABCE', 'L': 'ABCE'}, {'I':'A', 'P':'AB'}],
                'cost' : ['TUU','TUU'] },
           48 : {'name' : ['Pikku piipahdus','Ryöstele'],
                'effect' : ['A=4', 'A+0'],
                'limits' : [{'P':'ABCE', 'I':'ABCE', 'L': 'ABCE'}, {'I':'A', 'P':'AB'}],
                'cost' : ['TUU','TUU'] },
           49 : {'name' : ['Kohteliaasti kylässä','Ryöstele'],
                'effect' : ['A=4', 'A+0'],
                'limits' : [{'P':'ABCE', 'I':'ABCE', 'L': 'ABCE'}, {'I':'A', 'P':'AB'}],
                'cost' : ['TUU','TUU'] },
}
