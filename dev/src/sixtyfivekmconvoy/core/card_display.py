"""Human-facing formatting for action card faces (web / CLI)."""

from __future__ import annotations

import csv
import os
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
    path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        "data",
        "cards",
        "action_help.csv",
    )
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


def _help_reward_values() -> dict[str, int]:
    """Cash and atrocity amounts a face tip may mention. Names match ``{placeholders}``."""
    from . import config

    def amount(name: str) -> int:
        return int(getattr(config, name, 0) or 0)

    return {
        "attack_cash": amount("ATTACK_CASH"),
        "service_cash": amount("SERVICE_CASH"),
        "soak_air_cash": amount("SOAK_AIR_CASH"),
        "soak_air_atrocities": amount("SOAK_AIR_ATROCITIES"),
        "soak_ground_cash": amount("SOAK_GROUND_CASH"),
        "soak_sabotage_cash": amount("SOAK_SABOTAGE_CASH"),
        "reveal_mauling_cash": amount("REVEAL_MAULING_CASH"),
        "reveal_resistance_cash": amount("REVEAL_RESISTANCE_CASH"),
    }


def _fill_help_amounts(entry: dict[str, str]) -> dict[str, str]:
    values = _help_reward_values()
    filled = dict(entry)
    for key in ("english_explanation", "finnish_explanation"):
        text = filled.get(key) or ""
        for name, value in values.items():
            text = text.replace("{" + name + "}", str(value))
        filled[key] = text
    return filled


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
