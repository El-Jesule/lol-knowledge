"""Evaluation tests for supported and unsupported formula nodes."""

from __future__ import annotations

import pytest
from binmodel.evaluate import EvaluationContext, FormulaError, evaluate
from binmodel.extract import extract_champion
from binmodel.model import Ability, Calculation
from binmodel.stats import champion_stats


def _extract(document):
    meta = document["_provenance"]
    return extract_champion(
        document,
        source={"sha256": meta["source_sha256"], "url": meta["url"]},
        content_version=meta["content_version"],
    )


def _abilities(extract):
    return {ability.ability_id: ability for ability in extract.abilities}


def _damage_context(extract, *, level=18, bonus_ad=100.0):
    abilities = _abilities(extract)
    stats = champion_stats(extract.champion["base_stats"], level, bonus_attack_damage=bonus_ad)
    return abilities, EvaluationContext(abilities=abilities, stats=stats)


def test_main_damage_formulas_at_level_18_rank_1(extract_document):
    extract = _extract(extract_document)
    abilities, context = _damage_context(extract)
    expected = {
        ("q", "InitialDamage"): 35.0,
        ("q", "SecondHitDamage"): 50.0,
        ("w", "InitialDamage"): 90.0,
        ("w", "SecondaryDamage"): 60.0,
        ("e", "BaseDamageCalc"): 90.0,
        ("e", "BonusDamageCalc"): 135.0,
        ("r", "DamageEndCalc"): 450.0,
    }
    for (ability_id, calculation), value in expected.items():
        result = evaluate(abilities[ability_id], calculation, context, level=18, rank=1)
        assert result.complete is True
        assert result.value == pytest.approx(value)


def test_damage_formulas_scale_with_bonus_ad(extract_document):
    extract = _extract(extract_document)
    abilities, context = _damage_context(extract, level=1, bonus_ad=0.0)
    assert evaluate(abilities["q"], "InitialDamage", context, level=1, rank=1).value == 15.0
    assert evaluate(abilities["r"], "DamageEndCalc", context, level=1, rank=1).value == 250.0


def test_passive_percent_interpolation(extract_document):
    extract = _extract(extract_document)
    passive = _abilities(extract)["passive"]
    context = EvaluationContext(abilities={"passive": passive}, stats={})
    level_one = evaluate(passive, "PercentBonusADCalc", context, level=1, rank=1)
    level_eighteen = evaluate(passive, "PercentBonusADCalc", context, level=18, rank=1)
    assert level_one.value == pytest.approx(0.015)
    assert level_eighteen.value == pytest.approx(0.028)


def test_revive_cooldown_breakpoints(extract_document):
    extract = _extract(extract_document)
    passive = _abilities(extract)["passive"]
    context = EvaluationContext(abilities={"passive": passive}, stats={})
    expected = {1: 300.0, 6: 240.0, 11: 180.0, 16: 120.0, 18: 120.0}
    for level, value in expected.items():
        result = evaluate(passive, "ReviveCooldownCalc", context, level=level, rank=1)
        assert result.complete is True
        assert result.value == pytest.approx(value)


def test_revive_percent_is_incomplete_without_missing_values(extract_document):
    extract = _extract(extract_document)
    passive = _abilities(extract)["passive"]
    context = EvaluationContext(abilities={"passive": passive}, stats={})
    result = evaluate(passive, "RevivePercentCalc", context, level=18, rank=1)
    assert result.complete is False
    assert result.value == pytest.approx(0.75)
    assert "ReviveBonusPerLevel" in " ".join(result.missing)
    assert "ReviveBonusPerLevelAtAndAfter" in " ".join(result.missing)


def test_missing_data_value_raises():
    ability = Ability(
        ability_id="test",
        slot="Q",
        path="test",
        name="test",
        root_spell="test",
        level_count=1,
        source_level_count="synthetic",
        calculations=[
            Calculation(
                name="Damage",
                tree={
                    "kind": "game_calculation",
                    "parts": [{"kind": "data_value", "name": "MissingValue"}],
                },
                source_path="test",
            )
        ],
    )
    context = EvaluationContext(abilities={"test": ability}, stats={})
    with pytest.raises(FormulaError) as captured:
        evaluate(ability, "Damage", context, level=1, rank=1)
    assert captured.value.code == "missing_data_value"


def test_unresolved_node_raises():
    ability = Ability(
        ability_id="test",
        slot="Q",
        path="test",
        name="test",
        root_spell="test",
        level_count=1,
        source_level_count="synthetic",
        calculations=[
            Calculation(
                name="Damage",
                tree={"kind": "unresolved", "type": {"type_hash": "0xdeadbeef"}},
                source_path="test",
            )
        ],
    )
    context = EvaluationContext(abilities={"test": ability}, stats={})
    with pytest.raises(FormulaError) as captured:
        evaluate(ability, "Damage", context, level=1, rank=1)
    assert captured.value.code == "unresolved_node"


def test_calculation_cycle_raises():
    ability = Ability(
        ability_id="test",
        slot="Q",
        path="test",
        name="test",
        root_spell="test",
        level_count=1,
        source_level_count="synthetic",
        calculations=[
            Calculation(
                name="A",
                tree={
                    "kind": "game_calculation",
                    "parts": [{"kind": "calculation_reference", "key": "A"}],
                },
                source_path="test",
            )
        ],
    )
    context = EvaluationContext(abilities={"test": ability}, stats={})
    with pytest.raises(FormulaError) as captured:
        evaluate(ability, "A", context, level=1, rank=1)
    assert captured.value.code == "calculation_cycle"
