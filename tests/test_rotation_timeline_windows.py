"""Yun Tal's Flurry, stack windows and the Spellblade window on the timeline (timeline.md)."""

from __future__ import annotations

from dataclasses import replace
from fractions import Fraction as F
from pathlib import Path

import pytest

from lol_knowledge.errors import StatsError
from lol_knowledge.kit import load_kit, passive_contributions
from lol_knowledge.rotation import CritBase, _Rotation, evaluate_rotation, parse_steps
from lol_knowledge.scenario import target_from_values
from lol_knowledge.stats import (
    Label,
    build_stat_sheet,
    effect_amount,
    load_champion,
    load_issues,
    load_items,
    load_records,
    with_bonus,
)
from lol_knowledge.stats.sheet import ATTACK_SPEED_RATIO

ROOT = Path(__file__).resolve().parents[1]
KIT = load_kit(ROOT, "Zaahen")
RANKS = {"Q": 5, "W": 1, "E": 5, "R": 3}
CRIT = CritBase(F(2), Label.DERIVED, "test record")
TIMER = (
    "timeline: the time to the next attack uses the attack speed just after each attack; "
    "whether the game recomputes it when the attack speed changes before the next attack is "
    "not verified"
)


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


def run(steps, *items, timeline=True, kind="champion"):
    target = target_from_values(F(0), F(0), max_health=F(10**6), kind=kind)
    return evaluate_rotation(
        KIT, sheet(*items), RANKS, target, parse_steps(steps), CRIT,
        holder_range="melee", timeline=timeline,
    )  # fmt: skip


def times(outcome):
    return [step.time for step in outcome.steps]


def base(*items):
    return 1 / sheet(*items)["attack_speed"].total()


def flurry(*items):
    data = with_bonus(sheet(*items), "attack_speed", F(30, 100), "test", Label.DERIVED)
    return 1 / data["attack_speed"].total()


def fired(outcome, prefix):
    return [step.index for step in outcome.steps
            if any(part.source.startswith(prefix) for part in step.parts)]  # fmt: skip


# Stat sheet


def test_bonus_attack_speed_is_rescaled_by_the_ratio():
    data = sheet("3032")
    faster = with_bonus(data, "attack_speed", F(30, 100), "test", Label.DERIVED)
    ratio = data.attack_speed_ratio.value
    assert faster["attack_speed"].total() == data["attack_speed"].total() + ratio * F(30, 100)
    assert faster["attack_speed_bonus"].total() == data["attack_speed_bonus"].total() + F(3, 10)
    assert sum(item.scaled for item in faster["attack_speed"].contributions) == 1
    assert effect_amount("attack_speed", F(30)) == F(30, 100)
    assert effect_amount("lethality", F(15)) == 15
    with pytest.raises(StatsError, match="needs the attack speed ratio"):
        with_bonus(
            replace(data, attack_speed_ratio=None), "attack_speed", F(1, 10), "t", Label.DERIVED
        )  # noqa: E501
    with pytest.raises(StatsError, match="feeds other stats"):
        with_bonus(data, "crit_chance", F(1, 10), "test", Label.DERIVED)


def test_a_sheet_keeps_the_attack_speed_ratio_of_the_records():
    data = sheet()
    assert data.attack_speed_ratio.value == load_records(ROOT).value("Zaahen", ATTACK_SPEED_RATIO)
    assert data.attack_speed_ratio.label is Label.DERIVED
    assert data.attack_speed_ratio.source.endswith(")")


# Yun Tal's Flurry


def test_flurry_speeds_up_the_attacks_against_a_champion():
    outcome = run("attack attack attack", "3032")
    assert times(outcome) == [0, flurry("3032"), 2 * flurry("3032")]
    assert flurry("3032") < base("3032")
    assert TIMER in outcome.notes
    assert outcome.label is Label.PENDING


def test_flurry_needs_a_champion():
    outcome = run("attack attack", "3032", kind="minion")
    assert times(outcome) == [0, base("3032")]
    assert TIMER not in outcome.notes


def test_flurry_lasts_six_seconds():
    outcome = run("attack wait:6 attack attack", "3032")
    assert times(outcome) == [0, 0, 6, 6 + base("3032")]
    early = run("attack wait:5.9 attack attack", "3032")
    assert times(early)[3] == F("5.9") + flurry("3032")


def test_flurry_cooldown_is_shortened_by_every_attack_hit():
    # 30 s from 0, minus 1 s for the first attack: ready at 29; the attack at 28 takes it to 28.
    outcome = run("attack wait:28 attack attack attack", "3032")
    first = 28 + base("3032")
    assert times(outcome) == [0, 0, 28, first, first + flurry("3032")]


