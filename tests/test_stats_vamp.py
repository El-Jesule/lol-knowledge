"""Life steal and omnivamp as stat sheet totals (life-steal-and-omnivamp.md)."""

from __future__ import annotations

from fractions import Fraction as F
from pathlib import Path

import pytest

from lol_knowledge.errors import StatsError
from lol_knowledge.kit import sheet_stats
from lol_knowledge.stats import STATS, Label, Stacking, Unit, build_stat_sheet, load_champion
from lol_knowledge.stats import load_items as load_curated_items
from stats_helpers import champion, item

ROOT = Path(__file__).resolve().parents[1]
RULES = "lol-knowledge/mechanics/life-steal-and-omnivamp.md"


@pytest.mark.parametrize("stat_id", ["life_steal", "omnivamp"])
def test_vamp_stats_are_additive_fractions_with_a_rule(stat_id):
    definition = STATS[stat_id]
    assert definition.resolvable
    assert definition.stacking is Stacking.ADDITIVE
    assert definition.unit is Unit.FRACTION
    assert definition.rules == RULES
    assert definition.cap is None


def test_no_source_is_an_official_zero():
    sheet = build_stat_sheet(champion(), 18)
    for stat_id in ("life_steal", "omnivamp"):
        assert sheet[stat_id].total() == 0
        assert sheet[stat_id].label is Label.OFFICIAL


def test_sources_add_up_without_a_cap():
    items = [
        item("1", ("life_steal", "percent", 15)),
        item("2", ("life_steal", "percent", 10), ("omnivamp", "percent", 2.5)),
        item("3", ("omnivamp", "percent", 5)),
    ]
    sheet = build_stat_sheet(champion(), 1, items)
    assert sheet["life_steal"].total() == F("0.25")
    assert sheet["omnivamp"].total() == F("0.075")
    assert sheet["life_steal"].scoped("bonus") == F("0.25")
    stats, _ = sheet_stats(sheet)
    assert stats["life_steal"] == F("0.25") and stats["omnivamp"] == F("0.075")


@pytest.mark.parametrize(
    ("stats", "message"),
    [
        (("life_steal", "flat", 10), "not supported"),
        (("omnivamp", "percent", 150), "fraction"),
    ],
)
def test_invalid_vamp_items(stats, message):
    with pytest.raises(StatsError, match=message):
        build_stat_sheet(champion(), 1, [item("1", stats)])


def test_blade_of_the_ruined_king_life_steal_is_official():
    sheet = build_stat_sheet(load_champion(ROOT, "Zaahen"), 1, load_curated_items(ROOT, ["3153"]))
    life_steal = sheet["life_steal"]
    assert life_steal.total() == F("0.1")
    assert life_steal.label is Label.OFFICIAL
    assert life_steal.contributions[0].source == "data:item:3153 ddragon_stat (16.22.1)"
