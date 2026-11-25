"""Text and JSON reports for rotations."""

from __future__ import annotations

from collections.abc import Sequence
from fractions import Fraction
from typing import Any

from .damage import format_number, format_percent
from .resources import ResourceEvent
from .rotation import RULES, CritBase, Healing, Part, RotationOutcome
from .scenario import Target
from .stats import StatSheet
from .survival import HealEvent, ShieldEvent

RESULT_LABEL = "Calculado"


def _percent_list(entries: tuple[tuple[str, Fraction], ...]) -> str:
    return ", ".join(f"{name} {format_number(percent)}%" for name, percent in entries)


def _percent(rate: Fraction) -> str:
    return format_percent(rate)


def _heal_lines(healing: Healing) -> list[str]:
    lines = [
        f"      heal: (life steal {_percent(healing.life_steal)} + omnivamp "
        f"{_percent(healing.omnivamp)}) = {format_number(healing.amount)} [{healing.label.value}]"
    ]
    return lines + [f"      heal note: {note}" for note in healing.notes]


def _healing_dict(healing: Healing) -> dict[str, Any]:
    return {
        "life_steal": float(healing.life_steal),
        "omnivamp": float(healing.omnivamp),
        "amount": float(healing.amount),
        "exact_amount": str(healing.amount),
        "label": healing.label.value,
        "notes": list(healing.notes),
    }


def _part_line(part: Part, heals: bool) -> list[str]:
    result = part.mitigation
    lines = [
        f"    {part.kind} {part.damage_type.value}: raw {format_number(part.raw)} "
        f"[{part.label.value}] ({part.source})"
    ]
    if result.resistance is None:
        mitigation = f"true damage -> {format_number(result.damage)}"
    else:
        mitigation = (
            f"resistance {format_number(result.resistance.initial)} -> "
            f"{format_number(result.resistance.effective)}; multiplier "
            f"{format_number(result.multiplier)} -> {format_number(result.damage)}"
        )
    modifiers = []
    if part.dealt:
        modifiers.append(
            f"dealt +({_percent_list(part.dealt)}) x{format_number(part.dealt_factor)}"
        )
    if part.taken:
        modifiers.append(f"taken ({_percent_list(part.taken)}) x{format_number(part.taken_factor)}")
    tail = f"; {'; '.join(modifiers)}" if modifiers else ""
    if not part.hits_primary:
        unit = part.mitigation.damage * part.dealt_factor * part.taken_factor
        lines.append(
            f"      {mitigation}{tail} = {format_number(unit)} x{part.targets_hit} secondary "
            f"= {format_number(part.damage)}"
        )
    elif part.targets_hit > 1:
        if part.secondary_damage_ratio == 1:
            lines.append(
                f"      {mitigation}{tail} = {format_number(part.primary_damage)} "
                f"x{part.targets_hit} targets = {format_number(part.damage)}"
            )
        else:
            lines.append(
                f"      {mitigation}{tail} = {format_number(part.primary_damage)} primary + "
                f"{part.targets_hit - 1}x {format_number(part.secondary_damage_ratio * 100)}% "
                f"secondary ({format_number(part.secondary_damage)}) = {format_number(part.damage)}"
            )
    else:
        lines.append(f"      {mitigation}{tail} = {format_number(part.damage)}")
    lines += [f"      note: {note}" for note in part.notes]
    if heals:
        lines += _heal_lines(part.healing)
    return lines


def _heal_event_dict(event: HealEvent) -> dict[str, Any]:
    return {
        "source": event.source,
        "raw": float(event.raw),
        "amount": float(event.amount),
        "exact_amount": str(event.amount),
        "uses_hsp": event.uses_hsp,
        "grievous_applied": event.grievous_applied,
        "label": event.label.value,
        "notes": list(event.notes),
    }


