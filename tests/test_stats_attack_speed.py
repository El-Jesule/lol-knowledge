"""Attack speed: base, ratio, level growth, bonus sources and cap (attack-speed.md)."""

from __future__ import annotations

from dataclasses import replace
from fractions import Fraction as F

import pytest

from lol_knowledge.errors import StatsError
from lol_knowledge.kit import sheet_stats
from lol_knowledge.stats import (
    STATS,
    Contribution,
    DerivedRecords,
    Label,
    StatBlocked,
    build_stat_sheet,
    format_text,
    to_dict,
)
from stats_helpers import PATCH, champion, item

GAME_VERSION = ".".join(PATCH.split(".")[:2])


def records(ratio: float | None = 0.625, champion_id: str = "Testchamp", game_version=None):
    game_version = game_version or GAME_VERSION
    fields = {} if ratio is None else {"attackspeedratio": F(str(ratio))}
    return DerivedRecords(
        "lol-knowledge/derived/champion-records.json",
        f"{game_version}.1+test",
        game_version,
        {champion_id: fields},
    )


def speed_items(*percents: float):
    return [item(str(index), ("attack_speed", "percent", p)) for index, p in enumerate(percents)]


def test_registry_declares_the_rule_cap_and_routing():
    speed, bonus = STATS["attack_speed"], STATS["attack_speed_bonus"]
    assert speed.resolvable and bonus.resolvable
    assert speed.cap == 3 and bonus.cap is None
    assert speed.routes_to == "attack_speed_bonus"
    assert speed.item_kind == bonus.item_kind == "percent"
    assert speed.rules == bonus.rules == "lol-knowledge/mechanics/attack-speed.md"


def test_level_one_without_bonus_is_the_official_base_and_needs_no_ratio():
    sheet = build_stat_sheet(champion(), 1)
    speed = sheet["attack_speed"]
    assert speed.total() == F("0.625")
    assert speed.label is Label.OFFICIAL
    assert [c.scope for c in speed.contributions] == ["base"]
    assert sheet["attack_speed_bonus"].total() == 0
    assert not speed.capped


def test_level_growth_is_bonus_attack_speed_with_the_growth_formula():
    # attack-speed.md: 2.5 % x 9 x (0.7025 + 0.0175 x 9) = 19.35 % at level 10.
    sheet = build_stat_sheet(champion(), 10, derived=records())
    bonus = sheet["attack_speed_bonus"]
    assert bonus.total() == F("0.1935")
    assert bonus.label is Label.DERIVED
    (growth,) = bonus.contributions
    assert growth.scope == "base"
    assert growth.source == f"data:champion:Testchamp stats.attackspeedperlevel ({PATCH})"
    assert growth.note == "growth to level 10"
    speed = sheet["attack_speed"]
    assert speed.total() == F("0.625") + F("0.625") * F("0.1935")
    assert speed.scoped("base") == F("0.625")
    assert speed.scoped("bonus") == F("0.625") * F("0.1935")
    assert speed.label is Label.DERIVED


def test_zero_growth_stays_official_and_adds_no_ratio_contribution():
    sheet = build_stat_sheet(champion(stats={"attackspeedperlevel": 0}), 18)
    assert sheet["attack_speed_bonus"].label is Label.OFFICIAL
    assert sheet["attack_speed"].total() == F("0.625")
    assert len(sheet["attack_speed"].contributions) == 1


def test_wiki_example_with_a_ratio_different_from_the_base():
    # Twisted Fate in the wiki: 0.625 + 0.651 x 97.35 / 100.
    sheet = build_stat_sheet(champion(), 1, speed_items(97.35), derived=records(0.651))
    speed = sheet["attack_speed"]
    assert speed.total() == F("0.625") + F("0.651") * F("0.9735")
    assert round(float(speed.total()), 7) == 1.2587485
    scaled = speed.contributions[-1]
    assert scaled.label is Label.DERIVED
    assert scaled.note == "ratio 0.651 x bonus 97.35%"
    assert "Testchamp.attackspeedratio (16.20.1+test) x attack_speed_bonus" in scaled.source


