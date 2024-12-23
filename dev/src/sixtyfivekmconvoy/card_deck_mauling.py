class CardDeckMauling:

  from random import choice
  deck = {}
  for i in range(20):
    deck[i] = { 'name' : f'maul_{i}',
                'effect' : {'damage' : [2,4],
                            'target' : choice(['B',
                                               'C',
                                               'A-1',
                                               'A1',
                                               'B1',
                                               'B-1',
                                               'E1',
                                               'E-1']),
                            'atrocity_threshold' : 2,
                            'type' : 'Ground' }}
  
  """
  deck = { 0 : { 'name' : 'Kiväärihenkilöitä/Panssarirynnäkkö',
                 'effect' : { 'type' : 'G',
                              'damage' : ['D1', 'D3'] } },
           1 : { 'name' : 'Satunnaista ammuskelua /Tykistöisku',
                 'effect' : { 'type' : 'G',
                              'damage' : ['D1', 'D3'] } },
           2 : { 'name' : 'Kiväärihenkilöitä/Sinkohenkilöitä',
                 'effect' : { 'type' : 'G',
                              'damage' : ['D1', 'D3'] } },
           3 : { 'name' : 'Satunnaista ammuskelua/Raketinheittimiä',
                 'effect' : { 'type' : 'G',
                              'damage' : ['D1', 'D3'] } },
           4 : { 'name' : 'Nelikoptereita/Lennokki-isku',
                 'effect' : { 'type' : 'A',
                              'damage' : ['D1', 'D3'] } },
           5 : { 'name' : 'Nelikoptereita/Lennokki-isku',
                 'effect' : { 'type' : 'A',
                              'damage' : ['D1', 'D3'] } },
           6 : { 'name' : 'Räjähtäviä lepakoita/Napalmia',
                 'effect' : { 'type' : 'A',
                              'damage' : ['D1', 'D3'] } },
           7 : { 'name' : 'Nelikoptereita/Risteilyohjus',
                 'effect' : { 'type' : 'A',
                              'damage' : ['D1', 'D3'] } },
           8 : { 'name' : 'Räjähtäviä lepakoita/Napalmia',
                 'effect' : { 'type' : 'A',
                              'damage' : ['D1', 'D3'] } },
           9 : { 'name' : 'Nelikoptereita/Kiertoratapommitus',
                 'effect' : { 'type' : 'A',
                              'damage' : ['D1', 'D3'] } },
           10 : { 'name' : 'Räjähtäviä lepakoita/Lennokki-isku',
                 'effect' : { 'type' : 'A',
                              'damage' : ['D1', 'D3'] } },
           11 : { 'name' : 'Räjähtäviä lepakoita/Lennokki-isku',
                 'effect' : { 'type' : 'A',
                              'damage' : ['D1', 'D3'] } },
           12 : { 'name' : 'Varkaita/Robottininjoja',
                 'effect' : { 'type' : 'S',
                              'damage' : ['D1', 'D3'] } },
           13 : { 'name' : 'Kaukopartiolaisia/Desantteja',
                 'effect' : { 'type' : 'S',
                              'damage' : ['D1', 'D3'] } },
           14 : { 'name' : 'Varkaita/Kommunisteja',
                 'effect' : { 'type' : 'S',
                              'damage' : ['D1', 'D3'] } },
           15 : { 'name' : 'Maanalainen armeija/Desantteja',
                 'effect' : { 'type' : 'S',
                              'damage' : ['D1', 'D3'] } },
           16 : { 'name' : 'Kaukopartiolaisia/Robottininjoja',
                 'effect' : { 'type' : 'S',
                              'damage' : ['D1', 'D3'] } },
           17 : { 'name' : 'Tienvarsiräjähde/telamiinoja',
                 'effect' : { 'type' : 'T',
                              'damage' : ['D1', 'D3'] } },
           18 : { 'name' : 'Tienvarsiräjähde/viuhkamiinoja',
                 'effect' : { 'type' : 'T',
                              'damage' : ['D1', 'D3'] } },
           19 : { 'name' : 'Tienvarsiräjähde/???',
                 'effect' : { 'type' : 'T',
                              'damage' : ['D1', 'D3'] } },
           20 : { 'name' : '',
                 'effect' : { 'type' : 'G',
                              'damage' : ['D1', 'D3'] } },
           21 : { 'name' : '',
                 'effect' : { 'type' : 'G',
                              'damage' : ['D1', 'D3'] } },
           17 : { 'name' : '',
                 'effect' : { 'type' : 'G',
                              'damage' : ['D1', 'D3'] } },
           18 : { 'name' : '',
                 'effect' : { 'type' : 'G',
                              'damage' : ['D1', 'D3'] } },
           19 : { 'name' : '',
                 'effect' : { 'type' : 'G',
                              'damage' : ['D1', 'D3'] } },

          }
"""
