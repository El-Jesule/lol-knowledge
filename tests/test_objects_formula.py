"""Tests for the supported and unsupported object formula subset."""

from __future__ import annotations

import pytest

from lol_knowledge.objects import (
    FormulaError,
    classify_formula,
    evaluate_formula,
    formula_issues,
)

STATS = {
    "attack_damage": 100.0,
    "bonus_attack_damage": 40.0,
    "base_attack_damage": 60.0,
    "current_health": 1200.0,
    "max_health": 2500.0,
}


def test_constant_zero_is_a_real_zero() -> None:
    result = evaluate_formula({"op": "constant", "value": 0}, STATS)
    assert result.value == 0.0


def test_add_and_mul_with_stats() -> None:
    formula = {
        "op": "mul",
        "operands": [
            {"op": "stat", "stat": "attack_damage", "scope": "bonus"},
            {"op": "constant", "value": 2},
        ],
    }
    result = evaluate_formula(formula, STATS)
    assert result.value == 80.0
    assert result.dependencies == ("bonus_attack_damage",)

    added = evaluate_formula(
        {
            "op": "add",
            "operands": [
                {"op": "constant", "value": 10},
                {"op": "stat", "stat": "attack_damage", "scope": "base"},
            ],
        },
        STATS,
    )
    assert added.value == 70.0


def test_target_health_scope_resolves_to_current_health() -> None:
    result = evaluate_formula({"op": "stat", "stat": "health", "scope": "current"}, STATS)
    assert result.value == 1200.0
    assert result.dependencies == ("current_health",)


def test_unknown_is_never_zero() -> None:
    with pytest.raises(FormulaError) as captured:
        evaluate_formula(
            {"op": "unknown", "reason": "ratio not published"},
            STATS,
        )
    assert captured.value.code == "unknown_input"
    assert "ratio not published" in str(captured.value)


def test_unsupported_is_never_zero() -> None:
    with pytest.raises(FormulaError) as captured:
        evaluate_formula(
            {"op": "unsupported", "reason": "curve not published", "needed": ["curve"]},
            STATS,
        )
    assert captured.value.code == "unsupported_formula"


def test_missing_stat_is_explicit() -> None:
    with pytest.raises(FormulaError) as captured:
        evaluate_formula(
            {"op": "stat", "stat": "crit_chance", "scope": "total"},
            STATS,
        )
    assert captured.value.code == "missing_stat"


@pytest.mark.parametrize(
    "formula",
    [
        {"op": "constant", "value": None},
        {"op": "constant", "value": True},
        {"op": "add", "operands": []},
        {"op": "mul", "operands": "nope"},
        {"op": "divide", "operands": [{"op": "constant", "value": 1}]},
        {"op": "stat", "stat": "attack_damage", "scope": "current"},
        {"op": "unknown"},
        {"op": "unsupported", "reason": ""},
    ],
)
def test_malformed_formulas_have_issues(formula) -> None:
    assert formula_issues(formula)
    with pytest.raises(FormulaError):
        evaluate_formula(formula, STATS)


def test_depth_limit_is_enforced() -> None:
    formula = {"op": "constant", "value": 1}
    for _ in range(40):
        formula = {"op": "add", "operands": [formula]}
    assert formula_issues(formula)
    with pytest.raises(FormulaError):
        evaluate_formula(formula, STATS)


def test_classification_distinguishes_the_three_states() -> None:
    assert classify_formula({"op": "constant", "value": 1}) == "evaluable"
    assert (
        classify_formula(
            {
                "op": "mul",
                "operands": [
                    {"op": "stat", "stat": "attack_damage", "scope": "total"},
                    {"op": "unknown", "reason": "missing"},
                ],
            }
        )
        == "partially_evaluable"
    )
    assert classify_formula({"op": "unsupported", "reason": "not modelled"}) == "excluded"
