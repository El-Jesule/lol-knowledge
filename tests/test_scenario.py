"""Ability scenarios: kit damage mitigated by the target's matching resistance."""

from __future__ import annotations

from fractions import Fraction as F
from pathlib import Path

import pytest

from lol_knowledge.errors import KitError, StatsError
from lol_knowledge.kit import load_kit, passive_contributions
from lol_knowledge.scenario import Target, evaluate_ability, target_from_sheet, target_from_values
from lol_knowledge.stats import (
    Label,
    build_stat_sheet,
    growth_multiplier,
    load_champion,
    load_issues,
    load_items,
    load_records,
)

ROOT = Path(__file__).resolve().parents[1]
KIT = load_kit(ROOT, "Zaahen")


def sheet(champion="Zaahen", level=16, items=("3036",), ranks=None, kit=KIT):
    data = load_champion(ROOT, champion)
    extras = passive_contributions(kit, ranks) if kit and ranks else ()
    return build_stat_sheet(
        data,
        level,
        load_items(ROOT, list(items)),
        load_issues(ROOT),
        {},
        load_records(ROOT),
        extras,
    )


def test_r_against_a_manual_target():
    attacker = sheet(ranks={"R": 3})
    target = target_from_values(F(150), F(50))
    outcome = evaluate_ability(KIT, attacker, "R", 3, target)
    (case,) = outcome.cases
    (part,) = case.parts
    assert part.part.raw == 620
    assert part.mitigation.resistance.effective == F("68.25")
    assert case.total == 620 * F(100, F("168.25"))
    assert outcome.label is Label.DERIVED


def test_without_learning_r_its_penetration_does_not_apply():
    attacker = sheet(ranks={"Q": 5})
    outcome = evaluate_ability(KIT, attacker, "Q", 5, target_from_values(F(150), F(50)))
    first = outcome.cases[0].parts[0].mitigation
    assert first.modifiers.percent_penetration == (F(35, 100),)
    assert first.resistance.effective == F("97.5")


def test_magic_parts_use_magic_resist_and_magic_penetration():
    attacker = sheet(items=("3135",), ranks={"R": 3})  # Void Staff: 40 % magic penetration
    target = target_from_values(F(100), F(80), max_health=F(2000))
    outcome = evaluate_ability(KIT, attacker, "E", 5, target, case="edge")
    physical, magic = outcome.cases[0].parts
    assert physical.mitigation.resistance.initial == 100
    assert physical.mitigation.modifiers.percent_penetration == (F(3, 10),)
    assert magic.mitigation.resistance.initial == 80
    assert magic.mitigation.resistance.effective == 48
    assert magic.part.raw == 120
    assert magic.mitigation.damage == 120 * F(100, 148)


def test_target_champion_is_resolved_with_its_sheet():
    defender = sheet("Ahri", 16, ("3047",), kit=None)
    target = target_from_sheet(defender)
    level = growth_multiplier(16)
    assert target.armor == 21 + F("4.2") * level + 25
    assert target.magic_resist == 30 + F("1.3") * level
    assert target.stats == {
        "bonus_health": 0,
        "max_health": 590 + 104 * level,
        "current_health": 590 + 104 * level,
    }
    assert target.label is Label.DERIVED
    assert target.description == "Ahri level 16 (3047)"
    assert target.kind == "champion"
    assert [item.id for item in target.items] == ["3047"]


def test_case_totals_add_their_parts():
    attacker = sheet(ranks={"R": 3})
    outcome = evaluate_ability(
        KIT, attacker, "E", 5, target_from_values(F(0), F(0), max_health=F(1000))
    )
    center, edge = outcome.cases
    assert center.id == "center" and edge.id == "edge"
    assert edge.total == sum(item.mitigation.damage for item in edge.parts)
    assert edge.total == (120 + F(35, 2)) * F(3, 2) + 60


