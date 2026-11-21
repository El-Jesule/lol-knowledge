"""Text and JSON reports for ability scenarios."""

from __future__ import annotations

from fractions import Fraction
from typing import Any

from .damage import format_number
from .scenario import AbilityOutcome, Target
from .stats import StatSheet

RESULT_LABEL = "Calculado"
RULES = (
    "lol-knowledge/mechanics/damage-mitigation.md",
    "lol-knowledge/mechanics/stat-growth.md",
)


def _pct(values: tuple[Fraction, ...]) -> str:
    return ", ".join(f"{format_number(value * 100)}%" for value in values) or "none"


def _flat(values: tuple[Fraction, ...]) -> str:
    return format_number(sum(values, start=Fraction(0)))


def format_text(outcome: AbilityOutcome, sheet: StatSheet, target: Target) -> str:
    items = ", ".join(f"{item.id} {item.name}" for item in sheet.items) or "none"
    lines = [
        f"attacker: {sheet.champion.name} level {sheet.level}, patch {sheet.champion.patch}",
        f"items: {items}",
        f"target: {target.description}",
    ]
    if outcome.target_count > 1:
        lines.append(f"targets: {outcome.target_count}")
    lines.append(f"ability: {outcome.slot} {outcome.name}, rank {outcome.rank}")
    for case in outcome.cases:
        lines.append(f"case {case.id} ({case.name}):")
        for index, item in enumerate(case.parts, start=1):
            part, result = item.part, item.mitigation
            lines.append(
                f"  part {index} {part.damage_type.value}: raw {format_number(part.raw)} "
                f"[{part.label.value}] ({', '.join(part.dependencies) or 'constant'})"
            )
            trace = result.resistance
            if trace is None:
                lines.append(f"    true damage -> {format_number(result.damage)}")
                continue
            modifiers = result.modifiers
            lines.append(
                f"    resistance {format_number(trace.initial)} -> "
                f"{format_number(trace.effective)} "
                f"(percent pen {_pct(modifiers.percent_penetration)}, "
                f"flat pen {_flat(modifiers.flat_penetration)}); "
                f"multiplier {format_number(result.multiplier)} -> {format_number(result.damage)}"
            )
        if case.targets_hit > 1:
            if case.secondary_damage_ratio == 1:
                lines.append(
                    f"  primary target: {format_number(case.primary_total)}, "
                    f"targets hit: {case.targets_hit}"
                )
            else:
                lines.append(
                    f"  primary target: {format_number(case.primary_total)}, "
                    f"secondary ({case.targets_hit - 1}x "
                    f"{format_number(case.secondary_damage_ratio * 100)}%): "
                    f"{format_number(case.secondary_total)}, targets hit: {case.targets_hit}"
                )
        lines.append(f"  total: {format_number(case.total)}")
    for note in outcome.notes:
        lines.append(f"note: {note}")
    for note in outcome.not_modelled:
        lines.append(f"not modelled: {note}")
    lines.append(f"label: {RESULT_LABEL} (weakest input: {outcome.label.value})")
    return "\n".join(lines)


def to_dict(outcome: AbilityOutcome, sheet: StatSheet, target: Target) -> dict[str, Any]:
    return {
        "label": RESULT_LABEL,
        "weakest_input_label": outcome.label.value,
        "rules": list(RULES),
        "attacker": {
            "champion": sheet.champion.id,
            "level": sheet.level,
            "patch": sheet.champion.patch,
            "items": [item.id for item in sheet.items],
        },
        "target": {
            "description": target.description,
            "armor": float(target.armor),
            "magic_resist": float(target.magic_resist),
            "stats": {key: float(value) for key, value in target.stats.items()},
            "count": outcome.target_count,
            "label": target.label.value,
        },
        "target_count": outcome.target_count,
        "ability": {"slot": outcome.slot, "name": outcome.name, "rank": outcome.rank},
        "cases": [
            {
                "id": case.id,
                "name": case.name,
                "aoe": case.aoe,
                "max_targets": case.max_targets,
                "targets_hit": case.targets_hit,
                "secondary_damage_ratio": float(case.secondary_damage_ratio),
                "primary_total": float(case.primary_total),
                "exact_primary_total": str(case.primary_total),
                "secondary_total": float(case.secondary_total),
                "exact_secondary_total": str(case.secondary_total),
                "total": float(case.total),
                "exact_total": str(case.total),
                "parts": [
                    {
                        "damage_type": item.part.damage_type.value,
                        "raw": float(item.part.raw),
                        "label": item.part.label.value,
                        "dependencies": list(item.part.dependencies),
                        "source": item.part.source,
                        "resistance": None
                        if item.mitigation.resistance is None
                        else {
                            "initial": float(item.mitigation.resistance.initial),
                            "effective": float(item.mitigation.resistance.effective),
                        },
                        "percent_penetration": [
                            float(value) for value in item.mitigation.modifiers.percent_penetration
                        ],
                        "flat_penetration": [
                            float(value) for value in item.mitigation.modifiers.flat_penetration
                        ],
                        "multiplier": float(item.mitigation.multiplier),
                        "damage": float(item.mitigation.damage),
                    }
                    for item in case.parts
                ],
            }
            for case in outcome.cases
        ],
        "notes": list(outcome.notes),
        "not_modelled": list(outcome.not_modelled),
    }
