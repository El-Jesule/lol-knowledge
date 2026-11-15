"""Tests for the data-independent damage engine."""

from __future__ import annotations

import ast
from decimal import Decimal
from fractions import Fraction as F
from pathlib import Path

import pytest

from lol_knowledge.damage import (
    DamageType,
    Modifiers,
    damage_multiplier,
    effective_resistance,
    format_number,
    mitigate,
    to_dict,
    to_fraction,
)
from lol_knowledge.errors import DamageInputError

PACKAGE = Path(__file__).resolve().parents[1] / "src" / "lol_knowledge" / "damage"


# --- damage multiplier -------------------------------------------------------


@pytest.mark.parametrize(
    ("resistance", "expected"),
    [
        (0, F(1)),
        (25, F(4, 5)),
        (100, F(1, 2)),
        (200, F(1, 3)),
        # Negative branch, examples from the cited sources: -25 -> x1.2, -10 -> x1.0909...
        (-25, F(6, 5)),
        (-10, F(12, 11)),
        (-100, F(3, 2)),
    ],
)
def test_damage_multiplier(resistance, expected):
    assert damage_multiplier(resistance) == expected


def test_negative_resistance_never_doubles_damage():
    assert damage_multiplier(-(10**9)) < 2


# --- resistance pipeline -----------------------------------------------------


def test_no_modifiers_keeps_the_resistance():
    trace = effective_resistance(80)
    assert trace.initial == trace.effective == 80


def test_all_four_steps_apply_in_order():
    modifiers = Modifiers(
        flat_reduction=(20,),
        percent_reduction=("0.25",),
        percent_penetration=("0.3",),
        flat_penetration=(10,),
    )
    trace = effective_resistance(100, modifiers)
    assert trace.after_flat_reduction == 80
    assert trace.after_percent_reduction == 60
    assert trace.after_percent_penetration == 42
    assert trace.effective == 32


def test_percent_penetration_applies_before_flat_penetration():
    # (100 * 0.7) - 18 = 52; the reverse order would give (100 - 18) * 0.7 = 57.4.
    modifiers = Modifiers(percent_penetration=("0.3",), flat_penetration=(18,))
    assert effective_resistance(100, modifiers).effective == 52


def test_flat_reduction_applies_before_percent_reduction():
    # (100 - 20) * 0.75 = 60; the reverse order would give 100 * 0.75 - 20 = 55.
    modifiers = Modifiers(flat_reduction=(20,), percent_reduction=("0.25",))
    assert effective_resistance(100, modifiers).effective == 60


def test_percent_sources_stack_multiplicatively():
    penetration = Modifiers(percent_penetration=("0.3", "0.35"))
    assert effective_resistance(100, penetration).effective == F(91, 2)  # 100 * 0.7 * 0.65
    reduction = Modifiers(percent_reduction=("0.2", "0.3"))
    assert effective_resistance(100, reduction).effective == 56  # 44 % cumulative


def test_flat_sources_stack_additively():
    modifiers = Modifiers(flat_reduction=(10, 15), flat_penetration=(5, 7))
    trace = effective_resistance(100, modifiers)
    assert trace.after_flat_reduction == 75
    assert trace.effective == 63


def test_flat_reduction_can_go_below_zero_and_stops_later_steps():
    modifiers = Modifiers(
        flat_reduction=(30,),
        percent_reduction=("0.5",),
        percent_penetration=("0.5",),
        flat_penetration=(40,),
    )
    trace = effective_resistance(20, modifiers)
    assert trace.after_flat_reduction == -10
    assert trace.after_percent_reduction == -10
    assert trace.after_percent_penetration == -10
    assert trace.effective == -10


def test_flat_penetration_cannot_go_below_zero():
    assert effective_resistance(10, Modifiers(flat_penetration=(18,))).effective == 0


def test_zero_resistance_is_untouched_by_percentages_and_penetration():
    modifiers = Modifiers(
        flat_reduction=(50,),
        percent_reduction=("0.5",),
        percent_penetration=("0.5",),
        flat_penetration=(10,),
    )
    assert effective_resistance(50, modifiers).effective == 0


def test_already_negative_resistance_is_only_changed_by_flat_reduction():
    modifiers = Modifiers(flat_reduction=(5,), percent_penetration=("0.3",), flat_penetration=(9,))
    assert effective_resistance(-10, modifiers).effective == -15


def test_full_percent_values_are_allowed():
    assert effective_resistance(100, Modifiers(percent_penetration=(1,))).effective == 0


# --- mitigate ----------------------------------------------------------------


def test_physical_damage_with_penetration():
    result = mitigate(
        450, "physical", 100, Modifiers(percent_penetration=("0.3",), flat_penetration=(18,))
    )
    assert result.damage_type is DamageType.PHYSICAL
    assert result.resistance.effective == 52
    assert result.multiplier == F(25, 38)
    assert result.damage == F(5625, 19)


def test_magic_damage_follows_the_same_rules():
    modifiers = Modifiers(
        flat_reduction=(20,), percent_penetration=("0.4",), flat_penetration=(12,)
    )
    physical = mitigate(300, DamageType.PHYSICAL, 90, modifiers)
    magic = mitigate(300, DamageType.MAGIC, 90, modifiers)
    assert magic.damage_type is DamageType.MAGIC
    assert magic.damage == physical.damage == 300 * F(100, 130)


def test_negative_effective_resistance_amplifies_damage():
    result = mitigate(100, "physical", 20, Modifiers(flat_reduction=(45,)))
    assert result.resistance.effective == -25
    assert result.damage == 120


def test_true_damage_is_not_mitigated():
    result = mitigate(275, "true")
    assert result.resistance is None
    assert result.multiplier == 1
    assert result.damage == 275


