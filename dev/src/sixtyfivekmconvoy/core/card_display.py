"""Human-facing formatting for action card faces (web / CLI)."""

from __future__ import annotations

import csv
import unicodedata
from functools import lru_cache
from typing import Any

from .constants import ActionName
from .cost import cost_rates_for_display
from .i18n import troop_label

# Bottom-row symbols (web may restyle these as CSS circles / card backs).
SYMBOL_TIREDNESS = "🟢"  # tiredness token
SYMBOL_INFLUENCE = "🟡"  # under-influence token
SYMBOL_ATROCITY = "⚪"  # atrocity token (white circle; matches unit UI)
SYMBOL_PLAYING_CARD = "🂠"  # one action card paid
SYMBOL_OFFICER_DISCARD = "🂠↓"  # this officer card leaves play
SYMBOL_PASSIVE = "✦"  # always-on officer that changes another action

# Passive officer effect → action names it changes.
PASSIVE_TOUCHES: dict[str, frozenset[str]] = {
    "no_boozing_while_pillaging": frozenset({"pillage"}),
    "extra_damage_in_zone_A": frozenset({"attack", "assault", "retreat"}),
    "extra_pillage_search_card": frozenset({"search"}),
    "atrocity_conversion": frozenset({"pillage"}),
}

# Default ASCII card inner width for left/right meta alignment.
DEFAULT_META_WIDTH = 40


def _help_title_key(title: str | None) -> str:
    text = (title or "").strip().lower()
    for prefix in ("tietokone ehdottaa:", "uusi:"):
        if text.startswith(prefix):
            text = text[len(prefix) :].strip()
    return text.rstrip("!").strip()


