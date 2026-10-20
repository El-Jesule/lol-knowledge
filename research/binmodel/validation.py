"""Validation helpers for the user's in-game measurements.

These helpers are not part of the game model. They compare the model against
observed values and report every mismatch instead of adjusting the formula.
"""

from __future__ import annotations

from collections.abc import Mapping
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from .evaluate import EvaluationContext, FormulaError, evaluate
from .model import Ability
from .stats import champion_stats

AD_MEASUREMENTS = (
    (1, 74),
    (2, 77),
    (10, 105),
    (18, 142),
)

PASSIVE_PERCENT_MEASUREMENTS = (
    (1, 1.5),
    (5, 1.8),
    (6, 1.9),
    (10, 2.2),
    (11, 2.3),
    (15, 2.6),
    (16, 2.6),
    (18, 2.8),
)

RUNE_BONUS_AD = 10.8


def round_half_up(value: float, digits: int = 0) -> float:
    """Round half away from zero, matching the displayed-value comparison."""
    quantizer = Decimal(1).scaleb(-digits)
    return float(Decimal(str(value)).quantize(quantizer, rounding=ROUND_HALF_UP))


def validate_ad_growth(
    base_stats: Mapping[str, Any],
    *,
    rune_bonus_ad: float = RUNE_BONUS_AD,
) -> dict[str, Any]:
    """Compare the growth model with the observed AD table."""
    rows = []
    for level, expected in AD_MEASUREMENTS:
        stats = champion_stats(base_stats, level, bonus_attack_damage=rune_bonus_ad)
        displayed = round_half_up(stats["attack_damage"])
        rows.append(
            {
                "level": level,
                "computed": stats["attack_damage"],
                "displayed": displayed,
                "observed": expected,
                "match": displayed == expected,
                "base_attack_damage": stats["base_attack_damage"],
                "bonus_attack_damage": stats["bonus_attack_damage"],
            }
        )
    return {
        "rows": rows,
        "all_match": all(row["match"] for row in rows),
        "rune_bonus_ad": rune_bonus_ad,
        "note": (
            "Two adaptive-force shards give +5.4 AD each (+10.8 total). "
            "The earlier +10 reading paired with base 64 is an artefact of rounding."
        ),
    }


def validate_passive_percent(
    passive: Ability,
    *,
    calculation_name: str = "PercentBonusADCalc",
) -> dict[str, Any]:
    """Compare the interpolation with the observed passive percentages."""
    context = EvaluationContext(abilities={passive.ability_id: passive}, stats={})
    rows = []
    for level, expected in PASSIVE_PERCENT_MEASUREMENTS:
        evaluation = evaluate(
            passive,
            calculation_name,
            context,
            level=level,
            rank=1,
        )
        displayed = round_half_up(evaluation.value * 100.0, 1)
        rows.append(
            {
                "level": level,
                "computed_fraction": evaluation.value,
                "displayed_percent": displayed,
                "observed_percent": expected,
                "match": displayed == expected,
                "complete": evaluation.complete,
            }
        )
    return {
        "rows": rows,
        "all_match": all(row["match"] for row in rows),
        "formula": "start + (end-start)*(level-1)/17",
        "status": "validated against display; internal implementation inferred",
    }


def validate_one_stack(
    base_stats: Mapping[str, Any],
    passive: Ability,
    *,
    level: int = 18,
    rune_bonus_ad: float = RUNE_BONUS_AD,
) -> dict[str, Any]:
    """Test the three candidate bases for the passive's percentage."""
    stats = champion_stats(base_stats, level, bonus_attack_damage=rune_bonus_ad)
    context = EvaluationContext(abilities={passive.ability_id: passive}, stats=stats)
    evaluation = evaluate(passive, "PercentBonusADCalc", context, level=level, rank=1)
    fraction = evaluation.value
    total_before = stats["attack_damage"]
    bases = {
        "base_attack_damage": stats["base_attack_damage"],
        "total_attack_damage": stats["attack_damage"],
        "bonus_attack_damage": stats["bonus_attack_damage"],
    }
    rows = []
    for name, basis in bases.items():
        bonus = fraction * basis
        total_after = total_before + bonus
        rows.append(
            {
                "basis": name,
                "basis_value": basis,
                "bonus_ad": bonus,
                "total_after": total_after,
                "displayed_after": round_half_up(total_after),
                "matches_146": round_half_up(total_after) == 146,
            }
        )
    return {
        "level": level,
        "fraction": fraction,
        "total_before": total_before,
        "displayed_before": round_half_up(total_before),
        "rows": rows,
        "note": (
            "The single observation 142->146 is compatible with total AD and with "
            "display-rounding variants; it does not prove the internal basis."
        ),
    }


def evaluate_all_calculations(
    abilities: Mapping[str, Ability],
    stats: Mapping[str, float],
    *,
    level: int,
    rank: int,
) -> dict[str, Any]:
    """Evaluate every discovered calculation, without champion-specific names."""
    context = EvaluationContext(abilities=abilities, stats=stats)
    result: dict[str, Any] = {}
    for ability in abilities.values():
        for calculation in ability.calculations:
            key = f"{ability.ability_id}.{calculation.name}"
            try:
                evaluation = evaluate(ability, calculation.name, context, level=level, rank=rank)
                result[key] = evaluation.to_dict()
            except FormulaError as exc:
                result[key] = {
                    "error": str(exc),
                    "code": exc.code,
                    "missing": exc.missing,
                }
    return result


def validate_ability_damage(
    abilities: Mapping[str, Ability],
    stats: Mapping[str, float],
    *,
    level: int,
    rank: int,
) -> dict[str, Any]:
    """Evaluate the main damage calculations at one level and rank."""
    context = EvaluationContext(abilities=abilities, stats=stats)
    result: dict[str, Any] = {}
    for ability_id, calculation in (
        ("q", "InitialDamage"),
        ("q", "SecondHitDamage"),
        ("w", "InitialDamage"),
        ("w", "SecondaryDamage"),
        ("e", "BaseDamageCalc"),
        ("e", "BonusDamageCalc"),
        ("r", "DamageEndCalc"),
    ):
        ability = abilities.get(ability_id)
        if ability is None:
            continue
        key = f"{ability_id}.{calculation}"
        try:
            evaluation = evaluate(ability, calculation, context, level=level, rank=rank)
            result[key] = evaluation.to_dict()
        except FormulaError as exc:
            result[key] = {
                "error": str(exc),
                "code": exc.code,
                "missing": exc.missing,
            }
    return result