def test_items_add_to_the_bonus_with_a_note_and_stack_additively():
    sheet = build_stat_sheet(champion(), 1, speed_items(25, 30), derived=records())
    bonus = sheet["attack_speed_bonus"]
    assert bonus.total() == F("0.55")
    assert [c.note for c in bonus.contributions] == ["declared as attack_speed"] * 2
    assert [c.scope for c in bonus.contributions] == ["bonus", "bonus"]
    assert sheet["attack_speed"].total() == F("0.625") * F("1.55")
    assert sheet["attack_speed"].label is Label.DERIVED


def test_flat_attack_speed_items_are_rejected():
    with pytest.raises(StatsError, match="kind 'flat' is not supported for attack_speed_bonus"):
        build_stat_sheet(champion(), 1, [item("1", ("attack_speed", "flat", 1))])


def test_extras_are_routed_to_the_bonus():
    extra = Contribution(F("0.4"), "bonus", "kit:Testchamp P", Label.DERIVED)
    sheet = build_stat_sheet(champion(), 1, derived=records(), extras=[("attack_speed", extra)])
    assert sheet["attack_speed_bonus"].contributions == (extra,)
    assert sheet["attack_speed"].total() == F("0.625") * F("1.4")
    with pytest.raises(StatsError, match="not a fraction"):
        too_much = Contribution(F(2), "bonus", "x", Label.DERIVED)
        build_stat_sheet(champion(), 1, extras=[("attack_speed", too_much)])


@pytest.mark.parametrize("derived", [None, records(None), records(champion_id="Other")])
def test_bonus_without_a_ratio_blocks_the_total_only(derived):
    sheet = build_stat_sheet(champion(), 2, derived=derived)
    speed = sheet["attack_speed"]
    assert speed.status == "blocked"
    assert "needs the attack speed ratio" in speed.blocked
    assert "Testchamp.attackspeedratio" in speed.blocked
    with pytest.raises(StatBlocked):
        speed.total()
    assert sheet["attack_speed_bonus"].status == "resolved"
    assert "attack_speed: blocked: bonus attack speed 0.018" in format_text(sheet)


def test_ratio_from_another_client_patch_is_pending():
    sheet = build_stat_sheet(champion(), 1, speed_items(10), derived=records(game_version="16.19"))
    speed = sheet["attack_speed"]
    assert speed.label is Label.PENDING
    assert speed.contributions[-1].note.endswith("; client 16.19 record used with snapshot 16.20.1")
    assert "(client 16.19 record used with snapshot 16.20.1)" in format_text(sheet)


def test_total_is_capped_but_scopes_are_not():
    sheet = build_stat_sheet(champion(), 1, speed_items(100, 100, 100, 100), derived=records())
    speed = sheet["attack_speed"]
    assert speed.scoped("bonus") == F("2.5")
    assert speed.total() == 3
    assert speed.capped
    assert sheet["attack_speed_bonus"].total() == 4
    assert "  attack_speed: 3 (base 0.625 + bonus 2.5) (capped at 3) [Derivado]" in format_text(
        sheet
    )
    report = to_dict(sheet)["stats"]["attack_speed"]
    assert report["total"] == 3.0 and report["capped"] is True and report["cap"] == 3.0
    assert sheet_stats(sheet)[0]["attack_speed"] == 3


def test_reaching_the_cap_exactly_is_not_capped():
    # 0.625 + 0.625 x 3.8 = 3.0
    sheet = build_stat_sheet(champion(), 1, speed_items(100, 100, 100, 80), derived=records())
    assert sheet["attack_speed"].total() == 3
    assert not sheet["attack_speed"].capped
    assert to_dict(sheet)["stats"]["health"]["capped"] is False
    assert to_dict(sheet)["stats"]["health"]["cap"] is None


