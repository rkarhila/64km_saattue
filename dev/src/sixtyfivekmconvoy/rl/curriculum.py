"""When a training phase has settled enough to add two rounds.

Rounds 1, 3 and 5 follow the learner's money. After each 32-game eval, take
the mean of that bot's banked cash plus pillage chips still on its units. The phase moves on when the mean of the last
three evals is past ``2 * rounds`` and the latest eval has stopped growing:
it is at most half a cash above the better of the two before it, and it is
still past the bar.

From 7 rounds on, follow the eval win rate. A fair table wins about 32% of
games. The phase has settled when the last three evals average at least 0.45
and every one of those three is at least 0.375.
"""

from __future__ import annotations

PHASE_START = 1
PHASE_STEP = 2
PHASE_MAX = 25
CASH_PHASE_THROUGH = 5
CASH_PER_ROUND = 2.0
CASH_GROWTH = 0.5
EVAL_WINDOW = 3
WIN_MEAN_AT_LEAST = 0.45
WIN_EACH_AT_LEAST = 0.375


def cash_with_carried_loot(engine: object, seat: int) -> float:
    """Banked cash plus pillage chips still on this seat's units.

    Exit turns those chips into banked cash and removes the unit, so a chip
    is in one place or the other.
    """
    player = engine.players[int(seat)]
    total = float(player.total_cash)
    convoy = getattr(engine, "convoy", None)
    if convoy is None:
        return total
    for unit in convoy.units:
        if unit.player is player:
            total += sum(int(chip) for chip in unit.carry if int(chip) > 0)
    return total


def follows_cash(rounds: int) -> bool:
    """True while the phase is still scored by money rather than wins."""
    return int(rounds) <= CASH_PHASE_THROUGH


def cash_phase_ready(
    cash_means: list[float],
    rounds: int,
    *,
    window: int = EVAL_WINDOW,
    per_round: float = CASH_PER_ROUND,
    growth: float = CASH_GROWTH,
) -> bool:
    """True when average cash has passed ``per_round * rounds`` and flattened."""
    if rounds <= 0 or len(cash_means) < window:
        return False
    recent = [float(value) for value in cash_means[-window:]]
    bar = per_round * rounds
    if sum(recent) / window <= bar:
        return False
    if recent[-1] <= bar:
        return False
    earlier_best = max(recent[:-1])
    return recent[-1] <= earlier_best + growth


def phase_converged(
    win_rates: list[float],
    *,
    window: int = EVAL_WINDOW,
    mean_at_least: float = WIN_MEAN_AT_LEAST,
    each_at_least: float = WIN_EACH_AT_LEAST,
) -> bool:
    if len(win_rates) < window:
        return False
    recent = [float(rate) for rate in win_rates[-window:]]
    if min(recent) < each_at_least:
        return False
    return sum(recent) / window >= mean_at_least


def next_round_cap(current: int, *, step: int = PHASE_STEP, limit: int = PHASE_MAX) -> int | None:
    """The next cap, or None when ``current`` is already the longest phase."""
    if current >= limit:
        return None
    return min(limit, int(current) + step)
