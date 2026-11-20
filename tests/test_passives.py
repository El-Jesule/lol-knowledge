"""Tests for linear_by_level formulas and champion passive effects (CH-03)."""

from __future__ import annotations

from fractions import Fraction as F

import pytest

from lol_knowledge.errors import KitError
from lol_knowledge.formula import ABILITY_OPS, FormulaError, evaluate_formula
from lol_knowledge.kit import parse_kit


def _kit_with_passive(*effects: dict) -> dict:
    return {
        "schema": "lol-champion-kit/1",
        "champion": "Testchamp",
        "label": "Derivado",
        "game_version": "16.23",
        "content_version": "16.23.test",
        "abilities": {
            "P": {
                "name": "Pasiva de prueba",
                "max_rank": 1,
                "cases": [],
                "passive_stats": [],
                "passive_effects": list(effects),
                "not_modelled": [],
            }
        },
    }


def test_linear_by_level_formula_exact_arithmetic_and_validation():
    formula = {"op": "linear_by_level", "min": 1.5, "max": 2.8}
    at_1 = evaluate_formula(formula, {}, level=1, ops=ABILITY_OPS)
    at_18 = evaluate_formula(formula, {}, level=18, ops=ABILITY_OPS)
    at_11 = evaluate_formula(formula, {}, level=11, ops=ABILITY_OPS)
    assert at_1.exact == F(3, 2)
    assert at_18.exact == F(14, 5)
    assert at_11.exact == F(3, 2) + (F(14, 5) - F(3, 2)) * F(10, 17)
    assert at_11.dependencies == ("level",)

    with pytest.raises(FormulaError, match="explicit level"):
        evaluate_formula(formula, {}, ops=ABILITY_OPS)
    with pytest.raises(FormulaError, match="outside 1..18"):
        evaluate_formula(formula, {}, level=19, ops=ABILITY_OPS)
    with pytest.raises(FormulaError, match="unsupported formula op"):
        evaluate_formula(formula, {}, level=1)  # OBJECT_OPS rejects linear_by_level


def test_passive_effect_spec_parsing_and_validation():
    kit = parse_kit(
        _kit_with_passive(
            {
                "id": "determination",
                "name": "Determinación",
                "kind": "stacking_stat",
                "stat": "attack_damage",
                "mode": "percent",
                "trigger": "champion_hit",
                "formula": {"op": "linear_by_level", "min": 1.5, "max": 2.8},
                "max_stacks": 12,
                "max_stacks_multiplier": 2,
                "duration_seconds": 5,
                "input_name": "determination_stacks",
                "label": "Derivado",
                "source": "client",
            },
            {
                "id": "takedown_heal",
                "name": "Robo de esencias",
                "kind": "heal",
                "trigger": "on_champion_takedown",
                "formula": {"op": "linear_by_level", "min": 75, "max": 165},
                "label": "Derivado",
                "source": "client",
            },
            {
                "id": "third_hit",
                "name": "Tercer golpe",
                "kind": "damage_proc",
                "trigger": "every_n_attacks",
                "every": 3,
                "damage_type": "magic",
                "formula": {"op": "constant", "value": 60},
                "label": "Derivado",
                "source": "client",
            },
        )
    )
    effects = kit.ability("P").passive_effects
    assert len(effects) == 3
    assert effects[0].max_stacks == 12 and effects[0].max_stacks_multiplier == F(2)
    assert effects[1].kind == "heal" and effects[1].trigger == "on_champion_takedown"
    assert effects[2].kind == "damage_proc" and effects[2].every == 3

    with pytest.raises(KitError, match="kind must be one of"):
        parse_kit(
            _kit_with_passive(
                {
                    "id": "bad",
                    "name": "x",
                    "kind": "aura",
                    "formula": {"op": "constant", "value": 1},
                    "label": "Derivado",
                    "source": "s",
                }
            )
        )
    with pytest.raises(KitError, match="stacking_stat requires max_stacks"):
        parse_kit(
            _kit_with_passive(
                {
                    "id": "bad",
                    "name": "x",
                    "kind": "stacking_stat",
                    "stat": "attack_damage",
                    "trigger": "champion_hit",
                    "formula": {"op": "constant", "value": 1},
                    "label": "Derivado",
                    "source": "s",
                }
            )
        )
    with pytest.raises(KitError, match="every_n_attacks requires every >= 2"):
        parse_kit(
            _kit_with_passive(
                {
                    "id": "bad",
                    "name": "x",
                    "kind": "damage_proc",
                    "trigger": "every_n_attacks",
                    "damage_type": "magic",
                    "formula": {"op": "constant", "value": 1},
                    "label": "Derivado",
                    "source": "s",
                }
            )
        )
