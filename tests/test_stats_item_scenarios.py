"""Item effects the catalog declares under a scenario, and confirmed zeros."""

from __future__ import annotations

from fractions import Fraction as F

import pytest

from lol_knowledge.errors import StatsError
from lol_knowledge.objects.catalog import merge_generated
from lol_knowledge.stats import (
    EVIDENCE_LABEL,
    ItemData,
    ItemStat,
    Label,
    build_stat_sheet,
    format_text,
    items_from_model,
    sheet_effect_reason,
)
from stats_helpers import PATCH, champion, item


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
            "only stat modifiers can be sheet stats",
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
            "only always effects amplify a total amount",
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


# Always-active stat effects


def always(stat="ability_power", value=30, mode="percent", scope="total", **overrides):
    entry = effect(stat, value, **overrides)
    del entry["scenario"]
    entry["trigger"] = {"event": "always"}
    entry["components"][0].update({"mode": mode, "scope": scope})
    return entry


def ap_item(item_id, amount):
    return item(item_id, ("ability_power", "flat", amount))


def test_amplifiers_share_one_total_and_do_not_compound():
    data = ItemData("8", "Sombrero", PATCH, (), (always(), always(value=10)))
    ap = build_stat_sheet(champion(), 1, [ap_item("1", 100), data])["ability_power"]
    assert ap.total() == 100 + 30 + 10
    assert [part.note for part in ap.contributions[-2:]] == [
        "30% of the total",
        "10% of the total",
    ]


def test_an_always_flat_effect_is_a_plain_stat():
    ad = sheet(always("attack_damage", 10, mode="flat"))["attack_damage"]
    assert ad.scoped("bonus") == 10
    assert ad.contributions[-1].note == ""


def test_a_non_evaluable_always_effect_is_a_pending_zero():
    ap = sheet(always(model_status="excluded"))["ability_power"]
    assert ap.total() == 0 and ap.label is Label.PENDING
    assert ap.contributions[-1].note == "effect excluded, not applied"


@pytest.mark.parametrize(
    "entry",
    [always(scope="bonus"), always("crit_chance"), effect(), always(conditions=[{"kind": "x"}])],
)
def test_sheet_effect_reasons(entry):
    expected = {
        "max_stacks": "scenario max_stacks",
    }.get(entry.get("scenario"))
    if entry.get("conditions"):
        assert sheet_effect_reason(entry) is None
    elif expected:
        assert sheet_effect_reason(entry) == expected
    else:
        assert sheet_effect_reason(entry) == "always"


@pytest.mark.parametrize("entry", [always(scope="bonus"), always("crit_chance")])
def test_only_a_total_amount_can_be_amplified(entry):
    with pytest.raises(StatsError, match="only always effects amplify a total amount"):
        sheet(entry)


def test_an_always_effect_with_other_components_is_not_a_sheet_effect():
    entry = always()
    entry["components"].append({"kind": "damage"})
    assert sheet_effect_reason(entry) is None
    assert sheet(entry)["ability_power"].total() == 0


def test_an_amplifier_carries_the_weakest_label_of_its_total():
    pending = ItemData(
        "1",
        "Dudoso",
        PATCH,
        (ItemStat("ability_power", "flat", F(100), "ddragon_description", Label.PENDING),),
    )
    data = ItemData("8", "Sombrero", PATCH, (), (always(evidence_confidence="official"),))
    ap = build_stat_sheet(champion(), 1, [pending, data])["ability_power"]
    assert ap.contributions[-1].label is Label.PENDING


def test_a_scenario_cannot_amplify_a_total():
    entry = effect("ability_power", 30)
    entry["components"][0]["mode"] = "percent"
    with pytest.raises(StatsError, match="only always effects amplify a total amount"):
        sheet(entry)


def test_client_only_evidence_is_derived():
    assert EVIDENCE_LABEL["derived"] is Label.DERIVED
