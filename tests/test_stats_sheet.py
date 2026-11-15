"""Stat sheet tests on synthetic champions and items."""

from __future__ import annotations

from fractions import Fraction as F

import pytest

from lol_knowledge.errors import StatsError
from lol_knowledge.stats import (
    Label,
    StatBlocked,
    build_stat_sheet,
    champion_from_document,
    growth_multiplier,
    items_from_model,
)
from stats_helpers import PATCH, ad_growth_issue, champion, champion_document, item


def test_level_one_is_official_data():
    sheet = build_stat_sheet(champion(), 1)
    assert sheet["health"].total() == 640
    assert sheet["armor"].total() == 36
    assert sheet["magic_resist"].total() == 32
    assert sheet["health"].label is Label.OFFICIAL
    assert sheet["ability_power"].total() == 0


def test_growth_applies_from_level_two():
    sheet = build_stat_sheet(champion(), 11)
    expected = 640 + 114 * growth_multiplier(11)
    assert sheet["health"].total() == expected == F("1640.35")
    assert sheet["health"].label is Label.DERIVED
    assert sheet["health"].scoped("base") == expected
    assert sheet["health"].scoped("bonus") == 0


def test_zero_growth_stays_official():
    sheet = build_stat_sheet(champion(stats={"spellblockperlevel": 0}), 11)
    assert sheet["magic_resist"].total() == 32
    assert sheet["magic_resist"].label is Label.OFFICIAL


def test_open_issue_blocks_the_affected_stat_only_above_level_one():
    issues = [ad_growth_issue()]
    level_one = build_stat_sheet(champion(), 1, issues=issues)
    assert level_one["attack_damage"].total() == 63
    assert any("does not affect level 1" in note for note in level_one.notes)

    sheet = build_stat_sheet(champion(), 11, issues=issues)
    assert sheet["attack_damage"].status == "blocked"
    assert "--assume attackdamageperlevel" in sheet["attack_damage"].blocked
    with pytest.raises(StatBlocked):
        sheet["attack_damage"].total()
    assert sheet["health"].status == "resolved"


def test_assumption_unblocks_with_pending_label():
    sheet = build_stat_sheet(
        champion(), 11, issues=[ad_growth_issue()], assumptions={"attackdamageperlevel": "4"}
    )
    assert sheet["attack_damage"].total() == 63 + 4 * growth_multiplier(11)
    assert sheet["attack_damage"].label is Label.PENDING
    assert sheet.assumptions == {"attackdamageperlevel": 4}


def test_issue_for_other_champion_or_patch_does_not_apply():
    for issue in (ad_growth_issue(champions=("Other",)), ad_growth_issue(patch="16.21.1")):
        sheet = build_stat_sheet(champion(), 11, issues=[issue])
        assert sheet["attack_damage"].status == "resolved"


@pytest.mark.parametrize(
    ("assumptions", "message"),
    [
        ({"hpperlevel": "1"}, "only fields with an open data issue"),
        ({"attackdamageperlevel": "-1"}, "negative"),
        ({"attackdamageperlevel": "abc"}, "not a number"),
    ],
)
def test_invalid_assumptions(assumptions, message):
    with pytest.raises(StatsError, match=message):
        build_stat_sheet(champion(), 11, issues=[ad_growth_issue()], assumptions=assumptions)


def test_items_add_bonus_and_stack_by_rule():
    items = [
        item("1", ("health", "flat", 200), ("ability_haste", "flat", 10)),
        item("2", ("armor_penetration_percent", "percent", 35), ("lethality", "flat", 10)),
        item("3", ("armor_penetration_percent", "percent", 30), ("lethality", "flat", 18)),
    ]
    sheet = build_stat_sheet(champion(), 1, items)
    assert sheet["health"].total() == 840
    assert sheet["health"].scoped("bonus") == 200
    assert sheet["ability_haste"].total() == 10
    assert sheet["lethality"].total() == 28
    pen = sheet["armor_penetration_percent"]
    assert pen.sources() == (F(35, 100), F(30, 100))
    assert pen.total() == 1 - F(65, 100) * F(70, 100)
    with pytest.raises(StatsError, match="scopes"):
        pen.scoped("bonus")


def test_item_kind_must_match_a_resolvable_stat():
    with pytest.raises(StatsError, match="not supported"):
        build_stat_sheet(champion(), 1, [item("1", ("armor", "percent", 10))])


def test_pending_stat_keeps_contributions_without_a_total():
    sheet = build_stat_sheet(champion(), 1, [item("1", ("move_speed", "percent", 4))])
    move_speed = sheet["move_speed"]
    assert move_speed.status == "pending"
    assert [c.value for c in move_speed.contributions] == [345, F(4, 100)]
    with pytest.raises(StatBlocked):
        move_speed.total()


@pytest.mark.parametrize(
    ("stats", "message"),
    [
        (("charisma", "flat", 1), "unknown stat"),
        (("health", "ratio", 1), "unknown kind"),
        (("armor_penetration_percent", "percent", 150), "fraction"),
    ],
)
def test_invalid_item_stats(stats, message):
    with pytest.raises(StatsError, match=message):
        build_stat_sheet(champion(), 1, [item("1", stats)])


def test_items_must_match_the_champion_patch():
    with pytest.raises(StatsError, match="from 16.19.1"):
        build_stat_sheet(champion(), 1, [item("1", ("health", "flat", 1), version="16.19.1")])


def test_non_mana_champion_blocks_mana():
    sheet = build_stat_sheet(champion(partype="Energía"), 5, [item("1", ("mana", "flat", 300))])
    assert sheet["mana"].status == "blocked"
    assert "Energía" in sheet["mana"].blocked
    assert sheet["health"].status == "resolved"


def test_unknown_locale_is_rejected():
    data = champion_from_document(champion_document(), patch=PATCH, locale="xx_XX")
    with pytest.raises(StatsError, match="locale"):
        build_stat_sheet(data, 1)


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"id": "../x"}, "unsupported champion id"),
        ({"stats": {"hp": float("inf")}}, "finite"),
        ({"spells": []}, "spells"),
        (
            {"spells": [{"id": "x", "name": "x", "cooldown": [1, 2], "maxrank": 5}] * 4},
            "one value per rank",
        ),
        (
            {"spells": [{"id": "x", "name": "x", "cooldown": [-1], "maxrank": 1}] * 4},
            "negative",
        ),
    ],
)
def test_champion_document_validation(overrides, message):
    document = champion_document()
    if "stats" in overrides:
        document["stats"].update(overrides.pop("stats"))
    document.update(overrides)
    with pytest.raises(StatsError, match=message):
        champion_from_document(document, patch=PATCH, locale="es_ES")


def test_missing_base_field_is_an_error():
    data = champion()
    stats = dict(data.stats)
    del stats["hp"]
    broken = type(data)(**{**data.__dict__, "stats": stats})
    with pytest.raises(StatsError, match="stats.hp"):
        build_stat_sheet(broken, 1)


def test_uncurated_items_are_rejected():
    model = {"game_version": PATCH, "objects": [{"id": "1", "name": "a", "stats": []}]}
    assert items_from_model(model, ["1"])[0].stats == ()
    with pytest.raises(StatsError, match="curated"):
        items_from_model(model, ["2"])


def test_item_sources_must_be_official():
    model = {
        "game_version": PATCH,
        "objects": [
            {
                "id": "1",
                "name": "a",
                "stats": [{"id": "health", "kind": "flat", "value": 1, "source": {"kind": "wiki"}}],
            }
        ],
    }
    with pytest.raises(StatsError, match="unsupported stat source"):
        items_from_model(model, ["1"])
