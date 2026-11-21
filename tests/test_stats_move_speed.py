"""Movement speed: (base + flat) x (1 + additive %), then soft caps (move-speed.md)."""

from __future__ import annotations

from fractions import Fraction as F
from pathlib import Path

import pytest

from lol_knowledge.cli import main
from lol_knowledge.stats import (
    STATS,
    Contribution,
    Label,
    Stacking,
    Unit,
    build_stat_sheet,
    format_text,
    to_dict,
)
from lol_knowledge.stats.registry import move_speed_soft_cap
from stats_helpers import champion, item

ROOT = Path(__file__).resolve().parents[1]
RULES = "lol-knowledge/mechanics/move-speed.md"


def test_registry_declares_flat_percentages_and_the_soft_cap():
    definition = STATS["move_speed"]
    assert definition.resolvable
    assert definition.stacking is Stacking.ADDITIVE
    assert definition.unit is Unit.AMOUNT
    assert definition.rules == RULES
    assert definition.percent_of == "flat"
    assert definition.soft_cap is move_speed_soft_cap
    assert definition.cap is None


@pytest.mark.parametrize(
    ("raw", "speed"),
    [
        (300, 300),
        (220, 220),
        (415, 415),
        (416, F("415.8")),
        (F("415.5"), F("415.4")),
        (490, 475),
        (491, F("475.5")),
        (600, 530),  # move-speed.md: 415 + 75 x 0.8 + 110 x 0.5
        (219, F("219.5")),
        (180, 200),
        (-10, 110),
    ],
)
def test_soft_caps(raw, speed):
    assert move_speed_soft_cap(F(raw)) == speed


def test_base_speed_is_official_and_not_soft_capped():
    speed = build_stat_sheet(champion(), 18)["move_speed"]
    assert speed.total() == 345 and speed.raw() == 345
    assert speed.label is Label.OFFICIAL
    assert not speed.soft_capped


def test_flat_items_add_to_the_base():
    speed = build_stat_sheet(champion(), 1, [item("1", ("move_speed", "flat", 45))])["move_speed"]
    assert speed.total() == 390
    assert speed.label is Label.OFFICIAL


def test_percentages_apply_to_every_flat_amount_whatever_the_item_order():
    items = [item("1", ("move_speed", "percent", 10)), item("2", ("move_speed", "flat", 45))]
    sheet = build_stat_sheet(champion(), 1, items)
    speed = sheet["move_speed"]
    converted = speed.contributions[-1]
    assert converted.value == F("39")  # 10 % of 345 + 45
    assert converted.note == "10% of flat 390"
    assert converted.source.startswith("data:item:1 ")
    assert speed.raw() == 429
    assert speed.total() == F(429) * F("0.8") + 83
    assert speed.soft_capped
    assert speed.label is Label.DERIVED  # the soft cap rule is derived
    assert "  move_speed: 426.2 (base 345 + bonus 84) (soft cap from 429) [Derivado]" in (
        format_text(sheet)
    )
    report = to_dict(sheet)["stats"]["move_speed"]
    assert report["raw"] == 429 and report["soft_capped"] is True and report["total"] == 426.2


def test_percentages_add_up_instead_of_compounding():
    items = [item(str(i), ("move_speed", "percent", 10)) for i in range(2)]
    speed = build_stat_sheet(champion(), 1, items)["move_speed"]
    assert speed.raw() == F(345) * F("1.2")


def test_extras_count_as_flat_amounts_for_percentages():
    extra = Contribution(F(20), "bonus", "kit:Testchamp P", Label.PENDING)
    sheet = build_stat_sheet(
        champion(), 1, [item("1", ("move_speed", "percent", 10))], extras=[("move_speed", extra)]
    )
    converted = sheet["move_speed"].contributions[-1]
    assert converted.value == F("36.5")  # 10 % of 345 + 20
    assert converted.label is Label.PENDING


def test_cassiopeia_passive_amplifies_flat_and_percent_move_speed_bonuses():
    # Without bonuses, base move speed stays Official.
    base_sheet = build_stat_sheet(champion("Cassiopeia", stats={"movespeed": 335}), 1)
    assert base_sheet["move_speed"].total() == 335
    assert base_sheet["move_speed"].label is Label.OFFICIAL

    # At level 11, Serpentine Grace amplification is 5% + 1.8% * 10 = 23%.
    # With +20 flat bonus and +10% bonus:
    # flat bonus becomes 20 + 20 * 0.23 = 24.6 -> total flat = 335 + 24.6 = 359.6
    # % bonus becomes 10% + 10% * 0.23 = 12.3% of 359.6 = 44.2308 -> raw = 403.8308
    items = [item("1", ("move_speed", "flat", 20)), item("2", ("move_speed", "percent", 10))]
    sheet = build_stat_sheet(champion("Cassiopeia", stats={"movespeed": 335}), 11, items)
    speed = sheet["move_speed"]
    assert speed.raw() == F("359.6") * F("1.123")
    assert speed.total() == F("403.8308")
    assert speed.label is Label.DERIVED


def test_other_soft_capped_stats_do_not_exist():
    assert [d.id for d in STATS.values() if d.soft_cap] == ["move_speed"]


def test_stats_command_with_mercurys_treads(capsys):
    code = main(
        ["stats", "--root", str(ROOT), "--champion", "Zaahen", "--level", "1", "--item", "3111"]
    )
    out = capsys.readouterr().out
    assert code == 0
    assert "  move_speed: 390 (base 345 + bonus 45) [Oficial]" in out
    assert "not modelled yet: none" in out
