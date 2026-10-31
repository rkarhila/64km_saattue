"""Promotion-point and cash race victory conditions."""

from sixtyfivekmconvoy.core.config import CASH_TO_WIN, PROMOTION_POINTS_TO_WIN
from sixtyfivekmconvoy.core.engine import GameEngine


def _engine(seed: int = 0) -> GameEngine:
    engine = GameEngine()
    engine.reset(num_players=2, seed=seed)
    engine.pause_after_actions = False
    return engine


def test_config_defaults():
    assert PROMOTION_POINTS_TO_WIN == 6
    assert CASH_TO_WIN == 50


def test_cash_to_win_immediate():
    engine = _engine()
    p0, p1 = engine.players
    assert not engine.terminal
    # Approach threshold without crossing.
    p0.get_cash(CASH_TO_WIN - 1)
    assert not engine.terminal
    p0.get_cash(1)
    assert engine.terminal
    assert engine.ranking[0]["number"] == p0.number
    assert "cash" in (engine._end_message or "").lower()


def test_cash_to_win_does_not_fire_for_second_player_after_game_over():
    engine = _engine()
    p0, p1 = engine.players
    p0.get_cash(CASH_TO_WIN)
    assert engine.terminal
    p1.get_cash(CASH_TO_WIN)
    assert engine.ranking[0]["number"] == p0.number


def test_promotion_sole_winner():
    engine = _engine()
    p0, p1 = engine.players
    p0.promotion_points = PROMOTION_POINTS_TO_WIN
    p1.promotion_points = PROMOTION_POINTS_TO_WIN - 1
    result = engine._check_promotion_victory()
    assert result is not None and result.terminal
    assert engine.ranking[0]["number"] == p0.number
    assert not engine.sudden_death_pp


def test_promotion_tie_enters_sudden_death_then_sole_lead_wins():
    engine = _engine()
    p0, p1 = engine.players
    p0.promotion_points = PROMOTION_POINTS_TO_WIN
    p1.promotion_points = PROMOTION_POINTS_TO_WIN
    result = engine._check_promotion_victory()
    assert result is None
    assert engine.sudden_death_pp
    assert not engine.terminal

    # Still tied → continue
    assert engine._check_promotion_victory() is None
    assert not engine.terminal

    p0.promotion_points += 1
    result = engine._check_promotion_victory()
    assert result is not None and result.terminal
    assert engine.ranking[0]["number"] == p0.number
    assert "sudden death" in (engine._end_message or "").lower()
