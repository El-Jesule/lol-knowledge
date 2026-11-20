"""Text and JSON reports for rotations."""

from __future__ import annotations

from fractions import Fraction
from typing import Any

from .damage import format_number, format_percent
from .rotation import RULES, CritBase, Healing, Part, RotationOutcome
from .scenario import Target
from .stats import StatSheet

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
    lines.append(f"      {mitigation}{tail} = {format_number(part.damage)}")
    lines += [f"      note: {note}" for note in part.notes]
    if heals:
        lines += _heal_lines(part.healing)
    return lines


def format_text(
    outcome: RotationOutcome, sheet: StatSheet, target: Target, crit_base: CritBase | None
) -> str:
    items = ", ".join(f"{item.id} {item.name}" for item in sheet.items) or "none"
    target_items = ", ".join(item.id for item in target.items)
    lines = [
        f"attacker: {sheet.champion.name} level {sheet.level}, patch {sheet.champion.patch}, "
        f"range {outcome.holder_range or 'not given'}",
        f"items: {items}",
        f"target: {target.description}"
        + (f", effects from items {target_items}" if target_items else ""),
        f"target health: {format_number(outcome.start_health)} / "
        f"{format_number(outcome.max_health)}",
    ]
    if crit_base is not None and any(step.step.crit for step in outcome.steps):
        lines.append(
            f"critical multiplier: {format_number(crit_base.value)} [{crit_base.label.value}] "
            f"({crit_base.source})"
        )
    heals = bool(sheet["life_steal"].total() or sheet["omnivamp"].total() or outcome.healing)
    if heals:
        lines.append(
            f"life steal: {_percent(sheet['life_steal'].total())} "
            f"[{sheet['life_steal'].label.value}], omnivamp: "
            f"{_percent(sheet['omnivamp'].total())} [{sheet['omnivamp'].label.value}]"
        )
    for step in outcome.steps:
        at = "" if step.time is None else f" at {format_number(step.time)} s"
        lines.append(
            f"step {step.index} {step.step.text} ({step.name}){at}: "
            f"health {format_number(step.health_before)}"
        )
        for part in step.parts:
            lines += _part_line(part, heals)
        lines.append(
            f"  step total {format_number(step.total)} -> health {format_number(step.health_after)}"
        )
        if heals:
            lines.append(f"  step heal {format_number(step.healing)} [{step.healing_label.value}]")
            lines += [f"  heal note: {note}" for note in step.healing_notes]
    lines.append(f"total: {format_number(outcome.total)}")
    if heals:
        lines.append(
            f"total heal: {format_number(outcome.healing)} [{outcome.healing_label.value}]"
        )
    lines.append(f"remaining health: {format_number(outcome.remaining_health)}")
    if outcome.timeline is not None:
        lines.append(
            f"timeline: attack every {format_number(outcome.timeline.attack_interval)} s "
            f"[{outcome.timeline.label.value}]; duration {format_number(outcome.duration)} s"
        )
        if outcome.damage_per_second is not None:
            lines.append(f"damage per second: {format_number(outcome.damage_per_second)}")
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
        "damage": float(part.damage),
        "exact_damage": str(part.damage),
        "notes": list(part.notes),
        "healing": _healing_dict(part.healing),
    }


def to_dict(
    outcome: RotationOutcome, sheet: StatSheet, target: Target, crit_base: CritBase | None
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
            "items": [item.id for item in target.items],
            "label": target.label.value,
        },
        "steps": [
            {
                "index": step.index,
                "step": step.step.text,
                "name": step.name,
                "time": None if step.time is None else float(step.time),
                "health_before": float(step.health_before),
                "total": float(step.total),
                "exact_total": str(step.total),
                "health_after": float(step.health_after),
                "label": step.label.value,
                "healing": float(step.healing),
                "exact_healing": str(step.healing),
                "healing_label": step.healing_label.value,
                "healing_notes": list(step.healing_notes),
                "parts": [_part_dict(part) for part in step.parts],
            }
            for step in outcome.steps
        ],
        "total": float(outcome.total),
        "exact_total": str(outcome.total),
        "remaining_health": float(outcome.remaining_health),
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
        "not_applied": list(outcome.notes),
    }