def test_zero_raw_damage_is_valid():
    assert mitigate(0, "magic", 50).damage == 0


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"resistance": 30}, "true damage ignores"),
        ({"modifiers": Modifiers(flat_penetration=(10,))}, "true damage ignores"),
    ],
)
def test_true_damage_rejects_resistance_inputs(kwargs, message):
    with pytest.raises(DamageInputError, match=message):
        mitigate(100, "true", **kwargs)


def test_mitigated_damage_needs_a_resistance():
    with pytest.raises(DamageInputError, match="needs the target's resistance"):
        mitigate(100, "physical")


def test_rejects_unknown_damage_type():
    with pytest.raises(DamageInputError, match="damage type"):
        mitigate(100, "chaos", 10)


def test_rejects_negative_raw_damage():
    with pytest.raises(DamageInputError, match="raw damage"):
        mitigate(-1, "physical", 10)


# --- input validation --------------------------------------------------------


@pytest.mark.parametrize("value", [float("nan"), float("inf"), Decimal("NaN"), "abc", "", "1/0"])
def test_rejects_non_finite_or_non_numeric_values(value):
    with pytest.raises(DamageInputError):
        to_fraction(value, "value")


@pytest.mark.parametrize("value", [True, None, [1], b"1"])
def test_rejects_non_number_types(value):
    with pytest.raises(DamageInputError, match="expected a number"):
        to_fraction(value, "value")


@pytest.mark.parametrize(
    ("value", "expected"),
    [(0.3, F(3, 10)), ("0.3", F(3, 10)), (Decimal("0.3"), F(3, 10)), (7, F(7)), (F(1, 3), F(1, 3))],
)
def test_inputs_are_read_exactly(value, expected):
    assert to_fraction(value, "value") == expected


@pytest.mark.parametrize(
    "field", ["flat_reduction", "percent_reduction", "percent_penetration", "flat_penetration"]
)
def test_modifiers_reject_negative_values(field):
    with pytest.raises(DamageInputError, match="negative"):
        Modifiers(**{field: (-1,)})


@pytest.mark.parametrize("field", ["percent_reduction", "percent_penetration"])
def test_percentages_must_be_fractions(field):
    with pytest.raises(DamageInputError, match="between 0 and 1"):
        Modifiers(**{field: (30,)})


def test_modifiers_reject_a_bare_string():
    with pytest.raises(DamageInputError, match="sequence"):
        Modifiers(flat_penetration="18")


def test_modifiers_normalize_and_report_emptiness():
    assert Modifiers().is_empty
    modifiers = Modifiers(percent_penetration=[0.3])
    assert modifiers.percent_penetration == (F(3, 10),)
    assert not modifiers.is_empty


# --- determinism and reports -------------------------------------------------


def test_results_do_not_depend_on_source_order():
    a = Modifiers(percent_penetration=("0.1", "0.3", "0.35"), flat_penetration=("0.1", "0.2", 18))
    b = Modifiers(percent_penetration=("0.35", "0.1", "0.3"), flat_penetration=(18, "0.2", "0.1"))
    assert mitigate(1000, "physical", 137, a) == mitigate(1000, "physical", 137, a)
    assert mitigate(1000, "physical", 137, a).damage == mitigate(1000, "physical", 137, b).damage


def test_report_dictionary_carries_trace_label_and_exact_values():
    result = mitigate(
        450, "physical", 100, Modifiers(percent_penetration=("0.3",), flat_penetration=(18,))
    )
    report = to_dict(result)
    assert report["label"] == "Calculado"
    assert report["rules"] == "lol-knowledge/mechanics/damage-mitigation.md"
    assert report["assumptions"]
    assert report["input"] == {
        "damage_type": "physical",
        "raw_damage": 450.0,
        "resistance": 100.0,
        "flat_reduction": [],
        "percent_reduction": [],
        "percent_penetration": [0.3],
        "flat_penetration": [18.0],
    }
    assert report["resistance"] == {
        "initial": 100.0,
        "after_flat_reduction": 100.0,
        "after_percent_reduction": 100.0,
        "after_percent_penetration": 70.0,
        "effective": 52.0,
    }
    assert report["multiplier"] == 25 / 38
    assert report["post_mitigation_damage"] == 5625 / 19
    assert report["exact"] == {"multiplier": "25/38", "post_mitigation_damage": "5625/19"}


def test_report_dictionary_for_true_damage_has_no_resistance():
    report = to_dict(mitigate(275, "true"))
    assert report["resistance"] is None
    assert report["input"]["resistance"] is None
    assert report["post_mitigation_damage"] == 275.0


@pytest.mark.parametrize(
    ("value", "expected"),
    [(F(52), "52"), (F(7, 10), "0.7"), (F(5625, 19), "296.052632"), (F(1, 10**9), "1e-09")],
)
def test_format_number(value, expected):
    assert format_number(value) == expected


def test_rules_document_exists():
    root = Path(__file__).resolve().parents[1]
    assert (root / to_dict(mitigate(1, "true"))["rules"]).is_file()


def test_engine_does_not_import_game_data_modules():
    """The engine must stay independent of champions, items and snapshots."""
    allowed_relative = {"errors", "mitigation", "report"}
    for path in sorted(PACKAGE.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.level > 0:
                module = (node.module or "").split(".")[0]
                assert module in allowed_relative, f"{path.name} imports {node.module}"
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                names = (
                    [node.module]
                    if isinstance(node, ast.ImportFrom)
                    else [a.name for a in node.names]
                )
                assert not any((name or "").startswith("lol_knowledge") for name in names), (
                    path.name
                )
