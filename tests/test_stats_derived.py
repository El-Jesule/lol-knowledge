"""Derived client records replace defective Data Dragon fields, never official data."""

from __future__ import annotations

import copy
from fractions import Fraction as F
from pathlib import Path

import pytest

from lol_knowledge.errors import StatsError
from lol_knowledge.stats import (
    Label,
    build_stat_sheet,
    growth_multiplier,
    load_records,
    parse_records,
)
from stats_helpers import PATCH, ad_growth_issue, champion

ROOT = Path(__file__).resolve().parents[1]
DOCUMENT = {
    "schema": "lol-derived-champion-records/1",
    "label": "Derivado",
    "content_version": "16.20.1+branch.releases-16-20.content.release",
    "game_version": "16.20",
    "champions": {
        "Testchamp": {"fields": {"attackdamageperlevel": 3.5, "hpperlevel": 999.0}},
    },
}


def records(**changes):
    document = copy.deepcopy(DOCUMENT)
    document.update(changes)
    return parse_records(document)


def test_matching_patch_gives_derived_label():
    sheet = build_stat_sheet(champion(), 11, issues=[ad_growth_issue()], derived=records())
    ad = sheet["attack_damage"]
    assert ad.total() == 63 + F("3.5") * growth_multiplier(11)
    assert ad.label is Label.DERIVED
    assert "champion-records.json Testchamp.attackdamageperlevel" in ad.contributions[1].source


def test_other_patch_gives_pending_label_and_note():
    other = records(content_version="16.22.1+x", game_version="16.22")
    ad = build_stat_sheet(champion(), 11, issues=[ad_growth_issue()], derived=other)[
        "attack_damage"
    ]
    assert ad.label is Label.PENDING
    assert "client 16.22 record used with snapshot 16.20.1" in ad.contributions[1].note


def test_assumption_wins_over_the_derived_record():
    sheet = build_stat_sheet(
        champion(),
        11,
        issues=[ad_growth_issue()],
        assumptions={"attackdamageperlevel": "4"},
        derived=records(),
    )
    assert sheet["attack_damage"].total() == 63 + 4 * growth_multiplier(11)


def test_derived_records_never_override_fields_without_an_issue():
    sheet = build_stat_sheet(champion(), 11, issues=[ad_growth_issue()], derived=records())
    assert sheet["health"].total() == 640 + 114 * growth_multiplier(11)


def test_without_a_record_the_stat_stays_blocked():
    empty = records(champions={})
    ad = build_stat_sheet(champion(), 11, issues=[ad_growth_issue()], derived=empty)[
        "attack_damage"
    ]
    assert ad.status == "blocked"
    assert "No derived record for Testchamp" in ad.blocked


def test_level_one_ignores_growth_records():
    sheet = build_stat_sheet(champion(), 1, issues=[ad_growth_issue()], derived=records())
    assert sheet["attack_damage"].total() == 63
    assert sheet["attack_damage"].label is Label.OFFICIAL


def test_matches_patch():
    assert records().matches_patch(PATCH)
    assert not records().matches_patch("16.2.1")


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"schema": "x"}, "schema"),
        ({"label": "Oficial"}, "label"),
        ({"game_version": "16"}, "game_version"),
        ({"content_version": "16.21.1+x"}, "does not match"),
        ({"champions": []}, "'champions'"),
        ({"champions": {"A": {}}}, "'fields'"),
        ({"champions": {"A": {"fields": {"charisma": 1}}}}, "unknown field"),
        ({"champions": {"A": {"fields": {"hp": -1}}}}, "non-negative"),
        ({"champions": {"A": {"fields": {"hp": True}}}}, "non-negative"),
    ],
)
def test_rejects_malformed_records(changes, message):
    with pytest.raises(StatsError, match=message):
        records(**changes)


def test_project_records_cover_the_snapshot():
    project = load_records(ROOT)
    assert project is not None
    assert project.game_version == "16.22"
    assert project.value("Zaahen", "attackdamageperlevel") == 4
    assert project.value("Senna", "attackdamageperlevel") is None
    assert len(project.champions) == 173


def test_missing_records_file_returns_none(tmp_path):
    assert load_records(tmp_path) is None


def test_invalid_records_json_is_an_error(tmp_path):
    path = tmp_path / "lol-knowledge" / "derived" / "champion-records.json"
    path.parent.mkdir(parents=True)
    path.write_text("{", encoding="utf-8")
    with pytest.raises(StatsError, match="JSON"):
        load_records(tmp_path)
