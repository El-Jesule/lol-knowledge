"""Tenacity: item sources multiply within group A (tenacity.md)."""

from __future__ import annotations

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
    Unit,
    build_stat_sheet,
    format_text,
    to_dict,
)
from stats_helpers import champion, item

ROOT = Path(__file__).resolve().parents[1]
RULES = "lol-knowledge/mechanics/tenacity.md"
GROUP_NOTE = f"stacking group not declared; multiplied with items as group A (see {RULES})"


def tenacity_items(*percents: float):
    return [item(str(index), ("tenacity", "percent", p)) for index, p in enumerate(percents)]


def test_registry_declares_a_multiplicative_fraction_with_a_rule():
    definition = STATS["tenacity"]
    assert definition.resolvable
    assert definition.stacking is Stacking.MULTIPLICATIVE
    assert definition.unit is Unit.FRACTION
    assert definition.rules == RULES
    assert definition.item_kind == "percent"


def test_no_source_is_an_official_zero():
    tenacity = build_stat_sheet(champion(), 18)["tenacity"]
    assert tenacity.total() == 0
    assert tenacity.label is Label.OFFICIAL
    assert tenacity.contributions == ()


def test_item_sources_multiply():
    # tenacity.md: 1 - 0.7 x 0.8 = 44 %, not 50 %.
    sheet = build_stat_sheet(champion(), 1, tenacity_items(30, 20))
    tenacity = sheet["tenacity"]
    assert tenacity.total() == F("0.44")
    assert tenacity.label is Label.OFFICIAL
    assert "  tenacity: 44% [Oficial]" in format_text(sheet)
    report = to_dict(sheet)["stats"]["tenacity"]
    assert report["stacking"] == "multiplicative" and report["exact"] == "11/25"
    assert "base" not in report
    assert sheet_stats(sheet)[0]["tenacity"] == F("0.44")


def test_full_tenacity_from_one_source_is_full():
    assert build_stat_sheet(champion(), 1, tenacity_items(100, 30))["tenacity"].total() == 1


def test_non_item_sources_have_no_declared_group_and_are_pending():
    extra = Contribution(F("0.2"), "bonus", "kit:Testchamp P", Label.DERIVED, "while channelling")
    sheet = build_stat_sheet(champion(), 1, tenacity_items(30), extras=[("tenacity", extra)])
    tenacity = sheet["tenacity"]
    added = tenacity.contributions[-1]
    assert added.value == F("0.2") and added.source == "kit:Testchamp P"
    assert added.label is Label.PENDING
    assert added.note == f"while channelling; {GROUP_NOTE}"
    assert tenacity.total() == F("0.44")
    assert tenacity.label is Label.PENDING


def test_a_note_free_extra_gets_only_the_group_note():
    extra = Contribution(F("0.1"), "bonus", "x", Label.OFFICIAL)
    sheet = build_stat_sheet(champion(), 1, extras=[("tenacity", extra)])
    assert sheet["tenacity"].contributions[0].note == GROUP_NOTE


def test_other_extras_keep_their_label():
    extra = Contribution(F("0.1"), "bonus", "x", Label.OFFICIAL)
    sheet = build_stat_sheet(champion(), 1, extras=[("life_steal", extra)])
    assert sheet["life_steal"].contributions == (extra,)


@pytest.mark.parametrize(
    ("stats", "message"),
    [(("tenacity", "flat", 30), "not supported"), (("tenacity", "percent", 130), "fraction")],
)
def test_invalid_tenacity_items(stats, message):
    with pytest.raises(StatsError, match=message):
        build_stat_sheet(champion(), 1, [item("1", stats)])


def test_mercurys_treads_from_the_catalog(capsys):
    code = main(
        ["stats", "--root", str(ROOT), "--champion", "Zaahen", "--level", "1", "--item", "3111"]
    )
    out = capsys.readouterr().out
    assert code == 0
    assert "  tenacity: 30% [Oficial]" in out
    assert "  magic_resist: 52 (base 32 + bonus 20) [Oficial]" in out
