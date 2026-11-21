"""Ahri's kit: damage of her abilities and the recasts of Spirit Rush (phase 33)."""

from __future__ import annotations

import json
from fractions import Fraction as F
from pathlib import Path

import pytest

from lol_knowledge.damage import DamageType
from lol_knowledge.errors import KitError, RotationError
from lol_knowledge.kit import load_kit, passive_contributions
from lol_knowledge.kit.model import parse_kit
from lol_knowledge.rotation import CritBase, evaluate_rotation, parse_steps
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
KIT = load_kit(ROOT, "Ahri")
RANKS = {"Q": 5, "W": 3, "E": 2, "R": 2}
CRIT = CritBase(F(2), Label.DERIVED, "test record")


def sheet(*items, level=11):
    return build_stat_sheet(
        load_champion(ROOT, "Ahri"),
        level,
        load_items(ROOT, list(items)),
        load_issues(ROOT),
        {},
        load_records(ROOT),
        passive_contributions(KIT, RANKS),
    )


def run(steps, *items, timeline=False, mr=0):
    target = target_from_values(F(0), F(mr), max_health=F(10**6), kind="champion")
    return evaluate_rotation(
        KIT, sheet(*items), RANKS, target, parse_steps(steps), CRIT, timeline=timeline
    )


def ap(*items):
    return sheet(*items)["ability_power"].total()


def test_the_kit_has_the_five_slots_and_no_passive_damage():
    assert set(KIT.abilities) == {"P", "Q", "W", "E", "R"}
    assert KIT.abilities["P"].cases == ()
    assert KIT.label is Label.DERIVED


def test_orb_of_deception_is_magic_out_and_true_back():
    power = ap("3089")
    outcome = run("Q.out Q.back Q.both", "3089", mr=100)
    pass_damage = 135 + power / 2
    (out,), (back,), both = (step.parts for step in outcome.steps)
    assert (out.damage_type, out.raw) == (DamageType.MAGIC, pass_damage)
    assert (back.damage_type, back.raw, back.damage) == (DamageType.TRUE, pass_damage, pass_damage)
    assert [part.damage_type for part in both] == [DamageType.MAGIC, DamageType.TRUE]
    assert out.damage == pass_damage / 2  # 100 magic resist


def test_fox_fire_hits_after_the_first_deal_forty_percent():
    power = ap("3089")
    (one,), three = (step.parts for step in run("W.one W.all", "3089").steps)
    first = 80 + power * F("0.4")
    assert one.raw == first
    assert [part.raw for part in three] == [first, first * F("0.4"), first * F("0.4")]


def test_charm_and_spirit_rush_damage():
    power = ap("3089")
    charm, rush = run("E.hit R.dash", "3089").steps
    assert charm.parts[0].raw == 120 + power * F("0.85")
    assert rush.parts[0].raw == 125 + power * F("0.35")


def test_spirit_rush_recasts_twice_a_second_apart_within_fifteen_seconds():
    outcome = run("R.dash wait:1 R.recast wait:13.5 R.recast", timeline=True)
    assert [step.time for step in outcome.steps if step.step.slot] == [0, 1, F("14.5")]
    with pytest.raises(RotationError, match=r"R has no recast left \(2 per cast\)"):
        run("R.dash wait:1 R.recast wait:1 R.recast wait:1 R.recast", timeline=True)
    with pytest.raises(RotationError, match=r"the next R is available at 1 s \(now 0.5 s\)"):
        run("R.dash wait:0.5 R.recast", timeline=True)
    with pytest.raises(RotationError, match=r"the recast window \(15 s\) closed at 15 s"):
        run("R.dash wait:15.5 R.recast", timeline=True)


def test_recasts_open_again_with_a_new_cast():
    machine = run("R.dash wait:1 R.recast wait:1 R.recast", timeline=True)
    assert len(machine.steps) == 5
    with pytest.raises(RotationError, match="R is on cooldown"):
        run("R.dash wait:1 R.recast wait:1 R.recast R.dash", timeline=True)


def _document():
    return json.loads((ROOT / "lol-knowledge/champions/Ahri/kit.json").read_text("utf-8"))


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"max_recasts": 0}, "max_recasts must be a positive integer"),
        ({"max_recasts": True}, "max_recasts must be a positive integer"),
        ({"recast_interval_seconds": 0}, "recast_interval_seconds must be a positive number"),
        ({"recast_interval_seconds": "1"}, "recast_interval_seconds must be a positive number"),
    ],
)
def test_recast_settings_are_checked(changes, message):
    document = _document()
    document["abilities"]["R"].update(changes)
    with pytest.raises(KitError, match=message):
        parse_kit(document)


