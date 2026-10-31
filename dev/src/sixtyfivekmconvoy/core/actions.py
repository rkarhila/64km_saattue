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
)
from .cards import OfficerCard, OFFICER_CATALOG, parse_mauling_target
from .cost import evaluate_cost
from .i18n import unit_type_label

if TYPE_CHECKING:
    from .engine import ChoiceRequest, GameEngine
    from .models import Convoy, Unit


def unit_log_label(unit: Unit) -> str:
    """Human-readable unit id for logs, e.g. 'blue jalkaväki'."""
    color = PLAYER_COLORS[unit.player.number % len(PLAYER_COLORS)]
    return f"{color} {unit_type_label(unit.unittype)}"


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
    """Compact queue visibility for logs, e.g. 'resistance:1up/2hid mauling:1up/2hid'."""
    parts: list[str] = []
    for name, queue in (
        ("resistance", engine.resistance_queue),
        ("mauling", engine.mauling_queue),
        ("pillage", engine.pillage_queue),
    ):
        total = len(queue)
        hidden = sum(1 for _, vis in queue.cards_and_visibilities if not vis)
        parts.append(f"{name}:{total - hidden}up/{hidden}hid")
    return " ".join(parts)


def why_action_impossible(
    engine: GameEngine, actor_idx: int, action: dict
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
    hand = len(payer.action_cards)
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
        if not unit.can_overtake(modifier):
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
    elif name == ActionName.SCOUT:
        scoutable = scoutable_queues(engine)
        if not scoutable:
            reasons.append(
                f"nothing to scout ({hidden_queue_summary(engine)})"
            )
    elif name == ActionName.SIGINT:
        scoutable = scoutable_queues(
            engine, allowed_codes={SCOUT_QUEUE_MAULING}
        )
        if not scoutable:
            reasons.append(
                f"nothing to sigint in mauling queue ({hidden_queue_summary(engine)})"
            )
    elif name == ActionName.SEARCH:
        # Always available (zone/cost already checked): fills the pillage queue
        # from the pillage deck. Empty deck+discard is a no-op at resolve time.
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
    elif name == ActionName.SEARCH_PILLAGE_COMBO:
        # Always available when zone/cost allow: search can fill the pillage queue.
        pass
    elif name in (
        ActionName.DEFEND,
        ActionName.HUMAN_SHIELDS,
        ActionName.PATROL,
        ActionName.WAIT,
        ActionName.EXIT,
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


def _cash_for_resistance_hit(player, status: int) -> None:
    """Grant hit cash when resistance is damaged but not destroyed (destroy cash is on the card)."""
    if status != 1:
        return
    from .config import RESISTANCE_HIT_CASH

    if RESISTANCE_HIT_CASH > 0:
        player.get_cash(RESISTANCE_HIT_CASH)


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
        f"{unit_log_label(unit)} card revealed for Order → {names}"
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
        return "order failed: no neighbouring wait"
    if not orderer.action_cards:
        return "order failed: no hand card to assign"

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
            desc_bits.append(f"0={unit_log_label(preceding)} (previous, waited)")
        if following in targets:
            opts.append(1)
            desc_bits.append(f"1={unit_log_label(following)} (following, Wait card)")
        chosen = yield ChoiceRequest(
            player_id=orderer.agent_id(),
            choicetype=ChoiceType.CHOOSE_SERVICE,
            options=opts,
            num_choices=1,
            description="Order which neighbour: " + "; ".join(desc_bits),
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
        return f"order failed: card {card_id} not in hand"
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

    return f"ordered {unit_log_label(waiter)} → {nested} (card {card_id} returned)"


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
    payer = cost_player if cost_player is not None else player
    name = ActionName.normalize(action.get("action_name", "")) or ""
    modifier = action.get("action_modifier", 0)
    label = unit_log_label(unit)
    parts = [
        f"{label} resolved {action.get('name', name)}:"
    ]

    # Pay cost (possibly from ordering player)
    cost = get_cost(unit, action.get("cost", "0"))
    if cost > 0:
        if cost >= len(payer.action_cards):
            payer.discard(list(payer.action_cards))
        else:
            desc = f"Choose {cost} action cards to discard for {action.get('name', name)}"
            for c in payer.action_cards:
                card_desc = payer.action_deck.describe(c) if payer.action_deck else c
                if isinstance(card_desc, list):
                    clabel = "/".join(
                        f["name"] for f in card_desc if isinstance(f, dict)
                    )
                elif isinstance(card_desc, dict):
                    clabel = card_desc.get("name", str(c))
                else:
                    clabel = str(card_desc)
                desc += f"\n  {c}: {clabel}"
            chosen = yield ChoiceRequest(
                player_id=payer.agent_id(),
                choicetype=ChoiceType.CHOOSE_CARDS_TO_DISCARD,
                options=list(payer.action_cards),
                num_choices=cost,
                description=desc,
                payload={
                    "reason": "pay_cost",
                    "action_name": action.get("name", name),
                    "cost": cost,
                },
            )
            payer.discard(list(chosen))

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
        _cash_for_resistance_hit(player, status)
        parts.append(msg)

        from .config import ATTACK_CASH
        if ATTACK_CASH > 0:
            player.get_cash(ATTACK_CASH)
            engine._broadcast(
                f"{unit_log_label(unit)} rewarded {ATTACK_CASH} cash for attacking"
            )

    elif name == ActionName.ASSAULT:
        old_pos = actor_idx
        old_zone = unit.zone()
        new_pos = convoy.move_unit(actor_idx, 1)
        actor_idx = unit.index()
        parts.append(f"assaulted {old_pos}({old_zone})→{new_pos}({unit.zone()})")
        status, msg = engine.resistance.take_damage(
            UNIT_TYPE_LETTER[unit.unittype], f"={modifier}", player=player
        )
        _cash_for_resistance_hit(player, status)
        parts.append(msg)

    elif name == ActionName.RETREAT:
        # Suojatulta! → retreat one slot toward the rear, then deal damage.
        old_pos = actor_idx
        old_zone = unit.zone()
        new_pos = convoy.move_unit(actor_idx, -1)
        actor_idx = unit.index()
        parts.append(
            f"retreated {old_pos}({old_zone})→{new_pos}({unit.zone()})"
        )
        status, msg = engine.resistance.take_damage(
            UNIT_TYPE_LETTER[unit.unittype], modifier, player=player
        )
        _cash_for_resistance_hit(player, status)
        parts.append(msg)

    elif name == ActionName.BYPASS:
        new_pos = convoy.move_unit(actor_idx, modifier)
        parts.append(f"bypassed to {new_pos}")

    elif name == ActionName.EXIT:
        player.this_round_cash += sum(unit.carry)
        player.total_cash += sum(unit.carry)
        convoy.units.pop(unit.index())
        parts.append(f"exited with loot worth {sum(unit.carry)}")

    elif name in (ActionName.PILLAGE, ActionName.PILLAGE_WITH_EXTRA_ATROCITY):
        extra = 0 if name == ActionName.PILLAGE_WITH_EXTRA_ATROCITY else modifier
        rewards = yield from _resolve_pillage(engine, unit, extra)
        for r in rewards:
            player.this_round_cash += r["reward"]["cash"]
            player.total_cash += r["reward"]["cash"]
            unit.gain_loot(r["reward"]["loot"])
            atro = r["reward"]["atrocities"]
            if name == ActionName.PILLAGE_WITH_EXTRA_ATROCITY:
                atro = max(0, atro - 1)
            unit.gain_atrocities(atro)
            parts.append(f"pillaged {r['name']}")

    elif name in ATTACK_TYPE_BY_DEFENCE_ACTION:
        # Defend→G (ground), Human shields→A (air), Patrol→S (sabotage).
        # Soak rewards are config-driven in Unit.reward_defending.
        attack_letter = ATTACK_TYPE_BY_DEFENCE_ACTION[name]
        unit.resolve_defend(attack_letter)
        parts.append(f"defending ({attack_letter}/{name})")

    elif name == ActionName.SCOUT:
        count = modifier if modifier and modifier > 0 else 2
        scouted = yield from resolve_scout(engine, unit, count)
        if scouted:
            parts.append(f"scouted {len(scouted)}: " + ", ".join(scouted))
        else:
            parts.append(
                f"scout found nothing ({hidden_queue_summary(engine)})"
            )

    elif name == ActionName.SIGINT:
        # Like scout, but only face-down mauling cards.
        count = modifier if modifier and modifier > 0 else 2
        scouted = yield from resolve_scout(
            engine,
            unit,
            count,
            allowed_queue_codes={SCOUT_QUEUE_MAULING},
            verb="sigint",
        )
        if scouted:
            parts.append(f"sigint {len(scouted)}: " + ", ".join(scouted))
        else:
            parts.append(
                f"sigint found nothing ({hidden_queue_summary(engine)})"
            )

    elif name == ActionName.SEARCH:
        # "Etsi ryöstettävää": draw and scout cards in the pillage queue.
        count = modifier if modifier and modifier > 0 else 2
        summary_parts = yield from resolve_search(engine, unit, count)
        parts.extend(summary_parts)

    elif name == ActionName.WAIT:
        if not player.action_cards:
            parts.append("waited but no cards")
        else:
            desc = "Choose an action card to add (WAIT):"
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
            parts.append(f"waited, queued card {card}")

    elif name == ActionName.ORDER:
        msg = yield from resolve_order(engine, unit)
        parts.append(msg)

    elif name == ActionName.SEARCH_PILLAGE_COMBO:
        count = modifier if modifier and modifier > 0 else 2
        summary_parts = yield from resolve_search(engine, unit, count)
        parts.extend(summary_parts)
        if len(engine.pillage_queue) >= 1:
            rewards = yield from _resolve_pillage(engine, unit, 0)
            for r in rewards:
                player.this_round_cash += r["reward"]["cash"]
                player.total_cash += r["reward"]["cash"]
                unit.gain_loot(r["reward"]["loot"])
                unit.gain_atrocities(r["reward"]["atrocities"])
                parts.append(f"pillaged {r['name']}")
        else:
            parts.append("nothing to pillage after search")

    elif name == ActionName.SOBER_UP:
        officer = _has_officer(unit, "sober_up")
        unit.under_influence = 0
        if officer:
            _discard_officer(unit, officer)
        parts.append("sobered up")

    elif name == ActionName.PROMOTE:
        oq = engine.officer_queue
        indices = matching_officer_queue_indices(engine, unit)
        if not indices:
            parts.append(
                f"no officers available for troop "
                f"{UNIT_TYPE_LETTER[unit.unittype]}"
            )
        else:
            letter = UNIT_TYPE_LETTER[unit.unittype]
            desc = f"Choose an officer to promote ({letter}):"
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
            parts.append(f"promoted with {officer.name}")

    elif name == ActionName.SERVICE:
        msg = yield from _resolve_service(engine, unit)
        parts.append(msg)

    elif name == ActionName.REST:
        if modifier == 2 and unit.can_rest_with_cards():
            old = unit.tired
            unit.rest_with_cards()
            parts.append(f"rested hard {old}->{unit.tired}")
        else:
            old = unit.tired
            u = unit.under_influence
            unit.rest()
            parts.append(f"rested (influence={u}, tired {old}->{unit.tired})")

    elif name == ActionName.SUICIDAL_ATTACK:
        damage = modifier if modifier else 5
        status, msg = engine.resistance.take_damage(
            UNIT_TYPE_LETTER[unit.unittype], damage, player=player
        )
        _cash_for_resistance_hit(player, status)
        convoy.apply_damage(1, unit=unit)
        parts.append(msg)
        parts.append("unit took 1 damage")

    elif name == ActionName.EXIT_FROM_C_WITH_COST:
        cost_cash = modifier or 5
        player.total_cash = max(0, player.total_cash - cost_cash)
        player.this_round_cash += sum(unit.carry)
        player.total_cash += sum(unit.carry)
        convoy.units.pop(unit.index())
        parts.append(f"paid {cost_cash} and exited from C")

    else:
        parts.append(f"(no-op / unimplemented {name})")

    if action.get("tire"):
        unit.tire()
    if action.get("intoxicate"):
        unit.under_influence = 1

    if action.get("is_officer_discard") and action.get("officer"):
        _discard_officer(unit, action["officer"])
        parts.append(f"discarded officer {action['officer'].name}")

    engine.stats.record_action(player.number, name)
    summary = ", ".join(parts)
    engine.round_action_summaries.append(summary)
    return summary


def _resolve_pillage(
    engine: GameEngine, unit: Unit, modifier: int
) -> Generator[ChoiceRequest, list[int], list[dict]]:
    from .engine import ChoiceRequest
    from .cards import queue_card_detail

    count = min(2 + modifier, len(engine.pillage_queue))
    if count <= 0:
        return []

    # Reveal offered cards only if they are already visible (scouted).
    # Unscouted cards are kept face-down for blind pick.
    offered: list[dict] = []
    for i in range(count):
        pc, vis = engine.pillage_queue.cards_and_visibilities[i]
        if vis:
            detail = engine.pillage_deck.describe(pc)
            offered.append(
                {
                    "id": pc,
                    "name": detail.get("name", str(pc)),
                    "detail": queue_card_detail(detail),
                    "reward": detail.get("reward"),
                    "visible": True,
                }
            )
        else:
            offered.append(
                {
                    "id": pc,
                    "name": f"Face-down Card (Slot {i+1})",
                    "detail": "Must be scouted/revealed to see contents.",
                    "visible": False,
                }
            )

    options = [o["id"] for o in offered]
    desc = "Choose one pillage card:"
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

    drawn = [engine.pillage_queue.remove_card(0) for _ in range(count)]
    results = []
    for pc, vis in drawn:
        if pc == pick:
            results.append(engine.pillage_deck.describe(pc))
            engine.pillage_deck.discard_card(pc)
        else:
            engine.pillage_queue.return_card(pc, visible=vis)
    return results


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
            description="Service neighbour: 0=preceding, 1=following",
        )
        target = preceding if chosen[0] == 0 else following
    elif tired_prev:
        target = preceding
    else:
        target = following
    assert target is not None
    target.tired = max(0, target.tired - 1)
    
    msg = f"serviced {unit_log_label(target)}"
    from .config import SERVICE_CASH
    if SERVICE_CASH > 0:
        unit.player.get_cash(SERVICE_CASH)
        engine._broadcast(
            f"{unit_log_label(unit)} rewarded {SERVICE_CASH} cash for service"
        )
        msg += f" (rewarded {SERVICE_CASH} cash)"
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
    hint = summary.strip() if summary else "Toiminto kirjattu lokiin."
    if len(hint) > 160:
        hint = hint[:157] + "…"
    yield from _pause_after_log(
        engine,
        f"{hint} Jatka.",
        reason="action_pause",
    )


def resolve_search(
    engine: GameEngine, unit: Unit, count: int
) -> Generator[ChoiceRequest, list[int], list[str]]:
    """
    Search action (Etsi ryöstettävää):
    If there are unscouted pillage cards, search works like scout for these cards: Flip them and reorder.
    If there are less unscouted pillage cards than the value of search, add enough cards from the pillage deck to match it.
    So this is an action that can always be performed if player has enough cards to pay for it.
    """
    from .engine import ChoiceRequest

    label = unit_log_label(unit)

    # 1. Count current unscouted (face-down) pillage cards in the queue
    face_down_indices = [
        idx for idx, (_, vis) in enumerate(engine.pillage_queue.cards_and_visibilities) if not vis
    ]
    num_face_down = len(face_down_indices)

    # 2. If we have less than `count` face-down pillage cards, draw cards face-down from the deck to match
    drawn_ids = []
    if num_face_down < count:
        num_to_draw = count - num_face_down
        deck = engine.pillage_deck
        for step in range(num_to_draw):
            if not deck.deck and not deck.discard:
                engine._broadcast(
                    f"{label} search step {step + 1}/{num_to_draw}: pillage deck empty "
                    f"(queue size {len(engine.pillage_queue)})"
                )
                break
            try:
                card_id = deck.get_card(shuffle_if_necessary=True)
                engine.pillage_queue.put_card(card_id, visible=False)
                drawn_ids.append(card_id)
                name = deck.get_name(card_id) or f"#{card_id}"
                engine._broadcast(
                    f"{label} search → pillage queue +{name} "
                    f"(step {step + 1}/{num_to_draw}; queue={len(engine.pillage_queue)})"
                )
            except RuntimeError:
                engine._broadcast(
                    f"{label} search step {step + 1}/{num_to_draw}: cannot draw "
                    f"(queue size {len(engine.pillage_queue)})"
                )
                break

    # Recount face-down cards after drawing
    face_down_indices = [
        idx for idx, (_, vis) in enumerate(engine.pillage_queue.cards_and_visibilities) if not vis
    ]
    num_face_down = len(face_down_indices)

    # 3. Determine how many to scout/reveal (min of count and available face-down cards)
    num_to_scout = min(count, num_face_down)
    if num_to_scout <= 0:
        return ["searched, but no pillage cards to reveal"]

    # 4. Scout phase: select which face-down cards in the pillage queue to reveal
    options = [idx for idx in face_down_indices]
    desc = f"{label} search: Choose {num_to_scout} face-down pillage cards to reveal."

    queues_payload = []
    for idx in face_down_indices:
        queues_payload.append({
            "option": idx,
            "queue": "pillage",
            "index": idx
        })

    pick = yield ChoiceRequest(
        player_id=unit.player.agent_id(),
        choicetype=ChoiceType.CHOOSE_CARDS_TO_SCOUT,
        options=options,
        num_choices=num_to_scout,
        description=desc,
        payload={
            "reason": "scout_selection",
            "cards": queues_payload,
            "count": num_to_scout
        }
    )

    if not pick:
        pick = options[:num_to_scout]

    pillage_queue = engine.pillage_queue
    # Reveal one card at a time (pause after each so the UI can animate).
    pick = sorted(pick)
    scouted_card_names = []
    for idx in pick:
        pillage_queue.reveal_card(idx)
        card_id = pillage_queue.cards_and_visibilities[idx][0]
        card_name = pillage_queue.deck.get_name(card_id) if pillage_queue.deck else str(card_id)
        scouted_card_names.append(card_name)
        engine._broadcast(
            f"{label} searched pillage card → {card_name} (revealed)",
            kind="reveal",
            queue="pillage",
            index=idx,
            card_id=card_id,
        )
        yield from _pause_after_reveal(
            engine,
            f"Paljastettu: {card_name}. Jatka.",
        )

    if len(pick) > 1:
        # Reorder multiple revealed cards
        desc_reorder = f"{label} search: Choose the new order for the scouted pillage cards."
        reorder_payload_cards = []
        for idx in pick:
            card_id = pillage_queue.cards_and_visibilities[idx][0]
            card_name = pillage_queue.deck.get_name(card_id) if pillage_queue.deck else str(card_id)
            reorder_payload_cards.append({
                "option": idx,
                "name": card_name,
                "detail": pillage_queue.deck.describe(card_id) if pillage_queue.deck else None
            })

        reordered_pick = yield ChoiceRequest(
            player_id=unit.player.agent_id(),
            choicetype=ChoiceType.REORDER_SCOUTED_CARDS,
            options=pick,
            num_choices=len(pick),
            description=desc_reorder,
            payload={
                "reason": "scout_reorder",
                "queue": "pillage",
                "cards": reorder_payload_cards
            }
        )

        if not reordered_pick or set(reordered_pick) != set(pick):
            reordered_pick = pick

        original_entries = {idx: list(pillage_queue.cards_and_visibilities[idx]) for idx in pick}
        for i, orig_idx in enumerate(reordered_pick):
            target_idx = pick[i]
            pillage_queue.cards_and_visibilities[target_idx] = original_entries[orig_idx]

        scouted_card_names = []
        for idx in pick:
            card_id = pillage_queue.cards_and_visibilities[idx][0]
            card_name = pillage_queue.deck.get_name(card_id) if pillage_queue.deck else str(card_id)
            scouted_card_names.append(card_name)
        engine._broadcast(
            f"{label} reordered searched pillage cards: {', '.join(scouted_card_names)}"
        )

    return [f"searched and revealed {', '.join(scouted_card_names)} in pillage queue"]


def resolve_scout(
    engine: GameEngine,
    unit: Unit,
    count: int,
    *,
    allowed_queue_codes: set[int] | frozenset[int] | None = None,
    verb: str = "scout",
) -> Generator[ChoiceRequest, list[int], list[str]]:
    """
    Reveal up to `count` face-down queue cards.

    By default any of pillage/mauling/resistance may be chosen. Pass
    ``allowed_queue_codes`` (e.g. ``{SCOUT_QUEUE_MAULING}`` for sigint) to
    restrict which queues are eligible. If several cards from the same queue
    are chosen, the player can put them back in a different order.
    """
    from .engine import ChoiceRequest

    revealed: list[str] = []
    label = unit_log_label(unit)

    queue_mapping = [
        (SCOUT_QUEUE_PILLAGE, "pillage", engine.pillage_queue),
        (SCOUT_QUEUE_MAULING, "mauling", engine.mauling_queue),
        (SCOUT_QUEUE_RESISTANCE, "resistance", engine.resistance_queue),
    ]
    if allowed_queue_codes is not None:
        queue_mapping = [
            row for row in queue_mapping if row[0] in allowed_queue_codes
        ]

    # Find all face-down cards across allowed queues
    face_down_cards = []
    for code, qname, queue in queue_mapping:
        for idx, (card_id, vis) in enumerate(queue.cards_and_visibilities):
            if not vis:
                face_down_cards.append((code, qname, idx, card_id))

    num_to_scout = min(count, len(face_down_cards))
    if num_to_scout <= 0:
        engine._broadcast(
            f"{label} {verb}: nothing left to reveal "
            f"({hidden_queue_summary(engine)})"
        )
        return revealed

    queue_hint = (
        "any queues"
        if allowed_queue_codes is None
        else ", ".join(SCOUT_QUEUE_NAMES[c] for c in sorted(allowed_queue_codes))
    )
    # Choice phase 1: Select which face-down card(s) to scout
    options = [code * 100 + idx for code, qname, idx, cid in face_down_cards]
    desc = (
        f"{label} {verb}: Choose {num_to_scout} face-down card(s) "
        f"to reveal ({queue_hint})."
    )

    queues_payload = []
    for code, qname, idx, cid in face_down_cards:
        queues_payload.append({
            "option": code * 100 + idx,
            "queue": qname,
            "index": idx
        })

    pick = yield ChoiceRequest(
        player_id=unit.player.agent_id(),
        choicetype=ChoiceType.CHOOSE_CARDS_TO_SCOUT,
        options=options,
        num_choices=num_to_scout,
        description=desc,
        payload={
            "reason": f"{verb}_selection",
            "verb": verb,
            "cards": queues_payload,
            "count": num_to_scout,
            "allowed_queues": [
                SCOUT_QUEUE_NAMES[c]
                for c in (
                    sorted(allowed_queue_codes)
                    if allowed_queue_codes is not None
                    else sorted(SCOUT_QUEUE_NAMES)
                )
            ],
        }
    )

    # Validate pick
    if not pick:
        pick = options[:num_to_scout]

    # Group chosen cards by queue
    chosen_by_queue = {}  # code -> list of indices
    for opt in pick:
        code = opt // 100
        idx = opt % 100
        chosen_by_queue.setdefault(code, []).append(idx)

    # Scout incentive (resistance only; sigint/mauling does not grant it):
    if verb == "scout" and SCOUT_QUEUE_RESISTANCE in chosen_by_queue:
        from .config import SCOUT_CASH
        if SCOUT_CASH > 0:
            unit.player.get_cash(SCOUT_CASH)
            engine._broadcast(
                f"{label} rewarded {SCOUT_CASH} cash for scouting resistance card(s)"
            )

    # Process each queue: reveal one card at a time with optional pause.
    for code, indices in chosen_by_queue.items():
        queue = _queue_by_scout_code(engine, code)
        qname = SCOUT_QUEUE_NAMES[code]
        indices = sorted(indices)

        for idx in indices:
            queue.reveal_card(idx)
            card_id = queue.cards_and_visibilities[idx][0]
            card_name = queue.deck.get_name(card_id) if queue.deck else str(card_id)
            revealed.append(f"{qname}:{card_name}")
            engine._broadcast(
                f"{label} {verb} {qname} card → {card_name} (revealed)",
                kind="reveal",
                queue=qname,
                index=idx,
                card_id=card_id,
            )
            yield from _pause_after_reveal(
                engine,
                f"Paljastettu ({qname}): {card_name}. Jatka.",
            )

        # If several cards from the same queue were scouted, allow reordering.
        if len(indices) > 1:
            desc_reorder = (
                f"{label} {verb}: Choose the new order for the scouted "
                f"{qname} cards."
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
                f"{label} reordered {verb} {qname} cards: {', '.join(names)}"
            )

    return revealed


def mauling_target_units(convoy: Convoy, target: str) -> list[Unit]:
    """Resolve a mauling target string into living units."""
    sel = parse_mauling_target(target)
    units = list(convoy.units)
    if not units:
        return []

    kind = sel["kind"]
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


def resolve_mauling(
    engine: GameEngine, mauling: dict
) -> Generator[ChoiceRequest, list[int], str]:
    """
    Apply one mauling card.

    Hit-category damage uses the shared hit table. Forced discard yields a
    CHOOSE_CARDS_TO_DISCARD; if the player cannot pay, fail_hit_category damage
    is drawn instead.
    """
    from .engine import ChoiceRequest

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
            damage = engine.draw_hit_damage(hit_cat)
            if damage <= 0:
                parts.append(f"{unit_log_label(unit)} hit cat {hit_cat} for 0")
            else:
                parts.append(
                    convoy.apply_damage(damage, unit=unit, attack_type=atype)
                )

    if discard_n > 0:
        for unit in mauling_target_units(convoy, target):
            if unit not in convoy.units:
                continue
            player = unit.player
            if len(player.action_cards) >= discard_n:
                desc = (
                    f"Mauling {mauling.get('name', '')}: discard {discard_n} "
                    f"action card(s) for {unit_log_label(unit)}"
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
                    f"{unit_log_label(unit)} discards {discard_n} "
                    f"({player.agent_id()})"
                )
            elif fail_hit > 0:
                damage = engine.draw_hit_damage(fail_hit)
                if damage <= 0:
                    parts.append(
                        f"{unit_log_label(unit)} cannot discard {discard_n}; "
                        f"fail hit cat {fail_hit} for 0"
                    )
                else:
                    msg = convoy.apply_damage(
                        damage, unit=unit, attack_type=atype
                    )
                    parts.append(
                        f"{unit_log_label(unit)} cannot discard {discard_n}; "
                        f"fail hit: {msg}"
                    )
            else:
                parts.append(
                    f"{unit_log_label(unit)} cannot discard {discard_n}; no fail hit"
                )

    return "; ".join(parts) if parts else "no effect"
