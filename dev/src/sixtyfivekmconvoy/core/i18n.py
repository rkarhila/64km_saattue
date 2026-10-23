"""UI string translations. Default language is Finnish."""

from __future__ import annotations

DEFAULT_LANG = "fi"

# Canonical keys → per-language strings.
# Unit type keys match UNIT_TYPE_KEY / troop letters where noted.
TRANSLATIONS: dict[str, dict[str, str]] = {
    "fi": {
        "unit.panzer": "panssarit",
        "unit.infantry": "jalkaväki",
        "unit.logistics": "huolto",
        "unit.any": "kaikki",
        # Troop-type letters on action card faces
        "troop.P": "panssarit",
        "troop.I": "jalkaväki",
        "troop.L": "huolto",
        "troop.A": "kaikki",
        "ui.cost": "hinta",
        "ui.tires": "väsyttää",
        "ui.intoxicates": "humalaannuttaa",
        "ui.free": "ilmainen",
        "ui.card": "kortti",
        "ui.zone": "vyöhyke",
        "ui.player": "pelaaja",
        "ui.round": "kierros",
        "ui.resistance": "vastarinta",
        "ui.convoy": "saattue",
        "ui.hand": "käsi",
        "ui.choose_cards_for_units": "Valitse yksi toimintakortti jokaiselle yksikölle",
    },
    "en": {
        "unit.panzer": "panzer",
        "unit.infantry": "infantry",
        "unit.logistics": "logistics",
        "unit.any": "any",
        "troop.P": "panzer",
        "troop.I": "infantry",
        "troop.L": "logistics",
        "troop.A": "any",
        "ui.cost": "cost",
        "ui.tires": "tires",
        "ui.intoxicates": "intoxicates",
        "ui.free": "free",
        "ui.card": "card",
        "ui.zone": "zone",
        "ui.player": "player",
        "ui.round": "round",
        "ui.resistance": "resistance",
        "ui.convoy": "convoy",
        "ui.hand": "hand",
        "ui.choose_cards_for_units": "Choose one action card for each unit",
    },
}

# Stable internal codes (not localized) used in JSON / RL obs.
UNIT_TYPE_KEY = {0: "panzer", 1: "infantry", 2: "logistics"}
UNIT_TYPE_I18N_KEY = {0: "unit.panzer", 1: "unit.infantry", 2: "unit.logistics"}
TROOP_LETTER_I18N_KEY = {"P": "troop.P", "I": "troop.I", "L": "troop.L", "A": "troop.A"}

_current_lang = DEFAULT_LANG


def set_language(lang: str) -> None:
    global _current_lang
    if lang not in TRANSLATIONS:
        raise ValueError(f"Unsupported language: {lang}")
    _current_lang = lang


def get_language() -> str:
    return _current_lang


def t(key: str, lang: str | None = None) -> str:
    """Translate `key` into the active (or given) language; fall back to key."""
    lang = lang or _current_lang
    table = TRANSLATIONS.get(lang) or TRANSLATIONS[DEFAULT_LANG]
    if key in table:
        return table[key]
    # Fall back to Finnish, then English, then the raw key
    for fallback in (DEFAULT_LANG, "en"):
        if key in TRANSLATIONS.get(fallback, {}):
            return TRANSLATIONS[fallback][key]
    return key


def unit_type_label(unittype: int, lang: str | None = None) -> str:
    return t(UNIT_TYPE_I18N_KEY[unittype], lang=lang)


def troop_label(troop_letter: str, lang: str | None = None) -> str:
    key = TROOP_LETTER_I18N_KEY.get(troop_letter.upper(), "unit.any")
    return t(key, lang=lang)
