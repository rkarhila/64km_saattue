from sixtyfivekmconvoy.core.cards import (
    ACTION_CATALOG,
    MAULING_CATALOG,
    OFFICER_CATALOG,
    PILLAGE_CATALOG,
    RESISTANCE_CATALOG,
)


def test_catalogs_nonempty():
    assert len(ACTION_CATALOG) >= 10
    assert len(OFFICER_CATALOG) >= 5
    assert len(PILLAGE_CATALOG) >= 10
    assert len(MAULING_CATALOG) >= 10
    assert len(RESISTANCE_CATALOG) >= 5


def test_action_card_describe():
    card = next(iter(ACTION_CATALOG.values()))
    desc = card.describe()
    assert isinstance(desc, list)
    assert "action_name" in desc[0]
