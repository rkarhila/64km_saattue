"""Action legality and resolution helpers (pure; choices via engine.request_choice)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Generator

from .constants import (
    ATTACK_TYPE_BY_DEFENCE_ACTION,
    ActionName,
    AttackType,
    ChoiceType,
    PLAYER_COLORS,
    UNIT_TYPE_LETTER,
    UNIT_TYPE_STR,
)
from sixtyfivekmconvoy.rl.events import EVENT_INFLUENCE, EVENT_PILLAGE, EVENT_REVEAL

from .cards import OfficerCard, OFFICER_CATALOG, parse_mauling_target
from .cost import evaluate_cost
from .i18n import t, tf, unit_type_label
from .log_text import (
    color_adjective,
    format_action_log,
    gains_prefix,
    one_line,
    player_log_name,
    queue_name,
    raha,
    reward,
    scout_verb,
)

if TYPE_CHECKING:
    from .engine import ChoiceRequest, GameEngine
    from .models import Convoy, Unit


def _select_payment_cards(
    engine: GameEngine,
    payer,
    action: dict,
    name: str,
    cost: int,
    *,
    sell: bool = False,
):
    """Choose ``cost`` hand cards. The caller moves them."""
    from .engine import ChoiceRequest

    if cost <= 0:
        return []
    if cost >= len(payer.action_cards):
        return list(payer.action_cards)
    reward_amount = 0
    removes = False
    if sell:
        reward_amount, removes = engine.sell_income()
        desc = tf(
            "log.sell_pay_remove" if removes else "log.sell_pay",
            cost=cost,
            action=action.get("name", name),
            cash=raha(reward_amount),
        )
    else:
        desc = tf("log.pay_cost", cost=cost, action=action.get("name", name))
    for card_id in payer.action_cards:
        card_desc = payer.action_deck.describe(card_id) if payer.action_deck else card_id
        if isinstance(card_desc, list):
            clabel = "/".join(f["name"] for f in card_desc if isinstance(f, dict))
        elif isinstance(card_desc, dict):
            clabel = card_desc.get("name", str(card_id))
        else:
            clabel = str(card_desc)
        desc += f"\n  {card_id}: {clabel}"
    payload = {
        "reason": "pay_cost",
        "action_name": action.get("name", name),
        "cost": cost,
    }
    if sell:
        payload.update(sell=True, reward=reward_amount, removes=removes)
    chosen = yield ChoiceRequest(
        player_id=payer.agent_id(),
        choicetype=ChoiceType.CHOOSE_CARDS_TO_DISCARD,
        options=list(payer.action_cards),
        num_choices=cost,
        description=desc,
        payload=payload,
    )
    return list(chosen)


def _trace_payment(engine: GameEngine, payer, action: dict, name: str, cards: list[int]) -> None:
    if not getattr(engine, "balance_trace", False) or not cards:
        return
    deck = payer.action_deck
    engine.trace_payments.append(
        {
            "player": payer.number,
            "action": str(action.get("name") or name),
            "action_name": name,
            "cards": [
                {
                    "id": int(card),
                    "name": deck.label(card) if deck is not None else str(card),
                }
                for card in cards
            ],
        }
    )


def unit_log_label(unit: Unit) -> str:
    """Human-readable unit id, e.g. 'Foo siniset panssarit'."""
    color = PLAYER_COLORS[unit.player.number % len(PLAYER_COLORS)]
    adj = color_adjective(color, plural=unit.unittype == 0)
    return f"{player_log_name(unit.player)} {adj} {unit_type_label(unit.unittype)}"


def get_cost(
    unit: Unit,
    cost: str | int,
    *,
    action_name: str | None = None,
) -> int:
    """
    Cards to discard for an action.

    Cost comes from the card CSV. Forms:
      0, 1, 4              — flat card count
      1/T+1/U              — token formula (T=tired, U=influence, A=atrocity)
      T                    — legacy alias for 1/T+1/U+1/A

    `action_name` is ignored; kept for call-site compatibility.
    """
    del action_name  # cost string is authoritative
    return evaluate_cost(unit, cost)


def unit_zones(convoy: Convoy, actor_idx: int) -> list[str]:
    unit = convoy.units[actor_idx]
    return [unit.zone()]


# Scout / reveal queue option codes (stable for ChoiceRequest options).
SCOUT_QUEUE_PILLAGE = 0
SCOUT_QUEUE_MAULING = 1
SCOUT_QUEUE_RESISTANCE = 2
SCOUT_QUEUE_NAMES = {
    SCOUT_QUEUE_PILLAGE: "pillage",
    SCOUT_QUEUE_MAULING: "mauling",
    SCOUT_QUEUE_RESISTANCE: "resistance",
}


def scoutable_queues(
    engine: GameEngine,
    *,
    allowed_codes: set[int] | frozenset[int] | None = None,
) -> list[tuple[int, str]]:
    """Return (code, name) for queues that still have face-down cards."""
    mapping = [
        (SCOUT_QUEUE_PILLAGE, "pillage", engine.pillage_queue),
        (SCOUT_QUEUE_MAULING, "mauling", engine.mauling_queue),
        (SCOUT_QUEUE_RESISTANCE, "resistance", engine.resistance_queue),
    ]
    if allowed_codes is not None:
        mapping = [row for row in mapping if row[0] in allowed_codes]
    return [(code, name) for code, name, queue in mapping if queue.contains_hidden_cards()]


def hidden_queue_summary(engine: GameEngine) -> str:
    """Compact queue visibility for logs."""
    parts: list[str] = []
    for name, queue in (
        ("resistance", engine.resistance_queue),
        ("mauling", engine.mauling_queue),
        ("pillage", engine.pillage_queue),
    ):
        total = len(queue)
        hidden = sum(1 for _, vis in queue.cards_and_visibilities if not vis)
        parts.append(
            tf(
                "log.queue_visibility",
                queue=queue_name(name),
                up=total - hidden,
                hidden=hidden,
            )
        )
    return " ".join(parts)


def why_action_impossible(
    engine: GameEngine,
    actor_idx: int,
    action: dict,
    hand_size: int | None = None,
) -> list[str]:
    """
    Reasons this action cannot be taken now. Empty list ⇒ legal.
    Used for legality checks and diagnostic game logging.
    """
    reasons: list[str] = []
    name = ActionName.normalize(action.get("action_name", ""))
    if not name:
        return ["missing action_name"]
    if name in ActionName.UNIMPLEMENTED:
        reasons.append(f"action '{name}' is unimplemented")
        return reasons

    convoy = engine.convoy
    if actor_idx < 0 or actor_idx >= len(convoy.units):
        return [f"invalid unit index {actor_idx}"]
    unit = convoy.units[actor_idx]
    limits = action.get("limits") or {}
    letter = UNIT_TYPE_LETTER[unit.unittype]
    if letter not in limits:
        reasons.append(
            f"troop {letter} not in face limits {sorted(limits.keys())}"
        )
    else:
        zones = unit_zones(convoy, actor_idx)
        allowed = limits[letter]
        if not any(z in allowed for z in zones):
            reasons.append(
                f"zone {zones} not in allowed '{allowed}' for {letter}"
            )

    cost_player = action.get("_cost_player")  # optional override (Order nested play)
    payer = cost_player if cost_player is not None else unit.player
    required = get_cost(unit, action.get("cost", "0"))
    hand = len(payer.action_cards) if hand_size is None else max(0, int(hand_size))
    if hand < required:
        reasons.append(f"cost {required} but hand has {hand}")

    if reasons:
        return reasons

    modifier = action.get("action_modifier", 0)

    if name == ActionName.ATTACK:
        if not engine.resistance.active:
            reasons.append("no active resistance to attack")
    elif name == ActionName.ASSAULT:
        if not engine.resistance.active:
            reasons.append("no active resistance to assault")
        elif not unit.can_overtake(1):
            reasons.append("cannot overtake forward for assault")
    elif name == ActionName.RETREAT:
        if not engine.resistance.active:
            reasons.append("no active resistance to retreat")
        elif not unit.can_overtake(-1):
            reasons.append("cannot overtake backward for retreat")
    elif name == ActionName.BYPASS:
        if unit.bypass_distance(modifier) <= 0:
            reasons.append(f"cannot bypass/overtake by {modifier}")
    elif name == ActionName.PILLAGE:
        if len(engine.pillage_queue) < 1:
            reasons.append("pillage queue empty")
    elif name == ActionName.PILLAGE_WITH_EXTRA_ATROCITY:
        if len(engine.pillage_queue) < 2:
            reasons.append("pillage queue needs ≥2 cards")
    elif name == ActionName.REST:
        if modifier == 2:
            if not unit.can_rest_with_cards():
                reasons.append("cannot rest with cards")
        elif not unit.can_rest():
            reasons.append("cannot rest")
    elif name == ActionName.SERVICE:
        prev_u, next_u = unit.get_neighbours()
        if not (
            (prev_u is not None and prev_u.tired > 0)
            or (next_u is not None and next_u.tired > 0)
        ):
            reasons.append("no tired neighbour to service")
    elif name == ActionName.SOBER_UP:
        if unit.under_influence <= 0:
            reasons.append("not under influence")
        if _has_officer(unit, "sober_up") is None:
            reasons.append("no sober_up officer")
    elif name == ActionName.SUICIDAL_ATTACK:
        if not engine.resistance.active:
            reasons.append("no active resistance for suicidal attack")
    elif name == ActionName.EXIT_FROM_C_WITH_COST:
        if unit.zone() != "C":
            reasons.append(f"exit-from-C requires zone C, at {unit.zone()}")
        need = modifier or 5
        if unit.player.total_cash < need:
            reasons.append(f"need {need} cash, have {unit.player.total_cash}")
    elif name in (
        ActionName.SCOUT,
        ActionName.SIGINT,
        ActionName.SEARCH,
        ActionName.SEARCH_PILLAGE_COMBO,
    ):
        # Legal whenever the unit is in the zone and the cost can be paid.
        # Resolution flips face-down queue cards, then peeks the deck for
        # any flips that did not fit in the queue.
        pass
    elif name == ActionName.PROMOTE:
        if not matching_officer_queue_indices(engine, unit):
            letter = UNIT_TYPE_LETTER[unit.unittype]
            reasons.append(
                f"no officer in queue matching troop {letter}"
            )
    elif name == ActionName.ORDER:
        if not order_wait_targets(engine, unit):
            reasons.append(
                "order needs a neighbouring wait "
                "(previous already waited, or following card has Wait)"
            )
        # After paying Order's cost there must still be a card to assign.
        if len(unit.player.action_cards) <= required:
            reasons.append(
                "order needs a hand card left to assign after paying cost"
            )
    elif name in (
        ActionName.DEFEND,
        ActionName.HUMAN_SHIELDS,
        ActionName.PATROL,
        ActionName.WAIT,
        ActionName.EXIT,
        ActionName.SELL,
    ):
        pass
    # Unknown actions: allow (legacy default) unless already rejected above.
    return reasons


def is_action_possible(engine: GameEngine, actor_idx: int, action: dict) -> bool:
    return not why_action_impossible(engine, actor_idx, action)


def officer_troop_letters(officer: OfficerCard) -> set[str]:
    """
    Troop types an officer may be promoted onto.

    CSV `troop_type` is a letter set: A = all (P/I/L), otherwise each char
    is an allowed type (e.g. IP → panzer+infantry, L → logistics only).
    """
    raw = (officer.troop_type or "A").strip().upper()
    if not raw or raw == "A":
        return set(UNIT_TYPE_LETTER.values())
    return {ch for ch in raw if ch in UNIT_TYPE_LETTER.values()}


def officer_matches_unit(officer: OfficerCard, unit: Unit) -> bool:
    return UNIT_TYPE_LETTER[unit.unittype] in officer_troop_letters(officer)


def matching_officer_queue_indices(engine: GameEngine, unit: Unit) -> list[int]:
    """Queue indices of officers eligible for this unit's troop type."""
    oq = engine.officer_queue
    out: list[int] = []
    for i, (seq_id, _) in enumerate(oq.cards_and_visibilities):
        real_id = engine.officer_id_mapping.get(seq_id, seq_id)
        officer = OFFICER_CATALOG.get(real_id)
        if officer is not None and officer_matches_unit(officer, unit):
            out.append(i)
    return out


