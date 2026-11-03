"""Balanced convoy ownership patterns for the placement phase.

Each pattern is a tuple of player indices (0-based) of length 3 * num_players.
The convoy is split into three equal thirds; each player appears exactly once
in each third so starting positions stay roughly equidistant on average.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# 2 players — length 6, thirds of 2 (user examples + extras, capped ~12)
# ---------------------------------------------------------------------------
_POOL_2: tuple[tuple[int, ...], ...] = (
    (0, 1, 0, 1, 1, 0),  # 121221
    (0, 1, 1, 0, 1, 0),  # 122121
    (1, 0, 1, 0, 0, 1),  # 212112
    (1, 0, 0, 1, 0, 1),  # 211212
    (0, 1, 0, 1, 0, 1),  # 121212
    (1, 0, 1, 0, 1, 0),  # 212121
    (0, 1, 1, 0, 0, 1),  # 122112
    (1, 0, 0, 1, 1, 0),  # 211221
    (0, 1, 1, 0, 1, 0),  # duplicate-ish ok — 122121 already; use 101210 style
    (1, 0, 1, 0, 0, 1),
)

# Dedupe while preserving order
def _unique(pool: tuple[tuple[int, ...], ...]) -> tuple[tuple[int, ...], ...]:
    seen: set[tuple[int, ...]] = set()
    out: list[tuple[int, ...]] = []
    for p in pool:
        if p not in seen:
            seen.add(p)
            out.append(p)
    return tuple(out)


_POOL_2 = _unique(
    (
        (0, 1, 0, 1, 1, 0),
        (0, 1, 1, 0, 1, 0),
        (1, 0, 1, 0, 0, 1),
        (1, 0, 0, 1, 0, 1),
        (0, 1, 0, 1, 0, 1),
        (1, 0, 1, 0, 1, 0),
        (0, 1, 1, 0, 0, 1),
        (1, 0, 0, 1, 1, 0),
        (0, 1, 0, 1, 1, 0),
        (1, 0, 0, 1, 0, 1),
        (0, 1, 1, 0, 1, 0),
        (1, 0, 1, 0, 0, 1),
    )
)


# ---------------------------------------------------------------------------
# Helpers to build latin-style thirds for n > 2
# ---------------------------------------------------------------------------

def _thirds(n: int) -> list[list[int]]:
    """Return three blocks of size n: base seating rotations."""
    base = list(range(n))
    # Three cyclic shifts / reversals to vary tip distance
    t0 = base[:]
    t1 = base[1:] + base[:1]
    t2 = base[2:] + base[:2] if n > 2 else base[::-1]
    return [t0, t1, t2]


def _expand_pool(n: int, limit: int = 12) -> tuple[tuple[int, ...], ...]:
    """Generate up to `limit` valid patterns for n players."""
    import itertools

    third = list(range(n))
    patterns: list[tuple[int, ...]] = []
    seen: set[tuple[int, ...]] = set()

    # Prefer structured rotations first
    for shift in range(n):
        blocks = []
        for b in range(3):
            blocks.append([(p + shift + b) % n for p in third])
        # Permute order within each third lightly
        for perm0 in itertools.permutations(blocks[0]):
            for flip in (False, True):
                b1 = list(reversed(blocks[1])) if flip else blocks[1]
                for perm1 in itertools.permutations(b1):
                    b2 = blocks[2]
                    pat = tuple(perm0) + tuple(perm1) + tuple(b2)
                    if pat not in seen and _is_valid(pat, n):
                        seen.add(pat)
                        patterns.append(pat)
                        if len(patterns) >= limit:
                            return tuple(patterns)
                    if len(patterns) >= limit:
                        break
                if len(patterns) >= limit:
                    break
            if len(patterns) >= limit:
                break
        if len(patterns) >= limit:
            break

    # Fill with random-ish permutations of thirds if needed
    for rot in range(n):
        for rev in (False, True):
            blocks = []
            for b in range(3):
                row = [(p + rot + b * (1 if n % 2 else 2)) % n for p in third]
                if rev and b == 1:
                    row = list(reversed(row))
                blocks.append(row)
            pat = tuple(blocks[0] + blocks[1] + blocks[2])
            if pat not in seen and _is_valid(pat, n):
                seen.add(pat)
                patterns.append(pat)
            if len(patterns) >= limit:
                return tuple(patterns)

    return tuple(patterns[:limit])


def _is_valid(pattern: tuple[int, ...], n: int) -> bool:
    if len(pattern) != 3 * n:
        return False
    third = n
    expected = set(range(n))
    for t in range(3):
        block = pattern[t * third : (t + 1) * third]
        if set(block) != expected:
            return False
        if len(block) != len(set(block)):
            return False
    # Each player exactly 3 times overall
    for p in range(n):
        if pattern.count(p) != 3:
            return False
    return True


_POOL_3 = _expand_pool(3, 12)
_POOL_4 = _expand_pool(4, 12)
_POOL_5 = _expand_pool(5, 12)

SETUP_POOLS: dict[int, tuple[tuple[int, ...], ...]] = {
    2: _POOL_2[:12],
    3: _POOL_3,
    4: _POOL_4,
    5: _POOL_5,
}


def pick_setup_pattern(num_players: int, rng) -> tuple[int, ...]:
    pool = SETUP_POOLS.get(num_players)
    if not pool:
        raise ValueError(f"No setup pool for {num_players} players")
    return rng.choice(pool)


def slots_for_player(pattern: tuple[int, ...], player: int) -> list[int]:
    """Convoy indices owned by `player`, front to back."""
    return [i for i, owner in enumerate(pattern) if owner == player]


def validate_pools() -> None:
    for n, pool in SETUP_POOLS.items():
        assert 1 <= len(pool) <= 12, (n, len(pool))
        for pat in pool:
            assert _is_valid(pat, n), (n, pat)
