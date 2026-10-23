from sixtyfivekmconvoy.agents.random_agent import RandomAgent
from sixtyfivekmconvoy.core.engine import GameEngine
from sixtyfivekmconvoy.core.models import Convoy, Player, UnitType


def test_zones_three_players():
    players = [Player(i) for i in range(3)]
    convoy = Convoy(players)
    assert set(convoy.zones.keys()) == {"A", "B", "C", "E"}
    assert len(convoy.units) == 9
    # Front units in A/B
    assert convoy.units[0].zone() in "ABE"
    assert convoy.units[-1].zone() == "E"


def test_damage_removes_unit():
    players = [Player(i) for i in range(2)]
    convoy = Convoy(players)
    unit = convoy.units[0]
    status = unit.apply_damage(3)
    assert status == -1
    assert unit.is_damaged()


def test_defend_soak_increments():
    players = [Player(i) for i in range(2)]
    convoy = Convoy(players)
    unit = convoy.units[1]
    unit.resolve_defend("G", "c")
    before = unit.player.this_round_cash
    msg = convoy.apply_damage(1, unit=unit, attack_type="G")
    assert "Defense" in msg or unit.player.this_round_cash >= before


def test_seeded_random_episode_terminates():
    engine = GameEngine()
    engine.reset(num_players=3, seed=42)
    agents = {pid: RandomAgent(seed=100 + i) for i, pid in enumerate(engine.agent_ids())}
    steps = 0
    while not engine.terminal:
        pending = engine.pending_choice()
        assert pending is not None
        legal = engine.legal_actions()
        assert legal, f"No legal actions for {pending}"
        choice = agents[pending.player_id].choose(legal)
        result = engine.step(choice)
        steps += 1
        assert steps < 20_000
        if result.terminal:
            break
    assert engine.terminal
    ranking = engine.winner_ranking()
    assert ranking is not None
    assert len(ranking) == 3
    assert engine.stats.rounds >= 0
