"""search_pillage_combo officer discard: search then pillage immediately."""

from sixtyfivekmconvoy.core import actions as action_mod
from sixtyfivekmconvoy.core.cards import OFFICER_CATALOG
from sixtyfivekmconvoy.core.constants import ActionName, ChoiceType
from sixtyfivekmconvoy.core.engine import GameEngine
from sixtyfivekmconvoy.core.models import UnitType


def _seat(engine: GameEngine):
    if engine._unit_pool:
        engine.convoy.units = list(engine._unit_pool)
        engine._unit_pool = []
    engine.setup_complete = True
    for u in engine.convoy.units:
        u.convoy = engine.convoy
        u.engine = engine


def _combo_face():
    officer = OFFICER_CATALOG[7]
    face = officer.get_discard_action_description()
    assert face is not None
    assert ActionName.normalize(face["action_name"]) == ActionName.SEARCH_PILLAGE_COMBO
    return officer, face


def test_search_pillage_combo_not_unimplemented():
    assert ActionName.SEARCH_PILLAGE_COMBO not in ActionName.UNIMPLEMENTED


def test_search_pillage_combo_legal_with_empty_pillage_queue():
    engine = GameEngine()
    engine.reset(num_players=2, seed=8)
    _seat(engine)
    unit = next(u for u in engine.convoy.units if u.unittype == UnitType.INFANTRY)
    officer, face = _combo_face()
    unit.officers = [officer]
    assert len(engine.pillage_queue) == 0
    assert action_mod.why_action_impossible(engine, unit.index(), face) == []


def test_resolve_search_pillage_combo_searches_then_pillages():
    engine = GameEngine()
    engine.reset(num_players=2, seed=8)
    engine.pause_after_actions = False
    _seat(engine)
    unit = next(u for u in engine.convoy.units if u.unittype == UnitType.INFANTRY)
    officer, face = _combo_face()
    unit.officers = [officer]
    player = unit.player
    cash_before = player.total_cash
    assert len(engine.pillage_queue) == 0

    gen = action_mod.resolve_action(engine, unit.index(), face, -1)

    # 1) Search with empty queue → draw N from pillage deck, pick one face-up.
    req = next(gen)
    assert req.choicetype == ChoiceType.CHOOSE_PILLAGE_CARD
    assert req.payload.get("reason") == "scout_deck_pick"
    assert req.payload.get("queue") == "pillage"
    keep = req.options[0]

    # 2) The kept card is the only pillage choice, so a sober unit takes it.
    try:
        gen.send([keep])
        raise AssertionError("expected StopIteration")
    except StopIteration as stop:
        summary = stop.value

    assert "pillaged" in summary
    assert officer not in unit.officers
    assert player.total_cash >= cash_before
