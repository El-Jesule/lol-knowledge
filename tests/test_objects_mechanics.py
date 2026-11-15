"""Independent checks for the mechanics added in phase 6.

Expected values are hand-computed from the cited formulas; they do not reuse
the production formula trees.
"""

from __future__ import annotations

import pytest

from lol_knowledge.objects import FormulaError, classify_formula, evaluate_formula

LDR_CURVE = {
    "op": "min",
    "operands": [
        {"op": "percent_of", "percent": 1, "stat": "health", "scope": "bonus", "subject": "target"},
        {"op": "constant", "value": 15},
    ],
}

BOTRK_DAMAGE = {
    "op": "by_holder_range",
    "melee": {"op": "percent_of", "percent": 9, "stat": "health", "scope": "current"},
    "ranged": {"op": "percent_of", "percent": 6, "stat": "health", "scope": "current"},
}

THORNMAIL_DAMAGE = {
    "op": "add",
    "operands": [
        {"op": "constant", "value": 20},
        {"op": "percent_of", "percent": 10, "stat": "armor", "scope": "bonus"},
    ],
}


@pytest.mark.parametrize(
    ("bonus_health", "expected"),
    [(0, 0.0), (500, 5.0), (750, 7.5), (1000, 10.0), (1499, 14.99), (1500, 15.0)],
)
def test_lord_dominik_linear_curve(bonus_health: float, expected: float) -> None:
    result = evaluate_formula(LDR_CURVE, {"bonus_health": bonus_health})
    assert result.value == pytest.approx(expected)
    assert result.dependencies == ("bonus_health",)


def test_lord_dominik_curve_is_capped_above_1500() -> None:
    assert evaluate_formula(LDR_CURVE, {"bonus_health": 5000}).value == 15.0


@pytest.mark.parametrize(
    ("holder_range", "expected"),
    [("melee", 90.0), ("ranged", 60.0)],
)
def test_botrk_damage_by_holder_range(holder_range: str, expected: float) -> None:
    result = evaluate_formula(
        BOTRK_DAMAGE,
        {"current_health": 1000.0},
        holder_range=holder_range,
    )
    assert result.value == pytest.approx(expected)
    assert result.dependencies == ("holder_range", "current_health")


def test_botrk_does_not_default_a_missing_range() -> None:
    with pytest.raises(FormulaError) as error:
        evaluate_formula(BOTRK_DAMAGE, {"current_health": 1000.0})
    assert error.value.code == "missing_holder_range"

    with pytest.raises(FormulaError) as error:
        evaluate_formula(BOTRK_DAMAGE, {"current_health": 1000.0}, holder_range="siege")
    assert error.value.code == "missing_holder_range"


def test_botrk_zero_current_health_is_a_real_zero() -> None:
    assert (
        evaluate_formula(BOTRK_DAMAGE, {"current_health": 0.0}, holder_range="melee").value == 0.0
    )


@pytest.mark.parametrize(
    ("bonus_armor", "expected"),
    [(0, 20.0), (50, 25.0), (100, 30.0)],
)
def test_thornmail_reflect_uses_bonus_armor(bonus_armor: float, expected: float) -> None:
    result = evaluate_formula(THORNMAIL_DAMAGE, {"bonus_armor": bonus_armor})
    assert result.value == pytest.approx(expected)
    assert result.dependencies == ("bonus_armor",)


def test_missing_bonus_armor_is_not_zero() -> None:
    with pytest.raises(FormulaError) as error:
        evaluate_formula(THORNMAIL_DAMAGE, {})
    assert error.value.code == "missing_stat"


def test_percent_of_needs_a_finite_percent() -> None:
    formula = {"op": "percent_of", "percent": "ten", "stat": "armor", "scope": "bonus"}
    with pytest.raises(FormulaError) as error:
        evaluate_formula(formula, {"bonus_armor": 10.0})
    assert error.value.code == "malformed_formula"


def test_min_needs_operands() -> None:
    with pytest.raises(FormulaError) as error:
        evaluate_formula({"op": "min", "operands": []}, {})
    assert error.value.code == "malformed_formula"


def test_holder_range_classification_keeps_unknowns_visible() -> None:
    partial = {
        "op": "by_holder_range",
        "melee": {"op": "constant", "value": 9},
        "ranged": {"op": "unknown", "reason": "not published"},
    }
    assert classify_formula(partial) == "partially_evaluable"

    excluded = {
        "op": "by_holder_range",
        "melee": {"op": "constant", "value": 9},
        "ranged": {"op": "unsupported", "reason": "not modelled", "needed": ["range"]},
    }
    assert classify_formula(excluded) == "excluded"


def test_evaluation_is_deterministic() -> None:
    stats = {"bonus_health": 1200.0}
    first = evaluate_formula(LDR_CURVE, stats)
    second = evaluate_formula(LDR_CURVE, stats)
    assert first == second
