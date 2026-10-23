from sixtyfivekmconvoy.core.setup_layouts import (
    SETUP_POOLS,
    pick_setup_pattern,
    slots_for_player,
    validate_pools,
)
from sixtyfivekmconvoy.agents.random_agent import RandomAgent
from sixtyfivekmconvoy.core.engine import GameEngine
from sixtyfivekmconvoy.core.constants import ChoiceType
import random


def test_pools_valid():
    validate_pools()
    for n in (2, 3, 4, 5):
        assert 1 <= len(SETUP_POOLS[n]) <= 12


def test_slots_one_per_third():
    for n, pool in SETUP_POOLS.items():
        third = n
        for pat in pool:
            for p in range(n):
                slots = slots_for_player(pat, p)
                assert len(slots) == 3
                thirds = [s // third for s in slots]
                assert sorted(thirds) == [0, 1, 2]


def test_placement_phase_then_play():
    engine = GameEngine()
    engine.reset(num_players=3, seed=11, max_rounds=30)
    assert engine.setup_complete is False
    agents = {pid: RandomAgent(seed=50 + i) for i, pid in enumerate(engine.agent_ids())}
    steps = 0
    while not engine.terminal:
        pending = engine.pending_choice()
        assert pending is not None
        if steps == 0:
            assert pending.choicetype == ChoiceType.PLACE_UNITS
        legal = engine.legal_actions()
        engine.step(agents[pending.player_id].choose(legal))
        steps += 1
        if steps > 30_000:
            break
    assert engine.terminal
    assert engine.setup_complete
    assert engine.winner_ranking() is not None
    # After play only a few units remain; pattern length was 9 at setup.
    assert len(engine.setup_pattern) == 9