def _cash_for_revealed_cards(
    engine: GameEngine,
    player,
    code: int,
    count: int,
    label: str,
    paid_types: set[int] | None = None,
) -> str | None:
    """Pay for mauling or resistance cards turned face up. Pillage pays nothing.

    With ``REVEAL_CASH_PER_CARD`` false, the configured amount is paid once
    per action for that card type, as long as at least one card was turned.
    ``paid_types`` stops a later deck look in the same action from paying again.
    """
    del engine, label
    if count <= 0:
        return
    from .config import (
        REVEAL_CASH_PER_CARD,
        REVEAL_MAULING_CASH,
        REVEAL_RESISTANCE_CASH,
    )

    if code == SCOUT_QUEUE_MAULING:
        per, source, kind = REVEAL_MAULING_CASH, "reveal mauling", "mauling"
    elif code == SCOUT_QUEUE_RESISTANCE:
        per, source, kind = REVEAL_RESISTANCE_CASH, "reveal resistance", "resistance"
    else:
        return
    if per <= 0:
        return
    if not REVEAL_CASH_PER_CARD and paid_types is not None and code in paid_types:
        return
    total = per * count if REVEAL_CASH_PER_CARD else per
    if paid_types is not None:
        paid_types.add(code)
    player.get_cash(total, source=source)
    kind_fi = t(f"log.reveal_kind.{kind}")
    return reward("log.for_reveal", cash=raha(total), count=count, kind=kind_fi)


def _note_resistance_pay(engine: GameEngine, player, status: int, rewards: list[str]) -> None:
    hit_pay = _cash_for_resistance_hit(player, status)
    if hit_pay:
        rewards.append(hit_pay)
    destroy_pay = getattr(engine.resistance, "last_destroy_reward", None)
    if destroy_pay:
        rewards.append(destroy_pay)
        engine.resistance.last_destroy_reward = None


def _absorb_scout_lines(lines: list[str], effects: list[str], rewards: list[str]) -> None:
    for line in lines:
        if line.startswith(gains_prefix()):
            rewards.append(line)
        else:
            effects.append(line)


def _cash_for_resistance_hit(player, status: int) -> str | None:
    """Grant hit cash when resistance is damaged but not destroyed."""
    if status != 1:
        return None
    from .config import RESISTANCE_HIT_CASH

    if RESISTANCE_HIT_CASH <= 0:
        return None
    player.get_cash(RESISTANCE_HIT_CASH, source="resistance hit")
    return reward("log.for_hit", cash=raha(RESISTANCE_HIT_CASH))


def _current_action_index(engine: GameEngine) -> int:
    return int(getattr(engine, "current_action_index", 0) or 0)


def _card_faces(unit: Unit, card_id: int) -> list[dict]:
    if unit.player.action_deck is None:
        return []
    desc = unit.player.action_deck.describe(card_id)
    return list(desc) if isinstance(desc, list) else []


def _card_has_wait_face(unit: Unit, card_id: int) -> bool:
    return any(
        ActionName.normalize(f.get("action_name")) == ActionName.WAIT
        for f in _card_faces(unit, card_id)
    )


def _unit_resolved_wait(unit: Unit, action_index: int) -> bool:
    """True if this unit already resolved Wait at ``action_index``."""
    if action_index >= len(unit.actioncard):
        return False
    if action_index >= len(unit.action_resolution):
        return False
    res = unit.action_resolution[action_index]
    if not res or res.get("kind") == "frustrated":
        return False
    if ActionName.normalize(str(res.get("action_name") or "")) == ActionName.WAIT:
        return True
    face_i = res.get("face_index")
    if face_i is None:
        return ActionName.normalize(str(res.get("name") or "")) == ActionName.WAIT
    faces = _card_faces(unit, unit.actioncard[action_index])
    if 0 <= int(face_i) < len(faces):
        return (
            ActionName.normalize(faces[int(face_i)].get("action_name"))
            == ActionName.WAIT
        )
    return False


