"""Text and JSON reports for reverse defense / survival simulations (MEC-09)."""

from __future__ import annotations

from typing import Any

from .damage import format_number, format_percent
from .defense import DEFENSE_RULES, DefenseOutcome
from .stats import StatSheet

RESULT_LABEL = "Calculado"


def format_text(outcome: DefenseOutcome, sheet: StatSheet) -> str:
    items = ", ".join(f"{item.id} {item.name}" for item in sheet.items) or "none"
    lines = [
        f"defender: {outcome.defender_name} level {outcome.defender_level}, patch {outcome.patch}",
        f"items: {items}",
        f"enemy: {outcome.enemy_description}",
        f"defender health: {format_number(outcome.start_health)} / "
        f"{format_number(outcome.max_health)}",
        f"resistances: armor {format_number(sheet['armor'].total())}, "
        f"magic resist {format_number(sheet['magic_resist'].total())}",
    ]
    hsp = sheet["heal_and_shield_power"].total()
    if hsp:
        lines.append(f"heal & shield power: {format_percent(hsp)}")
    if outcome.start_shield > 0:
        lines.append(
            f"initial shield: {format_number(outcome.start_shield)} ({outcome.shield_type})"
        )
    for step in outcome.steps:
        at = "" if step.time is None else f" at {format_number(step.time)} s"
        lines.append(
            f"step {step.index} ({step.source}){at}: "
            f"health {format_number(step.health_before)}, "
            f"shield {format_number(step.shield_before)}"
        )
        for sh in step.shields_granted:
            lines.append(
                f"  shield granted: +{format_number(sh.amount)} ({sh.shield_type}) "
                f"[{sh.label.value}] ({sh.source})"
            )
            lines += [f"    shield note: {note}" for note in sh.notes]
        if step.incoming > 0:
            flat_str = (
                f", flat -{format_number(step.flat_reduced)} "
                f"-> {format_number(step.damage_after_flat)}"
                if step.flat_reduced > 0
                else ""
            )
            abs_str = (
                f", shield absorbed {format_number(step.shield_absorbed)}"
                if step.shield_absorbed > 0
                else ""
            )
            lines.append(
                f"  incoming {format_number(step.incoming)}{flat_str}{abs_str}, "
                f"health damage {format_number(step.health_damage)} -> "
                f"health {format_number(step.health_after)}, "
                f"shield {format_number(step.shield_after)}"
            )
        for hl in step.heals:
            lines.append(f"  heal: +{format_number(hl.amount)} [{hl.label.value}] ({hl.source})")
            lines += [f"    heal note: {note}" for note in hl.notes]
        if step.reactive_damage > 0:
            lines.append(f"  reactive damage: {format_number(step.reactive_damage)} raw magic")
        lines += [f"  note: {note}" for note in step.notes]
    lines.append(f"total damage taken: {format_number(outcome.total_damage_taken)}")
    if outcome.total_flat_reduced > 0:
        lines.append(f"total flat reduced: {format_number(outcome.total_flat_reduced)}")
    if outcome.total_shield_granted > 0 or outcome.total_shield_absorbed > 0:
        lines.append(
            f"shields: granted {format_number(outcome.total_shield_granted)}, "
            f"absorbed {format_number(outcome.total_shield_absorbed)}, "
            f"remaining {format_number(outcome.remaining_shield)}"
        )
    if outcome.total_healing > 0:
        lines.append(f"total defensive healing: {format_number(outcome.total_healing)}")
    if outcome.total_reactive_damage > 0:
        lines.append(
            f"total reactive damage: {format_number(outcome.total_reactive_damage)} raw magic"
        )
    lines.append(f"remaining health: {format_number(outcome.remaining_health)}")
    lines.append(f"survived: {'yes' if outcome.survived else 'no'}")
    if outcome.lethal_step is not None:
        ttd = (
            ""
            if outcome.time_to_die is None
            else f" (time to die: {format_number(outcome.time_to_die)} s)"
        )
        lines.append(f"lethal at step {outcome.lethal_step}{ttd}")
    if outcome.damage_taken_per_second is not None:
        lines.append(f"damage taken per second: {format_number(outcome.damage_taken_per_second)}")
    for note in outcome.notes:
        lines.append(f"note: {note}")
    lines.append(f"label: {RESULT_LABEL} (weakest input: {outcome.label.value})")
    return "\n".join(lines)


def to_dict(outcome: DefenseOutcome, sheet: StatSheet) -> dict[str, Any]:
    return {
        "label": RESULT_LABEL,
        "weakest_input_label": outcome.label.value,
        "rules": list(DEFENSE_RULES),
        "defender": {
            "champion": sheet.champion.id,
            "name": outcome.defender_name,
            "level": outcome.defender_level,
            "patch": outcome.patch,
            "items": [item.id for item in sheet.items],
            "armor": float(sheet["armor"].total()),
            "magic_resist": float(sheet["magic_resist"].total()),
            "max_health": float(outcome.max_health),
            "start_health": float(outcome.start_health),
            "start_shield": float(outcome.start_shield),
            "shield_type": outcome.shield_type,
            "heal_and_shield_power": float(sheet["heal_and_shield_power"].total()),
        },
        "enemy": outcome.enemy_description,
        "steps": [
            {
                "index": s.index,
                "source": s.source,
                "kind": s.kind,
                "damage_type": None if s.damage_type is None else s.damage_type.value,
                "time": None if s.time is None else float(s.time),
                "incoming": float(s.incoming),
                "flat_reduced": float(s.flat_reduced),
                "damage_after_flat": float(s.damage_after_flat),
                "shield_absorbed": float(s.shield_absorbed),
                "health_damage": float(s.health_damage),
                "health_before": float(s.health_before),
                "health_after": float(s.health_after),
                "shield_before": float(s.shield_before),
                "shield_after": float(s.shield_after),
                "shields_granted": [
                    {
                        "source": sh.source,
                        "amount": float(sh.amount),
                        "exact_amount": str(sh.amount),
                        "label": sh.label.value,
                        "notes": list(sh.notes),
                    }
                    for sh in s.shields_granted
                ],
                "heals": [
                    {
                        "source": hl.source,
                        "amount": float(hl.amount),
                        "exact_amount": str(hl.amount),
                        "label": hl.label.value,
                        "notes": list(hl.notes),
                    }
                    for hl in s.heals
                ],
                "reactive_damage": float(s.reactive_damage),
                "label": s.label.value,
                "notes": list(s.notes),
            }
            for s in outcome.steps
        ],
        "total_incoming": float(outcome.total_incoming),
        "total_flat_reduced": float(outcome.total_flat_reduced),
        "total_damage_taken": float(outcome.total_damage_taken),
        "total_shield_granted": float(outcome.total_shield_granted),
        "total_shield_absorbed": float(outcome.total_shield_absorbed),
        "total_healing": float(outcome.total_healing),
        "total_reactive_damage": float(outcome.total_reactive_damage),
        "remaining_health": float(outcome.remaining_health),
        "remaining_shield": float(outcome.remaining_shield),
        "survived": outcome.survived,
        "lethal_step": outcome.lethal_step,
        "time_to_die": None if outcome.time_to_die is None else float(outcome.time_to_die),
        "duration": None if outcome.duration is None else float(outcome.duration),
        "damage_taken_per_second": None
        if outcome.damage_taken_per_second is None
        else float(outcome.damage_taken_per_second),
        "notes": list(outcome.notes),
    }
