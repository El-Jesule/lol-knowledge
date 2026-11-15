"""Text and JSON reports for damage results."""

from __future__ import annotations

from fractions import Fraction
from typing import Any

from .mitigation import DamageResult

LABEL = "Calculado"
RULES_PATH = "lol-knowledge/mechanics/damage-mitigation.md"
ASSUMPTIONS = (
    "No rounding is applied; the rounding of displayed in-game damage is not modelled.",
    "Only resistance mitigation is modelled: damage amplification, damage reduction "
    "effects and shields are out of scope.",
    "Percent penetration acts on total resistance; bonus-only penetration is not modelled.",
)
DISPLAY_DECIMALS = 6


def format_number(value: Fraction) -> str:
    """Render a fraction for people: exact integers, else six decimals."""
    if value.denominator == 1:
        return str(value.numerator)
    text = f"{float(value):.{DISPLAY_DECIMALS}f}".rstrip("0").rstrip(".")
    if text in ("0", "-0"):
        return repr(float(value))
    return text


def _floats(values: tuple[Fraction, ...]) -> list[float]:
    return [float(value) for value in values]


def to_dict(result: DamageResult) -> dict[str, Any]:
    """Return a JSON-ready report with float values and exact final fractions."""
    trace = result.resistance
    modifiers = result.modifiers
    return {
        "label": LABEL,
        "rules": RULES_PATH,
        "assumptions": list(ASSUMPTIONS),
        "input": {
            "damage_type": result.damage_type.value,
            "raw_damage": float(result.raw_damage),
            "resistance": None if trace is None else float(trace.initial),
            "flat_reduction": _floats(modifiers.flat_reduction),
            "percent_reduction": _floats(modifiers.percent_reduction),
            "percent_penetration": _floats(modifiers.percent_penetration),
            "flat_penetration": _floats(modifiers.flat_penetration),
        },
        "resistance": None
        if trace is None
        else {
            "initial": float(trace.initial),
            "after_flat_reduction": float(trace.after_flat_reduction),
            "after_percent_reduction": float(trace.after_percent_reduction),
            "after_percent_penetration": float(trace.after_percent_penetration),
            "effective": float(trace.effective),
        },
        "multiplier": float(result.multiplier),
        "post_mitigation_damage": float(result.damage),
        "exact": {
            "multiplier": str(result.multiplier),
            "post_mitigation_damage": str(result.damage),
        },
    }


def format_text(result: DamageResult) -> str:
    """Return the human-readable report."""
    lines = [
        f"damage type: {result.damage_type.value}",
        f"raw damage: {format_number(result.raw_damage)}",
    ]
    trace = result.resistance
    if trace is None:
        lines.append("resistance: not applicable")
    else:
        lines += [
            f"resistance: {format_number(trace.initial)}",
            f"  after flat reduction: {format_number(trace.after_flat_reduction)}",
            f"  after percent reduction: {format_number(trace.after_percent_reduction)}",
            f"  after percent penetration: {format_number(trace.after_percent_penetration)}",
            f"  after flat penetration: {format_number(trace.effective)}",
        ]
    lines += [
        f"multiplier: {format_number(result.multiplier)}",
        f"post-mitigation damage: {format_number(result.damage)}",
        f"label: {LABEL}",
        f"rules: {RULES_PATH}",
    ]
    return "\n".join(lines)