def order_wait_targets(engine: GameEngine, ordering_unit: Unit) -> list[Unit]:
    """
    Neighbouring units that Order may target at the current action index.

    - Previous: already resolved Wait (revealed earlier in convoy order).
    - Following: assigned card has a Wait face (may be revealed during Order).
    """
    action_index = _current_action_index(engine)
    preceding, following = ordering_unit.get_neighbours()
    targets: list[Unit] = []
    if preceding is not None and _unit_resolved_wait(preceding, action_index):
        targets.append(preceding)
    if (
        following is not None
        and action_index < len(following.actioncard)
        and _card_has_wait_face(following, following.actioncard[action_index])
    ):
        targets.append(following)
    return targets


def _reveal_unit_action_card(engine: GameEngine, unit: Unit, action_index: int) -> None:
    """Face-up a unit's stack card for everyone (Order peek on following neighbour)."""
    if action_index < 0 or action_index >= len(unit.actioncard):
        return
    unit.revealed_card_indices.add(action_index)
    card_id = unit.actioncard[action_index]
    faces = _card_faces(unit, card_id)
    names = "/".join(
        str(f.get("name") or f.get("action_name") or "?") for f in faces
    ) or str(card_id)
    engine._broadcast(
        one_line(tf("log.order_peek", label=unit_log_label(unit), names=names))
    )


def resolve_order(
    engine: GameEngine, ordering_unit: Unit
) -> Generator[ChoiceRequest, list[int], str]:
    """
    Order: assign one hand card to a neighbouring Wait unit, resolve that action
    immediately as the waiter (orderer pays costs), then return the card to hand.
    """
    from .engine import ChoiceRequest
    from .card_display import format_face

    orderer = ordering_unit.player
    targets = order_wait_targets(engine, ordering_unit)
    if not targets:
        return t("log.order_no_waiter")
    if not orderer.action_cards:
        return t("log.order_empty_hand")

    action_index = _current_action_index(engine)
    preceding, following = ordering_unit.get_neighbours()

    if len(targets) == 1:
        waiter = targets[0]
    else:
        # 0 = preceding, 1 = following (both are wait-eligible).
        opts = []
        desc_bits = []
        if preceding in targets:
            opts.append(0)
            desc_bits.append(tf("log.order_prev", label=unit_log_label(preceding)))
        if following in targets:
            opts.append(1)
            desc_bits.append(tf("log.order_next", label=unit_log_label(following)))
        chosen = yield ChoiceRequest(
            player_id=orderer.agent_id(),
            choicetype=ChoiceType.CHOOSE_SERVICE,
            options=opts,
            num_choices=1,
            description=tf("log.order_choose", bits="; ".join(desc_bits)),
            payload={
                "reason": "order_target",
                "unit_index": ordering_unit.index(),
            },
        )
        waiter = preceding if chosen[0] == 0 else following
        assert waiter is not None

    # Reveal following neighbour's card when ordering them.
    if following is not None and waiter is following:
        _reveal_unit_action_card(engine, waiter, action_index)

    # Pick a hand card to assign (temporary — returned after resolve).
    desc = f"Order {unit_log_label(waiter)}: choose a hand card to assign:"
    hand_opts = list(orderer.action_cards)
    for c in hand_opts:
        faces = _card_faces(ordering_unit, c)
        names = "/".join(
            str(f.get("name") or f.get("action_name") or "?") for f in faces
        )
        desc += f"\n  {c}: {names}"
    picked = yield ChoiceRequest(
        player_id=orderer.agent_id(),
        choicetype=ChoiceType.CHOOSE_CARD,
        options=hand_opts,
        num_choices=1,
        description=desc,
        payload={
            "reason": "order_assign_card",
            "waiter_index": waiter.index(),
        },
    )
    card_id = picked[0]
    if card_id not in orderer.action_cards:
        return tf("log.order_card_missing", card=card_id)
    orderer.place_action_card(card_id)

    faces = _card_faces(waiter, card_id)
    possible: list[tuple[int, dict]] = []
    for e, face in enumerate(faces):
        # Cost paid by orderer; temporarily expose that to legality.
        check = dict(face)
        check["_cost_player"] = orderer
        # Card is out of hand already — cost cards must come from remaining hand.
        why = why_action_impossible(engine, waiter.index(), check)
        if not why:
            possible.append((e, face))

    if not possible:
        # Return card; Order itself still resolves (tires etc.) but no nested action.
        orderer.action_cards.append(card_id)
        orderer.action_cards.sort()
        return (
            f"ordered {unit_log_label(waiter)} with card {card_id} "
            f"but no legal face (card returned)"
        )

    if len(possible) == 1:
        face_i, face = possible[0]
    else:
        action_choices = []
        labels = list(range(len(possible)))
        for opt_i, (face_i, face) in enumerate(possible):
            action_choices.append(
                {
                    "option": opt_i,
                    "face_index": face_i,
                    "kind": "card",
                    "face": format_face(face),
                }
            )
        d = (
            f"Order {unit_log_label(waiter)}: choose face of card {card_id}: "
            + " ".join(f'{i}:"{possible[i][1].get("name")}"' for i in labels)
        )
        pick = yield ChoiceRequest(
            player_id=orderer.agent_id(),
            choicetype=ChoiceType.CHOOSE_ACTION,
            options=labels,
            num_choices=1,
            description=d,
            payload={
                "reason": "order_choose_face",
                "unit_index": waiter.index(),
                "card_id": card_id,
                "actions": action_choices,
            },
        )
        face_i, face = possible[pick[0]]

    nested = yield from resolve_action(
        engine,
        waiter.index(),
        face,
        card_id,
        cost_player=orderer,
    )

    # Return the assigned card to the ordering player.
    if card_id not in orderer.action_cards:
        orderer.action_cards.append(card_id)
        orderer.action_cards.sort()

    return tf("log.order_ok", label=unit_log_label(waiter), nested=nested)


def _has_officer(unit: Unit, effect_type: str, kind: str = "discard_effect") -> OfficerCard | None:
    for officer in unit.officers:
        if kind == "passive_effect" and officer.passive_effect == effect_type:
            return officer
        if kind == "discard_effect" and officer.discard_effect == effect_type:
            return officer
        # Also match CSV passive names used as passives
        if kind == "passive_effect" and officer.passive_effect == effect_type:
            return officer
    return None


def _discard_officer(unit: Unit, officer: OfficerCard) -> None:
    if officer in unit.officers:
        unit.officers.remove(officer)


