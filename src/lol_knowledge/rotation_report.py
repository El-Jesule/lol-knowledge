"""Text and JSON reports for rotations."""

from __future__ import annotations

from fractions import Fraction
from typing import Any

from .damage import format_number
from .rotation import RULES, CritBase, Part, RotationOutcome
from .scenario import Target
from .stats import StatSheet

RESULT_LABEL = "Calculado"


def _percent_list(entries: tuple[tuple[str, Fraction], ...]) -> str:
    return ", ".join(f"{name} {format_number(percent)}%" for name, percent in entries)


def _part_line(part: Part) -> list[str]:
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
    for step in outcome.steps:
        lines.append(
            f"step {step.index} {step.step.text} ({step.name}): "
            f"health {format_number(step.health_before)}"
        )
        for part in step.parts:
            lines += _part_line(part)
        lines.append(
            f"  step total {format_number(step.total)} -> health {format_number(step.health_after)}"
        )
    lines.append(f"total: {format_number(outcome.total)}")
    lines.append(f"remaining health: {format_number(outcome.remaining_health)}")
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
                "health_before": float(step.health_before),
                "total": float(step.total),
                "exact_total": str(step.total),
                "health_after": float(step.health_after),
                "label": step.label.value,
                "parts": [_part_dict(part) for part in step.parts],
            }
            for step in outcome.steps
        ],
        "total": float(outcome.total),
        "exact_total": str(outcome.total),
        "remaining_health": float(outcome.remaining_health),
        "lethal_step": outcome.lethal_step,
        "not_applied": list(outcome.notes),
    }
