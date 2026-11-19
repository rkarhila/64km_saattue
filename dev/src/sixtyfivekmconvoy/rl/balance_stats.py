"""Winner statistics for a finished game.

The engine records these when ``balance_trace`` is on. Training leaves it off.
"""

from __future__ import annotations

from collections import Counter
from typing import Any


def rounds_played(engine: Any) -> int:
    rounds = getattr(engine, "rounds", None)
    if rounds is None:
        return 0
    return int(rounds.count) + 1


def winner_record(engine: Any) -> dict[str, Any] | None:
    """One game, restricted to the player ranked first."""
    ranking = list(engine.ranking or [])
    if not ranking:
        return None
    winner = int(ranking[0]["number"])

    def owned(rows: list[dict]) -> list[dict]:
        return [row for row in rows if int(row.get("player", -1)) == winner]

    income: dict[str, int] = {}
    sources = getattr(engine, "cash_sources", None) or []
    if winner < len(sources):
        income = {str(k): int(v) for k, v in sources[winner].items()}

    promotion: dict[str, int] = {}
    for row in getattr(engine, "trace_promotion_income", []) or []:
        if int(row.get("player", -1)) != winner:
            continue
        for key, amount in (row.get("sources") or {}).items():
            promotion[str(key)] = promotion.get(str(key), 0) + int(amount)

    return {
        "seed": getattr(engine, "seed", None),
        "num_players": len(engine.players),
        "winner": winner,
        "rounds": rounds_played(engine),
        "end_reason": getattr(engine, "end_reason", "") or "other",
        "start_positions": [
            row
            for row in (getattr(engine, "opening_units", None) or [])
            if int(row.get("player", -1)) == winner
        ],
        "plays": owned(list(getattr(engine, "trace_plays", None) or [])),
        "payments": owned(list(getattr(engine, "trace_payments", None) or [])),
        "cards_for_money": owned(list(getattr(engine, "trace_cash_ins", None) or [])),
        "income": income,
        "promotion_income": promotion,
    }


def summarize(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Counts across winner records. Keys are stable for the JSON summary."""
    ends: Counter[str] = Counter()
    round_counts: Counter[int] = Counter()
    starts: Counter[str] = Counter()
    plays: Counter[str] = Counter()
    payments: Counter[str] = Counter()
    money_cards: Counter[str] = Counter()
    income: Counter[str] = Counter()
    promotion: Counter[str] = Counter()
    for rec in records:
        ends[str(rec.get("end_reason") or "other")] += 1
        round_counts[int(rec.get("rounds") or 0)] += 1
        for pos in rec.get("start_positions") or []:
            starts[f"{pos.get('unit')}@{pos.get('index')}"] += 1
        for play in rec.get("plays") or []:
            plays[
                f"{play.get('card_id')}|{play.get('card_name')}|{play.get('action_name')}"
            ] += 1
        for pay in rec.get("payments") or []:
            for card in pay.get("cards") or []:
                payments[f"{card.get('id')}|{card.get('name')}"] += 1
        for cash in rec.get("cards_for_money") or []:
            for card in cash.get("cards") or []:
                money_cards[f"{card.get('id')}|{card.get('name')}"] += 1
        income.update({str(k): int(v) for k, v in (rec.get("income") or {}).items()})
        promotion.update(
            {str(k): int(v) for k, v in (rec.get("promotion_income") or {}).items()}
        )
    values = [int(rec.get("rounds") or 0) for rec in records]
    return {
        "games": len(records),
        "rounds": int(sum(values)),
        "end_conditions": dict(ends),
        "rounds_played": {
            "min": min(values) if values else 0,
            "max": max(values) if values else 0,
            "mean": (sum(values) / len(values)) if values else 0.0,
            "counts": {str(k): int(v) for k, v in sorted(round_counts.items())},
        },
        "start_positions": dict(starts.most_common()),
        "card_actions": dict(plays.most_common()),
        "payment_cards": dict(payments.most_common()),
        "cards_for_money": dict(money_cards.most_common()),
        "income": dict(income),
        "promotion_round_income": dict(promotion),
    }