def resolve_action(
    engine: GameEngine,
    actor_idx: int,
    action: dict,
    cardnumber: int,
    *,
    cost_player=None,
) -> Generator[ChoiceRequest, list[int], str]:
    """Generator that yields ChoiceRequests and returns a summary string.

    ``cost_player``: when set (Order nested play), discard costs come from that
    player instead of the acting unit's owner. Rewards still go to the actor.
    """
    from .engine import ChoiceRequest  # local to avoid cycle at import

    convoy = engine.convoy
    unit = convoy.units[actor_idx]
    player = unit.player
    try:
        trace_unit_index = unit.index()
    except ValueError:
        trace_unit_index = None
    payer = cost_player if cost_player is not None else player
    name = ActionName.normalize(action.get("action_name", "")) or ""
    modifier = action.get("action_modifier", 0)
    label = unit_log_label(unit)
    effects: list[str] = []
    rewards: list[str] = []

    # Pay cost (possibly from ordering player). Sell moves the cards itself.
    cost = get_cost(unit, action.get("cost", "0"))
    if cost > 0 and name != ActionName.SELL:
        paid = yield from _select_payment_cards(engine, payer, action, name, cost)
        payer.discard(list(paid))
        _trace_payment(engine, payer, action, name, list(paid))

    if name == ActionName.ATTACK:
        damage = modifier
        officer = _has_officer(unit, "extra_damage_in_zone_A") or _has_officer(
            unit, "enhanced_attack"
        )
        # Match CSV passives loosely: suicidal / extra damage officers
        for o in unit.officers:
            if o.discard_effect in ("suicidal_attack", "enhanced_attack") or (
                o.passive_effect and "extra_damage" in (o.passive_effect or "")
            ):
                # optional boost only via discard effect handled separately
                pass
        status, msg = engine.resistance.take_damage(
            UNIT_TYPE_LETTER[unit.unittype], f"={damage}", player=player
        )
        effects.append(msg)
        hit_pay = _cash_for_resistance_hit(player, status)
        from .config import ATTACK_CASH
        if ATTACK_CASH > 0:
            player.get_cash(ATTACK_CASH, source="attack")
            rewards.append(reward("log.for_attack", cash=raha(ATTACK_CASH)))
        destroy_pay = getattr(engine.resistance, "last_destroy_reward", None)
        if destroy_pay:
            rewards.append(destroy_pay)
            engine.resistance.last_destroy_reward = None
        if hit_pay:
            rewards.append(hit_pay)

    elif name == ActionName.ASSAULT:
        old_pos = actor_idx
        old_zone = unit.zone()
        new_pos = _shift_off_mauling(engine, unit, 1)
        actor_idx = unit.index()
        effects.append(
            tf(
                "log.assault",
                old=old_pos,
                old_zone=old_zone,
                new=new_pos,
                new_zone=unit.zone(),
            )
        )
        status, msg = engine.resistance.take_damage(
            UNIT_TYPE_LETTER[unit.unittype], f"={modifier}", player=player
        )
        effects.append(msg)
        _note_resistance_pay(engine, player, status, rewards)

    elif name == ActionName.RETREAT:
        # Suojatulta! → retreat one slot toward the rear, then deal damage.
        old_pos = actor_idx
        old_zone = unit.zone()
        new_pos = _shift_off_mauling(engine, unit, -1)
        actor_idx = unit.index()
        effects.append(
            tf(
                "log.retreat",
                old=old_pos,
                old_zone=old_zone,
                new=new_pos,
                new_zone=unit.zone(),
            )
        )
        status, msg = engine.resistance.take_damage(
            UNIT_TYPE_LETTER[unit.unittype], modifier, player=player
        )
        effects.append(msg)
        _note_resistance_pay(engine, player, status, rewards)

    elif name == ActionName.BYPASS:
        new_pos = _shift_off_mauling(engine, unit, unit.bypass_distance(modifier))
        effects.append(tf("log.bypass", pos=new_pos))

    elif name == ActionName.EXIT:
        loot_cash = sum(unit.carry)
        if loot_cash:
            player.get_cash(loot_cash, source="exit loot")
        if engine is not None:
            engine.recycle_damage_markers(unit)
        convoy.units.pop(unit.index())
        effects.append(tf("log.exit", cash=raha(loot_cash)))

    elif name in (ActionName.PILLAGE, ActionName.PILLAGE_WITH_EXTRA_ATROCITY):
        extra = 0 if name == ActionName.PILLAGE_WITH_EXTRA_ATROCITY else modifier
        loot_cards = yield from _resolve_pillage(engine, unit, extra)
        disciplined = name == ActionName.PILLAGE_WITH_EXTRA_ATROCITY
        for card in loot_cards:
            applied = _apply_pillage_reward(
                player, unit, card, disciplined=disciplined
            )
            _note_pillage(engine, player, unit, card, applied)
            effects.append(format_pillage_effect(unit, card, applied=applied))

    elif name in ATTACK_TYPE_BY_DEFENCE_ACTION:
        # Defend→G (ground), Human shields→A (air), Patrol→S (sabotage).
        # Soak rewards are config-driven in Unit.reward_defending.
        attack_letter = ATTACK_TYPE_BY_DEFENCE_ACTION[name]
        unit.resolve_defend(attack_letter)
        defence_key = f"log.defend.{name}"
        defence_line = t(defence_key)
        if defence_line == defence_key:
            defence_line = tf("log.defend.other", letter=attack_letter)
        effects.append(defence_line)

    elif name == ActionName.SCOUT:
        count = modifier if modifier and modifier > 0 else 2
        scouted = yield from resolve_scout(engine, unit, count)
        if scouted:
            _absorb_scout_lines(scouted, effects, rewards)
        else:
            effects.append(tf("log.found_nothing", queues=hidden_queue_summary(engine)))

    elif name == ActionName.SIGINT:
        # Like scout, but only the mauling queue/deck.
        count = modifier if modifier and modifier > 0 else 2
        scouted = yield from resolve_scout(
            engine,
            unit,
            count,
            allowed_queue_codes={SCOUT_QUEUE_MAULING},
            verb="sigint",
        )
        if scouted:
            _absorb_scout_lines(scouted, effects, rewards)
        else:
            effects.append(tf("log.found_nothing", queues=hidden_queue_summary(engine)))

    elif name == ActionName.SEARCH:
        # Face-down pillage → reveal; empty queue → draw N / keep 1 face-up.
        count = modifier if modifier and modifier > 0 else 2
        scouted = yield from resolve_search(engine, unit, count)
        if scouted:
            _absorb_scout_lines(scouted, effects, rewards)
        else:
            effects.append(t("log.found_no_pillage"))

    elif name == ActionName.WAIT:
        if not player.action_cards:
            effects.append(t("log.wait_empty"))
        else:
            desc = t("log.wait_prompt")
            for c in player.action_cards:
                desc += f"\n  {c}"
            chosen = yield ChoiceRequest(
                player_id=player.agent_id(),
                choicetype=ChoiceType.CHOOSE_CARD,
                options=list(player.action_cards),
                num_choices=1,
                description=desc,
            )
            card = chosen[0]
            unit.actioncard.append(card)
            unit.actiontaken.append(None)
            unit.action_resolution.append(None)
            player.place_action_card(card)
            effects.append(tf("log.wait_queued", card=card))

    elif name == ActionName.ORDER:
        msg = yield from resolve_order(engine, unit)
        effects.append(msg)

    elif name == ActionName.SEARCH_PILLAGE_COMBO:
        count = modifier if modifier and modifier > 0 else 2
        scouted = yield from resolve_search(engine, unit, count)
        if scouted:
            _absorb_scout_lines(scouted, effects, rewards)
        else:
            effects.append(t("log.found_no_pillage"))
        if len(engine.pillage_queue) >= 1:
            loot_cards = yield from _resolve_pillage(engine, unit, 0)
            for card in loot_cards:
                applied = _apply_pillage_reward(
                    player, unit, card, disciplined=False
                )
                _note_pillage(engine, player, unit, card, applied)
                effects.append(format_pillage_effect(unit, card, applied=applied))
        else:
            effects.append(t("log.pillage_queue_empty"))

    elif name == ActionName.SOBER_UP:
        officer = _has_officer(unit, "sober_up")
        unit.under_influence = 0
        if officer:
            _discard_officer(unit, officer)
        effects.append(t("log.sober"))

    elif name == ActionName.PROMOTE:
        oq = engine.officer_queue
        indices = matching_officer_queue_indices(engine, unit)
        if not indices:
            effects.append(
                tf("log.no_officer", letter=UNIT_TYPE_LETTER[unit.unittype])
            )
        else:
            letter = UNIT_TYPE_LETTER[unit.unittype]
            desc = tf("log.choose_officer", letter=letter)
            for i in indices:
                seq_id, _ = oq.cards_and_visibilities[i]
                real_id = engine.officer_id_mapping.get(seq_id, seq_id)
                officer = OFFICER_CATALOG[real_id]
                desc += f"\n  {i}: {officer.name} [{officer.troop_type or 'A'}]"
            chosen = yield ChoiceRequest(
                player_id=player.agent_id(),
                choicetype=ChoiceType.CHOOSE_OFFICER,
                options=indices,
                num_choices=1,
                description=desc,
                payload={
                    "unit_index": unit.index(),
                    "troop_letter": letter,
                    "officer_indices": indices,
                },
            )
            idx = chosen[0]
            if idx not in indices:
                raise ValueError(
                    f"officer index {idx} not valid for troop {letter} "
                    f"(allowed {indices})"
                )
            seq_id, _ = oq.remove_card(idx)
            real_id = engine.officer_id_mapping.get(seq_id, seq_id)
            officer = OFFICER_CATALOG[real_id]
            if not officer_matches_unit(officer, unit):
                raise ValueError(
                    f"officer {officer.name} troop {officer.troop_type} "
                    f"does not match unit {letter}"
                )
            unit.officers.append(officer)
            engine.stats.record_officer_pick(player.number, officer.name)
            effects.append(tf("log.promoted", name=officer.name))

    elif name == ActionName.SERVICE:
        msg = yield from _resolve_service(engine, unit)
        effects.append(msg)

    elif name == ActionName.REST:
        # Tired and under_influence are the same burden for this bonus.
        if unit.tired + unit.under_influence >= 3:
            engine.note_shaping("rest_relief", player.number)
        if modifier == 2 and unit.can_rest_with_cards():
            old = unit.tired
            unit.rest_with_cards()
            effects.append(tf("log.rest_with_cards", old=old, new=unit.tired))
        else:
            old = unit.tired
            was_drunk = unit.under_influence
            unit.rest()
            if was_drunk:
                effects.append(t("log.rest_sober"))
            else:
                effects.append(tf("log.rest", old=old, new=unit.tired))

    elif name == ActionName.SUICIDAL_ATTACK:
        damage = modifier if modifier else 5
        status, msg = engine.resistance.take_damage(
            UNIT_TYPE_LETTER[unit.unittype], damage, player=player
        )
        effects.append(msg)
        _note_resistance_pay(engine, player, status, rewards)
        convoy.apply_damage(1, unit=unit)
        effects.append(t("log.self_damage"))

    elif name == ActionName.SELL:
        paid = yield from _select_payment_cards(
            engine, payer, action, name, cost, sell=True
        )
        gained = engine.apply_card_cash(payer, list(paid))
        _trace_payment(engine, payer, action, name, list(paid))
        rewards.append(reward("log.for_sell", cash=raha(gained)))

    elif name == ActionName.EXIT_FROM_C_WITH_COST:
        cost_cash = modifier or 5
        spent = player.pay_cash(cost_cash)
        spent_ledger = getattr(engine, "cash_spent", None)
        if spent_ledger is not None and spent:
            spent_ledger[player.number] += int(spent)
        loot_cash = sum(unit.carry)
        if loot_cash:
            player.get_cash(loot_cash, source="exit loot")
        if engine is not None:
            engine.recycle_damage_markers(unit)
        convoy.units.pop(unit.index())
        effects.append(
            tf(
                "log.exit_paid",
                cost=raha(cost_cash),
                loot=raha(loot_cash),
            )
        )

    else:
        effects.append(tf("log.unimplemented", name=name))

    if action.get("tire"):
        unit.tire()
    if action.get("intoxicate"):
        was_sober = unit.under_influence == 0
        unit.under_influence = 1
        if was_sober and unit.convoy is not None:
            engine._note_event(
                EVENT_INFLUENCE, actor=player.number, target=unit.index(), amount=1
            )

    if action.get("is_officer_discard") and action.get("officer"):
        _discard_officer(unit, action["officer"])
        effects.append(tf("log.discard_officer", name=action["officer"].name))

    engine.stats.record_action(player.number, name)
    if getattr(engine, "balance_trace", False):
        deck = player.action_deck
        engine.trace_plays.append(
            {
                "player": player.number,
                "unit_index": trace_unit_index,
                "unit": UNIT_TYPE_STR.get(unit.unittype, str(unit.unittype)),
                "card_id": int(cardnumber),
                "card_name": deck.label(cardnumber) if deck is not None else str(cardnumber),
                "action": str(action.get("name") or name),
                "action_name": name,
            }
        )
    summary = format_action_log(
        label, str(action.get("name") or name), effects, rewards
    )
    engine.round_action_summaries.append(summary)
    return summary


