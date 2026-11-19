"""One-line log phrases. Wording comes from the translation tables."""

from __future__ import annotations

from .i18n import t, tf


def one_line(text: str) -> str:
    return " ".join(str(text).split())


def raha(amount: int) -> str:
    """Cash amount in the active language. The unit does not inflect."""
    return tf("log.cash_many", n=int(amount))


def gains_prefix() -> str:
    return t("log.gains_prefix")


def reward(tail_key: str, **kwargs) -> str:
    """A cash clause that starts with the shared 'player gains' prefix."""
    return gains_prefix() + tf(tail_key, **kwargs)


def join_and(parts: list[str]) -> str:
    bits = [p.strip().rstrip(".") for p in parts if p and p.strip()]
    if not bits:
        return ""
    conj = t("log.and")
    if len(bits) == 1:
        return bits[0]
    if len(bits) == 2:
        return f"{bits[0]} {conj} {bits[1]}"
    return ", ".join(bits[:-1]) + f" {conj} " + bits[-1]


def join_rewards(parts: list[str]) -> str:
    """One 'player gains' for every cash clause on the same action."""
    bits = [p.strip().rstrip(".") for p in parts if p and p.strip()]
    prefix = gains_prefix()
    if len(bits) > 1 and all(bit.startswith(prefix) for bit in bits):
        return prefix + join_and([bit[len(prefix):] for bit in bits])
    return join_and(bits)


def _or_fallback(key: str, fallback: str) -> str:
    text = t(key)
    return fallback if text == key else text


def color_adjective(color: str, *, plural: bool) -> str:
    form = "plural" if plural else "singular"
    return _or_fallback(f"color.{color}.{form}", color)


def scout_verb(verb: str) -> str:
    return _or_fallback(f"log.verb.{verb}", verb)


def queue_name(code_name: str) -> str:
    return _or_fallback(f"log.queue.{code_name}", code_name)


def player_log_name(player) -> str:
    name = " ".join(str(getattr(player, "name", "") or "").split())
    number = getattr(player, "number", 0)
    if not name or name == f"player_{number}":
        return tf("log.player_n", n=number)
    return name


def format_action_log(
    label: str,
    action_name: str,
    effects: list[str],
    rewards: list[str] | None = None,
) -> str:
    """One line: who performed which action, what happened, and the cash."""
    head = tf("log.action_head", label=label, action=action_name)
    bits = [one_line(e).rstrip(".") for e in effects if e and str(e).strip()]
    gained = join_rewards(list(rewards or []))
    if gained:
        bits.append(gained)
    if not bits:
        return head
    return one_line(head + " " + ", ".join(bits) + ".")


def frustration_line(label: str, blocked: list[dict]) -> str:
    buckets: dict[str, list[str]] = {}
    for face in blocked:
        title = str(face.get("name") or face.get("action_name") or "?").strip()
        blob = " ".join(str(r) for r in (face.get("reasons") or []))
        buckets.setdefault(_reason_kind(blob), []).append(title)
    if not buckets:
        detail = t("log.frustration.none_available")
    else:
        bits = []
        for kind, names in buckets.items():
            shown = ", ".join(f"*{name}*" for name in names)
            bits.append(f"{t('log.frustration.' + kind)} ({shown})")
        detail = ", ".join(bits)
    return one_line(tf("log.frustrated", label=label, detail=detail))


def _reason_kind(blob: str) -> str:
    low = blob.lower()
    if "zone" in low:
        return "zone"
    if "troop" in low or "limits" in low:
        return "troop"
    if "cost" in low or "hand" in low:
        return "cost"
    if "no active" in low or "no tired" in low or "not under" in low:
        return "none"
    if "overtake" in low or "bypass" in low or "cannot rest" in low:
        return "room"
    if "empty" in low or "needs" in low:
        return "empty"
    return "other"
