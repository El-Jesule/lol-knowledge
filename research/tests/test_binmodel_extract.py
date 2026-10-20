"""Extraction tests against the compact Zaahen fixture."""

from __future__ import annotations

import pytest
from binmodel.extract import extract_champion
from binmodel.registry import Registry


def _extract(document):
    meta = document["_provenance"]
    return extract_champion(
        document,
        source={
            "url": meta["url"],
            "sha256": meta["source_sha256"],
            "input": "fixture",
        },
        registry=Registry(),
        content_version=meta["content_version"],
    )


def _by_slot(extract):
    return {ability.slot: ability for ability in extract.abilities}


def _values(ability, name, mode="base"):
    for value in ability.data_values:
        if value.name == name and value.mode == mode:
            return value
    raise AssertionError(f"missing {name} in {ability.slot}")


def test_champion_and_stat_block(extract_document):
    extract = _extract(extract_document)
    assert extract.champion["id"] == "Zaahen"
    values = extract.champion["base_stats"]["values"]
    assert values["attack_damage"] == 63.0
    assert values["attack_damage_per_level"] == 4.0
    assert values["health"] == 640.0
    assert values["health_per_level"] == 114.0
    assert values["armor"] == 36.0
    assert values["magic_resist"] == 32.0
    assert len(extract.champion["stats_by_level"]) == 18


def test_all_five_abilities_are_discovered(extract_document):
    extract = _extract(extract_document)
    slots = _by_slot(extract)
    assert tuple(slots) == ("P", "Q", "W", "E", "R")
    assert {slot: slots[slot].level_count for slot in slots} == {
        "P": 1,
        "Q": 5,
        "W": 5,
        "E": 5,
        "R": 3,
    }
    assert slots["Q"].source_level_count == "tooltip"
    assert slots["P"].source_level_count == "passive_default"


def test_calculation_names_are_discovered(extract_document):
    slots = _by_slot(_extract(extract_document))
    assert [item.name for item in slots["P"].calculations] == [
        "ReviveCooldownCalc",
        "RevivePercentCalc",
        "PercentBonusADCalc",
    ]
    assert [item.name for item in slots["Q"].calculations] == [
        "InitialDamage",
        "SecondHitDamage",
    ]
    assert [item.name for item in slots["W"].calculations] == [
        "InitialDamage",
        "SecondaryDamage",
    ]
    assert [item.name for item in slots["E"].calculations] == [
        "BaseDamageCalc",
        "BonusDamageCalc",
    ]
    assert [item.name for item in slots["R"].calculations] == ["DamageEndCalc"]


def test_rank_zero_is_skipped_even_when_nonzero(extract_document):
    slots = _by_slot(_extract(extract_document))
    assert _values(slots["Q"], "Q1BaseDamage").ranks == [15.0, 30.0, 45.0, 60.0, 75.0]
    assert _values(slots["Q"], "QCoeff").ranks == pytest.approx([0.2, 0.25, 0.3, 0.35, 0.4])
    assert _values(slots["Q"], "HealPercent").ranks == pytest.approx([0.05, 0.06, 0.07, 0.08, 0.09])
    assert _values(slots["W"], "InitialBaseDamage").ranks == [40.0, 60.0, 80.0, 100.0, 120.0]
    assert _values(slots["E"], "Damage_Base").ranks == [40.0, 60.0, 80.0, 100.0, 120.0]
    assert _values(slots["R"], "EndDamage").ranks == [250.0, 400.0, 550.0]
    assert _values(slots["R"], "ArmorPen").ranks == pytest.approx([0.1, 0.2, 0.3])


def test_effective_cooldown_and_legacy_mismatch(extract_document):
    slots = _by_slot(_extract(extract_document))
    q = slots["Q"].cooldown
    assert q is not None
    assert q["ranks"] == [10.0, 9.0, 8.0, 7.0, 6.0]
    w = slots["W"].cooldown
    assert w is not None
    assert w["ranks"] == [14.0, 13.5, 13.0, 12.5, 12.0]
    assert w["legacy"]["raw_values"] == [16.0, 16.0, 15.0, 14.0, 13.0, 12.0, 11.0]
    assert w["legacy"]["matches"] is False


def test_cooldown_mismatch_is_reported(extract_document):
    extract = _extract(extract_document)
    codes = [item.code for item in extract.diagnostics]
    assert "cooldown_mismatch" in codes


def test_passive_interpolation_tree_and_missing_values(extract_document):
    extract = _extract(extract_document)
    passive = _by_slot(extract)["P"]
    calculation = next(item for item in passive.calculations if item.name == "PercentBonusADCalc")
    part = calculation.tree["parts"][0]
    assert part["kind"] == "by_char_level_named_data_values_interpolation"
    assert part["start_data_value"] == "PBonusADMin"
    assert part["end_data_value"] == "PBonusADMax"
    assert part["scale_past_default_max_level"] is True
    assert part["type"]["provisional_name"] == (
        "ByCharLevelNamedDataValuesInterpolationCalculationPart"
    )
    codes = [item.code for item in extract.diagnostics if "ZaahenPassive" in item.path]
    # The two values without a values array are referenced from the base mode.
    assert codes.count("missing_data_value_values") == 2


def test_provenance_is_attached_to_nodes(extract_document):
    extract = _extract(extract_document)
    q = _by_slot(extract)["Q"]
    tree = next(item for item in q.calculations if item.name == "InitialDamage").tree
    assert tree["provenance"]["source_sha256"] == extract_document["_provenance"]["source_sha256"]
    assert tree["provenance"]["json_pointer"].endswith("/InitialDamage")
    assert "tooltip_only" in tree


def test_top_level_formula_nodes_are_resolved(extract_document):
    extract = _extract(extract_document)
    assert extract.unresolved == []
    assert all(
        calculation.tree.get("kind") != "unresolved"
        for ability in extract.abilities
        for calculation in ability.calculations
    )


def test_tooltip_level_count_is_the_rank_source(extract_document):
    extract = _extract(extract_document)
    q = _by_slot(extract)["Q"]
    assert q.tooltip["lists"]["LevelUp"]["level_count"] == 5
    assert q.tooltip["lists"]["LevelUp"]["elements"][4]["name_override"] == (
        "Spell_ListType_BonusADRatio"
    )