def _loot_list(loot: Any) -> list[int]:
    if loot is None or loot == "":
        return []
    if isinstance(loot, int):
        return [loot] if loot else []
    if isinstance(loot, str):
        return [int(x) for x in loot.split(",") if x.strip()]
    return [int(x) for x in loot if int(x)]


def _ignores_pillage_intoxication(unit: Unit) -> bool:
    """Officer passive: pillaging cards do not make this unit drunk."""
    return (
        _has_officer(unit, "no_boozing_while_pillaging", kind="passive_effect")
        is not None
    )


def _apply_pillage_reward(
    player: Any, unit: Unit, card: dict, *, disciplined: bool
) -> dict:
    """Apply one pillage card. Influence on the card is checked before it is set."""
    reward = card.get("reward") or {}
    was_influenced = unit.under_influence > 0
    cash = int(reward.get("cash") or 0)
    if cash:
        player.get_cash(cash, source="pillage")
    cards = int(reward.get("cards") or 0)
    if cards:
        player.draw_card(cards)
    loot = _loot_list(reward.get("loot"))
    if loot:
        unit.gain_loot(loot)
    atro = int(reward.get("atrocities") or 0)
    if disciplined:
        atro = max(0, atro - 1)
    if was_influenced:
        atro += int(reward.get("atrocities_if_under_influence") or 0)
    if atro:
        unit.gain_atrocities(atro)
    became_influenced = False
    intoxicate_ignored = False
    if int(reward.get("intoxicate") or 0) and not was_influenced:
        if _ignores_pillage_intoxication(unit):
            intoxicate_ignored = True
        else:
            unit.under_influence = 1
            became_influenced = True
    return {
        "cash": cash,
        "cards": cards,
        "loot": loot,
        "atrocities": atro,
        "became_influenced": became_influenced,
        "intoxicate_ignored": intoxicate_ignored,
    }


def format_pillage_effect(
    unit: Unit,
    card: dict,
    *,
    applied: dict | None = None,
    disciplined: bool = False,
    influence: bool = False,
) -> str:
    """Human log line: loot, atrocities, influence, cards drawn, money."""
    reward = card.get("reward") or {}
    name = card.get("name") or "?"
    if applied is None:
        loot = _loot_list(reward.get("loot"))
        atro = int(reward.get("atrocities") or 0)
        if disciplined:
            atro = max(0, atro - 1)
        cash = int(reward.get("cash") or 0)
        cards = int(reward.get("cards") or 0)
        became = influence
        ignored = False
    else:
        loot = applied.get("loot") or []
        atro = int(applied.get("atrocities") or 0)
        cash = int(applied.get("cash") or 0)
        cards = int(applied.get("cards") or 0)
        became = bool(applied.get("became_influenced"))
        ignored = bool(applied.get("intoxicate_ignored"))
    bits: list[str] = []
    if loot:
        shown = "+".join(str(v) for v in loot)
        bits.append(tf("log.pillage_loot", count=len(loot), shown=shown))
    if atro:
        bits.append(tf("log.pillage_atrocity", n=atro))
    if became:
        bits.append(t("log.pillage_drunk"))
    elif ignored:
        bits.append(t("log.pillage_sober"))
    if cards:
        bits.append(tf("log.pillage_cards", n=cards))
    if cash:
        bits.append(tf("log.pillage_cash", cash=raha(cash)))
    if not bits:
        bits.append(t("log.pillage_empty"))
    return f"*{name}*: " + ", ".join(bits)


def _pillage_offer(engine: GameEngine, index: int) -> dict:
    from .cards import queue_card_detail

    card_id, visible = engine.pillage_queue.cards_and_visibilities[index]
    if visible:
        detail = engine.pillage_deck.describe(card_id)
        return {
            "id": card_id,
            "index": index,
            "name": detail.get("name", str(card_id)),
            "detail": queue_card_detail(detail),
            "reward": detail.get("reward"),
            "visible": True,
        }
    return {
        "id": card_id,
        "index": index,
        "name": (
            t("log.pillage_face_down_front")
            if index == 0
            else tf("log.pillage_face_down", n=index + 1)
        ),
        "detail": t("log.pillage_face_down_detail"),
        "visible": False,
    }


def _pillage_choice_indices(engine: GameEngine, unit: Unit) -> list[int]:
    """Front card always. A sober unit may also take any other revealed card."""
    queue = engine.pillage_queue.cards_and_visibilities
    if not queue:
        return []
    if unit.under_influence > 0:
        return [0]
    indices = [0]
    for i, (_, visible) in enumerate(queue):
        if i != 0 and visible:
            indices.append(i)
    return indices


def _take_pillage_at(engine: GameEngine, index: int) -> dict:
    card_id, _visible = engine.pillage_queue.remove_card(index)
    engine.pillage_deck.discard_card(card_id)
    described = dict(engine.pillage_deck.describe(card_id))
    described["id"] = card_id
    return described


