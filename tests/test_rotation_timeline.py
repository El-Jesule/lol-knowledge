"""Rotations with a timeline: attack interval, cooldowns, recasts and waits (timeline.md)."""

from __future__ import annotations

import json
from fractions import Fraction as F
from pathlib import Path

import pytest

from lol_knowledge.cli import main
from lol_knowledge.errors import KitError, RotationError
from lol_knowledge.kit import load_kit, passive_contributions
from lol_knowledge.kit.model import parse_kit
from lol_knowledge.rotation import CritBase, Step, evaluate_rotation, parse_steps
from lol_knowledge.scenario import target_from_values
from lol_knowledge.stats import (
    Label,
    ability_cooldowns,
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


def sheet(*items):
    return build_stat_sheet(
        load_champion(ROOT, "Zaahen"),
        16,
        load_items(ROOT, list(items)),
        load_issues(ROOT),
        {},
        load_records(ROOT),
        passive_contributions(KIT, RANKS),
    )


def run(steps, *items, timeline=True):
    target = target_from_values(F(0), F(0), max_health=F(10**6), kind="champion")
    return evaluate_rotation(
        KIT,
        sheet(*items),
        RANKS,
        target,
        parse_steps(steps),
        CRIT,
        holder_range="melee",
        timeline=timeline,
    )


def interval(*items):
    return 1 / sheet(*items)["attack_speed"].total()


def cooldown(slot, *items):
    spells = {spell.slot: spell for spell in ability_cooldowns(sheet(*items)).spells}
    return spells[slot].effective[RANKS[slot] - 1]


# Steps


def test_wait_steps_parse_and_are_checked():
    assert parse_steps("wait:0.5 wait:2") == (
        Step("wait:0.5", wait=F("0.5")),
        Step("wait:2", wait=F(2)),
    )
    for token in ("wait", "wait:-1", "wait:abc", "wait:1:2"):
        with pytest.raises(RotationError, match="use wait:<seconds>"):
            parse_steps(token)
    with pytest.raises(RotationError, match="longer than 0 s"):
        parse_steps("wait:0")


def test_waits_need_the_timeline():
    with pytest.raises(RotationError, match="waits need the timeline"):
        run("wait:1 attack", timeline=False)


# Times


def test_attacks_are_spaced_by_the_attack_interval_and_abilities_do_not_wait():
    outcome = run("attack attack Q.first_hit attack wait:0.25 attack")
    step = interval()
    assert [s.time for s in outcome.steps] == [0, step, step, 2 * step, 2 * step, 3 * step]
    assert outcome.steps[4].name == "wait" and outcome.steps[4].parts == ()


def test_a_wait_longer_than_the_interval_delays_the_next_attack():
    outcome = run("attack wait:5 attack")
    assert outcome.steps[2].time == 5


def test_duration_and_damage_per_second():
    outcome = run("attack attack attack")
    assert outcome.duration == 2 * interval()
    assert outcome.damage_per_second == outcome.total / outcome.duration
    assert outcome.timeline.attack_interval == interval()
    assert run("attack").damage_per_second is None


def test_without_the_timeline_nothing_has_a_time():
    outcome = run("attack Q.first_hit Q.first_hit", timeline=False)
    assert [s.time for s in outcome.steps] == [None, None, None]
    assert outcome.timeline is None and outcome.duration is None


# Cooldowns and recasts


def test_a_cast_on_cooldown_is_an_error():
    with pytest.raises(RotationError, match=r"Q is on cooldown until .* s \(now 0 s\)"):
        run("Q.first_hit Q.first_hit")
    wait = cooldown("Q")
    outcome = run(f"Q.first_hit wait:{float(wait)} Q.first_hit")
    assert outcome.steps[2].time == wait


def test_a_recast_needs_a_cast_and_its_window():
    outcome = run("Q.first_hit wait:3.5 Q.recast")
    assert outcome.steps[2].time == F("3.5")
    with pytest.raises(RotationError, match="has not been cast to recast it"):
        run("Q.recast")
    with pytest.raises(RotationError, match=r"the recast window \(4 s\) closed at 4 s"):
        run("Q.first_hit wait:4.5 Q.recast")
    with pytest.raises(RotationError, match=r"Q has no recast left \(1 per cast\)"):
        run("Q.first_hit Q.recast Q.recast")


def test_spellblade_respects_its_cooldown():
    outcome = run("Q.first_hit attack Q.recast attack wait:1.5 E.center attack", "3078")
    names = [s.name for s in outcome.steps if s.step.slot is None and s.step.wait is None]
    assert names == [
        "basic attack with Spellblade",
        "basic attack",
        "basic attack with Spellblade",
    ]


# Kit declarations


def _kit(**ability):
    document = json.loads(
        (ROOT / "lol-knowledge/champions/Zaahen/kit.json").read_text(encoding="utf-8")
    )
    document["abilities"]["W"].update(ability)
    return document


@pytest.mark.parametrize(
    ("ability", "message"),
    [
        ({"recast_window_seconds": 4}, "needs a recast case"),
        ({"recast_window_seconds": 0}, "must be a positive number"),
    ],
)
def test_recast_declarations_are_checked(ability, message):
    with pytest.raises(KitError, match=message):
        parse_kit(_kit(**ability))


def test_the_recast_flag_must_be_a_boolean():
    document = _kit()
    document["abilities"]["W"]["cases"][0]["recast"] = "yes"
    with pytest.raises(KitError, match="recast must be true or false"):
        parse_kit(document)


# CLI


def test_cli_prints_times_and_damage_per_second(capsys):
    args = [
        "rotation", "--champion", "Zaahen", "--level", "16", "--learned", "Q=5",
        "--steps", "attack Q.first_hit attack", "--timeline", "--target-armor", "0",
        "--target-mr", "0", "--target-max-health", "5000", "--root", str(ROOT),
    ]  # fmt: skip
    assert main(args) == 0
    out = capsys.readouterr().out
    assert "step 1 attack (basic attack) at 0 s:" in out
    assert "damage per second:" in out
    assert main([*args, "--json"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["steps"][2]["time"] == pytest.approx(float(interval()))
    assert report["timeline"]["duration"] == pytest.approx(float(interval()))