def test_a_critical_hit_takes_two_seconds_off_the_cooldown():
    outcome = run("attack wait:27 attack:crit attack attack", "3032")
    first = 27 + base("3032")
    assert times(outcome)[4] == first + flurry("3032")
    plain = run("attack wait:27 attack attack attack", "3032")
    assert times(plain)[4] == first + base("3032")


def test_without_the_timeline_flurry_is_listed():
    outcome = run("attack", "3032", timeline=False)
    assert "attacker 3032 flurry: lasts 6 s; applied only with --timeline" in outcome.notes


def test_refunds_never_go_below_the_present():
    target = target_from_values(F(0), F(0), max_health=F(1000), kind="champion")
    rotation = _Rotation(KIT, sheet("3032"), RANKS, target, CRIT, "melee", {}, timeline=True)
    (flurry_effect,) = rotation.timed
    rotation.timed_ready[flurry_effect.title] = F(5, 2)
    rotation._refund(F(2), True)
    assert rotation.timed_ready[flurry_effect.title] == 2
    rotation._refund(F(3), False)
    assert rotation.timed_ready[flurry_effect.title] == 2


# Stack windows


def test_kraken_stacks_expire_four_seconds_after_the_last_attack():
    outcome = run("attack attack attack attack wait:4 attack attack attack", "6672")
    assert fired(outcome, "6672 bring-it-down") == [3, 8]
    assert outcome.steps[5].label is Label.PENDING
    assert any(
        note.startswith("6672 bring-it-down: 1 stack expired (4 s after") for note in outcome.notes
    )  # noqa: E501
    kept = run("attack attack attack attack wait:3.9 attack attack attack", "6672")
    assert fired(kept, "6672 bring-it-down") == [3, 7]
    assert kept.steps[5].label is not Label.PENDING


def test_stacks_expire_only_when_there_are_stacks():
    outcome = run("attack attack attack wait:9 attack attack attack", "6672")
    assert fired(outcome, "6672 bring-it-down") == [3, 7]
    assert not any("expired" in note for note in outcome.notes)


def test_two_stacks_expire_with_a_plural():
    outcome = run("attack attack wait:4 attack attack attack", "6672")
    assert fired(outcome, "6672 bring-it-down") == [6]
    assert any(note.startswith("6672 bring-it-down: 2 stacks expired") for note in outcome.notes)


def test_hullbreaker_stacks_last_ten_seconds():
    outcome = run("attack attack attack attack wait:10 attack attack attack attack attack", "3181")
    assert fired(outcome, "3181 skipper") == [10]


def test_counters_without_a_window_never_expire():
    # Phantom stacks from attacks 4 and 5 survive the wait; Seething Strike starts over.
    outcome = run(" ".join(["attack"] * 5 + ["wait:30"] + ["attack"] * 4), "3124")
    assert "3124 phantom-hit: no stack window declared; its count does not expire" in outcome.notes
    suffix = " - again by 3124 phantom-hit"
    repeats = [step.index for step in outcome.steps
               if any(part.source.endswith(suffix) for part in step.parts)]  # fmt: skip
    assert repeats == [10]


def test_without_the_timeline_windows_are_ignored():
    outcome = run("attack attack attack", "6672", timeline=False)
    assert "attack counters ignore their time windows (stacks expiring)" in outcome.notes


# Spellblade window


def test_a_spellblade_charge_lasts_ten_seconds():
    within = run("Q.first_hit wait:10 attack", "3057")
    assert within.steps[2].name == "basic attack with Spellblade"
    late = run("Q.first_hit wait:10.5 attack", "3057")
    assert late.steps[2].name == "basic attack"
    assert late.steps[2].label is Label.PENDING
    assert "Spellblade: the charge from 0 s expired after 10 s (LoL Wiki, secondary)" in late.notes


def test_a_new_ability_renews_the_spellblade_charge():
    outcome = run("Q.first_hit wait:9 E.edge wait:9 attack", "3057")
    assert outcome.steps[4].name == "basic attack with Spellblade"


def test_the_window_is_not_used_without_the_timeline():
    assert run("Q.first_hit attack", "3057", timeline=False).steps[1].name == (
        "basic attack with Spellblade"
    )


def test_the_attack_that_triggers_flurry_also_shortens_its_cooldown():
    # A critical trigger at 0: ready at 30 - 2 = 28, so the attack at 28 triggers it again.
    outcome = run("attack:crit wait:28 attack attack", "3032")
    assert times(outcome)[3] == 28 + flurry("3032")
