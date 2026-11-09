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
        "deck.action": "Toiminta",
        "deck.resistance": "Vastarinta",
        "deck.pillage": "Ryöstö",
        "deck.mauling": "Moukarointi",
        "deck.officer": "Upseerit",
        "deck.hit": "Osuma",
        "deck.hit_1": "1 $",
        "deck.hit_3": "3 $",
        "deck.hit_5": "5 $",
        "deck.hit_10": "10 $",
        "ui.deck": "pakka",
        "ui.discard": "poistopino",
        "ui.queues": "Pakat ja jonot",
        "resistance.ambush": "Väijytys",
        "resistance.counterattack": "Vastahyökkäys",
        "resistance.hitpoints": "Osumapisteet",
        "resistance.durability": "Kestävyys",
        "resistance.pillage_cards": "Ryöstökortteja",
        "resistance.damage": "Vahinko",
        "mauling.target_type": "Kohde / tyyppi",
        "mauling.target": "Kohde",
        "mauling.type": "Tyyppi",
        "mauling.damage": "Vahinko",
        "mauling.hit_category": "Osumaluokka",
        "mauling.discard": "Korttien poisto",
        "mauling.must_discard": "Poista {n} korttia.",
        "mauling.fail_hit": "Jos kortteja ei ole tarpeeksi, ota osumaluokan {m} vahinko.",
        "attack.A": "A (ilma)",
        "attack.G": "G (maa)",
        "attack.S": "S (sabotaasi)",
        "attack.R": "R (vastarinta)",
        "pillage.cash": "Rahaa",
        "pillage.loot": "Ryöstösaalis",
        "pillage.atrocities": "Hirmutekoja",
        "pillage.atrocities_if_under_influence": "Hirmuteko, jos humalassa",
        "pillage.cards": "Kortteja",
        "pillage.intoxicate": "Humalaannuttaa",
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
        "deck.action": "Action",
        "deck.resistance": "Resistance",
        "deck.pillage": "Pillage",
        "deck.mauling": "Mauling",
        "deck.officer": "Officers",
        "deck.hit": "Hit",
        "deck.hit_1": "1 $",
        "deck.hit_3": "3 $",
        "deck.hit_5": "5 $",
        "deck.hit_10": "10 $",
        "ui.deck": "deck",
        "ui.discard": "discard",
        "ui.queues": "Decks and queues",
        "resistance.ambush": "Ambush",
        "resistance.counterattack": "Counterattack",
        "resistance.hitpoints": "Hit points",
        "resistance.durability": "Durability",
        "resistance.pillage_cards": "Pillage cards",
        "resistance.damage": "Damage",
        "mauling.target_type": "Target / type",
        "mauling.target": "Target",
        "mauling.type": "Type",
        "mauling.damage": "Damage",
        "mauling.hit_category": "Hit category",
        "mauling.discard": "Card discard",
        "mauling.must_discard": "Must discard {n} cards.",
        "mauling.fail_hit": "If not enough cards, take hit category {m} damage.",
        "attack.A": "A (air)",
        "attack.G": "G (ground)",
        "attack.S": "S (sabotage)",
        "attack.R": "R (resistance)",
        "pillage.cash": "Cash",
        "pillage.loot": "Loot",
        "pillage.atrocities": "Atrocities",
        "pillage.atrocities_if_under_influence": "Atrocity if under the influence",
        "pillage.cards": "Cards",
        "pillage.intoxicate": "Intoxicates",
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


_ZONE_ORDINALS = {
    1: "ensimmäinen",
    2: "toinen",
    3: "kolmas",
    4: "neljäs",
    5: "viides",
    6: "kuudes",
}

# (plural heading, singular heading) for convoy-order troop selectors.
_TROOP_WHICH = {
    "first": ("Etummaiset", "Etummainen"),
    "second": ("Toiset", "Toinen"),
    "second_last": ("Toiset", "Toinen"),
    "last": ("Perimmäiset", "Perimmäinen"),
}
_TROOP_NOUN = {
    0: ("panssarit", True),
    1: ("jalkaväki", False),
    2: ("huolto", False),
}
_ATROCITY_LABEL = {
    "first": "Eniten hirmutekoja, kärjestä",
    "second": "Toinen eniten hirmutekoja, kärjestä",
    "second_last": "Toinen eniten hirmutekoja, perältä",
    "last": "Eniten hirmutekoja, perältä",
}


def format_mauling_target(target: str) -> str:
    """Finnish Kohde line for a mauling or ambush target code."""
    text = (target or "").strip()
    if not text or text == "-":
        return ""
    if all(ch in "ABCE" for ch in text):
        if len(text) == 1:
            return f"Kaikki vyöhykkeellä {text}"
        if len(text) == 2:
            return f"Vyöhykkeet {text[0]} ja {text[1]}"
        return "Vyöhykkeet " + ", ".join(text[:-1]) + f" ja {text[-1]}"

    from .cards import parse_mauling_target

    try:
        sel = parse_mauling_target(text)
    except ValueError:
        return text

    kind = sel["kind"]
    if kind == "none":
        return ""
    if kind == "zone":
        return f"Kaikki vyöhykkeellä {sel['zone']}"
    if kind == "zone_rel":
        rel = int(sel["rel"])
        n = abs(rel)
        word = _ZONE_ORDINALS.get(n, f"{n}.")
        side = "kärjestä" if rel > 0 else "perältä"
        return f"Vyöhykkeen {sel['zone']} {word} {side}"
    if kind == "type":
        noun, plural = _TROOP_NOUN[int(sel["unit_type"])]
        head = _TROOP_WHICH[sel["which"]][0 if plural else 1]
        if sel["which"] == "second":
            return f"{head} {noun} kärjestä"
        if sel["which"] == "second_last":
            return f"{head} {noun} perältä"
        return f"{head} {noun}"
    if kind == "atrocity":
        return _ATROCITY_LABEL[sel["which"]]
    return text
