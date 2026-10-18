"""Offline tests for cross-source comparison and conflict handling."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest
from cdragon_zaahen.compare import build_report, classify
from cdragon_zaahen.provenance import Status

RESEARCH_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = RESEARCH_ROOT.parent
DDRAGON_PATH = REPO_ROOT / "data" / "current" / "champions" / "Zaahen.json"
MANIFEST_PATH = REPO_ROOT / "data" / "current" / "manifest.json"


def make_report(bin_document, ddragon_document, rcp_document):
    meta = bin_document["_provenance"]
    patch = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))["patch"]
    return build_report(
        bin_document["objects"],
        url=meta["url"],
        content_version=meta["content_version"],
        sha256=meta["source_sha256"],
        ddragon=ddragon_document,
        rcp=rcp_document,
        ddragon_patch=patch,
    )


def by_parameter(report):
    return {item.parameter: item for item in report.comparisons}


def test_w_effective_cooldown_is_verified_across_sources(
    bin_document, ddragon_document, rcp_document
) -> None:
    report = make_report(bin_document, ddragon_document, rcp_document)
    item = by_parameter(report)["w.cooldown_seconds"]

    assert item.status is Status.VERIFIED
    assert item.cdragon == (14.0, 13.5, 13.0, 12.5, 12.0)
    assert item.ddragon == (14.0, 13.5, 13.0, 12.5, 12.0)
    assert item.rcp == (14.0, 13.5, 13.0, 12.5, 12.0)
    assert item.wiki == (14.0, 13.5, 13.0, 12.5, 12.0)
    assert "w.cooldown_seconds" not in report.blocked


def test_legacy_cooldown_is_diagnostic_only(bin_document, ddragon_document, rcp_document) -> None:
    report = make_report(bin_document, ddragon_document, rcp_document)

    compared = {item.parameter for item in report.comparisons}
    assert "w.cooldown_time_legacy" not in compared
    legacy = next(value for value in report.values if value.parameter == "w.cooldown_time_legacy")
    assert legacy.ranks == (16.0, 15.0, 14.0, 13.0, 12.0)
    assert legacy.status is Status.SOURCE_EXPLICIT


def test_q_cooldown_is_verified_across_sources(
    bin_document, ddragon_document, rcp_document
) -> None:
    report = make_report(bin_document, ddragon_document, rcp_document)
    item = by_parameter(report)["q.cooldown_seconds"]

    assert item.status is Status.VERIFIED
    assert item.cdragon == (10.0, 9.0, 8.0, 7.0, 6.0)


def test_ad_growth_conflict_does_not_touch_data_dragon(
    bin_document, ddragon_document, rcp_document
) -> None:
    before = DDRAGON_PATH.read_bytes()
    report = make_report(bin_document, ddragon_document, rcp_document)
    item = by_parameter(report)["champion.attack_damage_per_level"]

    assert item.status is Status.CONFLICT
    assert item.cdragon == (4.0,)
    assert item.ddragon == (0.0,)
    assert item.wiki == (4.0,)
    assert DDRAGON_PATH.read_bytes() == before
    assert report.champion_stat_block_present is True


def test_q_monster_damage_conflict(bin_document, ddragon_document, rcp_document) -> None:
    report = make_report(bin_document, ddragon_document, rcp_document)
    item = by_parameter(report)["q.monster_damage_multiplier"]

    assert item.status is Status.CONFLICT
    assert item.cdragon == (1.0,)
    assert item.wiki == (2.0,)
    assert "semantic" in item.missing_evidence.lower() or item.missing_evidence


def test_passive_ad_per_stack_conflict(bin_document, ddragon_document, rcp_document) -> None:
    report = make_report(bin_document, ddragon_document, rcp_document)
    item = by_parameter(report)["passive.ad_per_stack"]

    assert item.status is Status.CONFLICT
    assert item.cdragon == pytest.approx((0.028,))
    assert item.wiki == (2.95,)
    assert "2.8" in item.missing_evidence


def test_q_base_damage_is_corroborated_by_the_wiki(
    bin_document, ddragon_document, rcp_document
) -> None:
    report = make_report(bin_document, ddragon_document, rcp_document)
    item = by_parameter(report)["q.first_hit_base_damage"]

    assert item.status is Status.CORROBORATED
    assert item.cdragon == (15.0, 30.0, 45.0, 60.0, 75.0)
    assert item.ddragon is None
    assert item.wiki == (15.0, 30.0, 45.0, 60.0, 75.0)


def test_r_damage_calculation_is_derived_not_verified(
    bin_document, ddragon_document, rcp_document
) -> None:
    report = make_report(bin_document, ddragon_document, rcp_document)
    calculation = report.calculations[0]

    assert calculation.result == 450.0
    assert calculation.expression == "250 + 2 * 100"
    assert calculation.status is Status.DERIVED
    assert calculation.blocked is False
    assert "inferred" in calculation.notes


def test_blocked_parameters_are_scoped(bin_document, ddragon_document, rcp_document) -> None:
    report = make_report(bin_document, ddragon_document, rcp_document)

    assert set(report.blocked) == {
        "champion.attack_damage_per_level",
        "passive.ad_per_stack",
        "q.monster_damage_multiplier",
    }


def test_report_does_not_mutate_inputs(bin_document, ddragon_document, rcp_document) -> None:
    bin_before = deepcopy(bin_document["objects"])
    ddragon_before = deepcopy(ddragon_document)
    rcp_before = deepcopy(rcp_document)

    make_report(bin_document, ddragon_document, rcp_document)

    assert bin_document["objects"] == bin_before
    assert ddragon_document == ddragon_before
    assert rcp_document == rcp_before


def test_scalar_and_series_comparison() -> None:
    item = classify("cost", (25.0, 25.0, 25.0), (25.0, 25.0, 25.0), None, (25.0,))

    assert item.status is Status.VERIFIED


def test_agreement_between_two_derivations_is_corroborated() -> None:
    item = classify("x", (1.0, 2.0), (1.0, 2.0), None, None)

    assert item.status is Status.CORROBORATED


def test_absent_source_is_unverified() -> None:
    item = classify("x", None, None, None, (1.0,))

    assert item.status is Status.UNVERIFIED
