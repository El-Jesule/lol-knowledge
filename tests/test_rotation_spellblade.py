"""Spellblade in rotations: an ability charges the next basic attack (spellblade.md)."""

from __future__ import annotations

from fractions import Fraction as F
from pathlib import Path

import pytest

from lol_knowledge.errors import RotationError
from lol_knowledge.kit import load_kit, passive_contributions
from lol_knowledge.rotation import CritBase, Step, evaluate_rotation, parse_steps
from lol_knowledge.scenario import target_from_values
from lol_knowledge.stats import (
    Label,
    build_stat_sheet,
    load_champion,
    load_issues,
    load_items,
    load_records,
)

ROOT = Path(__file__).resolve().parents[1]
KIT = load_kit(ROOT, "Zaahen")
RANKS = {"Q": 5, "W": 1, "E": 5, "R": 3}
CRIT = CritBase(F(2), Label.DERIVED, "test record")


def sheet(*items, level=16):
    return build_stat_sheet(
        load_champion(ROOT, "Zaahen"),
        level,
        load_items(ROOT, list(items)),
        load_issues(ROOT),
        {},
        load_records(ROOT),
        passive_contributions(KIT, RANKS),
    )


def run(steps, *items):
    target = target_from_values(F(100), F(50), max_health=F(5000), kind="champion")
    return evaluate_rotation(
        KIT, sheet(*items), RANKS, target, parse_steps(steps), CRIT, holder_range="melee"
    )


def sources(step):
    return [part.source for part in step.parts]


def spellblade_part(step):
    (part,) = [part for part in step.parts if "Hoja encantada" in part.source]
    return part


# Steps


def test_attack_modifiers_parse_in_any_order():
    assert parse_steps("attack:nospellblade attack:crit:nospellblade attack:nospellblade:crit") == (
        Step("attack:nospellblade", spellblade=False),
        Step("attack:crit:nospellblade", crit=True, spellblade=False),
        Step("attack:nospellblade:crit", crit=True, spellblade=False),
    )
    assert parse_steps("attack:crit") == (Step("attack:crit", crit=True),)


@pytest.mark.parametrize("token", ["attack:crit:crit", "attack:fast", "attack:"])
def test_unknown_or_repeated_attack_modifiers_are_refused(token):
    with pytest.raises(RotationError, match="an attack takes crit and nospellblade"):
        parse_steps(token)


# When the empowered attack happens


def test_an_ability_charges_only_the_next_attack():
    outcome = run("attack Q.first_hit attack attack", "3078")
    first, _, empowered, after = outcome.steps
    assert not any("Hoja encantada" in source for source in sources(first) + sources(after))
    assert empowered.name == "basic attack with Spellblade"
    base_ad = sheet("3078")["attack_damage"].scoped("base")
    part = spellblade_part(empowered)
    assert part.raw == 2 * base_ad
    assert part.damage_type.value == "physical"
    assert part.source == "3078 spellblade (Hoja encantada)"


def test_two_abilities_charge_one_attack():
    outcome = run("Q.first_hit R attack attack", "3057")
    assert outcome.steps[2].name == "basic attack with Spellblade"
    assert outcome.steps[3].name == "basic attack"


def test_nospellblade_drops_the_charge():
    outcome = run("Q.first_hit attack:nospellblade attack", "3057")
    assert [step.name for step in outcome.steps[1:]] == ["basic attack", "basic attack"]


def test_the_spellblade_damage_is_not_a_critical_strike():
    outcome = run("Q.first_hit attack:crit", "3057")
    step = outcome.steps[1]
    assert step.name == "critical basic attack with Spellblade"
    assert spellblade_part(step).raw == sheet("3057")["attack_damage"].scoped("base")


def test_without_a_spellblade_item_nothing_changes():
    outcome = run("Q.first_hit attack", "3115")
    assert outcome.steps[1].name == "basic attack"


def test_two_spellblade_items_are_refused():
    with pytest.raises(RotationError, match="items 3057, 3078 all have Spellblade"):
        run("attack", "3057", "3078")


# Item formulas


def test_lich_bane_and_essence_reaver_formulas():
    lich = sheet("3100")
    part = spellblade_part(run("Q.first_hit attack", "3100").steps[1])
    expected = lich["attack_damage"].scoped("base") * F("0.75")
    assert part.raw == expected + lich["ability_power"].total() * F("0.45")
    assert part.damage_type.value == "magic"
    reaver = sheet("3508")
    part = spellblade_part(run("Q.first_hit attack", "3508").steps[1])
    crit = reaver["crit_chance"].total()
    assert crit == F("0.25")
    assert part.raw == reaver["attack_damage"].scoped("base") * F("1.25") + crit * 50


def test_dusk_and_dawn_repeats_the_on_hit_effects_as_pending():
    outcome = run("Q.first_hit attack", "2510", "3115")
    step = outcome.steps[1]
    nashor = [part for part in step.parts if part.source.startswith("3115 icathian-bite")]
    assert len(nashor) == 2
    assert nashor[0].raw == nashor[1].raw
    assert nashor[1].source.endswith(" - again by 2510 dusk-repeat")
    assert nashor[0].label is not Label.PENDING
    assert nashor[1].label is Label.PENDING
    data = sheet("2510", "3115")
    expected = data["attack_damage"].scoped("base") * F("0.75")
    assert spellblade_part(step).raw == expected + data["ability_power"].total() / 10
    assert "attacker 2510 dusk-heal: excluded, not applied" in outcome.notes


def test_bloodsong_mark_needs_the_timeline_and_weakens_the_rotation():
    outcome = run("Q.first_hit attack", "3877")
    assert "attacker 3877 bloodsong-mark: lasts 4 s; applied only with --timeline" in outcome.notes
    assert outcome.label is Label.PENDING


def test_terminus_shadow_is_corroborated_by_the_patch_notes():
    (part,) = [
        part for part in run("attack", "3302").steps[0].parts if part.source.startswith("3302")
    ]
    assert part.label is Label.DERIVED