def _note_pillage(engine: GameEngine, player: Any, unit: Unit, card: dict, applied: dict) -> None:
    cid = card.get("id")
    target = unit.index() if unit.convoy is not None else -1
    engine._note_event(
        EVENT_PILLAGE,
        actor=player.number,
        target=target,
        card_id=int(cid) if cid is not None else 0,
        amount=int(applied.get("cash") or 0),
        card_visible=cid is not None,
    )
    if applied.get("became_influenced") and target >= 0:
        engine._note_event(EVENT_INFLUENCE, actor=player.number, target=target, amount=1)


def _resolve_pillage(
    engine: GameEngine, unit: Unit, modifier: int
) -> Generator[ChoiceRequest, list[int], list[dict]]:
    from .engine import ChoiceRequest

    del modifier  # the printed number no longer limits which cards can be taken
    indices = _pillage_choice_indices(engine, unit)
    if not indices:
        return []

    offered = [_pillage_offer(engine, i) for i in indices]
    if len(offered) == 1:
        return [_take_pillage_at(engine, offered[0]["index"])]

    options = [o["id"] for o in offered]
    desc = t("log.choose_pillage")
    for o in offered:
        desc += f"\n  {o['id']}: {o['name']}"
    chosen = yield ChoiceRequest(
        player_id=unit.player.agent_id(),
        choicetype=ChoiceType.CHOOSE_PILLAGE_CARD,
        options=options,
        num_choices=1,
        description=desc,
        payload={
            "reason": "pillage",
            "unit_index": unit.index(),
            "pillage_cards": offered,
        },
    )
    pick = chosen[0]
    match = next((o for o in offered if o["id"] == pick), None)
    if match is None:
        raise ValueError(f"pillage card {pick} is not a legal choice")
    queue = engine.pillage_queue.cards_and_visibilities
    index = match["index"]
    if index >= len(queue) or queue[index][0] != pick:
        index = next(i for i, (cid, _) in enumerate(queue) if cid == pick)
    return [_take_pillage_at(engine, index)]


def _resolve_service(
    engine: GameEngine, unit: Unit
) -> Generator[ChoiceRequest, list[int], str]:
    from .engine import ChoiceRequest

    preceding, following = unit.get_neighbours()
    tired_prev = preceding is not None and preceding.tired > 0
    tired_next = following is not None and following.tired > 0
    if tired_prev and tired_next:
        chosen = yield ChoiceRequest(
            player_id=unit.player.agent_id(),
            choicetype=ChoiceType.CHOOSE_SERVICE,
            options=[0, 1],
            num_choices=1,
            description=t("log.service_choose"),
        )
        target = preceding if chosen[0] == 0 else following
    elif tired_prev:
        target = preceding
    else:
        target = following
    assert target is not None
    from .config import SERVICE_CASH, SERVICE_TIREDNESS

    target.tired = max(0, target.tired - int(SERVICE_TIREDNESS))
    msg = tf("log.service", label=unit_log_label(target))
    if SERVICE_CASH > 0:
        unit.player.get_cash(SERVICE_CASH, source="service")
        msg += tf("log.service_cash", cash=raha(SERVICE_CASH))
    return msg


def _queue_by_scout_code(engine: GameEngine, code: int):
    if code == SCOUT_QUEUE_PILLAGE:
        return engine.pillage_queue
    if code == SCOUT_QUEUE_MAULING:
        return engine.mauling_queue
    if code == SCOUT_QUEUE_RESISTANCE:
        return engine.resistance_queue
    raise ValueError(f"unknown scout queue code {code}")


def _pause_after_log(
    engine: GameEngine,
    description: str,
    *,
    reason: str = "log_pause",
) -> Generator[ChoiceRequest, list[int], None]:
    """Optional continue prompt after a log-worthy event (reveal, action, etc.)."""
    from .engine import ChoiceRequest

    if not getattr(engine, "pause_after_actions", True):
        return
    yield ChoiceRequest(
        player_id=f"player_{getattr(engine, 'human_seat', 0)}",
        choicetype=ChoiceType.LOG_PAUSE,
        options=[0],
        num_choices=1,
        description=description,
        payload={"reason": reason},
    )


def _pause_after_reveal(
    engine: GameEngine, description: str
) -> Generator[ChoiceRequest, list[int], None]:
    """Optional continue prompt after a single card reveal."""
    yield from _pause_after_log(engine, description, reason="reveal_pause")


def pause_after_action(
    engine: GameEngine, summary: str
) -> Generator[ChoiceRequest, list[int], None]:
    """Pause after an action resolves (or a unit becomes frustrated)."""
    hint = summary.strip() if summary else t("log.action_logged")
    if len(hint) > 480:
        hint = hint[:477] + "…"
    yield from _pause_after_log(
        engine,
        hint + t("log.continue_suffix"),
        reason="action_pause",
    )


def _deck_by_scout_code(engine: GameEngine, code: int):
    if code == SCOUT_QUEUE_PILLAGE:
        return engine.pillage_deck
    if code == SCOUT_QUEUE_MAULING:
        return engine.mauling_deck
    if code == SCOUT_QUEUE_RESISTANCE:
        return engine.resistance_deck
    raise ValueError(f"unknown scout queue code {code}")


def _scout_queue_mapping(
    engine: GameEngine,
    allowed_queue_codes: set[int] | frozenset[int] | None = None,
) -> list[tuple[int, str, Any]]:
    mapping = [
        (SCOUT_QUEUE_PILLAGE, "pillage", engine.pillage_queue),
        (SCOUT_QUEUE_MAULING, "mauling", engine.mauling_queue),
        (SCOUT_QUEUE_RESISTANCE, "resistance", engine.resistance_queue),
    ]
    if allowed_queue_codes is not None:
        mapping = [row for row in mapping if row[0] in allowed_queue_codes]
    return mapping


def _drawn_card_offer(engine: GameEngine, code: int, card_id: int) -> dict:
    """Payload entry for choosing among cards drawn during scout/search/sigint."""
    from .cards import queue_card_detail

    deck = _deck_by_scout_code(engine, code)
    desc = deck.describe(card_id) if deck else None
    offer: dict[str, Any] = {
        "id": card_id,
        "name": str(card_id),
        "detail": None,
        "visible": True,
    }
    if isinstance(desc, dict):
        offer.update(desc)
        offer["id"] = card_id
        offer["name"] = desc.get("name", str(card_id))
        offer["detail"] = queue_card_detail(desc)
        offer["visible"] = True
    return offer


