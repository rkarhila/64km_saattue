from sixtyfivekmconvoy.core.i18n import (
    DEFAULT_LANG,
    get_language,
    set_language,
    t,
    troop_label,
    unit_type_label,
)


def test_default_language_is_finnish():
    assert DEFAULT_LANG == "fi"
    assert get_language() == "fi"
    assert unit_type_label(0) == "panssarit"
    assert unit_type_label(1) == "jalkaväki"
    assert unit_type_label(2) == "huolto"
    assert troop_label("L") == "huolto"


def test_english_override():
    set_language("en")
    try:
        assert unit_type_label(0) == "panzer"
        assert unit_type_label(1) == "infantry"
        assert unit_type_label(2) == "logistics"
        assert t("ui.cost") == "cost"
    finally:
        set_language("fi")
