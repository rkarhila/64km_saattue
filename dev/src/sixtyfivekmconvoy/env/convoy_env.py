"""PettingZoo AECEnv wrapper around GameEngine."""

from __future__ import annotations

from typing import Any

import functools
import numpy as np
from gymnasium import spaces
from pettingzoo import AECEnv
from pettingzoo.utils import agent_selector, wrappers

from sixtyfivekmconvoy.core.engine import GameEngine
from sixtyfivekmconvoy.env.spaces import flatten_observation, observation_size

MAX_LEGAL = 256


def env(**kwargs):
    """PettingZoo-style factory with order enforcing + capture stdout."""
    environment = ConvoyEnv(**kwargs)
    environment = wrappers.OrderEnforcingWrapper(environment)
    return environment


class ConvoyEnv(AECEnv):
    """
    Multi-agent AEC environment.

    Each step the current agent selects an index into `legal_actions()`
    (stored in infos['legal_actions']). Actions outside the mask are ignored
    and replaced with legal action 0.
    """

    metadata = {"render_modes": ["human"], "name": "sixtyfivekmconvoy_v0", "is_parallelizable": False}

    def __init__(
        self,
        num_players: int = 3,
        seed: int | None = None,
        reward_mode: str = "rank",
        max_cycles: int = 10_000,
        render_mode: str | None = None,
    ):
        super().__init__()
        self.num_players = num_players
        self._seed = seed
        self.reward_mode = reward_mode
        self.max_cycles = max_cycles
        self.render_mode = render_mode
        self.engine = GameEngine()
        self.possible_agents = [f"player_{i}" for i in range(num_players)]
        self.agents: list[str] = []
        self._obs_size = observation_size(num_players)
        self._cycle = 0
        self._agent_selector: agent_selector.agent_selector | None = None

    @functools.lru_cache(maxsize=None)
    def observation_space(self, agent: str):
        return spaces.Box(low=-10.0, high=10.0, shape=(self._obs_size,), dtype=np.float32)

    @functools.lru_cache(maxsize=None)
    def action_space(self, agent: str):
        return spaces.Discrete(MAX_LEGAL)

    def reset(self, seed: int | None = None, options: dict | None = None):
        if seed is None:
            seed = self._seed
        self.engine.reset(num_players=self.num_players, seed=seed)
        self.agents = self.possible_agents[:]
        self.rewards = {a: 0.0 for a in self.agents}
        self._cumulative_rewards = {a: 0.0 for a in self.agents}
        self.terminations = {a: False for a in self.agents}
        self.truncations = {a: False for a in self.agents}
        self.infos = {a: {} for a in self.agents}
        self._cycle = 0

        self._sync_agent_order()
        self._update_views()

    def observe(self, agent: str):
        raw = self.engine.observe(agent)
        idx = int(agent.split("_")[1])
        return flatten_observation(raw, idx, self.num_players)

    def step(self, action: int | None):
        if self.terminations.get(self.agent_selection, False) or self.truncations.get(
            self.agent_selection, False
        ):
            self._was_dead_step(action)
            return

        legal = self.engine.legal_actions()
        if not legal:
            # No pending choice — should not happen if agent order is synced
            self._sync_agent_order()
            self._update_views()
            return

        if action is None or action < 0 or action >= len(legal):
            action = 0
        choice = legal[int(action)]
        result = self.engine.step(choice)
        self._cycle += 1

        for a in self.agents:
            self.rewards[a] = 0.0

        if result.terminal:
            ranking = result.ranking or []
            order = [f"player_{r['number']}" for r in ranking]
            for a in self.agents:
                self.terminations[a] = True
                self.rewards[a] = self._terminal_reward(a, order)
                self._cumulative_rewards[a] += self.rewards[a]
            self._update_views()
            # Keep last agent_selection for PettingZoo bookkeeping
            return

        if self._cycle >= self.max_cycles:
            for a in self.agents:
                self.truncations[a] = True
            self._update_views()
            return

        self._sync_agent_order()
        self._update_views()

    def render(self):
        if self.render_mode != "human":
            return
        agent = self.agent_selection
        raw = self.engine.observe(agent)
        print(f"[{agent}] round={raw.get('round')} stage={raw.get('stage')} res={raw.get('resistance')}")
        if "choice" in raw:
            print("  choice:", raw["choice"].get("description", "")[:120])

    def close(self):
        pass

    # ------------------------------------------------------------------

    def _terminal_reward(self, agent: str, order: list[str]) -> float:
        if agent not in order:
            return -1.0
        place = order.index(agent)
        n = max(1, len(order) - 1)
        if self.reward_mode == "points":
            # Use promotion points from ranking payload
            ranking = self.engine.winner_ranking() or []
            for r in ranking:
                if f"player_{r['number']}" == agent:
                    return float(r.get("promotion_points", 0))
            return 0.0
        # rank: first +1, last -1, linear in between
        return 1.0 - 2.0 * place / n

    def _sync_agent_order(self) -> None:
        current = self.engine.current_agent()
        if current is None:
            # Terminal or between — pick first living agent
            self.agent_selection = self.agents[0]
            return
        # Rotate agents list so agent_selector starts at current
        if current in self.agents:
            self.agent_selection = current
        else:
            self.agent_selection = self.agents[0]

    def _update_views(self) -> None:
        for a in self.agents:
            raw = self.engine.observe(a)
            legal: list[list[int]] = []
            mask = np.zeros(MAX_LEGAL, dtype=np.int8)
            if self.engine.current_agent() == a:
                legal = self.engine.legal_actions()
                for i in range(min(len(legal), MAX_LEGAL)):
                    mask[i] = 1
            self.infos[a] = {
                "raw": raw,
                "legal_actions": legal,
                "action_mask": mask,
                "stats": self.engine.stats.to_json() if self.engine.terminal else None,
            }
