"""Action legality and resolution helpers (pure; choices via engine.request_choice)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Generator

from .constants import ActionName, ChoiceType, UNIT_TYPE_LETTER
from .cards import OfficerCard, OFFICER_CATALOG
from .i18n import unit_type_label

if TYPE_CHECKING:
    from .engine import ChoiceRequest, GameEngine
    from .models import Convoy, Unit


def get_cost(unit: Unit, cost: str | int) -> int:
    if cost == "T":
        return unit.tired + (1 if unit.under_influence else 0)
    return int(cost)


def unit_zones(convoy: Convoy, actor_idx: int) -> list[str]:
    unit = convoy.units[actor_idx]
    return [unit.zone()]


def is_action_possible(engine: GameEngine, actor_idx: int, action: dict) -> bool:
    name = ActionName.normalize(action.get("action_name", ""))
    if name in ActionName.UNIMPLEMENTED:
        return False

    convoy = engine.convoy
    unit = convoy.units[actor_idx]
    limits = action.get("limits") or {}
    letter = UNIT_TYPE_LETTER[unit.unittype]
    if letter not in limits:
        return False
    zones = unit_zones(convoy, actor_idx)
    if not any(z in limits[letter] for z in zones):
        return False

    required = get_cost(unit, action.get("cost", "0"))
    if len(unit.player.action_cards) < required:
        return False

    modifier = action.get("action_modifier", 0)

    if name == ActionName.ATTACK:
        return engine.resistance.active
    if name == ActionName.ASSAULT:
        return engine.resistance.active and unit.can_overtake(1)
    if name == ActionName.RETREAT:
        return engine.resistance.active and unit.can_overtake(-1)
    if name == ActionName.BYPASS:
        return unit.can_overtake(modifier)
    if name == ActionName.PILLAGE:
        return len(engine.pillage_queue) >= 1
    if name == ActionName.PILLAGE_WITH_EXTRA_ATROCITY:
        return len(engine.pillage_queue) >= 2
    if name == ActionName.REST:
        if modifier == 0:
            return unit.can_rest()
        if modifier == 2:
            return unit.can_rest_with_cards()
        # Treat unknown rest modifiers as basic rest
        return unit.can_rest()
    if name == ActionName.SERVICE:
        prev_u, next_u = unit.get_neighbours()
        return (prev_u is not None and prev_u.tired > 0) or (
            next_u is not None and next_u.tired > 0
        )
    if name == ActionName.SOBER_UP:
        return unit.under_influence > 0 and _has_officer(unit, "sober_up") is not None
    if name == ActionName.SUICIDAL_ATTACK:
        return engine.resistance.active
    if name == ActionName.EXIT_FROM_C_WITH_COST:
        return unit.zone() == "C" and unit.player.total_cash >= (modifier or 5)
    if name in (
        ActionName.DEFEND,
        ActionName.PROMOTE,
        ActionName.WAIT,
        ActionName.EXIT,
    ):
        return True
    return True


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
    parts = [
        f"Unit {actor_idx} {unit_type_label(unit.unittype)} resolved {action.get('name', name)}:"
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
        new_pos = convoy.move_unit(actor_idx, 1)
        parts.append(f"moved to {new_pos}")
        # actor index may have changed — find unit again
        actor_idx = unit.index()
        reward, msg = engine.resistance.take_damage(
            UNIT_TYPE_LETTER[unit.unittype], f"={modifier}"
        )
        player.get_cash(reward)
        parts.append(msg)

    elif name == ActionName.RETREAT:
        new_pos = convoy.move_unit(actor_idx, -1)
        parts.append(f"moved to {new_pos}")
        actor_idx = unit.index()
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

    elif name == ActionName.DEFEND:
        unit.resolve_defend("S", "_")
        parts.append("defending")

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

    count = min(2 + modifier, len(engine.pillage_queue))
    drawn: list[tuple[int, bool]] = []
    for _ in range(count):
        drawn.append(engine.pillage_queue.remove_card(0))
    if not drawn:
        return []
    options = [pc for pc, _ in drawn]
    desc = "Choose one pillage card:"
    for pc, _ in drawn:
        d = engine.pillage_deck.describe(pc)
        desc += f"\n  {pc}: {d.get('name', pc)}"
    chosen = yield ChoiceRequest(
        player_id=unit.player.agent_id(),
        choicetype=ChoiceType.CHOOSE_PILLAGE_CARD,
        options=options,
        num_choices=1,
        description=desc,
    )
    pick = chosen[0]
    results = []
    for pc, vis in drawn:
        if pc == pick:
            results.append(engine.pillage_deck.describe(pc))
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
    return f"serviced unit {target.index()}"
