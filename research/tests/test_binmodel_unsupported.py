"""Unsupported-but-preserved structures must stay explicit."""

from __future__ import annotations

import pytest
from binmodel.evaluate import EvaluationContext, FormulaError, evaluate
from binmodel.model import Ability, Calculation
from binmodel.registry import Registry
from binmodel.traverse import TraversalContext, parse_calculation, parse_part


def _context(document=None):
    return TraversalContext(
        document=document or {},
        registry=Registry(),
        source_sha256="synthetic",
        content_version="synthetic",
        spell_path="Test",
    )


def test_conditional_calculation_is_parsed_structurally():
    context = _context()
    node = parse_calculation(
        {
            "__type": "GameCalculationConditional",
            "mDefaultGameCalculation": "Default",
            "mConditionalGameCalculation": "Evolved",
            "mConditionalCalculationRequirements": {
                "__type": "HasBuffCastRequirement",
                "mBuffName": "Buff",
            },
            "tooltipOnly": True,
        },
        context=context,
        pointer="/Test/Conditional",
    )
    assert node["kind"] == "conditional"
    assert node["default_calculation"] == "Default"
    assert node["conditional_calculation"] == "Evolved"
    assert node["condition"]["type"]["name"] == "HasBuffCastRequirement"
    assert node["tooltip_only"] is True


def test_effect_value_part_is_typed_and_reported_as_unresolved():
    context = _context()
    node = parse_part(
        {"__type": "EffectValueCalculationPart", "mEffectIndex": 1},
        context=context,
        pointer="/Test/Effect",
    )
    assert node["kind"] == "effect_value"
    assert node["effect_index"] == 1
    assert node["resolved"] is False
    assert context.unresolved[0]["reason"] == "effect value requires SpellEffectAmount data"


def test_conditional_and_effect_value_cannot_be_evaluated():
    ability = Ability(
        ability_id="test",
        slot="Q",
        path="Test",
        name="Test",
        root_spell="Test",
        level_count=1,
        source_level_count="synthetic",
        calculations=[
            Calculation(
                name="Conditional",
                tree={
                    "kind": "conditional",
                    "default_calculation": "Default",
                    "conditional_calculation": "Evolved",
                },
                source_path="Test",
            ),
            Calculation(
                name="Effect",
                tree={
                    "kind": "game_calculation",
                    "parts": [{"kind": "effect_value", "effect_index": 1}],
                },
                source_path="Test",
            ),
        ],
    )
    context = EvaluationContext(abilities={"test": ability}, stats={})
    with pytest.raises(FormulaError) as conditional:
        evaluate(ability, "Conditional", context, level=1, rank=1)
    assert conditional.value.code == "conditional_requires_game_state"
    with pytest.raises(FormulaError) as effect:
        evaluate(ability, "Effect", context, level=1, rank=1)
    assert effect.value.code == "effect_value_unresolved"
