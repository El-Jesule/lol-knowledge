"""Critical strike chance: Data Dragon base, additive sources and 100 % cap."""

from __future__ import annotations

from dataclasses import replace
from fractions import Fraction as F
from pathlib import Path

import pytest

from lol_knowledge.cli import main
from lol_knowledge.errors import StatsError
from lol_knowledge.kit import sheet_stats
from lol_knowledge.stats import (
    STATS,
    Contribution,
    Label,
    Stacking,
    StatBlocked,
    Unit,
    build_stat_sheet,
    format_text,
    to_dict,
)
from stats_helpers import PATCH, champion, item

ROOT = Path(__file__).resolve().parents[1]
RULES = "lol-knowledge/mechanics/critical-strike.md"


def crit_items(*percents: float):
    return [item(str(index), ("crit_chance", "percent", p)) for index, p in enumerate(percents)]


def test_registry_declares_an_additive_capped_fraction():
    definition = STATS["crit_chance"]
    assert definition.resolvable
    assert definition.stacking is Stacking.ADDITIVE
    assert definition.unit is Unit.FRACTION
    assert definition.cap == 1
    assert definition.rules == RULES
    assert definition.item_kind == "percent"


def test_champion_base_is_the_official_zero_of_data_dragon():
    crit = build_stat_sheet(champion(), 18)["crit_chance"]
    assert crit.total() == 0
    assert crit.label is Label.OFFICIAL
    (base,) = crit.contributions
    assert base.scope == "base"
    assert base.source == f"data:champion:Testchamp stats.crit ({PATCH})"


def test_item_sources_add_up():
    crit = build_stat_sheet(champion(), 1, crit_items(25, 30))["crit_chance"]
    assert crit.total() == F("0.55")
    assert crit.scoped("bonus") == F("0.55")
    assert crit.label is Label.OFFICIAL
    assert not crit.capped


def test_total_is_capped_at_one_and_the_excess_stays_in_the_scope():
    sheet = build_stat_sheet(champion(), 1, crit_items(60, 50))
    crit = sheet["crit_chance"]
    assert crit.total() == 1
    assert crit.scoped("bonus") == F("1.1")
    assert crit.capped
    assert "  crit_chance: 100% (base 0% + bonus 110%) (capped at 100%) [Oficial]" in format_text(
        sheet
    )
    report = to_dict(sheet)["stats"]["crit_chance"]
    assert report["cap"] == 1.0 and report["capped"] is True and report["bonus"] == 1.1
    stats, _ = sheet_stats(sheet)
    assert stats["crit_chance"] == 1
    assert stats["bonus_crit_chance"] == F("1.1")


def test_exactly_one_hundred_percent_is_not_capped():
    crit = build_stat_sheet(champion(), 1, crit_items(50, 50))["crit_chance"]
    assert crit.total() == 1 and not crit.capped


@pytest.mark.parametrize("field_name", ["crit", "critperlevel"])
def test_a_non_zero_data_dragon_field_blocks_the_stat(field_name):
    data = champion(stats={field_name: 5})
    sheet = build_stat_sheet(data, 1, crit_items(20))
    crit = sheet["crit_chance"]
    assert crit.status == "blocked"
    assert crit.blocked == (
        f"Testchamp has non-zero stats.{field_name} in Data Dragon; its unit is not "
        f"documented (see {RULES})"
    )
    assert [c.value for c in crit.contributions] == [F("0.2")]
    with pytest.raises(StatBlocked):
        crit.total()
    assert sheet["health"].status == "resolved"


@pytest.mark.parametrize("field_name", ["crit", "critperlevel"])
def test_a_missing_data_dragon_field_is_an_error(field_name):
    base = champion()
    stats = {key: value for key, value in base.stats.items() if key != field_name}
    with pytest.raises(StatsError, match=f"stats.{field_name} is missing"):
        build_stat_sheet(replace(base, stats=stats), 1)


PASSIVE = f"{RULES} ({{}} passive)"


@pytest.mark.parametrize("champion_id", ["Yasuo", "Yone"])
def test_passives_double_crit_chance(champion_id):
    sheet = build_stat_sheet(champion(champion_id), 1, crit_items(30))
    crit = sheet["crit_chance"]
    assert crit.total() == F("0.6")
    assert crit.label is Label.DERIVED
    doubled = crit.contributions[-1]
    assert doubled.value == F("0.3")
    assert doubled.source == PASSIVE.format(champion_id)
    assert doubled.note == "passive doubles critical strike chance (30% x 2)"
    assert sheet["attack_damage"].scoped("bonus") == 0
    assert sheet.notes == ()


@pytest.mark.parametrize("champion_id", ["Yasuo", "Yone"])
def test_excess_crit_chance_becomes_half_an_attack_damage_per_percent(champion_id):
    sheet = build_stat_sheet(champion(champion_id), 1, crit_items(35, 25))
    crit = sheet["crit_chance"]
    assert crit.total() == 1 and crit.capped and crit.scoped("bonus") == F("1.2")
    attack_damage = sheet["attack_damage"]
    (converted,) = [c for c in attack_damage.contributions if c.scope == "bonus"]
    assert converted.value == 10  # 20 % excess x 0.5
    assert converted.source == PASSIVE.format(champion_id)
    assert converted.note == "excess critical strike chance 20% x 0.5 per 1%"
    assert converted.label is Label.DERIVED
    assert attack_damage.total() == 63 + 10


def test_reaching_exactly_one_hundred_percent_converts_nothing():
    sheet = build_stat_sheet(champion("Yasuo"), 1, crit_items(50))
    assert sheet["crit_chance"].total() == 1
    assert sheet["attack_damage"].scoped("bonus") == 0
    assert [c.source for c in sheet["attack_damage"].contributions] == [
        f"data:champion:Yasuo stats.attackdamage ({PATCH})"
    ]


def test_a_pending_source_weakens_the_passive():
    pending = Contribution(F("0.6"), "bonus", "assumption", Label.PENDING)
    sheet = build_stat_sheet(champion("Yone"), 1, extras=[("crit_chance", pending)])
    assert sheet["crit_chance"].contributions[-1].label is Label.PENDING
    assert sheet["attack_damage"].label is Label.PENDING


def test_blocked_crit_chance_blocks_the_converted_attack_damage():
    sheet = build_stat_sheet(champion("Yasuo", stats={"crit": 5}), 1)
    assert sheet["crit_chance"].status == "blocked"
    assert sheet["attack_damage"].blocked == (
        "Yasuo's passive converts excess crit chance into attack damage, and crit chance is blocked"
    )


def test_other_champions_are_not_doubled():
    sheet = build_stat_sheet(champion("Zaahen"), 1, crit_items(60))
    assert sheet["crit_chance"].total() == F("0.6")
    assert sheet["crit_chance"].label is Label.OFFICIAL
    assert sheet["attack_damage"].scoped("bonus") == 0


def test_stats_command_with_infinity_edge(capsys):
    code = main(
        ["stats", "--root", str(ROOT), "--champion", "Zaahen", "--level", "18", "--item", "3031"]
    )
    out = capsys.readouterr().out
    assert code == 0
    assert "  crit_chance: 25% (base 0% + bonus 25%) [Oficial]" in out
    assert "  crit_chance: pending" not in out


def test_stats_command_doubles_yasuo_crit_chance(capsys):
    code = main(
        ["stats", "--root", str(ROOT), "--champion", "Yasuo", "--level", "1", "--item", "3031"]
    )
    out = capsys.readouterr().out
    assert code == 0
    assert "  crit_chance: 50% (base 0% + bonus 50%) [Derivado]" in out