def _shield_event_dict(event: ShieldEvent) -> dict[str, Any]:
    return {
        "source": event.source,
        "raw": float(event.raw),
        "amount": float(event.amount),
        "exact_amount": str(event.amount),
        "shield_type": event.shield_type,
        "duration": None if event.duration is None else float(event.duration),
        "label": event.label.value,
        "notes": list(event.notes),
    }


def _resource_event_dict(event: ResourceEvent) -> dict[str, Any]:
    return {
        "source": event.source,
        "resource": event.resource,
        "kind": event.kind,
        "raw": float(event.raw),
        "effective": float(event.effective),
        "exact_effective": str(event.effective),
        "label": event.label.value,
        "notes": list(event.notes),
    }


def format_text(
    outcome: RotationOutcome,
    sheet: StatSheet,
    target: Target,
    crit_base: CritBase | None,
    *,
    windows: Sequence[Fraction] = (),
) -> str:
    items = ", ".join(f"{item.id} {item.name}" for item in sheet.items) or "none"
    target_items = ", ".join(item.id for item in target.items)
    lines = [
        f"attacker: {sheet.champion.name} level {sheet.level}, patch {sheet.champion.patch}, "
        f"range {outcome.holder_range or 'not given'}",
        f"items: {items}",
        f"target: {target.description}"
        + (f", effects from items {target_items}" if target_items else ""),
    ]
    if outcome.target_count > 1:
        lines.append(f"targets: {outcome.target_count}")
    lines.append(
        f"target health: {format_number(outcome.start_health)} / "
        f"{format_number(outcome.max_health)}"
    )
    if outcome.start_shield > 0:
        lines.append(
            f"target shield: {format_number(outcome.start_shield)} ({outcome.shield_type})"
        )
    res = outcome.resource
    if res is not None and res.uses_casting_pool:
        lines.append(
            f"attacker resource: {res.name} {format_number(res.start)} / "
            f"{format_number(res.maximum)} [{res.label.value}]"
        )
    if crit_base is not None and any(step.step.crit for step in outcome.steps):
        lines.append(
            f"critical multiplier: {format_number(crit_base.value)} [{crit_base.label.value}] "
            f"({crit_base.source})"
        )
    heals = bool(sheet["life_steal"].total() or sheet["omnivamp"].total() or outcome.healing)
    hsp = sheet["heal_and_shield_power"]
    if heals or hsp.total() or outcome.total_shield_granted:
        extra_hsp = (
            f", heal & shield power: {_percent(hsp.total())} [{hsp.label.value}]"
            if hsp.total()
            else ""
        )
        lines.append(
            f"life steal: {_percent(sheet['life_steal'].total())} "
            f"[{sheet['life_steal'].label.value}], omnivamp: "
            f"{_percent(sheet['omnivamp'].total())} [{sheet['omnivamp'].label.value}]{extra_hsp}"
        )
    if outcome.grievous_wounds_applied:
        lines.append("grievous wounds: applied (-40% healing)")
    for step in outcome.steps:
        at = "" if step.time is None else f" at {format_number(step.time)} s"
        shield_str = (
            f", shield {format_number(step.shield_before)}" if outcome.start_shield > 0 else ""
        )
        lines.append(
            f"step {step.index} {step.step.text} ({step.name}){at}: "
            f"health {format_number(step.health_before)}{shield_str}"
        )
        for part in step.parts:
            lines += _part_line(part, heals)
        for event in step.heal_events:
            lines.append(
                f"    effect heal: {format_number(event.amount)} [{event.label.value}] "
                f"({event.source})"
            )
            lines += [f"      heal note: {note}" for note in event.notes]
        for event in step.shield_events:
            lines.append(
                f"    attacker shield: {format_number(event.amount)} ({event.shield_type}) "
                f"[{event.label.value}] ({event.source})"
            )
            lines += [f"      shield note: {note}" for note in event.notes]
        for event in step.resource_events:
            sign = "-" if event.kind == "cost" else "+"
            cap_note = f" (raw {format_number(event.raw)})" if event.effective != event.raw else ""
            lines.append(
                f"    resource {event.kind}: {sign}{format_number(event.effective)} "
                f"{event.resource}{cap_note} [{event.label.value}] ({event.source})"
            )
            lines += [f"      resource note: {note}" for note in event.notes]
        absorbed_str = (
            f" (shield absorbed {format_number(step.shield_absorbed)} -> "
            f"shield {format_number(step.shield_after)})"
            if outcome.start_shield > 0
            else ""
        )
        res_str = (
            f"; {res.name} {format_number(step.resource_before)} -> "
            f"{format_number(step.resource_after)}"
            if res is not None
            and res.uses_casting_pool
            and step.resource_before is not None
            and step.resource_after is not None
            and (step.resource_before != step.resource_after or step.resource_events)
            else ""
        )
        split_str = (
            f" (primary {format_number(step.primary_total)}, "
            f"secondary {format_number(step.secondary_total)})"
            if step.secondary_total > 0
            else ""
        )
        lines.append(
            f"  step total {format_number(step.total)}{split_str}{absorbed_str} -> "
            f"health {format_number(step.health_after)}{res_str}"
        )
        if heals:
            lines.append(f"  step heal {format_number(step.healing)} [{step.healing_label.value}]")
            lines += [f"  heal note: {note}" for note in step.healing_notes]
    total_split = (
        f" (primary {format_number(outcome.primary_total)}, "
        f"secondary {format_number(outcome.secondary_total)})"
        if outcome.secondary_total > 0
        else ""
    )
    lines.append(f"total: {format_number(outcome.total)}{total_split}")
    if outcome.start_shield > 0:
        lines.append(
            f"shield absorbed: {format_number(outcome.total_shield_absorbed)}, "
            f"remaining shield: {format_number(outcome.remaining_shield)}"
        )
    if heals:
        lines.append(
            f"total heal: {format_number(outcome.healing)} [{outcome.healing_label.value}]"
        )
    if outcome.effective_healing is not None and outcome.attacker_max_health is not None:
        lines.append(
            f"effective heal: {format_number(outcome.effective_healing)} "
            f"(attacker health {format_number(outcome.attacker_start_health or 0)} -> "
            f"{format_number(outcome.attacker_remaining_health or 0)} / "
            f"{format_number(outcome.attacker_max_health)})"
        )
    if outcome.total_shield_granted > 0:
        lines.append(f"total attacker shield: {format_number(outcome.total_shield_granted)}")
    if res is not None and res.uses_casting_pool:
        parts_res = [
            f"spent {format_number(res.spent)}",
            f"restored {format_number(res.effective_restored)}",
        ]
        if res.regenerated:
            parts_res.append(f"regenerated {format_number(res.regenerated)}")
        parts_res.append(f"remaining {format_number(res.remaining)} / {format_number(res.maximum)}")
        lines.append(f"resource ({res.name}): {', '.join(parts_res)} [{res.label.value}]")
    if res is not None and res.health_cost_spent > 0:
        lines.append(f"health cost spent: {format_number(res.health_cost_spent)}")
    lines.append(f"remaining health: {format_number(outcome.remaining_health)}")
    if outcome.timeline is not None:
        lines.append(
            f"timeline: attack every {format_number(outcome.timeline.attack_interval)} s "
            f"[{outcome.timeline.label.value}]; duration {format_number(outcome.duration)} s"
        )
        if outcome.damage_per_second is not None:
            lines.append(f"damage per second: {format_number(outcome.damage_per_second)}")
        for sec in windows:
            win = outcome.window(sec)
            lines.append(
                f"window 0..{format_number(win.seconds)} s: total {format_number(win.total)}, "
                f"DPS {format_number(win.damage_per_second)}, steps {win.steps_count}, "
                f"remaining health {format_number(win.remaining_health)} [{win.label.value}]"
            )
    if outcome.lethal_step is not None:
        lines.append(f"lethal at step {outcome.lethal_step}")
    for note in outcome.notes:
        lines.append(f"note: {note}")
    lines.append(f"label: {RESULT_LABEL} (weakest input: {outcome.label.value})")
    return "\n".join(lines)


