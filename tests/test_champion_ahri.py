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
