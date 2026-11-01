"""Pillage-card columns: conditional atrocities, card draw, intoxication."""

from sixtyfivekmconvoy.core import actions as action_mod
from sixtyfivekmconvoy.core.cards import OFFICER_CATALOG, PILLAGE_CATALOG
from sixtyfivekmconvoy.core.engine import GameEngine
from sixtyfivekmconvoy.core.models import UnitType


def _unit(seed: int = 1):
    engine = GameEngine()
    engine.reset(num_players=2, seed=seed)
    if engine._unit_pool:
        engine.convoy.units = list(engine._unit_pool)
        engine._unit_pool = []
    engine.setup_complete = True
    unit = next(u for u in engine.convoy.units if u.unittype == UnitType.INFANTRY)
    unit.convoy = engine.convoy
    unit.engine = engine
    return unit


def _card(card_id: int) -> dict:
    card = PILLAGE_CATALOG[card_id]
    return card.describe()


def test_catalog_loads_new_pillage_columns():
    beer = PILLAGE_CATALOG[6].reward
    assert beer["cards"] == 2
    assert beer["intoxicate"] == 1
    assert beer["atrocities_if_under_influence"] == 0
    toy = PILLAGE_CATALOG[1].reward
    assert toy["atrocities_if_under_influence"] == 1
    assert toy["intoxicate"] == 0
    assert toy["cards"] == 0


def test_sober_unit_draws_cards_and_becomes_influenced():
    unit = _unit()
    player = unit.player
    before = len(player.action_cards)
    applied = action_mod._apply_pillage_reward(
        player, unit, _card(6), disciplined=False
    )
    assert applied["cards"] == 2
    assert applied["became_influenced"] is True
    assert applied["atrocities"] == 0
    assert len(player.action_cards) == before + 2
    assert unit.under_influence == 1
    assert unit.atrocities == 0
    line = action_mod.format_pillage_effect(unit, _card(6), applied=applied)
    assert "draws 2 cards" in line
    assert "under the influence" in line
    assert "atrocities" not in line


def test_influenced_unit_gains_conditional_atrocity_and_stays_drunk():
    unit = _unit()
    unit.under_influence = 1
    applied = action_mod._apply_pillage_reward(
        unit.player, unit, _card(1), disciplined=False
    )
    assert applied["atrocities"] == 1
    assert applied["became_influenced"] is False
    assert unit.atrocities == 1
    assert unit.under_influence == 1
    line = action_mod.format_pillage_effect(unit, _card(1), applied=applied)
    assert "commits 1 atrocities" in line
    assert "under the influence" not in line


def test_sober_unit_does_not_take_conditional_atrocity():
    unit = _unit()
    applied = action_mod._apply_pillage_reward(
        unit.player, unit, _card(1), disciplined=False
    )
    assert applied["atrocities"] == 0
    assert unit.atrocities == 0
    assert unit.under_influence == 0


def test_officer_ignores_pillage_intoxication():
    unit = _unit()
    officer = OFFICER_CATALOG[0]
    assert officer.passive_effect == "no_boozing_while_pillaging"
    unit.officers = [officer]
    before = len(unit.player.action_cards)
    applied = action_mod._apply_pillage_reward(
        unit.player, unit, _card(6), disciplined=False
    )
    assert applied["became_influenced"] is False
    assert applied["intoxicate_ignored"] is True
    assert applied["cards"] == 2
    assert unit.under_influence == 0
    assert len(unit.player.action_cards) == before + 2
    line = action_mod.format_pillage_effect(unit, _card(6), applied=applied)
    assert "ignores intoxication" in line
    assert "under the influence" not in line


def test_officer_does_not_block_atrocity_when_already_influenced():
    unit = _unit()
    unit.under_influence = 1
    unit.officers = [OFFICER_CATALOG[0]]
    # Card 9: cash 1, conditional atrocity 1, intoxicate 1.
    applied = action_mod._apply_pillage_reward(
        unit.player, unit, _card(9), disciplined=False
    )
    assert applied["atrocities"] == 1
    assert applied["became_influenced"] is False
    assert applied["intoxicate_ignored"] is False
    assert unit.atrocities == 1
    assert unit.under_influence == 1
    assert unit.player.total_cash == 1
