"""Unit tests for Track A hot-path memoization (PERF-01)."""

from __future__ import annotations

from dataclasses import replace
from fractions import Fraction as F

import pytest

from lol_knowledge.damage import DamageType, mitigate
from lol_knowledge.errors import StatsError
from lol_knowledge.kit import parse_kit, sheet_stats
from lol_knowledge.passives import PassiveCombat
from lol_knowledge.rotation.models import Part
from lol_knowledge.scenario import target_from_values
from lol_knowledge.stats import (
    STATS,
    Contribution,
    Label,
    Stacking,
    StatBlocked,
    StatDef,
    StatSheet,
    StatValue,
    Unit,
    build_stat_sheet,
    with_bonus,
)
from stats_helpers import champion


def _kit_with_passives(*effects: dict) -> dict:
    return {
        "schema": "lol-champion-kit/1",
        "champion": "Testchamp",
        "label": "Derivado",
        "game_version": "16.23",
        "content_version": "16.23.test",
        "abilities": {
            "P": {
                "name": "Pasiva de prueba",
                "max_rank": 1,
                "cases": [],
                "passive_stats": [],
                "passive_effects": list(effects),
                "not_modelled": [],
            }
        },
    }


def test_stat_value_precomputes_additive_capped_and_soft_capped():
    base = Contribution(F(350), "base", "champion", Label.OFFICIAL)
    bonus = Contribution(F(150), "bonus", "items", Label.DERIVED)
    extra = Contribution(F(100), "bonus", "buff", Label.OFFICIAL)

    ms = StatValue(STATS["move_speed"], (base, bonus))
    assert ms.status == "resolved"
    assert ms.raw() == F(500)
    assert ms.scoped("base") == F(350)
    assert ms.scoped("bonus") == F(150)
    assert ms.scoped("other") == F(0)
    assert ms.soft_capped is True
    assert ms.capped is False
    expected_ms = STATS["move_speed"].soft_cap(F(500))
    assert ms.total() == expected_ms
    assert isinstance(ms.total(), F)
    assert ms.label is Label.DERIVED
    assert ms.sources() == (F(350), F(150))

    updated = replace(ms, contributions=(base, bonus, extra))
    assert updated.raw() == F(600)
    assert updated.scoped("bonus") == F(250)
    assert updated.total() == STATS["move_speed"].soft_cap(F(600))

    crit = StatValue(
        STATS["crit_chance"],
        (
            Contribution(F(75, 100), "bonus", "items", Label.OFFICIAL),
            Contribution(F(50, 100), "bonus", "items", Label.OFFICIAL),
        ),
    )
    assert crit.capped is True
    assert crit.soft_capped is False
    assert crit.raw() == F(125, 100)
    assert crit.total() == F(1)


def test_stat_value_multiplicative_blocked_and_pending():
    tenacity = StatValue(
        STATS["tenacity"],
        (
            Contribution(F(30, 100), "bonus", "boots", Label.OFFICIAL),
            Contribution(F(20, 100), "bonus", "rune", Label.DERIVED),
        ),
    )
    assert tenacity.status == "resolved"
    assert tenacity.total() == 1 - F(70, 100) * F(80, 100)
    assert tenacity.label is Label.DERIVED
    with pytest.raises(StatsError, match="scopes"):
        tenacity.scoped("base")

    empty_mult = StatValue(STATS["tenacity"], ())
    assert empty_mult.total() == F(0)

    blocked = StatValue(
        STATS["attack_damage"],
        (Contribution(F(60), "base", "champ", Label.OFFICIAL),),
        blocked="missing growth",
    )
    assert blocked.status == "blocked"
    assert blocked.soft_capped is False
    assert blocked.capped is False
    assert blocked.label is Label.OFFICIAL
    for accessor in (
        blocked.total,
        blocked.raw,
        lambda: blocked.scoped("base"),
        blocked.sources,
    ):
        with pytest.raises(StatBlocked):
            accessor()

    pending_def = StatDef("test_pend", "Pendiente", Stacking.ADDITIVE, Unit.AMOUNT, None, "no rule")
    pending = StatValue(pending_def, (Contribution(F(10), "bonus", "s", Label.DERIVED),))
    assert pending.status == "pending"
    assert pending.label is Label.DERIVED
    with pytest.raises(StatBlocked):
        pending.total()


def test_stat_sheet_cached_sheet_stats_and_copy_safety():
    sheet = build_stat_sheet(champion(), 1)
    cached_first = sheet.cached_sheet_stats()
    cached_second = sheet.cached_sheet_stats()
    assert cached_first is cached_second

    values_copy, origin_copy = sheet_stats(sheet)
    assert values_copy == cached_first[0]
    assert origin_copy == cached_first[1]
    assert values_copy is not cached_first[0]
    assert origin_copy is not cached_first[1]

    values_copy["attack_damage"] = F(99999)
    origin_copy["attack_damage"] = ("tampered", Label.PENDING)
    assert sheet.cached_sheet_stats()[0]["attack_damage"] == sheet["attack_damage"].total()
    assert sheet.cached_sheet_stats()[1]["attack_damage"] == (
        "attack_damage",
        sheet["attack_damage"].label,
    )

    buffed = with_bonus(sheet, "attack_damage", F(25), "buff", Label.DERIVED)
    assert buffed.cached_sheet_stats() is not cached_first
    assert buffed.cached_sheet_stats()[0]["attack_damage"] == sheet["attack_damage"].total() + F(25)