def _part_dict(part: Part) -> dict[str, Any]:
    result = part.mitigation
    return {
        "kind": part.kind,
        "source": part.source,
        "damage_type": part.damage_type.value,
        "raw": float(part.raw),
        "label": part.label.value,
        "resistance": None
        if result.resistance is None
        else {
            "initial": float(result.resistance.initial),
            "effective": float(result.resistance.effective),
        },
        "multiplier": float(result.multiplier),
        "mitigated": float(result.damage),
        "dealt_modifiers": [{"effect": name, "percent": float(p)} for name, p in part.dealt],
        "taken_modifiers": [{"effect": name, "percent": float(p)} for name, p in part.taken],
        "aoe": part.aoe,
        "hits_primary": part.hits_primary,
        "targets_hit": part.targets_hit,
        "secondary_damage_ratio": float(part.secondary_damage_ratio),
        "primary_damage": float(part.primary_damage),
        "exact_primary_damage": str(part.primary_damage),
        "secondary_damage": float(part.secondary_damage),
        "exact_secondary_damage": str(part.secondary_damage),
        "damage": float(part.damage),
        "exact_damage": str(part.damage),
        "notes": list(part.notes),
        "healing": _healing_dict(part.healing),
    }


def to_dict(
    outcome: RotationOutcome,
    sheet: StatSheet,
    target: Target,
    crit_base: CritBase | None,
    *,
    windows: Sequence[Fraction] = (),
) -> dict[str, Any]:
    return {
        "label": RESULT_LABEL,
        "weakest_input_label": outcome.label.value,
        "rules": list(RULES),
        "attacker": {
            "champion": sheet.champion.id,
            "level": sheet.level,
            "patch": sheet.champion.patch,
            "items": [item.id for item in sheet.items],
            "range": outcome.holder_range,
            "life_steal": {
                "value": float(sheet["life_steal"].total()),
                "label": sheet["life_steal"].label.value,
            },
            "omnivamp": {
                "value": float(sheet["omnivamp"].total()),
                "label": sheet["omnivamp"].label.value,
            },
            "heal_and_shield_power": {
                "value": float(sheet["heal_and_shield_power"].total()),
                "label": sheet["heal_and_shield_power"].label.value,
            },
            "critical_multiplier": None
            if crit_base is None
            else {
                "value": float(crit_base.value),
                "label": crit_base.label.value,
                "source": crit_base.source,
            },
        },
        "target": {
            "description": target.description,
            "kind": target.kind,
            "armor": float(target.armor),
            "magic_resist": float(target.magic_resist),
            "stats": {key: float(value) for key, value in target.stats.items()},
            "shield": float(target.shield),
            "shield_type": target.shield_type,
            "items": [item.id for item in target.items],
            "count": outcome.target_count,
            "label": target.label.value,
        },
        "target_count": outcome.target_count,
        "steps": [
            {
                "index": step.index,
                "step": step.step.text,
                "name": step.name,
                "time": None if step.time is None else float(step.time),
                "targets_hit": step.targets_hit,
                "health_before": float(step.health_before),
                "shield_before": float(step.shield_before),
                "shield_absorbed": float(step.shield_absorbed),
                "shield_after": float(step.shield_after),
                "primary_total": float(step.primary_total),
                "exact_primary_total": str(step.primary_total),
                "secondary_total": float(step.secondary_total),
                "exact_secondary_total": str(step.secondary_total),
                "total": float(step.total),
                "exact_total": str(step.total),
                "health_after": float(step.health_after),
                "label": step.label.value,
                "healing": float(step.healing),
                "exact_healing": str(step.healing),
                "healing_label": step.healing_label.value,
                "healing_notes": list(step.healing_notes),
                "heal_events": [_heal_event_dict(ev) for ev in step.heal_events],
                "shield_events": [_shield_event_dict(ev) for ev in step.shield_events],
                "resource_cost": None
                if step.resource_cost is None
                else {
                    "resource": step.resource_cost.resource,
                    "amount": float(step.resource_cost.amount),
                    "exact_amount": str(step.resource_cost.amount),
                    "label": step.resource_cost.label.value,
                    "source": step.resource_cost.source,
                },
                "resource_before": None
                if step.resource_before is None
                else float(step.resource_before),
                "resource_after": None
                if step.resource_after is None
                else float(step.resource_after),
                "resource_events": [_resource_event_dict(ev) for ev in step.resource_events],
                "parts": [_part_dict(part) for part in step.parts],
            }
            for step in outcome.steps
        ],
        "primary_total": float(outcome.primary_total),
        "exact_primary_total": str(outcome.primary_total),
        "secondary_total": float(outcome.secondary_total),
        "exact_secondary_total": str(outcome.secondary_total),
        "total": float(outcome.total),
        "exact_total": str(outcome.total),
        "remaining_health": float(outcome.remaining_health),
        "shield_absorbed": float(outcome.total_shield_absorbed),
        "remaining_shield": float(outcome.remaining_shield),
        "total_shield_granted": float(outcome.total_shield_granted),
        "grievous_wounds_applied": outcome.grievous_wounds_applied,
        "effective_healing": None
        if outcome.effective_healing is None
        else float(outcome.effective_healing),
        "attacker_health": None
        if outcome.attacker_max_health is None
        else {
            "start": float(outcome.attacker_start_health or 0),
            "remaining": float(outcome.attacker_remaining_health or 0),
            "max": float(outcome.attacker_max_health),
        },
        "resource": None
        if outcome.resource is None
        else {
            "kind": outcome.resource.kind,
            "name": outcome.resource.name,
            "maximum": float(outcome.resource.maximum),
            "start": float(outcome.resource.start),
            "spent": float(outcome.resource.spent),
            "exact_spent": str(outcome.resource.spent),
            "restored": float(outcome.resource.restored),
            "effective_restored": float(outcome.resource.effective_restored),
            "exact_effective_restored": str(outcome.resource.effective_restored),
            "regenerated": float(outcome.resource.regenerated),
            "exact_regenerated": str(outcome.resource.regenerated),
            "remaining": float(outcome.resource.remaining),
            "exact_remaining": str(outcome.resource.remaining),
            "health_cost_spent": float(outcome.resource.health_cost_spent),
            "insufficient_steps": list(outcome.resource.insufficient_steps),
            "uses_casting_pool": outcome.resource.uses_casting_pool,
            "label": outcome.resource.label.value,
            "notes": list(outcome.resource.notes),
        },
        "timeline": None
        if outcome.timeline is None
        else {
            "attack_interval": float(outcome.timeline.attack_interval),
            "label": outcome.timeline.label.value,
            "duration": float(outcome.duration or 0),
            "damage_per_second": None
            if outcome.damage_per_second is None
            else float(outcome.damage_per_second),
        },
        "lethal_step": outcome.lethal_step,
        "healing": float(outcome.healing),
        "exact_healing": str(outcome.healing),
        "healing_label": outcome.healing_label.value,
        "windows": [
            {
                "seconds": float(win.seconds),
                "steps_count": win.steps_count,
                "total": float(win.total),
                "exact_total": str(win.total),
                "primary_total": float(win.primary_total),
                "secondary_total": float(win.secondary_total),
                "damage_per_second": float(win.damage_per_second),
                "healing": float(win.healing),
                "remaining_health": float(win.remaining_health),
                "label": win.label.value,
            }
            for win in (outcome.window(sec) for sec in windows)
        ]
        if (windows and outcome.timeline is not None)
        else [],
        "not_applied": list(outcome.notes),
    }
