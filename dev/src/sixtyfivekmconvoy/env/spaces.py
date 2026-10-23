"""Observation helpers for ConvoyEnv."""

from __future__ import annotations

from typing import Any

import numpy as np


MAX_UNITS = 15
MAX_HAND = 20
MAX_PLAYERS = 5


def flatten_observation(obs: dict[str, Any], agent_index: int, num_players: int) -> np.ndarray:
    """Build a fixed-size float32 vector from a player FOV dict."""
    feats: list[float] = []

    # Self identity
    one_hot = [0.0] * MAX_PLAYERS
    one_hot[agent_index] = 1.0
    feats.extend(one_hot)

    feats.append(float(obs.get("round", 0)))
    feats.append(float(obs.get("stage", -1)))
    feats.append(1.0 if obs.get("terminal") else 0.0)

    # Resistance
    res = obs.get("resistance") or {}
    feats.append(1.0 if res.get("active") else 0.0)
    feats.append(float(res.get("durability") or 0) / 20.0)

    # Players (pad)
    players = obs.get("players") or []
    for i in range(MAX_PLAYERS):
        if i < len(players):
            p = players[i]
            feats.extend(
                [
                    float(p.get("cash_this_round", 0)) / 20.0,
                    float(p.get("total_cash", 0)) / 50.0,
                    float(p.get("promotion_points", 0)) / 10.0,
                    float(p.get("card_count", 0)) / MAX_HAND,
                ]
            )
        else:
            feats.extend([0.0, 0.0, 0.0, 0.0])

    # Convoy units
    convoy = obs.get("convoy") or []
    for i in range(MAX_UNITS):
        if i < len(convoy):
            u = convoy[i]
            ut = {"Pnz": 0, "Inf": 1, "Log": 2}.get(u.get("unit_type"), 0)
            ut_oh = [0.0, 0.0, 0.0]
            ut_oh[ut] = 1.0
            feats.extend(ut_oh)
            feats.append(float(u.get("player", 0)) / max(1, num_players - 1))
            feats.append(float(u.get("tiredness", 0)) / 10.0)
            feats.append(1.0 if u.get("under_influence") else 0.0)
            feats.append(float(u.get("atrocities", 0)) / 10.0)
            carry = u.get("carry") or []
            feats.append(len(carry) / 4.0)
            feats.append(sum(c for c in carry if c > 0) / 20.0)
        else:
            feats.extend([0.0] * 9)

    # Hand size / presence of choice
    choice = obs.get("choice")
    feats.append(1.0 if choice else 0.0)
    if choice:
        feats.append(float(choice.get("choicetype", -1)) / 10.0)
        feats.append(float(choice.get("num_choice", 0)) / 5.0)
        feats.append(float(len(choice.get("options") or [])) / MAX_HAND)
    else:
        feats.extend([0.0, 0.0, 0.0])

    return np.asarray(feats, dtype=np.float32)


def observation_size(num_players: int = MAX_PLAYERS) -> int:
    # Compute once from a dummy structure
    dummy = {
        "round": 0,
        "stage": 0,
        "terminal": False,
        "resistance": {},
        "players": [],
        "convoy": [],
        "choice": None,
    }
    return int(flatten_observation(dummy, 0, num_players).shape[0])
