from sixtyfivekmconvoy.agents.random_agent import RandomAgent
from sixtyfivekmconvoy.env.convoy_env import ConvoyEnv


def test_pettingzoo_episode():
    env = ConvoyEnv(num_players=3, seed=7, max_cycles=50_000)
    env.reset(seed=7)
    agents = {a: RandomAgent(seed=20 + i) for i, a in enumerate(env.possible_agents)}
    steps = 0
    while env.agents and not all(env.terminations.values()):
        agent = env.agent_selection
        mask = env.infos[agent].get("action_mask")
        legal = env.infos[agent].get("legal_actions") or []
        if legal:
            action = agents[agent].act(env.observe(agent), legal)
        else:
            action = 0
        env.step(action)
        steps += 1
        if steps > 30_000:
            break
        # After terminal, PettingZoo may still have dead-agent steps
        if all(env.terminations.get(a, False) for a in env.possible_agents):
            break
    assert steps > 0
    assert env.engine.terminal or steps > 100
