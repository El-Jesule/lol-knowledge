"""Effects that read the target's health in rotations (target-health.md)."""

from __future__ import annotations

from fractions import Fraction as F
from pathlib import Path

import pytest

from lol_knowledge.kit import load_kit, passive_contributions
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
KIT = load_kit(ROOT, "Zaahen")
RANKS = {"Q": 5, "W": 1, "E": 5, "R": 3}
CRIT = CritBase(F(2), Label.DERIVED, "test record")


def run(steps, *items, health=1000, current=None, kind="champion", holder="melee"):
    sheet = build_stat_sheet(
        load_champion(ROOT, "Zaahen"),
        16,
        load_items(ROOT, list(items)),
        load_issues(ROOT),
        {},
        load_records(ROOT),
        passive_contributions(KIT, RANKS),
    )
    target = target_from_values(
        F(0),
        F(0),
        max_health=F(health),
        current_health=None if current is None else F(current),
        kind=kind,
    )
    return evaluate_rotation(
        KIT, sheet, RANKS, target, parse_steps(steps), CRIT, holder_range=holder
    )


def parts(step, prefix):
    return [part for part in step.parts if part.source.startswith(prefix)]


# Kraken Slayer: missing health


@pytest.mark.parametrize("holder", ["melee", "ranged"])
def test_kraken_grows_with_the_missing_health_at_the_start_of_the_step(holder):
    outcome = run("attack attack attack", "6672", health=100000, current=50000, holder=holder)
    third = outcome.steps[2]
    (part,) = parts(third, "6672 bring-it-down")
    missing = 1 - third.health_before / 100000
    base = 190 if holder == "melee" else 190 * F("0.8")
    assert part.raw == base * (1 + F("0.75") * missing)
    assert outcome.label is not Label.PENDING


def test_kraken_at_full_health_has_no_increase():
    outcome = run("Q.first_hit Q.first_hit attack attack attack", "6672", health=10**9)
    (part,) = parts(outcome.steps[4], "6672")
    missing = 1 - outcome.steps[4].health_before / 10**9
    assert part.raw == 190 * (1 + F("0.75") * missing)
    assert part.raw < 191


# Shadowflame: threshold on the target's health


def test_shadowflame_amplifies_magic_damage_below_forty_percent():
    low = run("attack", "4645", "3115", health=1000, current=399)
    (nashor,) = parts(low.steps[0], "3115")
    (attack,) = [part for part in low.steps[0].parts if part.kind == "attack"]
    assert nashor.dealt == (("4645 cinderbloom", 20),)
    assert attack.dealt == ()  # physical damage is not amplified
    high = run("attack", "4645", "3115", health=1000, current=400)
    assert parts(high.steps[0], "3115")[0].dealt == ()


# The Collector: execute


def test_collector_executes_a_champion_left_below_five_percent():
    dealt = run("attack", "6676", health=10**6).steps[0].total
    outcome = run("attack", "6676", health=1000, current=dealt + 40)
    (execute,) = [part for part in outcome.steps[0].parts if part.kind == "execute"]
    assert execute.source == "6676 death (Muerte)"
    assert execute.damage_type.value == "true"
    assert execute.raw == execute.damage == 40
    assert outcome.steps[0].health_after == 0


def test_collector_needs_a_champion_and_the_threshold():
    probe = run("attack", "6676", health=10**6).steps[0].total
    above = run("attack", "6676", health=1000, current=probe + 60)
    assert not [part for part in above.steps[0].parts if part.kind == "execute"]
    minion = run("attack", "6676", health=1000, current=probe + 40, kind="minion")
    assert not [part for part in minion.steps[0].parts if part.kind == "execute"]
    dead = run("attack", "6676", health=1000, current=probe - 1)
    assert not [part for part in dead.steps[0].parts if part.kind == "execute"]