def _resolve_scout_from_deck(
    engine: GameEngine,
    unit: Unit,
    count: int,
    *,
    allowed_queue_codes: set[int] | frozenset[int] | None = None,
    verb: str = "scout",
    paid_types: set[int] | None = None,
) -> Generator[ChoiceRequest, list[int], list[str]]:
    """
    When no face-down queue cards remain: choose an allowed deck, draw up to
    ``count`` cards, keep one face-up in that deck's queue, discard the rest.
    """
    from .engine import ChoiceRequest

    label = unit_log_label(unit)
    mapping = _scout_queue_mapping(engine, allowed_queue_codes)

    eligible: list[tuple[int, str, Any, Any]] = []
    for code, qname, queue in mapping:
        deck = _deck_by_scout_code(engine, code)
        if deck.deck or deck.discard:
            eligible.append((code, qname, queue, deck))

    if not eligible:
        engine._broadcast(
            one_line(
                tf(
                    "log.no_cards_left",
                    label=label,
                    queues=hidden_queue_summary(engine),
                )
            )
        )
        return []

    if len(eligible) == 1:
        code, qname, queue, deck = eligible[0]
    else:
        options = [c for c, _, _, _ in eligible]
        desc = (
            tf("log.choose_deck", label=label, verb=scout_verb(verb), count=count)
        )
        for c, name, _, d in eligible:
            ds, disc = d.get_sizes()
            desc += f"\n  {c}: {name} (deck={ds}, discard={disc})"
        chosen = yield ChoiceRequest(
            player_id=unit.player.agent_id(),
            choicetype=ChoiceType.CHOOSE_QUEUE_TO_SCOUT,
            options=options,
            num_choices=1,
            description=desc,
            payload={
                "reason": f"{verb}_choose_deck",
                "verb": verb,
                "count": count,
                "queues": [
                    {
                        "option": c,
                        "queue": name,
                        "deck": d.get_sizes()[0],
                        "discard": d.get_sizes()[1],
                    }
                    for c, name, _, d in eligible
                ],
            },
        )
        code = chosen[0]
        match = next(row for row in eligible if row[0] == code)
        code, qname, queue, deck = match

    drawn: list[int] = []
    for step in range(count):
        try:
            drawn.append(deck.get_card(shuffle_if_necessary=True))
        except RuntimeError:
            engine._broadcast(
                one_line(
                    tf(
                        "log.deck_ran_out",
                        label=label,
                        queue=queue_name(qname),
                        step=step,
                        count=count,
                    )
                )
            )
            break

    if not drawn:
        return []

    offers = [_drawn_card_offer(engine, code, cid) for cid in drawn]
    if len(drawn) == 1:
        keep = drawn[0]
    else:
        desc = (
            tf(
                "log.choose_drawn",
                label=label,
                verb=scout_verb(verb),
                count=len(drawn),
                queue=queue_name(qname),
            )
        )
        for offer in offers:
            desc += f"\n  {offer['id']}: {offer['name']}"
        pick = yield ChoiceRequest(
            player_id=unit.player.agent_id(),
            choicetype=ChoiceType.CHOOSE_PILLAGE_CARD,
            options=list(drawn),
            num_choices=1,
            description=desc,
            payload={
                "reason": "scout_deck_pick",
                "verb": verb,
                "queue": qname,
                "pillage_cards": offers,
            },
        )
        keep = pick[0]
        if keep not in drawn:
            keep = drawn[0]

    for cid in drawn:
        if cid != keep:
            deck.discard_card(cid)

    queue.put_card(keep, visible=True)
    keep_name = deck.get_name(keep) or str(keep)
    placed_index = len(queue) - 1

    pay = _cash_for_revealed_cards(
        engine, unit.player, code, 1, label, paid_types=paid_types
    )
    found = [
        tf("log.into_queue_from_deck", name=keep_name, queue=queue_name(qname))
    ]
    if pay:
        found.append(pay)

    engine._broadcast(
        one_line(
            tf(
                "log.draw_into_queue",
                label=label,
                name=keep_name,
                queue=queue_name(qname),
            )
        ),
        kind="reveal",
        queue=code,
        index=placed_index,
        card_id=keep,
        event_type=EVENT_REVEAL,
        actor=unit.player.number,
        amount=1,
        card_visible=True,
    )
    yield from _pause_after_reveal(
        engine,
        tf("log.deck_pause", queue=queue_name(qname), name=keep_name),
    )
    return found


def resolve_search(
    engine: GameEngine, unit: Unit, count: int
) -> Generator[ChoiceRequest, list[int], list[str]]:
    """Search is scout limited to the pillage queue and deck."""
    return (
        yield from resolve_scout(
            engine,
            unit,
            count,
            allowed_queue_codes={SCOUT_QUEUE_PILLAGE},
            verb="search",
        )
    )


def resolve_scout(
    engine: GameEngine,
    unit: Unit,
    count: int,
    *,
    allowed_queue_codes: set[int] | frozenset[int] | None = None,
    verb: str = "scout",
) -> Generator[ChoiceRequest, list[int], list[str]]:
    """
    Scout / sigint / search. Modifier ``count`` is N.

    Turn M = min(N, face-down cards in the allowed queues). Every one of
    those M cards is turned face up; the player does not turn fewer. When
    more than N cards are face down, the player chooses which N. The turned
    cards go back face up in an order the player chooses.

    If M < N and every allowed queue is then face up, look at N-M cards from
    an allowed deck and place one of them face up in that queue.
    """
    from .engine import ChoiceRequest

    revealed: list[str] = []
    label = unit_log_label(unit)
    paid_types: set[int] = set()
    queue_mapping = _scout_queue_mapping(engine, allowed_queue_codes)

    face_down_cards = []
    for code, qname, queue in queue_mapping:
        for idx, (card_id, vis) in enumerate(queue.cards_and_visibilities):
            if not vis:
                face_down_cards.append((code, qname, idx, card_id))

    # M flips, all of them. No subset smaller than the cards that fit.
    flips = min(count, len(face_down_cards))
    if flips <= 0:
        pick = []
    elif flips == len(face_down_cards):
        pick = [code * 100 + idx for code, qname, idx, cid in face_down_cards]
    else:
        queue_hint = (
            t("log.all_queues")
            if allowed_queue_codes is None
            else ", ".join(
                queue_name(SCOUT_QUEUE_NAMES[c]) for c in sorted(allowed_queue_codes)
            )
        )
        options = [code * 100 + idx for code, qname, idx, cid in face_down_cards]
        desc = (
            tf(
                "log.turn_cards",
                label=label,
                verb=scout_verb(verb),
                flips=flips,
                queues=queue_hint,
            )
        )
        queues_payload = []
        for code, qname, idx, cid in face_down_cards:
            queues_payload.append({
                "option": code * 100 + idx,
                "queue": qname,
                "index": idx,
            })
        pick = yield ChoiceRequest(
            player_id=unit.player.agent_id(),
            choicetype=ChoiceType.CHOOSE_CARDS_TO_SCOUT,
            options=options,
            num_choices=flips,
            description=desc,
            payload={
                "reason": f"{verb}_selection",
                "verb": verb,
                "cards": queues_payload,
                "count": flips,
                "allowed_queues": [
                    SCOUT_QUEUE_NAMES[c]
                    for c in (
                        sorted(allowed_queue_codes)
                        if allowed_queue_codes is not None
                        else sorted(SCOUT_QUEUE_NAMES)
                    )
                ],
            },
        )
        if not pick:
            pick = options[:flips]

    chosen_by_queue: dict[int, list[int]] = {}
    for opt in pick:
        code = opt // 100
        idx = opt % 100
        chosen_by_queue.setdefault(code, []).append(idx)

    for code, indices in chosen_by_queue.items():
        pay = _cash_for_revealed_cards(
            engine, unit.player, code, len(indices), label, paid_types=paid_types
        )
        if pay:
            revealed.append(pay)

    for code, indices in chosen_by_queue.items():
        queue = _queue_by_scout_code(engine, code)
        qname = SCOUT_QUEUE_NAMES[code]
        indices = sorted(indices)

        for idx in indices:
            queue.reveal_card(idx)
            card_id = queue.cards_and_visibilities[idx][0]
            card_name = queue.deck.get_name(card_id) if queue.deck else str(card_id)
            revealed.append(
                tf("log.from_queue", name=card_name, queue=queue_name(qname))
            )
            engine._broadcast(
                one_line(
                    tf(
                        "log.reveal_card",
                        label=label,
                        queue=queue_name(qname),
                        name=card_name,
                    )
                ),
                kind="reveal",
                queue=code,
                index=idx,
                card_id=card_id,
                event_type=EVENT_REVEAL,
                actor=unit.player.number,
                amount=1,
                card_visible=True,
            )
            yield from _pause_after_reveal(
                engine,
                tf("log.reveal_pause", queue=queue_name(qname), name=card_name),
            )

        if len(indices) > 1:
            desc_reorder = (
                tf(
                    "log.reorder_prompt",
                    label=label,
                    verb=scout_verb(verb),
                    queue=queue_name(qname),
                )
            )
            reorder_payload_cards = []
            for idx in indices:
                card_id = queue.cards_and_visibilities[idx][0]
                card_name = queue.deck.get_name(card_id) if queue.deck else str(card_id)
                reorder_payload_cards.append({
                    "option": idx,
                    "name": card_name,
                    "detail": queue.deck.describe(card_id) if queue.deck else None
                })

            reordered_pick = yield ChoiceRequest(
                player_id=unit.player.agent_id(),
                choicetype=ChoiceType.REORDER_SCOUTED_CARDS,
                options=indices,
                num_choices=len(indices),
                description=desc_reorder,
                payload={
                    "reason": "scout_reorder",
                    "verb": verb,
                    "queue": qname,
                    "cards": reorder_payload_cards
                }
            )

            if not reordered_pick or set(reordered_pick) != set(indices):
                reordered_pick = indices

            original_entries = {
                idx: list(queue.cards_and_visibilities[idx]) for idx in indices
            }
            for i, orig_idx in enumerate(reordered_pick):
                target_idx = indices[i]
                queue.cards_and_visibilities[target_idx] = original_entries[orig_idx]

            names = []
            for idx in indices:
                card_id = queue.cards_and_visibilities[idx][0]
                names.append(
                    queue.deck.get_name(card_id) if queue.deck else str(card_id)
                )
            engine._broadcast(
                one_line(
                    tf(
                        "log.reorder_cards",
                        label=label,
                        queue=queue_name(qname),
                        names=", ".join(names),
                    )
                )
            )

    queues_face_up = all(
        not queue.contains_hidden_cards() for _, _, queue in queue_mapping
    )
    if flips < count and queues_face_up:
        from_deck = yield from _resolve_scout_from_deck(
            engine,
            unit,
            count - flips,
            allowed_queue_codes=allowed_queue_codes,
            verb=verb,
            paid_types=paid_types,
        )
        revealed.extend(from_deck)

    return revealed


