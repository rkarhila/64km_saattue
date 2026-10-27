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


def scoutable_queues(engine: GameEngine) -> list[tuple[int, str]]:
    """Return (code, name) for queues that still have face-down cards."""
    mapping = [
        (SCOUT_QUEUE_PILLAGE, "pillage", engine.pillage_queue),
        (SCOUT_QUEUE_MAULING, "mauling", engine.mauling_queue),
        (SCOUT_QUEUE_RESISTANCE, "resistance", engine.resistance_queue),
    ]
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

    required = get_cost(unit, action.get("cost", "0"))
    hand = len(unit.player.action_cards)
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
    elif name == ActionName.SEARCH:
        # Always available (zone/cost already checked): fills the pillage queue
        # from the pillage deck. Empty deck+discard is a no-op at resolve time.
        pass
    elif name in (
        ActionName.DEFEND,
        ActionName.HUMAN_SHIELDS,
        ActionName.PATROL,
        ActionName.PROMOTE,
        ActionName.WAIT,
        ActionName.EXIT,
    ):
        pass
    # Unknown actions: allow (legacy default) unless already rejected above.
    return reasons


def is_action_possible(engine: GameEngine, actor_idx: int, action: dict) -> bool:
    return not why_action_impossible(engine, actor_idx, action)


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
    engine: GameEngine, actor_idx: int, action: dict, cardnumber: int
) -> Generator[ChoiceRequest, list[int], str]:
    """Generator that yields ChoiceRequests and returns a summary string."""
    from .engine import ChoiceRequest  # local to avoid cycle at import

    convoy = engine.convoy
    unit = convoy.units[actor_idx]
    player = unit.player
    name = ActionName.normalize(action.get("action_name", "")) or ""
    modifier = action.get("action_modifier", 0)
    label = unit_log_label(unit)
    parts = [
        f"{label} resolved {action.get('name', name)}:"
    ]

    # Pay cost
    cost = get_cost(unit, action.get("cost", "0"))
    if cost > 0:
        if cost >= len(player.action_cards):
            player.discard(list(player.action_cards))
        else:
            desc = f"Choose {cost} action cards to discard for {action.get('name', name)}"
            for c in player.action_cards:
                card_desc = player.action_deck.describe(c) if player.action_deck else c
                if isinstance(card_desc, list):
                    label = "/".join(f["name"] for f in card_desc if isinstance(f, dict))
                elif isinstance(card_desc, dict):
                    label = card_desc.get("name", str(c))
                else:
                    label = str(card_desc)
                desc += f"\n  {c}: {label}"
            chosen = yield ChoiceRequest(
                player_id=player.agent_id(),
                choicetype=ChoiceType.CHOOSE_CARDS_TO_DISCARD,
                options=list(player.action_cards),
                num_choices=cost,
                description=desc,
                payload={
                    "reason": "pay_cost",
                    "action_name": action.get("name", name),
                    "cost": cost,
                },
            )
            player.discard(list(chosen))

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
        result = engine.resistance.take_damage(UNIT_TYPE_LETTER[unit.unittype], f"={damage}")
        reward, msg = result
        player.get_cash(reward)
        parts.append(msg)

    elif name == ActionName.ASSAULT:
        old_pos = actor_idx
        old_zone = unit.zone()
        new_pos = convoy.move_unit(actor_idx, 1)
        actor_idx = unit.index()
        parts.append(f"assaulted {old_pos}({old_zone})→{new_pos}({unit.zone()})")
        reward, msg = engine.resistance.take_damage(
            UNIT_TYPE_LETTER[unit.unittype], f"={modifier}"
        )
        player.get_cash(reward)
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
        reward, msg = engine.resistance.take_damage(
            UNIT_TYPE_LETTER[unit.unittype], modifier
        )
        player.get_cash(reward)
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
        attack_letter = ATTACK_TYPE_BY_DEFENCE_ACTION[name]
        unit.resolve_defend(attack_letter, "_")
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

    elif name == ActionName.SEARCH:
        # "Etsi ryöstettävää": draw loot opportunities into the pillage queue.
        count = modifier if modifier and modifier > 0 else 2
        drawn = resolve_search(engine, unit, count)
        if drawn:
            parts.append(
                f"searched, added {len(drawn)} to pillage queue "
                f"(now {len(engine.pillage_queue)})"
            )
        else:
            parts.append("searched but pillage deck empty")

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

    elif name == ActionName.SOBER_UP:
        officer = _has_officer(unit, "sober_up")
        unit.under_influence = 0
        if officer:
            _discard_officer(unit, officer)
        parts.append("sobered up")

    elif name == ActionName.PROMOTE:
        oq = engine.officer_queue
        if len(oq) == 0:
            parts.append("no officers available")
        else:
            indices = list(range(len(oq)))
            desc = "Choose an officer to promote:"
            for i in indices:
                seq_id, _ = oq.cards_and_visibilities[i]
                # Map sequential deck index to officer catalog
                real_id = engine.officer_id_mapping.get(seq_id, seq_id)
                officer = OFFICER_CATALOG[real_id]
                desc += f"\n  {i}: {officer.name}"
            chosen = yield ChoiceRequest(
                player_id=player.agent_id(),
                choicetype=ChoiceType.CHOOSE_OFFICER,
                options=indices,
                num_choices=1,
                description=desc,
            )
            idx = chosen[0]
            seq_id, _ = oq.remove_card(idx)
            real_id = engine.officer_id_mapping.get(seq_id, seq_id)
            officer = OFFICER_CATALOG[real_id]
            # Attach a copy-like instance
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
        reward, msg = engine.resistance.take_damage(
            UNIT_TYPE_LETTER[unit.unittype], damage
        )
        player.get_cash(reward)
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

    # Reveal offered cards in-place so the queue UI stays populated during the
    # choice (previously cards were removed first, emptying the queue box).
    offered: list[dict] = []
    for i in range(count):
        engine.pillage_queue.reveal_card(i)
        pc, _vis = engine.pillage_queue.cards_and_visibilities[i]
        detail = engine.pillage_deck.describe(pc)
        offered.append(
            {
                "id": pc,
                "name": detail.get("name", str(pc)),
                "detail": queue_card_detail(detail),
                "visible": True,
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
            engine.pillage_queue.return_card(pc, visible=True)
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
    return f"serviced {unit_log_label(target)}"


def _queue_by_scout_code(engine: GameEngine, code: int):
    if code == SCOUT_QUEUE_PILLAGE:
        return engine.pillage_queue
    if code == SCOUT_QUEUE_MAULING:
        return engine.mauling_queue
    if code == SCOUT_QUEUE_RESISTANCE:
        return engine.resistance_queue
    raise ValueError(f"unknown scout queue code {code}")


def resolve_search(engine: GameEngine, unit: Unit, count: int) -> list[int]:
    """
    Draw up to `count` cards from the pillage deck into the pillage queue.

    Cards enter face-down (same as resistance loot). Always legal; returns the
    card ids drawn (may be fewer than count if the deck+discard are empty).
    """
    drawn: list[int] = []
    label = unit_log_label(unit)
    for step in range(int(count)):
        deck = engine.pillage_deck
        if not deck.deck and not deck.discard:
            engine._broadcast(
                f"{label} search step {step + 1}/{count}: pillage deck empty "
                f"(queue size {len(engine.pillage_queue)})"
            )
            break
        try:
            card_id = deck.get_card(shuffle_if_necessary=True)
        except RuntimeError:
            engine._broadcast(
                f"{label} search step {step + 1}/{count}: cannot draw "
                f"(queue size {len(engine.pillage_queue)})"
            )
            break
        engine.pillage_queue.put_card(card_id, visible=False)
        drawn.append(card_id)
        name = deck.get_name(card_id) or f"#{card_id}"
        engine._broadcast(
            f"{label} search → pillage queue +{name} "
            f"(step {step + 1}/{count}; queue={len(engine.pillage_queue)})"
        )
    return drawn


def resolve_scout(
    engine: GameEngine, unit: Unit, count: int
) -> Generator[ChoiceRequest, list[int], list[str]]:
    """
    Reveal up to `count` face-down queue cards.

    Each reveal: if several queues have hidden cards, ask which queue to scout;
    otherwise auto-pick the only scoutable queue. Reveals the next hidden card
    in that queue (front-to-back).
    """
    from .engine import ChoiceRequest

    revealed: list[str] = []
    label = unit_log_label(unit)
    for step in range(int(count)):
        options = scoutable_queues(engine)
        if not options:
            engine._broadcast(
                f"{label} scout step {step + 1}/{count}: nothing left to reveal "
                f"({hidden_queue_summary(engine)})"
            )
            break
        codes = [code for code, _ in options]
        if len(codes) == 1:
            chosen_code = codes[0]
        else:
            desc = (
                f"{label} scout {step + 1}/{count}: choose queue to reveal "
                f"({hidden_queue_summary(engine)})"
            )
            for code, qname in options:
                desc += f"\n  {code}: {qname}"
            pick = yield ChoiceRequest(
                player_id=unit.player.agent_id(),
                choicetype=ChoiceType.CHOOSE_QUEUE_TO_SCOUT,
                options=codes,
                num_choices=1,
                description=desc,
                payload={
                    "reason": "scout",
                    "step": step + 1,
                    "count": count,
                    "queues": [
                        {"code": code, "name": qname} for code, qname in options
                    ],
                },
            )
            chosen_code = pick[0]
        queue = _queue_by_scout_code(engine, chosen_code)
        qname = SCOUT_QUEUE_NAMES.get(chosen_code, str(chosen_code))
        # Snapshot which card will be revealed (first hidden).
        hidden_idx = next(
            (i for i, (_, vis) in enumerate(queue.cards_and_visibilities) if not vis),
            None,
        )
        card_id = (
            queue.cards_and_visibilities[hidden_idx][0]
            if hidden_idx is not None
            else None
        )
        queue.reveal_next_hidden()
        card_name = None
        if card_id is not None and queue.deck is not None:
            card_name = queue.deck.get_name(card_id)
        detail = card_name or (f"#{card_id}" if card_id is not None else "?")
        revealed.append(f"{qname}:{detail}")
        engine._broadcast(
            f"{label} scouted {qname} → {detail} "
            f"(step {step + 1}/{count}; {hidden_queue_summary(engine)})"
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
        return [matched[0] if sel["which"] == "first" else matched[-1]]

    if kind == "atrocity":
        max_atr = max(u.atrocities for u in units)
        matched = [u for u in units if u.atrocities == max_atr]
        return [matched[0] if sel["which"] == "first" else matched[-1]]

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
