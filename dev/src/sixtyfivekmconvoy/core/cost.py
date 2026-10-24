"""Action-card cost formulas from CSV (e.g. 1/T+2/U+1/A)."""

from __future__ import annotations

import re
from typing import Any

# Token letters in cost formulas (CSV / display).
TOKEN_TIREDNESS = "T"
TOKEN_INFLUENCE = "U"
TOKEN_ATROCITY = "A"

_TERM_RE = re.compile(
    r"^\s*(\d+)\s*(?:/\s*([TUA]))?\s*$",
    re.IGNORECASE,
)


def parse_cost_rates(cost: str | int | None) -> tuple[int, int, int] | int:
    """
    Parse a cost cell into either:
      - flat int (cards to discard), or
      - (tiredness_rate, influence_rate, atrocity_rate) for token costs.

    Accepted forms:
      0, 1, 4              → flat
      T                    → legacy shorthand for 1/T+1/U+1/A
      1/T+1/U              → rates
      1/T+2/U+1/A          → rates
      1/T + 1/U + 1/A      → rates (whitespace ok)
    """
    if cost is None or cost == "":
        return 0
    if isinstance(cost, int):
        return cost
    raw = str(cost).strip()
    if not raw:
        return 0
    if raw.upper() == "T":
        return (1, 1, 1)
    # Flat integer?
    try:
        return int(raw)
    except ValueError:
        pass

    t_r = u_r = a_r = 0
    for part in raw.replace(" ", "").split("+"):
        if not part:
            continue
        m = _TERM_RE.match(part)
        if not m:
            raise ValueError(f"Invalid cost term {part!r} in {cost!r}")
        n = int(m.group(1))
        token = (m.group(2) or "").upper()
        if not token:
            # Bare number in a formula — treat as flat-only if sole term
            if "+" not in raw.replace(" ", ""):
                return n
            raise ValueError(f"Bare number in token formula {cost!r}")
        if token == TOKEN_TIREDNESS:
            t_r += n
        elif token == TOKEN_INFLUENCE:
            u_r += n
        elif token == TOKEN_ATROCITY:
            a_r += n
        else:
            raise ValueError(f"Unknown cost token {token!r}")
    return (t_r, u_r, a_r)


def evaluate_cost(unit: Any, cost: str | int | None) -> int:
    """Cards to discard for `cost` given unit tired / influence / atrocities."""
    parsed = parse_cost_rates(cost)
    if isinstance(parsed, int):
        return max(0, parsed)
    t_r, u_r, a_r = parsed
    return (
        t_r * max(0, int(getattr(unit, "tired", 0) or 0))
        + u_r * (1 if getattr(unit, "under_influence", 0) else 0)
        + a_r * max(0, int(getattr(unit, "atrocities", 0) or 0))
    )


def cost_rates_for_display(cost: str | int | None) -> tuple[int, int, int] | None:
    """Return (T,U,A) rates for UI, or None if the cost is a flat card count."""
    parsed = parse_cost_rates(cost)
    if isinstance(parsed, int):
        return None
    return parsed