def test_part_precomputes_factors_and_recomputes_on_replace():
    mitigation = mitigate(F(200), DamageType.PHYSICAL, F(100))
    assert mitigation.damage == F(100)

    simple = Part(
        kind="attack",
        source="basic attack",
        damage_type=DamageType.PHYSICAL,
        raw=F(200),
        mitigation=mitigation,
        dealt=(),
        taken=(),
        label=Label.OFFICIAL,
    )
    assert simple.dealt_factor == F(1)
    assert simple.taken_factor == F(1)
    assert simple.primary_damage == F(100)
    assert simple.secondary_damage == F(0)
    assert simple.damage == F(100)

    aoe = Part(
        kind="ability",
        source="Q",
        damage_type=DamageType.PHYSICAL,
        raw=F(200),
        mitigation=mitigation,
        dealt=(("a", F(10)), ("b", F(5))),
        taken=(("c", F(-20)),),
        label=Label.DERIVED,
        targets_hit=3,
        secondary_damage_ratio=F(1, 2),
        flat_reduction=F(12),
    )
    expected_dealt = F(115, 100)
    expected_taken = F(80, 100)
    unit = F(100) * expected_dealt * expected_taken
    assert aoe.dealt_factor == expected_dealt
    assert aoe.taken_factor == expected_taken
    assert aoe.primary_damage == unit - F(12)
    assert aoe.secondary_damage == unit * 2 * F(1, 2)
    assert aoe.damage == (unit - F(12)) + unit

    reduced = replace(aoe, flat_reduction=F(200))
    assert reduced.primary_damage == F(0)
    assert reduced.secondary_damage == unit
    assert reduced.damage == unit

    secondary_only = replace(aoe, hits_primary=False, flat_reduction=F(0))
    assert secondary_only.primary_damage == F(0)
    assert secondary_only.secondary_damage == unit * 3 * F(1, 2)
    assert secondary_only.damage == unit * 3 * F(1, 2)


def test_passive_combat_skips_sheet_stats_when_no_effect_triggers(monkeypatch):
    kit = parse_kit(
        _kit_with_passives(
            {
                "id": "proc_hit",
                "name": "Third hit",
                "kind": "damage_proc",
                "trigger": "every_n_attacks",
                "every": 3,
                "damage_type": "magic",
                "formula": {"op": "constant", "value": 50},
                "label": "Derivado",
                "source": "client",
            },
            {
                "id": "heal_takedown",
                "name": "Takedown heal",
                "kind": "heal",
                "trigger": "on_champion_takedown",
                "formula": {"op": "constant", "value": 80},
                "label": "Derivado",
                "source": "client",
            },
            {
                "id": "shield_cast",
                "name": "Cast shield",
                "kind": "shield",
                "trigger": "on_ability_cast",
                "shield_type": "normal",
                "duration_seconds": 2,
                "formula": {"op": "constant", "value": 60},
                "label": "Derivado",
                "source": "client",
            },
            {
                "id": "mana_restore",
                "name": "Kill mana",
                "kind": "resource_restore",
                "resource": "mana",
                "trigger": "on_any_kill",
                "formula": {"op": "constant", "value": 30},
                "label": "Derivado",
                "source": "client",
            },
        )
    )
    sheet = build_stat_sheet(champion(), 1)
    target = target_from_values(F(50), F(50), max_health=F(1000), kind="champion")
    combat = PassiveCombat(kit, target, {}, timeline=True)

    calls = 0
    original_cached = StatSheet.cached_sheet_stats

    def spy_cached(self: StatSheet):
        nonlocal calls
        calls += 1
        return original_cached(self)

    def fail_sheet_stats(_sheet: StatSheet):
        raise AssertionError("sheet_stats() should not be called by PassiveCombat")

    monkeypatch.setattr(StatSheet, "cached_sheet_stats", spy_cached)
    monkeypatch.setattr("lol_knowledge.kit.sheet_stats", fail_sheet_stats)

    assert combat.active_stat_modifiers(F(0), 1) == ([], [])
    assert combat.on_step(None, True, F(0), sheet) == []
    assert combat.on_step_heals(None, True, False, F(0), sheet) == []
    assert combat.on_step_shields(None, True, F(0), sheet) == []
    assert combat.on_step_resources(None, True, False, F(0), sheet) == []
    assert calls == 0

    # Trigger proc on 3rd attack, heal on takedown, shield on ability cast, resource on kill.
    assert combat.on_step(None, True, F(1), sheet) == []
    assert calls == 0
    procs = combat.on_step(None, True, F(2), sheet)
    assert len(procs) == 1 and procs[0].raw == F(50)
    assert calls == 1

    heals = combat.on_step_heals("Q", True, True, F(3), sheet)
    assert len(heals) == 1 and heals[0].raw == F(80)
    assert calls == 2

    shields = combat.on_step_shields("Q", True, F(4), sheet)
    assert len(shields) == 1 and shields[0].raw == F(60)
    assert calls == 3

    restores = combat.on_step_resources("Q", True, True, F(5), sheet)
    assert len(restores) == 1 and restores[0].amount == F(30)
    assert calls == 4