@lru_cache(maxsize=1)
def load_action_help() -> tuple[dict[str, tuple[dict[str, str], ...]], dict[tuple[str, str], dict[str, str]]]:
    """Rows from ``action_help.csv``, keyed by action name and by Finnish title."""
    from .cards import _cards_path

    path = _cards_path("action_help.csv")
    by_action: dict[str, list[dict[str, str]]] = {}
    by_title: dict[tuple[str, str], dict[str, str]] = {}
    with open(path, encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            action_name = ActionName.normalize(row.get("action_name")) or ""
            if not action_name:
                continue
            entry = {
                "action_name": action_name,
                "english_title": (row.get("English_title") or "").strip(),
                "english_explanation": (row.get("English_explanation") or "").strip(),
                "finnish_title": (row.get("Finnish_title") or "").strip(),
                "finnish_explanation": (row.get("Finnish_explanation") or "").strip(),
            }
            by_action.setdefault(action_name, []).append(entry)
            by_title[(action_name, _help_title_key(entry["finnish_title"]))] = entry
    return (
        {key: tuple(rows) for key, rows in by_action.items()},
        by_title,
    )


_CASH_PLACEHOLDERS = (
    "attack_cash",
    "service_cash",
    "soak_air_cash",
    "soak_ground_cash",
    "soak_sabotage_cash",
    "reveal_mauling_cash",
    "reveal_resistance_cash",
    "cash_in_reward",
)
_ATROCITY_PLACEHOLDERS = (
    "soak_air_atrocities",
    "soak_ground_atrocities",
    "soak_sabotage_atrocities",
)


def _help_reward_values() -> dict[str, int]:
    """Amounts a face tip may mention. Names match ``{placeholders}`` in the CSV."""
    from . import config

    def amount(name: str) -> int:
        return int(getattr(config, name, 0) or 0)

    values = {name: amount(name.upper()) for name in (*_CASH_PLACEHOLDERS, *_ATROCITY_PLACEHOLDERS)}
    values["rest_tiredness"] = amount("REST_TIREDNESS")
    values["service_tiredness"] = amount("SERVICE_TIREDNESS")
    return values


def _english_amount(name: str, value: int) -> str:
    n = int(value)
    if name in _CASH_PLACEHOLDERS:
        return _money_phrase(n, "en")
    if name in _ATROCITY_PLACEHOLDERS:
        return f"{n} atrocity" if n == 1 else f"{n} atrocities"
    if name in ("rest_tiredness", "service_tiredness"):
        return f"{n} tiredness"
    return str(n)


def _finnish_amount(name: str, value: int) -> str:
    n = int(value)
    if name in _CASH_PLACEHOLDERS:
        return _money_phrase(n, "fi")
    if name in _ATROCITY_PLACEHOLDERS:
        if n == 1:
            return "1 hirmutekopisteen"
        return f"{n} hirmutekopistettä"
    if name == "service_tiredness":
        if n == 1:
            return "1 väsymys"
        return f"{n} väsymystä"
    if name == "rest_tiredness":
        if n == 1:
            return "1 väsymysmerkki"
        return f"{n} väsymysmerkkiä"
    return str(n)


def _fill_help_amounts(entry: dict[str, str]) -> dict[str, str]:
    values = _help_reward_values()
    filled = dict(entry)
    for key, phrase in (
        ("english_explanation", _english_amount),
        ("finnish_explanation", _finnish_amount),
    ):
        text = filled.get(key) or ""
        lang = "en" if key.startswith("english") else "fi"
        text = text.replace("{cash_in_where}", _cash_in_where(lang))
        for name, value in values.items():
            text = text.replace("{" + name + "}", phrase(name, value))
        filled[key] = text
    return filled


def _cash_in_where(lang: str) -> str:
    """Where sell's cards go, in the language of the face tip."""
    from .configs import get_config

    remove = bool(getattr(get_config(), "CASH_IN_REMOVES_FROM_PLAY", False))
    if lang == "fi":
        if remove:
            return "Kortit poistuvat pelistä eivätkä palaa pakkaan."
        return "Kortit menevät poistopakkaan."
    if remove:
        return "The cards leave the game and do not return to the deck."
    return "The cards go to the discard pile."


def _printed_sell_cost(cfg) -> int:
    from .cards import ACTION_CATALOG
    from .constants import ActionName

    costs: list[int] = []
    for card in ACTION_CATALOG.values():
        for face in getattr(card, "actions", ()) or ():
            if ActionName.normalize(getattr(face, "action_name", None)) != ActionName.SELL:
                continue
            raw = str(getattr(face, "cost", "0")).strip()
            if raw.isdigit():
                costs.append(int(raw))
    if costs:
        return costs[0]
    return int(getattr(cfg, "CASH_IN_CARDS", 4) or 4)


def _money_phrase(amount: int, lang: str) -> str:
    """Cash amount with the unit from ``log.cash_many`` (``N $``)."""
    from .i18n import t

    return t("log.cash_many", lang=lang).replace("{n}", str(int(amount)))


def _fi_cash(amount: int) -> str:
    """Finnish cash phrase for the rules page, independent of the UI language."""
    return _money_phrase(amount, "fi")


def rules_placeholders() -> dict[str, str]:
    """Values the start-page rules substitute from the active balance profile."""
    from .configs import get_config
    from .i18n import t

    cfg = get_config()

    def amount(name: str) -> str:
        return str(int(getattr(cfg, name, 0) or 0))

    cards = _printed_sell_cost(cfg)
    reward = int(getattr(cfg, "CASH_IN_REWARD", 1) or 0)
    cash = _fi_cash(reward)
    if bool(getattr(cfg, "CASH_IN_REMOVES_FROM_PLAY", False)):
        cash_in = (
            f"Maksaa {cards} korttia. Kortit poistuvat pelistä eivätkä palaa "
            f"pakkaan, ja saat {cash}."
        )
    else:
        cash_in = (
            f"Maksaa {cards} korttia. Kortit menevät poistopakkaan ja saat {cash}."
        )
    raw = _help_reward_values()
    values = {
        name: _fi_cash(value) if name in _CASH_PLACEHOLDERS else str(int(value))
        for name, value in raw.items()
    }
    values.update(
        {
            "cards_to_deal": amount("CARDS_TO_DEAL"),
            "cash_to_win": _fi_cash(int(getattr(cfg, "CASH_TO_WIN", 0) or 0)),
            "promotions_to_win": amount("PROMOTION_POINTS_TO_WIN"),
            "cash_in_sentence": cash_in,
            "cash_unit": t("ui.cash_unit", lang="fi"),
        }
    )
    return values


def fill_rules_html(html: str) -> str:
    """Replace ``{name}`` tokens in the rules page from the active profile."""
    text = html
    for name, value in rules_placeholders().items():
        text = text.replace("{" + name + "}", value)
    return text


def action_help_for(action_name: str | None, finnish_name: str | None = None) -> dict[str, str]:
    """Help text for one action face. Empty strings when the action is unknown."""
    empty = {
        "action_name": ActionName.normalize(action_name) or "",
        "english_title": "",
        "english_explanation": "",
        "finnish_title": "",
        "finnish_explanation": "",
    }
    key = empty["action_name"]
    if not key:
        return empty
    by_action, by_title = load_action_help()
    titled = by_title.get((key, _help_title_key(finnish_name)))
    if titled is None:
        rows = by_action.get(key) or ()
        titled = rows[0] if rows else None
    if titled is None:
        return empty
    return _fill_help_amounts(titled)


def face_title(name: str, modifier: int | None) -> str:
    """Finnish card name with optional value in parentheses, e.g. 'Hyökkää (3)'."""
    if modifier is None or modifier == 0:
        return name
    return f"{name} ({modifier})"


def action_reward_bits(action_name: str | None) -> dict[str, Any]:
    """
    Possible cash / atrocity from a successful meaningful resolution.

    Shown in parentheses on the face (e.g. '(+$2)' or '(+$2 +⚪)') because the
    gain only applies when the action actually pays off (hit, soak, service, …).
    """
    empty = {"cash": 0, "atrocities": 0, "contingent": True, "label": ""}
    if not action_name:
        return empty
    from . import config
    from .constants import ActionName

    key = ActionName.normalize(action_name) or str(action_name).lower().strip()
    cash = 0
    atrocities = 0
    if key == ActionName.SERVICE:
        cash = int(getattr(config, "SERVICE_CASH", 0) or 0)
    elif key == ActionName.ATTACK:
        cash = int(getattr(config, "ATTACK_CASH", 0) or 0)
    elif key == ActionName.SELL:
        cash = int(getattr(config, "CASH_IN_REWARD", 0) or 0)
    elif key == ActionName.SCOUT:
        cash = int(getattr(config, "REVEAL_RESISTANCE_CASH", 0) or 0)
    elif key == ActionName.SIGINT:
        cash = int(getattr(config, "REVEAL_MAULING_CASH", 0) or 0)
    elif key in (ActionName.DEFEND, ActionName.HUMAN_SHIELDS, ActionName.PATROL):
        soak = {
            ActionName.HUMAN_SHIELDS: (
                int(getattr(config, "SOAK_AIR_CASH", 0) or 0),
                int(getattr(config, "SOAK_AIR_ATROCITIES", 0) or 0),
            ),
            ActionName.DEFEND: (
                int(getattr(config, "SOAK_GROUND_CASH", 0) or 0),
                int(getattr(config, "SOAK_GROUND_ATROCITIES", 0) or 0),
            ),
            ActionName.PATROL: (
                int(getattr(config, "SOAK_SABOTAGE_CASH", 0) or 0),
                int(getattr(config, "SOAK_SABOTAGE_ATROCITIES", 0) or 0),
            ),
        }[key]
        cash, atrocities = soak
    return {
        "cash": cash,
        "atrocities": atrocities,
        "contingent": True,
        "label": format_reward_label(cash, atrocities),
    }


def action_cash_bonus(action_name: str | None) -> int:
    """Cash part of action_reward_bits (compat helper)."""
    return int(action_reward_bits(action_name).get("cash") or 0)


def format_reward_label(cash: int = 0, atrocities: int = 0) -> str:
    """Parenthetical contingent reward, e.g. '(+$2)', '(+$2 +⚪)', '(+⚪)'."""
    bits: list[str] = []
    if cash > 0:
        bits.append(f"+{cash}")
    if atrocities > 0:
        if atrocities == 1:
            bits.append(f"+{SYMBOL_ATROCITY}")
        else:
            bits.append(f"+{atrocities}{SYMBOL_ATROCITY}")
    if not bits:
        return ""
    return "(" + " ".join(bits) + ")"


def _n_cards(n: int) -> str:
    """Flat card cost: '0🂠', '1🂠', '2🂠', …"""
    return f"{max(0, int(n))}{SYMBOL_PLAYING_CARD}"


def _card_glyphs(n: int) -> str:
    """n card backs with no leading digit: '🂠', '🂠🂠', …"""
    return SYMBOL_PLAYING_CARD * max(0, int(n))


def format_cost(
    cost: str | int,
    *,
    action_name: str | None = None,
) -> str:
    """
    Cost as shown on cards, driven by the CSV cost string.

    Token rates are grouped by cards-per-token:
      1/T+1/U+1/A  →  🂠 🟢🟡⚪
      1/T+2/U+1/A  →  🂠 🟢⚪ + 🂠🂠 🟡
      1/T+1/U      →  🂠 🟢🟡
      0, 1, 4      →  N🂠
    """
    del action_name  # display follows the cost string
    rates = cost_rates_for_display(cost)
    if rates is None:
        n = 0 if cost in ("0", 0, None, "") else int(cost)
        return _n_cards(n)
    t_r, u_r, a_r = rates
    by_rate: dict[int, list[str]] = {}
    for rate, token in (
        (t_r, SYMBOL_TIREDNESS),
        (u_r, SYMBOL_INFLUENCE),
        (a_r, SYMBOL_ATROCITY),
    ):
        if rate > 0:
            by_rate.setdefault(rate, []).append(token)
    if not by_rate:
        return _n_cards(0)
    # Stable order: ascending card count, tokens keep T → U → A insertion order.
    parts = [
        f"{_card_glyphs(rate)} {''.join(tokens)}"
        for rate, tokens in sorted(by_rate.items())
    ]
    return " + ".join(parts)


def officer_spent_cost(cost_label: str, raw_cost: str | int | None) -> str:
    """Hand-card cost, plus a mark that the officer card itself is discarded."""
    if raw_cost in (0, "0", None, ""):
        return SYMBOL_OFFICER_DISCARD
    return f"{cost_label} + {SYMBOL_OFFICER_DISCARD}"


def passive_clues_for(officers: list[Any], action_name: str | None) -> list[dict[str, str]]:
    """Officers whose always-on effect changes this action."""
    key = ActionName.normalize(action_name) or ""
    clues: list[dict[str, str]] = []
    for officer in officers:
        effect = getattr(officer, "passive_effect", None) or ""
        if key and key in PASSIVE_TOUCHES.get(effect, frozenset()):
            clues.append(
                {
                    "mark": SYMBOL_PASSIVE,
                    "name": getattr(officer, "name", "") or "",
                    "effect": effect,
                }
            )
    return clues


def format_effects(tire: int = 0, intoxicate: int = 0) -> str:
    """
    Side-effect markers (influence does not cascade — always +1 token):
      tires 1  →  → +🟢
      tires n  →  → +n🟢
      intox 1  →  → 🟡
      intox n  →  → n🟡
    """
    bits: list[str] = []
    if tire:
        if int(tire) == 1:
            bits.append(f"→ +{SYMBOL_TIREDNESS}")
        else:
            bits.append(f"→ +{int(tire)}{SYMBOL_TIREDNESS}")
    if intoxicate:
        if int(intoxicate) == 1:
            bits.append(f"→ {SYMBOL_INFLUENCE}")
        else:
            bits.append(f"→ {int(intoxicate)}{SYMBOL_INFLUENCE}")
    return "  ".join(bits)


def display_width(s: str) -> int:
    """Terminal display columns for `s` (emoji / wide glyphs ≈ 2)."""
    width = 0
    for ch in s:
        o = ord(ch)
        if unicodedata.combining(ch) or o in (0xFE0E, 0xFE0F, 0x200D):
            continue
        ea = unicodedata.east_asian_width(ch)
        if ea in ("F", "W"):
            width += 2
        elif (
            0x1F000 <= o <= 0x1FFFF  # emoji & playing cards
            or 0x2600 <= o <= 0x27BF  # misc symbols
            or 0x2300 <= o <= 0x23FF
        ):
            width += 2
        else:
            width += 1
    return width


def pad_display(s: str, width: int, *, align: str = "left") -> str:
    """Pad `s` with spaces to `width` display columns."""
    gap = max(0, width - display_width(s))
    if align == "right":
        return (" " * gap) + s
    if align == "center":
        left = gap // 2
        return (" " * left) + s + (" " * (gap - left))
    return s + (" " * gap)


def align_meta(cost: str, effects: str, width: int = DEFAULT_META_WIDTH) -> str:
    """Cost left-aligned, effects right-aligned within `width` display columns."""
    if not effects:
        return pad_display(cost, width)
    gap = width - display_width(cost) - display_width(effects)
    if gap < 1:
        gap = 1
    return cost + (" " * gap) + effects


def face_meta(
    cost: str | int,
    tire: int = 0,
    intoxicate: int = 0,
    *,
    action_name: str | None = None,
    width: int = DEFAULT_META_WIDTH,
) -> str:
    """Bottom row: cost on the left, → effects on the right."""
    del action_name
    return align_meta(
        format_cost(cost),
        format_effects(tire, intoxicate),
        width=width,
    )


def format_face(action: Any, *, meta_width: int = DEFAULT_META_WIDTH) -> dict[str, Any]:
    """
    Build display fields for one action-card face.

    Accepts a CardAction or a describe() dict.
    `meta` has cost left / effects right; web can also use `cost` + `effects` with CSS.
    """
    if hasattr(action, "name"):
        name = action.name
        modifier = action.action_modifier
        cost = action.cost
        tire = action.tire
        intoxicate = action.intoxicate
        troop = action.troop_type
        zone = action.zone
        action_name = getattr(action, "action_name", None)
    else:
        name = action["name"]
        modifier = action.get("action_modifier", 0)
        cost = action.get("cost", "0")
        tire = action.get("tire", 0)
        intoxicate = action.get("intoxicate", 0)
        troop = action.get("troop_type", "A")
        zone = action.get("zone", "")
        action_name = action.get("action_name")

    rates = cost_rates_for_display(cost)
    cost_s = format_cost(cost)
    effects_s = format_effects(tire, intoxicate)
    officer_discard = bool(action.get("is_officer_discard")) if isinstance(action, dict) else bool(
        getattr(action, "is_officer_discard", False)
    )
    if officer_discard:
        cost_s = officer_spent_cost(cost_s, cost)
        officer_name = action.get("officer_name") if isinstance(action, dict) else None
        if officer_name:
            name = officer_name
    reward = action_reward_bits(action_name or name)
    troop_key = {"P": "panzer", "I": "infantry", "L": "logistics", "A": "any"}.get(
        str(troop).upper()[:1] if troop else "A",
        "any",
    )
    t_r, u_r, a_r = rates if rates else (0, 0, 0)
    resolved_name = ActionName.normalize(action_name) or ActionName.normalize(name) or ""
    return {
        "action_name": resolved_name,
        "help": action_help_for(resolved_name, name),
        "troop_label": troop_label(troop),
        "troop_key": troop_key,
        "zone": zone,
        "title": face_title(name, modifier),
        "cost": cost_s,
        "effects": effects_s,
        "cash_bonus": int(reward.get("cash") or 0),
        "reward": reward,
        "meta": align_meta(cost_s, effects_s, width=meta_width),
        "cost_includes_atrocities": a_r > 0,
        "cost_rates": {
            "tiredness": t_r,
            "influence": u_r,
            "atrocity": a_r,
        },
        "symbols": {
            "tiredness": SYMBOL_TIREDNESS,
            "influence": SYMBOL_INFLUENCE,
            "atrocity": SYMBOL_ATROCITY,
            "playing_card": SYMBOL_PLAYING_CARD,
        },
    }


def describe_action_card(card_id: int) -> dict[str, Any]:
    """JSON-friendly action card for the web UI (all faces)."""
    from .i18n import get_language

    return _describe_action_card(card_id, get_language())


@lru_cache(maxsize=512)
def _describe_action_card(card_id: int, _lang: str) -> dict[str, Any]:
    from .cards import ACTION_CATALOG

    card = ACTION_CATALOG[card_id]
    return {
        "id": card_id,
        "faces": [format_face(a) for a in card.actions],
    }


def render_card_ascii(card_id: int, actions: list[Any], *, inner_width: int = DEFAULT_META_WIDTH) -> str:
    """Draw one action card with borders aligned using display_width."""
    w = inner_width
    lines: list[str] = []
    header = pad_display(f" #{card_id} ", w, align="center").replace(" ", "─")
    # center title on dashes: rebuild properly
    label = f" #{card_id} "
    side = max(0, w - display_width(label))
    left_d = side // 2
    right_d = side - left_d
    lines.append("┌" + ("─" * left_d) + label + ("─" * right_d) + "┐")

    for i, action in enumerate(actions):
        f = format_face(action, meta_width=w)
        troop = f" {f['troop_label'].upper()}"
        zone = f"{f['zone']} "
        gap = max(1, w - display_width(troop) - display_width(zone))
        lines.append("│" + troop + (" " * gap) + zone + "│")
        lines.append("│" + pad_display(f" {f['title']}", w) + "│")
        lines.append("│" + pad_display(f["meta"], w) + "│")
        if i < len(actions) - 1:
            lines.append("├" + ("─" * w) + "┤")

    lines.append("└" + ("─" * w) + "┘")
    return "\n".join(lines)
