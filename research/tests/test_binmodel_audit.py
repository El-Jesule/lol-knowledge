"""Regression tests for the extractor audit (phase 5)."""

from __future__ import annotations

import pytest
from binmodel.evaluate import EvaluationContext, FormulaError, evaluate
from binmodel.extract import extract_champion
from binmodel.model import Ability, Calculation
from binmodel.registry import Registry
from binmodel.traverse import TraversalContext, parse_calculation, parse_part


def _ability(*calculations: Calculation, level_count: int = 1) -> Ability:
    return Ability(
        ability_id="test",
        slot="Q",
        path="Test",
        name="Test",
        root_spell="Test",
        level_count=level_count,
        source_level_count="synthetic",
        calculations=list(calculations),
    )


def _context(ability: Ability, stats: dict[str, float] | None = None) -> EvaluationContext:
    return EvaluationContext(abilities={"test": ability}, stats=stats or {})


def _calculation(name: str, tree: dict) -> Calculation:
    return Calculation(name=name, tree=tree, source_path="Test")


def _traversal_context(**kwargs) -> TraversalContext:
    return TraversalContext(
        document=kwargs.pop("document", {}),
        registry=Registry(),
        source_sha256=kwargs.pop("source_sha256", "sha256:test"),
        content_version=kwargs.pop("content_version", "16.20.test"),
        spell_path="Test",
        **kwargs,
    )


def test_missing_breakpoint_fields_are_not_zero():
    ability = _ability(
        _calculation(
            "Breakpoints",
            {
                "kind": "by_char_level_breakpoints",
                "level1_value": None,
                "initial_bonus_per_level": 0.0,
                "breakpoints": [],
            },
        )
    )
    with pytest.raises(FormulaError) as captured:
        evaluate(ability, "Breakpoints", _context(ability), level=1, rank=1)
    assert captured.value.code == "missing_breakpoint_field"


def test_missing_breakpoint_bonus_is_not_zero():
    ability = _ability(
        _calculation(
            "Breakpoints",
            {
                "kind": "by_char_level_breakpoints",
                "level1_value": 300.0,
                "initial_bonus_per_level": 0.0,
                "breakpoints": [
                    {
                        "level": 6,
                        "additional_bonus_at_this_level": None,
                        "bonus_per_level_at_and_after": 0.0,
                    }
                ],
            },
        )
    )
    with pytest.raises(FormulaError) as captured:
        evaluate(ability, "Breakpoints", _context(ability), level=6, rank=1)
    assert captured.value.code == "missing_breakpoint_field"


def test_number_node_without_value_is_malformed():
    ability = _ability(
        _calculation("Damage", {"kind": "game_calculation", "parts": [{"kind": "number"}]})
    )
    with pytest.raises(FormulaError) as captured:
        evaluate(ability, "Damage", _context(ability), level=1, rank=1)
    assert captured.value.code == "malformed_number"


def test_interpolation_without_bounds_is_malformed():
    ability = _ability(
        _calculation(
            "Damage",
            {
                "kind": "by_char_level_interpolation",
                "start_value": 1.0,
                "end_value": None,
                "scale_past_default_max_level": True,
            },
        )
    )
    with pytest.raises(FormulaError) as captured:
        evaluate(ability, "Damage", _context(ability), level=1, rank=1)
    assert captured.value.code == "malformed_interpolation"


def test_unsupported_stat_is_a_formula_error():
    ability = _ability(
        _calculation(
            "Damage",
            {
                "kind": "game_calculation",
                "parts": [
                    {
                        "kind": "stat_scaled",
                        "stat": {
                            "resolved": True,
                            "stat": "critical_strike_chance",
                            "formula": "bonus",
                        },
                        "factor": {"kind": "number", "value": 1.0},
                    }
                ],
            },
        )
    )
    with pytest.raises(FormulaError) as captured:
        evaluate(ability, "Damage", _context(ability), level=1, rank=1)
    assert captured.value.code == "unsupported_stat"


def test_game_calculation_without_parts_is_not_zero():
    ability = _ability(_calculation("Damage", {"kind": "game_calculation", "parts": None}))
    with pytest.raises(FormulaError) as captured:
        evaluate(ability, "Damage", _context(ability), level=1, rank=1)
    assert captured.value.code == "missing_formula_parts"


def test_sum_without_operands_is_not_zero():
    ability = _ability(_calculation("Damage", {"kind": "sum", "operands": None}))
    with pytest.raises(FormulaError) as captured:
        evaluate(ability, "Damage", _context(ability), level=1, rank=1)
    assert captured.value.code == "missing_formula_operands"


