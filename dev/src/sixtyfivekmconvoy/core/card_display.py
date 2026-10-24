"""Human-facing formatting for action card faces (web / CLI)."""

from __future__ import annotations

import unicodedata
from typing import Any

from .cost import cost_rates_for_display
from .i18n import troop_label

# Bottom-row symbols (web may restyle these as CSS circles / card backs).
SYMBOL_TIREDNESS = "🟢"  # tiredness token
SYMBOL_INFLUENCE = "🟡"  # under-influence token
SYMBOL_ATROCITY = "⚪"  # atrocity token (white circle; matches unit UI)
SYMBOL_PLAYING_CARD = "🂠"  # one action card paid

# Default ASCII card inner width for left/right meta alignment.
DEFAULT_META_WIDTH = 40


def face_title(name: str, modifier: int | None) -> str:
    """Finnish card name with optional value in parentheses, e.g. 'Hyökkää (3)'."""
    if modifier is None or modifier == 0:
        return name
    return f"{name} ({modifier})"


def _n_cards(n: int) -> str:
    """Render n cards as '0🂠', '1🂠', '2🂠' (placeholder until custom numbered icons)."""
    return f"{max(0, int(n))}{SYMBOL_PLAYING_CARD}"


def _cards_per_token(n_cards: int, token: str) -> str:
    """e.g. '1🂠 / 🟢' or '2🂠 / 🟡'."""
    return f"{_n_cards(n_cards)} / {token}"


def format_cost(
    cost: str | int,
    *,
    action_name: str | None = None,
) -> str:
    """
    Cost as shown on cards, driven by the CSV cost string:
      1/T+1/U+1/A  →  1🂠 / 🟢 + 1🂠 / 🟡 + 1🂠 / ⚪
      1/T+2/U+1/A  →  1🂠 / 🟢 + 2🂠 / 🟡 + 1🂠 / ⚪
      1/T+1/U      →  1🂠 / 🟢 + 1🂠 / 🟡
      0, 1, 4      →  N🂠
    """
    del action_name  # display follows the cost string
    rates = cost_rates_for_display(cost)
    if rates is None:
        n = 0 if cost in ("0", 0, None, "") else int(cost)
        return _n_cards(n)
    t_r, u_r, a_r = rates
    parts: list[str] = []
    if t_r > 0:
        parts.append(_cards_per_token(t_r, SYMBOL_TIREDNESS))
    if u_r > 0:
        parts.append(_cards_per_token(u_r, SYMBOL_INFLUENCE))
    if a_r > 0:
        parts.append(_cards_per_token(a_r, SYMBOL_ATROCITY))
    return " + ".join(parts) if parts else _n_cards(0)


def format_effects(tire: int = 0, intoxicate: int = 0) -> str:
    """
    Side-effect markers (influence does not cascade — always +1 token):
      tires    →  → +1🟢
      intox.   →  → 1🟡
    """
    bits: list[str] = []
    if tire:
        bits.append(f"→ +1{SYMBOL_TIREDNESS}")
    if intoxicate:
        bits.append(f"→ 1{SYMBOL_INFLUENCE}")
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
    troop_key = {"P": "panzer", "I": "infantry", "L": "logistics", "A": "any"}.get(
        str(troop).upper()[:1] if troop else "A",
        "any",
    )
    t_r, u_r, a_r = rates if rates else (0, 0, 0)
    return {
        "troop_label": troop_label(troop),
        "troop_key": troop_key,
        "zone": zone,
        "title": face_title(name, modifier),
        "cost": cost_s,
        "effects": effects_s,
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
