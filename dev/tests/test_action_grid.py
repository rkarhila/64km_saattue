"""Action cards load from a face-per-row CSV or from a troop-by-card grid."""

from pathlib import Path

from sixtyfivekmconvoy.core.cards import load_action_deck

_DEV = Path(__file__).resolve().parents[1]


def test_row_action_cards_keep_their_own_faces(monkeypatch):
    monkeypatch.delenv("CONVOY_CARDS", raising=False)
    monkeypatch.delenv("CONVOY_VERSION", raising=False)
    deck = load_action_deck()
    face = deck[0].actions[0]
    assert face.zone
    assert face.cost
    assert face.action_name


def test_minimal_reverse_is_bypass_toward_the_tail(monkeypatch):
    monkeypatch.setenv("CONVOY_CARDS", str(_DEV / "versions" / "alpha_01" / "cards"))
    alpha = load_action_deck()
    assert alpha[0].actions[0].zone
    monkeypatch.setenv("CONVOY_CARDS", str(_DEV / "versions" / "minimal" / "cards"))
    deck = load_action_deck()
    # Card 5: panzer attack, infantry reverse, shared pillage.
    infantry = next(face for face in deck[5].actions if face.troop_type == "I")
    assert infantry.action_name == "bypass"
    assert infantry.action_modifier == -1
    assert infantry.zone == "ABCE"
    assert infantry.cost == "1/T+1/U"
    assert infantry.tire == 1
    assert infantry.name == "Ohita"
    for card_id, troop in ((6, "L"), (7, "L"), (9, "P")):
        face = next(item for item in deck[card_id].actions if item.troop_type == troop)
        assert face.action_name == "bypass"
        assert face.action_modifier == -1


def test_grid_faces_take_zone_cost_and_name_from_the_defs(tmp_path, monkeypatch):
    cards = tmp_path / "cards"
    cards.mkdir()
    (cards / "action.csv").write_text(
        "\n".join(
            [
                "card_id,0,1",
                "p_action,p_attack,",
                "p_action_mod,3,",
                "i_action,,",
                "i_action_mod,,",
                "l_action,,service",
                "l_action_mod,,1",
                "a_action,pillage,",
                "a_action_mod,1,",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (cards / "action_defs.csv").write_text(
        (_DEV / "versions" / "minimal" / "cards" / "action_defs.csv").read_text(
            encoding="utf-8"
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("CONVOY_CARDS", str(cards))
    deck = load_action_deck()
    panzer, shared = deck[0].actions
    assert (panzer.troop_type, panzer.action_name, panzer.zone) == ("P", "attack", "AB")
    assert panzer.cost == "1/T+1/U"
    assert panzer.tire == 1
    assert panzer.intoxicate == 0
    assert panzer.action_modifier == 3
    assert panzer.name == "Hyökkää"
    assert (shared.troop_type, shared.action_name, shared.zone) == (
        "A",
        "pillage",
        "ABCE",
    )
    assert shared.cost == "1/T"
    assert shared.action_modifier == 1
    assert shared.limits == {"I": "ABCE", "P": "ABCE", "L": "ABCE"}
    service = deck[1].actions[0]
    assert service.troop_type == "L"
    assert service.action_name == "service"
    assert service.zone == "ABCE"
    assert service.cost == "1/T+1/U+1/A"
    assert service.name == "Huolla"
    assert service.action_modifier == 1
