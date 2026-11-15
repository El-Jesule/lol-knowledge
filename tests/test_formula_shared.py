"""Shared formula evaluator: kit-only operations, exactness and item compatibility."""

from __future__ import annotations

from fractions import Fraction as F

import pytest

from lol_knowledge.formula import (
    ABILITY_OPS,
    OBJECT_OPS,
    FormulaError,
    classify_formula,
    evaluate_formula,
    formula_issues,
)
from lol_knowledge.objects import evaluate_formula as object_evaluate

RANKED = {"op": "by_rank", "values": [250, 400, 550]}


def ability(formula, stats=None, **kwargs):
    return evaluate_formula(formula, stats or {}, ops=ABILITY_OPS, **kwargs)


def test_by_rank_picks_the_rank():
    assert ability(RANKED, rank=1).exact == 250
    assert ability(RANKED, rank=3).exact == 550
    assert ability(RANKED, rank=2).dependencies == ("rank",)


@pytest.mark.parametrize(
    ("rank", "code"),
    [
        (None, "missing_rank"),
        (0, "rank_out_of_range"),
        (4, "rank_out_of_range"),
        (True, "rank_out_of_range"),
    ],
)
def test_by_rank_needs_a_valid_rank(rank, code):
    with pytest.raises(FormulaError) as exc:
        ability(RANKED, rank=rank)
    assert exc.value.code == code


def test_by_level_picks_the_level():
    formula = {"op": "by_level", "values": [1, 2, 3]}
    assert ability(formula, level=2).exact == 2
    with pytest.raises(FormulaError, match="level"):
        ability(formula)


def test_input_must_be_given():
    formula = {"op": "input", "name": "passive_stacks"}
    assert ability(formula, inputs={"passive_stacks": 12}).exact == 12
    assert ability(formula, inputs={"passive_stacks": 12}).dependencies == ("input:passive_stacks",)
    with pytest.raises(FormulaError) as exc:
        ability(formula)
    assert exc.value.code == "missing_input"


def test_items_cannot_use_kit_operations():
    assert formula_issues(RANKED) == ["unsupported formula op 'by_rank'"]
    assert formula_issues(RANKED, ops=ABILITY_OPS) == []
    with pytest.raises(FormulaError, match="by_rank"):
        object_evaluate(
            RANKED,
            {},
        )
    assert "by_rank" not in OBJECT_OPS


@pytest.mark.parametrize(
    "formula",
    [
        {"op": "by_rank", "values": []},
        {"op": "by_rank", "values": [1, "x"]},
        {"op": "by_rank", "values": [1, True]},
        {"op": "by_level", "values": "123"},
        {"op": "input", "name": ""},
        {"op": "input", "name": "x", "extra": 1},
    ],
)
def test_malformed_kit_operations(formula):
    assert formula_issues(formula, ops=ABILITY_OPS)


def test_arithmetic_is_exact():
    formula = {
        "op": "add",
        "operands": [{"op": "constant", "value": 0.1}, {"op": "constant", "value": 0.2}],
    }
    result = evaluate_formula(formula, {})
    assert result.exact == F(3, 10)
    assert result.value == 0.3


def test_target_stats_are_separate_when_given():
    formula = {
        "op": "add",
        "operands": [
            {"op": "stat", "stat": "health", "scope": "max"},
            {"op": "stat", "stat": "health", "scope": "max", "subject": "target"},
        ],
    }
    result = evaluate_formula(formula, {"max_health": 1000}, target_stats={"max_health": 3000})
    assert result.exact == 4000
    assert result.dependencies == ("max_health", "target:max_health")
    with pytest.raises(FormulaError, match="target:max_health"):
        evaluate_formula(formula, {"max_health": 1000}, target_stats={})


def test_without_target_stats_items_read_one_mapping():
    formula = {"op": "stat", "stat": "health", "scope": "bonus", "subject": "target"}
    assert evaluate_formula(formula, {"bonus_health": 500}).exact == 500


def test_kit_operations_are_evaluable_leaves():
    formula = {"op": "add", "operands": [RANKED, {"op": "input", "name": "x"}]}
    assert classify_formula(formula) == "evaluable"
