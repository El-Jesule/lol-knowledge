"""Measurement-validation tests."""

from __future__ import annotations

import pytest
from binmodel.extract import extract_champion
from binmodel.stats import champion_stats
from binmodel.validation import (
    validate_ability_damage,
    validate_ad_growth,
    validate_one_stack,
    validate_passive_percent,
)


def _extract(document):
    meta = document["_provenance"]
    return extract_champion(
        document,
        source={"sha256": meta["source_sha256"], "url": meta["url"]},
        content_version=meta["content_version"],
    )


def test_ad_growth_matches_all_measurements(extract_document):
    extract = _extract(extract_document)
    result = validate_ad_growth(extract.champion["base_stats"])
    assert result["all_match"] is True
    assert [row["displayed"] for row in result["rows"]] == [74, 77, 105, 142]
    assert [row["computed"] for row in result["rows"]] == pytest.approx(
        [73.8, 76.68, 104.76, 141.8]
    )


def test_passive_percent_matches_all_measurements(extract_document):
    extract = _extract(extract_document)
    passive = next(item for item in extract.abilities if item.ability_id == "passive")
    result = validate_passive_percent(passive)
    assert result["all_match"] is True
    assert [row["displayed_percent"] for row in result["rows"]] == [
        1.5,
        1.8,
        1.9,
        2.2,
        2.3,
        2.6,
        2.6,
        2.8,
    ]


def test_one_stack_favours_total_ad_but_is_not_proof(extract_document):
    extract = _extract(extract_document)
    passive = next(item for item in extract.abilities if item.ability_id == "passive")
    result = validate_one_stack(extract.champion["base_stats"], passive)
    rows = {row["basis"]: row for row in result["rows"]}
    assert rows["total_attack_damage"]["matches_146"] is True
    assert rows["base_attack_damage"]["matches_146"] is False
    assert rows["bonus_attack_damage"]["matches_146"] is False
    assert "does not prove" in result["note"]


def test_ability_damage_validation_table(extract_document):
    extract = _extract(extract_document)
    abilities = {item.ability_id: item for item in extract.abilities}
    stats = champion_stats(extract.champion["base_stats"], 18, bonus_attack_damage=100.0)
    result = validate_ability_damage(abilities, stats, level=18, rank=1)
    assert result["q.InitialDamage"]["value"] == pytest.approx(35.0)
    assert result["q.SecondHitDamage"]["value"] == pytest.approx(50.0)
    assert result["w.InitialDamage"]["value"] == pytest.approx(90.0)
    assert result["w.SecondaryDamage"]["value"] == pytest.approx(60.0)
    assert result["e.BaseDamageCalc"]["value"] == pytest.approx(90.0)
    assert result["e.BonusDamageCalc"]["value"] == pytest.approx(135.0)
    assert result["r.DamageEndCalc"]["value"] == pytest.approx(450.0)
