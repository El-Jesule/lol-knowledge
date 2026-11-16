"""Burns and full-stack damage amplifiers in rotations (burns.md)."""

from __future__ import annotations

from fractions import Fraction as F
from pathlib import Path

from lol_knowledge.kit import load_kit, passive_contributions
from lol_knowledge.rotation import CritBase, _Rotation, evaluate_rotation, parse_steps
from lol_knowledge.scenario import target_from_values
from lol_knowledge.stats import (
    Contribution,
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


def sheet(*items, extras=()):
    return build_stat_sheet(
        load_champion(ROOT, "Zaahen"),
        16,
        load_items(ROOT, list(items)),
        load_issues(ROOT),
        {},
        load_records(ROOT),
        (*passive_contributions(KIT, RANKS), *extras),
    )


def run(steps, *items, kind="champion", health=3000, current=None, extras=()):
    target = target_from_values(
        F(0),
        F(0),
        max_health=F(health),
        current_health=None if current is None else F(current),
        kind=kind,
    )
    return evaluate_rotation(
        KIT, sheet(*items, extras=extras), RANKS, target, parse_steps(steps), CRIT,
        holder_range="melee",
    )  # fmt: skip


def burns(step):
    return [part for part in step.parts if part.kind == "burn"]


def test_a_burn_is_applied_once_on_the_first_damaging_ability():
    outcome = run("attack Q.first_hit attack R Q.first_hit", "6653")
    applied = [index for index, step in enumerate(outcome.steps, 1) if burns(step)]
    assert applied == [2]
    (part,) = burns(outcome.steps[1])
    assert part.raw == 3000 * F("0.02") * 3
    assert part.source == "6653 torment (Tormento) over 3 s"
    assert part.damage_type.value == "magic"


def test_each_target_kind_has_its_own_burn():
    minion = run("Q.first_hit", "6653", kind="minion")
    assert [part.source.split(" (")[0] for part in burns(minion.steps[0])] == [
        "6653 torment-minions"
    ]
    monster = run("Q.first_hit", "6653", kind="monster")
    assert not burns(monster.steps[0])
    assert monster.label is Label.PENDING
    ashes = run("Q.first_hit", "2508", kind="monster")
    assert [part.raw for part in burns(ashes.steps[0])] == [45]


def test_ultimate_burns_need_the_ultimate():
    outcome = run("Q.first_hit R", "3118", "3050")
    assert not burns(outcome.steps[0])
    sources = [part.source.split(" (")[0] for part in burns(outcome.steps[1])]
    assert sources == ["3118 hatefog", "3050 frostfire-tempest"]
    ap = sheet("3118", "3050")["ability_power"].total()
    raws = [part.raw for part in burns(outcome.steps[1])]
    assert raws == [(60 + ap * F("0.05")) * 3, 150]
    assert outcome.label is Label.PENDING  # the magic resist shred is not applied


def test_in_combat_amplifiers_stay_at_zero_without_the_timeline():
    outcome = run("attack", "3147")
    (attack,) = outcome.steps[0].parts
    assert attack.dealt == ()
    note = "attacker 3147 madness: grows each second in combat; without --timeline it stays at 0"
    assert note in outcome.notes
    assert outcome.label is Label.PENDING
    minion = run("attack", "3147", kind="minion")
    assert minion.label is not Label.PENDING


def test_burns_take_damage_modifiers_and_heal_like_damage_over_time():
    low = run("Q.first_hit", "6653", "4645", current=1000)
    (part,) = burns(low.steps[0])
    assert ("4645 cinderbloom", 20) in part.dealt
    omnivamp = (Contribution(F("0.3"), "bonus", "test", Label.OFFICIAL),)
    extras = [("omnivamp", item) for item in omnivamp]
    champion = burns(run("Q.first_hit", "6653", extras=extras).steps[0])[0]
    minion = burns(run("Q.first_hit", "6653", kind="minion", extras=extras).steps[0])[0]
    assert champion.healing.amount == champion.damage * F("0.3")
    assert minion.healing.amount == minion.damage * F("0.1")
    assert minion.healing.notes == ("omnivamp from damage over time against a minion: 33%",)
    assert champion.healing.notes == ()


def test_life_steal_does_not_heal_from_burns():
    extras = [("life_steal", Contribution(F("0.2"), "bonus", "test", Label.OFFICIAL))]
    (part,) = burns(run("Q.first_hit", "6653", extras=extras).steps[0])
    assert part.healing.life_steal == 0
    assert part.healing.notes == ()
    assert part.healing.label is not Label.PENDING


def test_a_damaging_ability_burn_needs_damage_in_the_step():
    target = target_from_values(F(0), F(0), max_health=F(3000), kind="champion")
    rotation = _Rotation(KIT, sheet("6653"), RANKS, target, CRIT, "melee", {})
    (step,) = parse_steps("Q.first_hit")
    stats = {**target.stats, "missing_fraction_health": F(0)}
    assert rotation._burns(step, [], stats, set()) == []
    assert len(rotation._burns(step, ["damage"], stats, set())) == 1