def test_dependencies_do_not_leak_between_evaluations():
    scaled = {
        "kind": "stat_scaled",
        "stat": {"resolved": True, "stat": "attack_damage", "formula": "total"},
        "factor": {"kind": "number", "value": 2.0},
    }
    ability = _ability(
        _calculation(
            "Scaled", {"kind": "product", "operands": [{"kind": "number", "value": 1.0}, scaled]}
        ),
        _calculation("Plain", {"kind": "number", "value": 5.0}),
    )
    context = _context(ability, {"attack_damage": 10.0})
    first = evaluate(ability, "Scaled", context, level=1, rank=1)
    second = evaluate(ability, "Plain", context, level=1, rank=1)
    assert first.dependencies == ["stat:attack_damage/total"]
    assert second.dependencies == []


def test_repeated_evaluation_is_deterministic():
    ability = _ability(
        _calculation(
            "Damage",
            {
                "kind": "product",
                "operands": [
                    {"kind": "number", "value": 2.0},
                    {
                        "kind": "stat_scaled",
                        "stat": {"resolved": True, "stat": "attack_damage", "formula": "total"},
                        "factor": {"kind": "number", "value": 1.0},
                    },
                ],
            },
        )
    )
    context = _context(ability, {"attack_damage": 10.0})
    first = evaluate(ability, "Damage", context, level=1, rank=1).to_dict()
    second = evaluate(ability, "Damage", context, level=1, rank=1).to_dict()
    assert first == second


def test_unresolved_entry_keeps_artifact_provenance():
    context = _traversal_context()
    parse_part({"__type": "0xdeadbeef"}, context=context, pointer="/Test/Part")
    assert context.unresolved
    entry = context.unresolved[0]
    assert entry["source_sha256"] == "sha256:test"
    assert entry["content_version"] == "16.20.test"


def test_breakpoint_extraction_preserves_absent_fields():
    context = _traversal_context()
    node = parse_part(
        {
            "__type": "ByCharLevelBreakpointsCalculationPart",
            "mLevel1Value": 300.0,
            "mBreakpoints": [{"mLevel": 6, "mAdditionalBonusAtThisLevel": -60.0}],
        },
        context=context,
        pointer="/Test/Breakpoint",
    )
    assert node["level1_value"] == 300.0
    assert node["initial_bonus_per_level"] is None
    assert node["breakpoints"][0]["additional_bonus_at_this_level"] == -60.0
    assert node["breakpoints"][0]["bonus_per_level_at_and_after"] is None
    assert node["default_policy"] == "lol-bin-omitted-float-defaults/v1"
    assert "initial_bonus_per_level" in node["absent_fields"]
    assert "breakpoints[0].bonus_per_level_at_and_after" in node["absent_fields"]
    assert node["value_confidence"] == "inferred"


def test_game_calculation_without_parts_is_diagnosed():
    context = _traversal_context()
    node = parse_calculation(
        {"__type": "GameCalculation", "mSpellCalculations": {}},
        context=context,
        pointer="/Test/Calculation",
    )
    assert node["parts"] is None
    assert any(item.code == "missing_formula_parts" for item in context.diagnostics)


def test_inline_factor_nodes_keep_confidence_and_provenance():
    context = _traversal_context()
    coefficient = parse_part(
        {
            "__type": "StatByCoefficientCalculationPart",
            "mStat": 2,
            "mStatFormula": 2,
            "mCoefficient": 0.5,
        },
        context=context,
        pointer="/Test/Coefficient",
    )
    assert coefficient["factor"]["confidence"] == "source_explicit"
    assert coefficient["factor"]["provenance"]["json_pointer"].endswith("/mCoefficient")

    named = parse_part(
        {
            "__type": "StatByNamedDataValueCalculationPart",
            "mStat": 2,
            "mStatFormula": 2,
            "mDataValue": "QCoeff",
        },
        context=context,
        pointer="/Test/Named",
    )
    assert named["factor"]["confidence"] == "source_explicit"
    assert named["factor"]["provenance"]["json_pointer"].endswith("/mDataValue")


def test_malformed_factor_is_marked_unverified():
    context = _traversal_context()
    node = parse_part(
        {
            "__type": "StatByCoefficientCalculationPart",
            "mStat": 2,
            "mStatFormula": 2,
            "mCoefficient": None,
        },
        context=context,
        pointer="/Test/Coefficient",
    )
    assert node["factor"]["confidence"] == "unverified"
    assert node["factor"]["value"] is None


def test_extraction_is_deterministic(extract_document):
    first = extract_champion(extract_document).to_dict()
    second = extract_champion(extract_document).to_dict()
    assert first == second
