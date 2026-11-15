"""Metric tests: effective health and ability cooldowns."""

from __future__ import annotations

from fractions import Fraction as F

import pytest

from lol_knowledge.stats import (
    DataIssue,
    Label,
    ability_cooldowns,
    build_stat_sheet,
    effective_health,
)
from stats_helpers import champion, item


def test_effective_health_matches_the_source_formula():
    sheet = build_stat_sheet(champion(), 1)
    # S1: (1 + R / 100) x health
    assert effective_health(sheet, "physical").value == 640 * (1 + F(36, 100))
    assert effective_health(sheet, "magic").value == 640 * (1 + F(32, 100))
    assert effective_health(sheet, "true").value == 640


def test_effective_health_labels():
    level_one = build_stat_sheet(champion(), 1)
    assert effective_health(level_one, "physical").label is Label.DERIVED
    assert effective_health(level_one, "true").label is Label.OFFICIAL


def test_negative_resistance_never_halves_effective_health_more_than_the_floor():
    sheet = build_stat_sheet(champion(stats={"armor": -20}), 1)
    result = effective_health(sheet, "physical").value
    assert result == 640 * F(6, 7)  # multiplier 2 - 100/120 = 7/6
    assert result > 640 / 2


def test_effective_health_is_blocked_by_a_blocked_resistance():
    issue = DataIssue(
        "armor-issue", "data_dragon", "16.20.1", "armorperlevel", None, "open", "s", "d.md"
    )
    sheet = build_stat_sheet(champion(), 5, issues=[issue])
    physical = effective_health(sheet, "physical")
    assert physical.value is None
    assert "armor-issue" in physical.blocked
    assert effective_health(sheet, "magic").value is not None


def test_cooldowns_without_haste_are_the_official_values():
    result = ability_cooldowns(build_stat_sheet(champion(), 1))
    assert result.haste == 0
    assert result.label is Label.OFFICIAL
    assert [spell.effective for spell in result.spells] == [spell.base for spell in result.spells]
    assert [spell.slot for spell in result.spells] == ["Q", "W", "E", "R"]


@pytest.mark.parametrize(("haste", "factor"), [(100, F(1, 2)), (200, F(1, 3)), (10, F(10, 11))])
def test_cooldowns_follow_the_haste_formula(haste, factor):
    sheet = build_stat_sheet(champion(), 1, [item("1", ("ability_haste", "flat", haste))])
    result = ability_cooldowns(sheet)
    assert result.factor == factor
    assert result.spells[0].effective == tuple(value * factor for value in (10, 9, 8, 7, 6))
    assert result.label is Label.DERIVED


def test_haste_from_several_sources_adds_up():
    items = [item("1", ("ability_haste", "flat", 40)), item("2", ("ability_haste", "flat", 60))]
    assert ability_cooldowns(build_stat_sheet(champion(), 1, items)).factor == F(1, 2)
