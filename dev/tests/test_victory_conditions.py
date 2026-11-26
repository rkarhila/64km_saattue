"""Promotion-point and cash race victory conditions."""

from sixtyfivekmconvoy.core.config import CASH_TO_WIN, PROMOTION_POINTS_TO_WIN
from sixtyfivekmconvoy.core.configs import get_config
from sixtyfivekmconvoy.core.engine import GameEngine


def _engine(seed: int = 0) -> GameEngine:
    engine = GameEngine()
    engine.reset(num_players=2, seed=seed)
    engine.pause_after_actions = False
    return engine


def test_config_defaults():
    assert PROMOTION_POINTS_TO_WIN == 6
    assert CASH_TO_WIN == 25
    assert get_config().CASH_WIN_AT_END_OF_ROUND is False


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
    assert "rahalla" in (engine._end_message or "").lower() or "voittaa" in (
        engine._end_message or ""
    ).lower()


def test_cash_to_win_does_not_fire_for_second_player_after_game_over():
    engine = _engine()
    p0, p1 = engine.players
    p0.get_cash(CASH_TO_WIN)
    assert engine.terminal
    p1.get_cash(CASH_TO_WIN)
    assert engine.ranking[0]["number"] == p0.number


def test_end_of_round_cash_win_waits_until_bookkeeping():
    cfg = get_config()
    previous = cfg.CASH_WIN_AT_END_OF_ROUND
    try:
        cfg.CASH_WIN_AT_END_OF_ROUND = True
        engine = _engine()
        p0, p1 = engine.players
        p0.get_cash(CASH_TO_WIN)
        assert not engine.terminal
        p1.get_cash(CASH_TO_WIN - 1)
        result = engine._check_end_of_round_victories()
        assert result is not None and result.terminal
        assert engine.ranking[0]["number"] == p0.number
        assert engine.end_reason == "cash"
    finally:
        cfg.CASH_WIN_AT_END_OF_ROUND = previous


def test_end_of_round_cash_and_promotion_conflict_is_a_tie():
    cfg = get_config()
    previous = cfg.CASH_WIN_AT_END_OF_ROUND
    try:
        cfg.CASH_WIN_AT_END_OF_ROUND = True
        engine = _engine()
        p0, p1 = engine.players
        p0.get_cash(CASH_TO_WIN + 2)
        p1.get_cash(1)
        p1.promotion_points = PROMOTION_POINTS_TO_WIN
        result = engine._check_end_of_round_victories()
        assert result is not None and result.terminal
        assert engine.end_reason == "tie"
        assert "tasapeli" in (engine._end_message or "").lower()
    finally:
        cfg.CASH_WIN_AT_END_OF_ROUND = previous


def test_end_of_round_same_player_cash_and_promotion_wins():
    cfg = get_config()
    previous = cfg.CASH_WIN_AT_END_OF_ROUND
    try:
        cfg.CASH_WIN_AT_END_OF_ROUND = True
        engine = _engine()
        p0, p1 = engine.players
        p0.get_cash(CASH_TO_WIN)
        p0.promotion_points = PROMOTION_POINTS_TO_WIN
        result = engine._check_end_of_round_victories()
        assert result is not None and result.terminal
        assert engine.ranking[0]["number"] == p0.number
        assert engine.end_reason == "cash"
    finally:
        cfg.CASH_WIN_AT_END_OF_ROUND = previous


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
    assert "äkkikuoleman" in (engine._end_message or "").lower()


def test_promotion_point_goes_only_to_the_sole_cash_leader():
    from sixtyfivekmconvoy.core.configs import get_config

    engine = _engine()
    p0, p1 = engine.players
    cfg = get_config()
    previous = cfg.SOLE_CASH_LEAD_FOR_PROMOTION
    try:
        cfg.SOLE_CASH_LEAD_FOR_PROMOTION = True
        p0.this_round_cash = 4
        p1.this_round_cash = 4
        assert engine._players_earning_promotion() == []

        p0.this_round_cash = 5
        assert engine._players_earning_promotion() == [p0]

        p0.this_round_cash = 0
        p1.this_round_cash = 0
        assert engine._players_earning_promotion() == []

        cfg.SOLE_CASH_LEAD_FOR_PROMOTION = False
        p0.this_round_cash = 4
        p1.this_round_cash = 4
        assert engine._players_earning_promotion() == [p0, p1]
    finally:
        cfg.SOLE_CASH_LEAD_FOR_PROMOTION = previous


def test_action_log_wording_comes_from_the_language_table():
    from sixtyfivekmconvoy.core.i18n import get_language, set_language
    from sixtyfivekmconvoy.core.log_text import format_action_log

    previous = get_language()
    try:
        set_language("fi")
        finnish = format_action_log("Foo punaiset panssarit", "Hyökkää", ["Vastarinta tuhoutui"], [])
        assert "suorittaa" in finnish
        assert "ratkaisee" not in finnish
        set_language("en")
        english = format_action_log("Foo red panzers", "Attack", ["Resistance is destroyed"], [])
        assert "resolves" in english
        assert "suorittaa" not in english
    finally:
        set_language(previous)


def test_scout_ui_copy_comes_from_the_language_table():
    from sixtyfivekmconvoy.core.i18n import get_language, set_language, tf

    previous = get_language()
    try:
        set_language("fi")
        finnish = tf("ui.scout.confirm_order")
        assert finnish == "Vahvista järjestys"
        assert "Tiedustelu" in tf("ui.scout.reorder_title", verb=tf("ui.verb.scout"), queue="ryöstö")
        set_language("en")
        assert tf("ui.scout.confirm_order") == "Confirm order"
        assert "Scout" in tf("ui.scout.select_title", verb=tf("ui.verb.scout"))
    finally:
        set_language(previous)