def test_recast_settings_need_a_recast_case():
    for key, value in (("max_recasts", 2), ("recast_interval_seconds", 1)):
        document = _document()
        document["abilities"]["E"][key] = value
        with pytest.raises(KitError, match="need a recast case"):
            parse_kit(document)
    assert parse_kit(_document()).abilities["R"].max_recasts == 2
    assert parse_kit(_document()).abilities["Q"].max_recasts == 1


def test_the_interval_counts_from_the_last_dash():
    with pytest.raises(RotationError, match=r"the next R is available at 2 s \(now 1.5 s\)"):
        run("R.dash wait:1 R.recast wait:0.5 R.recast", timeline=True)


def test_spirit_rush_and_orb_multi_target_rotation():
    from lol_knowledge.rotation_report import format_text, to_dict
    from lol_knowledge.stats import Contribution

    target = target_from_values(F(0), F(0), max_health=F(2000), kind="champion")
    ahri = sheet("3089")
    # Single-target vs 3-target rotation: R.dash (max_targets=3), Q.both (aoe=True),
    # W.all (max_targets=1), E.hit (max_targets=1), attack (1 target).
    single = evaluate_rotation(
        KIT, ahri, RANKS, target, parse_steps("R.dash Q.both W.all E.hit attack"), CRIT
    )
    multi = evaluate_rotation(
        KIT,
        ahri,
        RANKS,
        target,
        parse_steps("R.dash Q.both W.all E.hit attack"),
        CRIT,
        target_count=5,
    )
    # R.dash caps at 3 targets (RMaxTargetsPerCast=3); Q.both hits all 5 targets;
    # W.all, E.hit and attack hit only the primary target (1).
    assert [step.targets_hit for step in multi.steps] == [3, 5, 1, 1, 1]
    assert multi.steps[0].total == single.steps[0].total * 3
    assert multi.steps[1].total == single.steps[1].total * 5
    assert multi.steps[2].total == single.steps[2].total
    assert multi.steps[3].total == single.steps[3].total
    assert multi.steps[4].total == single.steps[4].total
    # Primary target health only subtracts primary_total, matching the 1-target rotation!
    assert multi.primary_total == single.total
    assert multi.remaining_health == single.remaining_health

    # Per-step @<N> override in parse_steps: R.dash@2 hits 2 targets, Q.both@3 hits 3.
    per_step = evaluate_rotation(
        KIT, ahri, RANKS, target, parse_steps("R.dash@2 Q.both@3 E.hit@4"), CRIT
    )
    assert [step.targets_hit for step in per_step.steps] == [2, 3, 1]
    assert per_step.steps[0].total == single.steps[0].total * 2
    assert per_step.steps[1].total == single.steps[1].total * 3
    assert per_step.steps[2].total == single.steps[3].total

    # Area omnivamp against minions is 33% for Q and R (aoe=True), 100% for E and W (aoe=False).
    vamp_sheet = build_stat_sheet(
        load_champion(ROOT, "Ahri"),
        11,
        (),
        load_issues(ROOT),
        {},
        load_records(ROOT),
        (("omnivamp", Contribution(F("0.15"), "bonus", "test omnivamp", Label.OFFICIAL)),),
    )
    minion_target = target_from_values(F(0), F(0), max_health=F(5000), kind="minion")
    vamp_out = evaluate_rotation(
        KIT, vamp_sheet, RANKS, minion_target, parse_steps("R.dash E.hit"), CRIT, target_count=3
    )
    r_part = vamp_out.steps[0].parts[0]
    e_part = vamp_out.steps[1].parts[0]
    assert r_part.targets_hit == 3
    assert r_part.healing.omnivamp == F("0.05")  # 15% / 3 = 5% against minions
    assert r_part.healing.amount == r_part.damage * F("0.05")
    assert r_part.healing.label is Label.DERIVED
    assert e_part.targets_hit == 1
    assert e_part.healing.omnivamp == F("0.15")  # 100% for single-target E
    assert e_part.healing.amount == e_part.damage * F("0.15")
    assert e_part.healing.label is Label.DERIVED

    text = format_text(multi, ahri, target, CRIT)
    assert "targets: 5" in text
    assert "x3 targets =" in text
    assert "x5 targets =" in text
    report = to_dict(multi, ahri, target, CRIT)
    assert report["target_count"] == 5
    assert report["steps"][0]["targets_hit"] == 3
    assert report["steps"][1]["targets_hit"] == 5
