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
