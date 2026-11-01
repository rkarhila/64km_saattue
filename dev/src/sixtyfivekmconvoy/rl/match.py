"""Head-to-head evaluation between league checkpoints."""

from __future__ import annotations

from typing import Any

import numpy as np

from sixtyfivekmconvoy.env.convoy_env import ConvoyEnv
from sixtyfivekmconvoy.rl.agent import RLAgent
from sixtyfivekmconvoy.rl.league import League


def head_to_head(
    league: League,
    alpha_id: str,
    beta_id: str,
    *,
    episodes: int = 12,
    num_players: int = 3,
    seed: int = 0,
    device: str = "cpu",
) -> dict[str, Any]:
    """
    Play ``episodes`` games with alpha in one seat and beta filling the others.

    Returns win rate of alpha (fraction of games where alpha finishes 1st).
    """
    alpha_pol = league.load_model(alpha_id, map_location=device)
    beta_pol = league.load_model(beta_id, map_location=device)
    alpha = RLAgent(alpha_pol, deterministic=True, device=device, seed=seed)
    beta = RLAgent(beta_pol, deterministic=True, device=device, seed=seed + 1)
    env = ConvoyEnv(num_players=num_players, reward_mode="win", max_cycles=50_000)
    rng = np.random.default_rng(seed)
    wins = 0
    for ep in range(episodes):
        env.reset(seed=int(rng.integers(0, 2**31 - 1)))
        alpha_seat = ep % num_players
        alpha_id_str = f"player_{alpha_seat}"
        alpha.reset_memory()
        beta.reset_memory()
        steps = 0
        while env.agents and not all(env.terminations.values()):
            agent = env.agent_selection
            info = env.infos[agent]
            legal = info.get("legal_actions") or []
            mask = info.get("action_mask")
            obs = env.observe(agent)
            raw = info.get("raw") or {}
            bot = alpha if agent == alpha_id_str else beta
            action = bot.act(
                obs, legal, action_mask=mask, raw_choice=raw.get("choice")
            )
            env.step(action if legal else 0)
            steps += 1
            if steps > 50_000:
                break
        ranking = env.engine.winner_ranking() or []
        if ranking and f"player_{ranking[0]['number']}" == alpha_id_str:
            wins += 1
    wr = wins / max(1, episodes)
    return {
        "alpha_id": alpha_id,
        "beta_id": beta_id,
        "episodes": episodes,
        "alpha_wins": wins,
        "alpha_win_rate": wr,
    }
