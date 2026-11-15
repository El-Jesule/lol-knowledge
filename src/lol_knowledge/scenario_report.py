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
        f"ability: {outcome.slot} {outcome.name}, rank {outcome.rank}",
    ]
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
        lines.append(f"  total: {format_number(case.total)}")
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
            "label": target.label.value,
        },
        "ability": {"slot": outcome.slot, "name": outcome.name, "rank": outcome.rank},
        "cases": [
            {
                "id": case.id,
                "name": case.name,
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
        "not_modelled": list(outcome.not_modelled),
    }