def test_belveth_has_no_attack_speed_cap():
    sheet = build_stat_sheet(
        champion("Belveth", stats={"attackspeed": F("0.67"), "attackspeedperlevel": F(0)}),
        1,
        speed_items(100, 100, 100, 100),
        derived=records(0.67, champion_id="Belveth"),
    )
    speed = sheet["attack_speed"]
    assert speed.definition.cap is None
    assert not speed.capped
    assert speed.total() == F("0.67") + F("0.67") * F(4)  # 3.35 > 3.0
    assert speed.label is Label.DERIVED


def test_zeri_caps_attack_speed_at_1_5_and_converts_excess_to_bonus_ad():
    # Base AS = 0.658, ratio = 0.625 -> reaches 1.5 at (1.5 - 0.658) / 0.625 = 134.72% bonus AS.
    # With 200% bonus AS, excess is 65.28% -> +65.28 * 0.6 = +39.168 bonus AD.
    zeri = champion("Zeri", stats={"attackspeed": F("0.658"), "attackdamage": F(56)})
    sheet = build_stat_sheet(
        zeri,
        1,
        speed_items(100, 100),
        derived=records(0.625, champion_id="Zeri"),
    )
    speed = sheet["attack_speed"]
    assert speed.definition.cap == F(3, 2)
    assert speed.capped
    assert speed.total() == F(3, 2)
    assert sheet["attack_damage"].scoped("bonus") == F("0.6528") * F(60)
    assert sheet["attack_damage"].total() == F(56) + F("39.168")
    assert sheet["attack_damage"].label is Label.DERIVED


def test_jhin_fixed_attack_speed_and_whisper_total_ad_amplifier():
    # At level 18: fixed AS = 0.625 * (1 + 0.03 * 17) = 0.94375 regardless of bonus AS.
    # Whisper AD % at level 18 = 44% + 35% * crit_chance + 30% * bonus_as.
    jhin = champion(
        "Jhin",
        stats={"attackspeed": F("0.625"), "attackspeedperlevel": F(0), "attackdamage": F(61)},
    )
    items = [item("1", ("attack_speed", "percent", 50)), item("2", ("crit_chance", "percent", 40))]
    sheet = build_stat_sheet(jhin, 18, items, derived=records(0.0, champion_id="Jhin"))
    speed = sheet["attack_speed"]
    assert speed.total() == F("0.625") * F("1.51")  # 0.94375 (~0.944)
    assert speed.scoped("bonus") == 0
    assert speed.label is Label.DERIVED
    # Whisper % = 44 + 40*0.35 + 50*0.30 = 44 + 14 + 15 = 73% of 61 = 44.53 bonus AD
    assert sheet["attack_damage"].scoped("bonus") == F(61) * F(73, 100)
    assert sheet["attack_damage"].total() == F(61) * F(173, 100)


def test_sion_and_graves_resolve_attack_speed_without_pending():
    sion = build_stat_sheet(champion("Sion"), 1)
    assert sion["attack_speed"].total() == F("0.625")
    assert sion["attack_speed"].label is Label.OFFICIAL
    graves = build_stat_sheet(
        champion("Graves", stats={"attackspeed": F("0.475")}),
        1,
        speed_items(50),
        derived=records(0.49, champion_id="Graves"),
    )
    assert graves["attack_speed"].total() == F("0.475") + F("0.49") * F("0.5")
    assert graves["attack_speed"].label is Label.DERIVED
    assert any("Graves fires 2 shells before reloading" in note for note in graves.notes)


def test_missing_growth_field_is_an_error_above_level_one():
    base = champion()
    trimmed = {key: value for key, value in base.stats.items() if key != "attackspeedperlevel"}
    without = replace(base, stats=trimmed)
    assert build_stat_sheet(without, 1)["attack_speed"].total() == F("0.625")
    with pytest.raises(StatsError, match="stats.attackspeedperlevel is missing"):
        build_stat_sheet(without, 2)


def test_a_pending_bonus_source_weakens_the_scaled_total():
    extra = Contribution(F("0.2"), "bonus", "assumption", Label.PENDING)
    sheet = build_stat_sheet(champion(), 1, derived=records(), extras=[("attack_speed", extra)])
    assert sheet["attack_speed"].contributions[-1].label is Label.PENDING
    assert sheet["attack_speed"].label is Label.PENDING
