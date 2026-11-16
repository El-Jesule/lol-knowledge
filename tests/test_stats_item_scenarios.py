"""Item effects the catalog declares under a scenario, and confirmed zeros."""

from __future__ import annotations

from fractions import Fraction as F

import pytest

from lol_knowledge.errors import StatsError
from lol_knowledge.objects.catalog import merge_generated
from lol_knowledge.stats import (
    ItemData,
    Label,
    build_stat_sheet,
    format_text,
    items_from_model,
)
from stats_helpers import PATCH, champion


def effect(stat="crit_chance", value=25, **overrides):
    entry = {
        "id": "stacking",
        "scenario": "max_stacks",
        "evidence_confidence": "official",
        "model_status": "evaluable",
        "components": [
            {
                "kind": "stat_modifier",
                "stat": stat,
                "scope": "total",
                "mode": "flat",
                "formula": {"op": "constant", "value": value},
            }
        ],
    }
    entry.update(overrides)
    return entry


def sheet(*effects, base=None):
    data = ItemData("7", "Objeto", PATCH, (), tuple(effects))
    return build_stat_sheet(base or champion(), 1, [data])


def test_a_fraction_stat_takes_percentage_points():
    crit = sheet(effect())["crit_chance"]
    assert crit.total() == F(1, 4)
    assert crit.label is Label.DERIVED
    assert crit.contributions[-1].source == f"data:item:7 effect stacking ({PATCH})"
    assert "crit_chance: 25% (base 0% + bonus 25%) [Derivado] (scenario: maximum stacks)" in (
        format_text(sheet(effect()))
    )


def test_an_amount_stat_takes_its_own_unit():
    assert sheet(effect("attack_damage", 10))["attack_damage"].scoped("bonus") == 10


def test_secondary_evidence_is_pending():
    crit = sheet(effect(evidence_confidence="secondary"))["crit_chance"]
    assert crit.label is Label.PENDING


def test_a_non_evaluable_scenario_effect_is_a_pending_zero():
    crit = sheet(effect(model_status="partially_evaluable"))["crit_chance"]
    assert crit.total() == 0
    assert crit.label is Label.PENDING
    assert crit.contributions[-1].note == (
        "scenario: maximum stacks; effect partially_evaluable, not applied"
    )


def test_effects_without_a_scenario_are_not_stats():
    plain = effect()
    del plain["scenario"]
    assert sheet(plain)["crit_chance"].total() == 0


def test_the_passive_doubling_includes_the_stacks():
    assert sheet(effect(), base=champion("Yasuo"))["crit_chance"].total() == F(1, 2)


@pytest.mark.parametrize(
    ("entry", "message"),
    [
        (effect(scenario="half_stacks"), "scenario 'half_stacks' is not modelled"),
        (
            effect(components=[{"kind": "damage", "formula": {"op": "constant", "value": 1}}]),
            "only flat stat modifiers",
        ),
        (
            effect(
                formula=None,
                components=[
                    {
                        "kind": "stat_modifier",
                        "stat": "crit_chance",
                        "mode": "flat",
                        "formula": {
                            "op": "by_holder_range",
                            "melee": {"op": "constant", "value": 25},
                            "ranged": {"op": "constant", "value": 20},
                        },
                    }
                ],
            ),
            "item 7 stacking",
        ),
        (effect(value=150), "is not a fraction 0..1"),
        (
            effect(
                components=[
                    {
                        "kind": "stat_modifier",
                        "stat": "crit_chance",
                        "mode": "percent",
                        "formula": {"op": "constant", "value": 25},
                    }
                ]
            ),
            "only flat stat modifiers",
        ),
    ],
)
def test_invalid_scenario_effects_are_errors(entry, message):
    with pytest.raises(StatsError, match=message):
        sheet(entry)


def test_an_unknown_description_value_is_a_pending_zero():
    model = {
        "game_version": PATCH,
        "objects": [
            {
                "id": "1",
                "name": "a",
                "stats": [
                    {
                        "id": "crit_chance",
                        "kind": "percent",
                        "value": None,
                        "reason": "unpublished",
                        "source": {"kind": "ddragon_description"},
                    }
                ],
            }
        ],
    }
    (stat,) = items_from_model(model, ["1"])[0].stats
    assert (stat.value, stat.label, stat.note) == (0, Label.PENDING, "value unknown: unpublished")


def test_a_model_stat_note_reaches_the_sheet():
    model = {
        "game_version": PATCH,
        "objects": [
            {
                "id": "1",
                "name": "a",
                "stats": [
                    {
                        "id": "crit_chance",
                        "kind": "percent",
                        "value": 0,
                        "note": "confirmed zero: why",
                        "source": {"kind": "ddragon_description"},
                    }
                ],
            }
        ],
    }
    (stat,) = items_from_model(model, ["1"])[0].stats
    assert (stat.value, stat.label, stat.note) == (0, Label.OFFICIAL, "confirmed zero: why")


def test_merge_turns_a_confirmed_unknown_zero_into_a_real_zero():
    unknown = {
        "id": "crit_chance",
        "kind": "percent",
        "status": "unknown",
        "reason": "zero",
        "quote": "0% de crítico",
    }
    other = {"id": "armor", "kind": "flat", "status": "unknown", "reason": "zero", "quote": "0"}
    catalog = {
        "objects": [
            {
                "id": "1",
                "effect_review": "complete",
                "confirmed_zero_stats": [
                    {"id": "crit_chance", "kind": "percent", "reason": "no such stat"}
                ],
                "stats": [],
                "effects": [],
            }
        ]
    }
    known = {"id": "crit_chance", "kind": "percent", "value": 5, "quote": "5% de crítico"}
    generated = {"objects": [{"id": "1", "stats": [known]}]}
    assert merge_generated(catalog, generated)["objects"][0]["stats"] == [known]
    generated = {"objects": [{"id": "1", "stats": [unknown, other]}]}
    (merged,) = merge_generated(catalog, generated)["objects"]
    assert merged["stats"] == [
        {
            "id": "crit_chance",
            "kind": "percent",
            "value": 0,
            "quote": "0% de crítico",
            "confirmed_zero": "no such stat",
        },
        other,
    ]