def test_manual_target_needs_max_health_for_health_scaling():
    attacker = sheet(ranks={"R": 3})
    with pytest.raises(KitError, match="target:max_health"):
        evaluate_ability(KIT, attacker, "E", 5, target_from_values(F(100), F(50)), case="edge")


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"max_health": F(0)}, "max health must be positive"),
        ({"max_health": F(100), "current_health": F(101)}, "exceeds"),
        ({"current_health": F(-1)}, "must not be negative"),
    ],
)
def test_invalid_target_health(kwargs, message):
    with pytest.raises(StatsError, match=message):
        target_from_values(F(1), F(1), **kwargs)


def test_current_health_defaults_to_max_only_when_max_is_known():
    assert target_from_values(F(1), F(1), max_health=F(500)).stats["current_health"] == 500
    assert target_from_values(F(1), F(1)).stats == {}
    assert target_from_values(F(1), F(1), current_health=F(10)).stats == {"current_health": 10}


def test_a_pending_target_weakens_the_result_label():
    attacker = sheet(ranks={"R": 3})
    target = Target(F(100), F(50), {}, Label.PENDING, "pending target")
    assert evaluate_ability(KIT, attacker, "R", 3, target).label is Label.PENDING


def test_multi_target_and_area_ability_evaluation():
    ahri_kit = load_kit(ROOT, "Ahri")
    ahri_sheet = sheet("Ahri", 11, ("3089",), ranks={"Q": 5, "W": 3, "E": 2, "R": 2}, kit=ahri_kit)
    target = target_from_values(F(50), F(50), max_health=F(2000), kind="champion")

    # Ahri Q is uncapped AoE: hits all 4 targets when target_count=4.
    q_out = evaluate_ability(ahri_kit, ahri_sheet, "Q", 5, target, case="both", target_count=4)
    (q_case,) = q_out.cases
    assert q_case.aoe is True and q_case.max_targets is None
    assert q_case.targets_hit == 4
    assert q_case.secondary_total == q_case.primary_total * 3
    assert q_case.total == q_case.primary_total * 4
    assert q_out.label is Label.DERIVED

    # Ahri R is AoE capped at RMaxTargetsPerCast=3: hits 3 of 5 targets.
    r_out = evaluate_ability(ahri_kit, ahri_sheet, "R", 2, target, case="dash", target_count=5)
    (r_case,) = r_out.cases
    assert r_case.aoe is True and r_case.max_targets == 3
    assert r_case.targets_hit == 3
    assert r_case.total == r_case.primary_total * 3

    # Ahri W: W.one hits up to 3 distinct targets; W.all focuses 1 target.
    w_out = evaluate_ability(ahri_kit, ahri_sheet, "W", 3, target, target_count=3)
    w_one, w_all = w_out.cases
    assert w_one.targets_hit == 3 and w_one.total == w_one.primary_total * 3
    assert w_all.targets_hit == 1 and w_all.total == w_all.primary_total

    # Caitlyn Q.first has secondary_damage_ratio=0.6 (SecondaryMult): 1 primary + 2x 60% secondary.
    cait_kit = load_kit(ROOT, "Caitlyn")
    cait_sheet = sheet("Caitlyn", 11, (), ranks={"Q": 5}, kit=cait_kit)
    cait_q = evaluate_ability(
        cait_kit, cait_sheet, "Q", 5, target, case="first", target_count=3
    ).cases[0]
    assert cait_q.targets_hit == 3
    assert cait_q.secondary_damage_ratio == F("0.6")
    assert cait_q.secondary_total == cait_q.primary_total * 2 * F("0.6")
    assert cait_q.total == cait_q.primary_total * F("2.2")

    # Undeclared kit case with target_count > 1 evaluates against 1 target and marks PENDING.
    zaahen_r = evaluate_ability(KIT, sheet(ranks={"R": 3}), "R", 3, target, target_count=3)
    assert zaahen_r.cases[0].targets_hit == 1
    assert zaahen_r.label is Label.PENDING
    assert any("does not declare aoe or max_targets" in note for note in zaahen_r.notes)

    with pytest.raises(StatsError, match="target count must be an integer >= 1"):
        evaluate_ability(ahri_kit, ahri_sheet, "Q", 5, target, target_count=0)
