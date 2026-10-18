"""Offline tests for extraction and provenance."""

from __future__ import annotations

from copy import deepcopy

import pytest
from cdragon_zaahen.extract import (
    E_PATH,
    Q_PATH,
    R_PATH,
    ROOT_PATH,
    W_PATH,
    ExtractionError,
    extract_formula,
    extract_zaahen,
    has_champion_stat_block,
    rank_slice,
)
from cdragon_zaahen.provenance import Status

URL = "https://raw.communitydragon.org/16.20/game/data/characters/zaahen/zaahen.bin.json"


def records(bin_document):
    meta = bin_document["_provenance"]
    return {
        record.parameter: record
        for record in extract_zaahen(
            bin_document["objects"],
            url=URL,
            content_version=meta["content_version"],
            sha256=meta["source_sha256"],
        )
    }


def test_q_first_hit_base_damage_has_full_provenance(bin_document) -> None:
    record = records(bin_document)["q.first_hit_base_damage"]

    assert record.ranks == (15.0, 30.0, 45.0, 60.0, 75.0)
    assert record.source == "communitydragon"
    assert record.url == URL
    assert record.source_version == "16.20.8248524+branch.releases-16-20.content.release"
    assert record.source_path == (f"{Q_PATH}.mSpell.DataValues['Q1BaseDamage'].values")
    assert record.source_sha256 == bin_document["_provenance"]["source_sha256"]
    assert record.extraction == "DataValues array"
    assert record.transformation == "index 1..5 = ranks 1..5"
    assert record.status is Status.SOURCE_EXPLICIT


def test_representative_parameters_are_extracted(bin_document) -> None:
    found = records(bin_document)

    assert found["q.bonus_ad_ratio"].ranks == pytest.approx((0.2, 0.25, 0.3, 0.35, 0.4))
    assert found["w.initial_base_damage"].ranks == (40.0, 60.0, 80.0, 100.0, 120.0)
    assert found["w.secondary_base_damage"].ranks == (30.0, 50.0, 70.0, 90.0, 110.0)
    assert found["w.cooldown_seconds"].ranks == (14.0, 13.5, 13.0, 12.5, 12.0)
    assert found["w.cooldown_time_legacy"].ranks == (16.0, 15.0, 14.0, 13.0, 12.0)
    assert found["champion.attack_damage_per_level"].ranks == (4.0,)
    assert found["champion.base_attack_damage"].ranks == (63.0,)
    assert found["e.base_damage"].ranks == (40.0, 60.0, 80.0, 100.0, 120.0)
    assert found["e.percent_max_hp_magic"].ranks == pytest.approx((0.04, 0.045, 0.05, 0.055, 0.06))
    assert found["r.base_damage"].ranks == (250.0, 400.0, 550.0)
    assert found["r.bonus_ad_ratio"].ranks == (2.0,)
    assert found["r.armor_penetration"].ranks == pytest.approx((0.1, 0.2, 0.3))
    assert found["passive.ad_per_stack"].ranks == pytest.approx((0.028,))


def test_bin_exposes_the_champion_stat_block(bin_document) -> None:
    assert has_champion_stat_block(bin_document["objects"]) is True


def test_rank_slice_rejects_short_arrays() -> None:
    with pytest.raises(ExtractionError):
        rank_slice([0.0, 1.0], 5, "x")


def test_rank_slice_rejects_non_numeric_values() -> None:
    with pytest.raises(ExtractionError):
        rank_slice([0.0, 1.0, "two", 3.0, 4.0, 5.0, 6.0], 5, "x")


def test_known_calculation_parts_are_supported(bin_document) -> None:
    formula = extract_formula(bin_document["objects"], R_PATH, "DamageEndCalc")

    assert formula.supported is True
    assert formula.status is Status.INFERRED
    assert any(part.get("mDataValue") == "BonusADDamageRatio" for part in formula.parts)


def test_unknown_calculation_parts_stay_unverified(bin_document) -> None:
    document = deepcopy(bin_document["objects"])
    spell = document[Q_PATH]["mSpell"]
    spell["mSpellCalculations"]["InitialDamage"] = {
        "mFormulaParts": [{"__type": "{deadbeef}"}],
        "__type": "GameCalculation",
    }

    formula = extract_formula(document, Q_PATH, "InitialDamage")

    assert formula.supported is False
    assert formula.status is Status.UNVERIFIED
    assert "Unrecognised" in formula.notes


def test_each_spell_path_is_present(bin_document) -> None:
    for path in (Q_PATH, W_PATH, E_PATH, R_PATH):
        assert path in bin_document["objects"]
    assert ROOT_PATH in bin_document["objects"]


def test_effective_cooldown_is_not_the_legacy_mirror(bin_document) -> None:
    found = records(bin_document)

    assert found["w.cooldown_seconds"].ranks != found["w.cooldown_time_legacy"].ranks
    assert "Cooldown.values" in found["w.cooldown_seconds"].source_path
    assert "cooldownTime" in found["w.cooldown_time_legacy"].source_path
    assert "must not be used" in found["w.cooldown_seconds"].notes


def test_champion_stats_come_from_character_record(bin_document) -> None:
    growth = records(bin_document)["champion.attack_damage_per_level"]

    assert growth.ranks == (4.0,)
    assert growth.source_path == f"{ROOT_PATH}.damagePerLevelModifiable.baseValue"
    assert growth.extraction == "ModifiableFloat.baseValue"