def _visible_mauling_target(engine: GameEngine) -> str | None:
    """Target code of the front mauling card, when that card is face up."""
    queue = engine.mauling_queue
    if not queue.cards_and_visibilities:
        return None
    card_id, visible = queue.cards_and_visibilities[0]
    if not visible:
        return None
    described = engine.mauling_deck.describe(card_id)
    if not isinstance(described, dict):
        return None
    target = (described.get("effect") or {}).get("target") or ""
    if not target or target == "-":
        return None
    return str(target)


def _on_visible_mauling(engine: GameEngine, unit: Unit) -> bool:
    target = _visible_mauling_target(engine)
    convoy = engine.convoy
    if not target or convoy is None or unit not in convoy.units:
        return False
    try:
        return unit in mauling_target_units(convoy, target)
    except ValueError:
        return False


def _shift_off_mauling(engine: GameEngine, unit: Unit, delta: int) -> int:
    """Move the unit. Note when that leaves the visible front mauling's target."""
    convoy = engine.convoy
    assert convoy is not None
    was_target = _on_visible_mauling(engine, unit)
    new_pos = convoy.move_unit(unit.index(), delta)
    if was_target and unit in convoy.units and not _on_visible_mauling(engine, unit):
        engine.note_shaping("mauling_dodge", unit.player.number)
    return new_pos


def mauling_target_units(convoy: Convoy, target: str) -> list[Unit]:
    """Resolve a mauling target string into living units."""
    sel = parse_mauling_target(target)
    units = list(convoy.units)
    if not units:
        return []

    kind = sel["kind"]
    if kind == "none":
        return []
    if kind == "zone":
        return list(convoy.get_units_in_zone(sel["zone"]))

    if kind == "zone_rel":
        units_in_zone = convoy.get_units_in_zone(sel["zone"])
        if not units_in_zone:
            return []
        target_rel = int(sel["rel"])
        while len(units_in_zone) < abs(target_rel) and target_rel != 0:
            if target_rel < 0:
                target_rel += 1
            else:
                target_rel -= 1
        if target_rel > 0:
            zi = min(target_rel - 1, len(units_in_zone) - 1)
        else:
            zi = max(target_rel, -len(units_in_zone))
        return [units_in_zone[zi]]

    if kind == "type":
        matched = [u for u in units if u.unittype == sel["unit_type"]]
        if not matched:
            return []
        which = sel["which"]
        if which == "first":
            return [matched[0]]
        elif which == "second":
            return [matched[1]] if len(matched) >= 2 else []
        elif which == "second_last":
            return [matched[-2]] if len(matched) >= 2 else []
        else:
            return [matched[-1]]

    if kind == "atrocity":
        max_atr = max(u.atrocities for u in units)
        matched = [u for u in units if u.atrocities == max_atr]
        which = sel["which"]
        if which == "first":
            return [matched[0]]
        elif which == "second":
            return [matched[1]] if len(matched) >= 2 else []
        elif which == "second_last":
            return [matched[-2]] if len(matched) >= 2 else []
        else:
            return [matched[-1]]

    raise ValueError(f"unhandled mauling target kind {kind}")


def _apply_category_hit(engine: GameEngine, unit: Unit, category: int, attack_type: str) -> str:
    """Lower the category for matching defence, then draw that deck."""
    convoy = engine.convoy
    assert convoy is not None
    label = unit_log_label(unit)
    engine.note_struck_unit(unit)
    cat = convoy.category_after_defence(unit, category, attack_type)
    note = ""
    if cat != category:
        note = tf("log.category_lowered", label=label, old=category, new=cat)
    if cat <= 0:
        return note or tf("log.category_dodged", label=label, category=category)
    damage = engine.draw_hit_damage(cat)
    if damage <= 0:
        line = tf("log.category_zero", label=label, category=cat)
    else:
        line = convoy.apply_damage(damage, unit=unit, attack_type=attack_type)
        engine.note_shaping("mauling_damage", unit.player.number, damage=int(damage))
        if unit in convoy.units:
            engine.attach_damage_marker(unit, damage, category=cat)
    engine.discard_unclaimed_hits()
    if note:
        return one_line(f"{note}, {line}")
    return line


def resolve_mauling(
    engine: GameEngine, mauling: dict
) -> Generator[ChoiceRequest, list[int], str]:
    """
    Apply one mauling card.

    Hit-category damage draws that category's deck (1, 3, 5, or 10). A matching
    defence lowers the category one step per defender before the draw.
    Forced discard yields a CHOOSE_CARDS_TO_DISCARD; if the player cannot pay,
    fail_hit_category damage is drawn instead.
    """
    from .engine import ChoiceRequest

    engine.clear_hit_draws()
    effect = mauling["effect"]
    target = effect["target"]
    hit_cat = int(effect.get("hit_category") or 0)
    discard_n = int(effect.get("discard") or 0)
    fail_hit = int(effect.get("fail_hit_category") or 0)
    # Attack type vs defence soak (default ground). See AttackType.
    atype = effect.get("attack_type") or AttackType.GROUND
    if isinstance(atype, (list, tuple)):
        atype = atype[0]
    atype = str(atype)[0].upper() if atype else AttackType.GROUND

    if atype == AttackType.RESISTANCE:
        # Category comes from the active resistance card. The target stays the
        # one printed on this mauling card; the resistance card's counterattack
        # target is not used.
        atype = AttackType.GROUND
        if engine.resistance.active:
            if hit_cat > 0:
                hit_cat = engine.resistance.resistance_attack_category
            if fail_hit > 0:
                fail_hit = engine.resistance.resistance_attack_category
        else:
            hit_cat = 0
            fail_hit = 0

    parts: list[str] = []
    convoy = engine.convoy
    assert convoy is not None

    if hit_cat > 0:
        for unit in mauling_target_units(convoy, target):
            # Unit may have been removed by an earlier hit in this card.
            if unit not in convoy.units:
                continue
            parts.append(_apply_category_hit(engine, unit, hit_cat, atype))

    if discard_n > 0:
        for unit in mauling_target_units(convoy, target):
            if unit not in convoy.units:
                continue
            player = unit.player
            if len(player.action_cards) >= discard_n:
                desc = (
                    tf(
                        "log.mauling_discard_prompt",
                        name=mauling.get("name", ""),
                        label=unit_log_label(unit),
                        n=discard_n,
                    )
                )
                chosen = yield ChoiceRequest(
                    player_id=player.agent_id(),
                    choicetype=ChoiceType.CHOOSE_CARDS_TO_DISCARD,
                    options=list(player.action_cards),
                    num_choices=discard_n,
                    description=desc,
                    payload={
                        "reason": "mauling_discard",
                        "mauling": mauling.get("name"),
                        "discard": discard_n,
                        "unit_index": unit.index(),
                    },
                )
                player.discard(list(chosen))
                parts.append(
                    tf("log.discarded", label=unit_log_label(unit), n=discard_n)
                )
            elif fail_hit > 0:
                msg = _apply_category_hit(engine, unit, fail_hit, atype)
                parts.append(
                    tf(
                        "log.cannot_discard_hit",
                        label=unit_log_label(unit),
                        n=discard_n,
                        hit=msg,
                    )
                )
            else:
                parts.append(
                    tf("log.cannot_discard", label=unit_log_label(unit), n=discard_n)
                )

    return one_line(", ".join(parts)) if parts else t("log.no_effect")
