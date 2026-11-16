"""Text and JSON reports for a stat sheet and its metrics."""

from __future__ import annotations

from fractions import Fraction
from typing import Any

from ..damage import DamageType, format_number, format_percent
from .metrics import Cooldowns, EffectiveHealth, ability_cooldowns, effective_health
from .registry import Stacking, Unit
from .sheet import StatSheet, StatValue

RESULT_LABEL = "Calculado"
EHP_TYPES = (DamageType.PHYSICAL, DamageType.MAGIC, DamageType.TRUE)


def _num(value: Fraction | None) -> float | None:
    return None if value is None else float(value)


def _stat_dict(value: StatValue) -> dict[str, Any]:
    definition = value.definition
    result: dict[str, Any] = {
        "name": definition.name,
        "status": value.status,
        "stacking": definition.stacking.value,
        "unit": definition.unit.value,
        "rules": definition.rules,
        "cap": _num(definition.cap),
        "label": value.label.value,
        "contributions": [
            {
                "value": float(item.value),
                "scope": item.scope,
                "source": item.source,
                "label": item.label.value,
                "note": item.note,
            }
            for item in value.contributions
        ],
    }
    if value.status == "resolved":
        result["total"] = float(value.total())
        result["exact"] = str(value.total())
        result["capped"] = value.capped
        result["soft_capped"] = value.soft_capped
        result["raw"] = float(value.raw())
        if definition.stacking is Stacking.ADDITIVE:
            result["base"] = float(value.scoped("base"))
            result["bonus"] = float(value.scoped("bonus"))
    elif value.status == "blocked":
        result["reason"] = value.blocked
    else:
        result["reason"] = definition.pending
    return result


def _ehp_dict(item: EffectiveHealth) -> dict[str, Any]:
    return {
        "value": _num(item.value),
        "exact": None if item.value is None else str(item.value),
        "label": item.label.value,
        "blocked": item.blocked,
        "rules": item.rules,
    }


def _cooldowns_dict(item: Cooldowns) -> dict[str, Any]:
    return {
        "ability_haste": _num(item.haste),
        "factor": _num(item.factor),
        "label": item.label.value,
        "blocked": item.blocked,
        "rules": item.rules,
        "spells": [
            {
                "slot": spell.slot,
                "id": spell.spell_id,
                "name": spell.name,
                "base": [float(value) for value in spell.base],
                "effective": [float(value) for value in spell.effective],
            }
            for spell in item.spells
        ],
    }


def to_dict(sheet: StatSheet) -> dict[str, Any]:
    champion = sheet.champion
    return {
        "label": RESULT_LABEL,
        "champion": {"id": champion.id, "name": champion.name, "resource": champion.resource},
        "patch": champion.patch,
        "level": sheet.level,
        "items": [{"id": item.id, "name": item.name} for item in sheet.items],
        "assumptions": {key: float(value) for key, value in sheet.assumptions.items()},
        "notes": list(sheet.notes),
        "stats": {stat_id: _stat_dict(value) for stat_id, value in sheet.values.items()},
        "metrics": {
            "effective_health": {
                kind.value: _ehp_dict(effective_health(sheet, kind)) for kind in EHP_TYPES
            },
            "cooldowns": _cooldowns_dict(ability_cooldowns(sheet)),
        },
    }


def _shown(value: Fraction, unit: Unit) -> str:
    """Fractions are shown as percentages in text; JSON keeps the fraction."""
    return format_percent(value) if unit is Unit.FRACTION else format_number(value)


def _stat_line(stat_id: str, value: StatValue) -> str:
    if value.status != "resolved":
        reason = value.blocked if value.status == "blocked" else value.definition.pending
        return f"  {stat_id}: {value.status}: {reason}"
    unit = value.definition.unit
    total = _shown(value.total(), unit)
    detail = ""
    if value.definition.stacking is Stacking.ADDITIVE and value.scoped("bonus"):
        detail = (
            f" (base {_shown(value.scoped('base'), unit)}"
            f" + bonus {_shown(value.scoped('bonus'), unit)})"
        )
    if value.capped:
        detail += f" (capped at {_shown(value.definition.cap, unit)})"
    if value.soft_capped:
        detail += f" (soft cap from {_shown(value.raw(), unit)})"
    line = f"  {stat_id}: {total}{detail} [{value.label.value}]"
    notes = [item.note for item in value.contributions if "client" in item.note]
    if notes:
        line += f" ({notes[0].split('; ', 1)[1]})"
    return line


def format_text(sheet: StatSheet) -> str:
    champion = sheet.champion
    items = ", ".join(f"{item.id} {item.name}" for item in sheet.items) or "none"
    assumptions = (
        ", ".join(f"{key}={format_number(value)}" for key, value in sheet.assumptions.items())
        or "none"
    )
    lines = [
        f"champion: {champion.name} ({champion.id}), patch {champion.patch}, level {sheet.level}",
        f"resource: {champion.resource or 'none'}",
        f"items: {items}",
        f"assumptions: {assumptions}",
    ]
    lines += [f"note: {note}" for note in sheet.notes]
    resolved = [(k, v) for k, v in sheet.values.items() if v.status != "pending"]
    pending = [(k, v) for k, v in sheet.values.items() if v.status == "pending"]
    lines.append("stats:")
    lines += [_stat_line(stat_id, value) for stat_id, value in resolved]
    lines.append("not modelled yet:" if pending else "not modelled yet: none")
    lines += [f"  {stat_id}: {value.definition.pending}" for stat_id, value in pending]
    lines.append("effective health:")
    for kind in EHP_TYPES:
        item = effective_health(sheet, kind)
        if item.value is None:
            lines.append(f"  {kind.value}: blocked: {item.blocked}")
        else:
            lines.append(f"  {kind.value}: {format_number(item.value)} [{item.label.value}]")
    cooldowns = ability_cooldowns(sheet)
    if cooldowns.blocked:
        lines.append(f"cooldowns: blocked: {cooldowns.blocked}")
    else:
        lines.append(
            f"cooldowns (ability haste {format_number(cooldowns.haste)}): [{cooldowns.label.value}]"
        )
        for spell in cooldowns.spells:
            effective = "/".join(format_number(value) for value in spell.effective)
            lines.append(f"  {spell.slot} {spell.name}: {effective}")
    lines.append(f"label: {RESULT_LABEL}")
    return "\n".join(lines)
