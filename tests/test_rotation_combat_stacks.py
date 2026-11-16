"""Stacks that expire in combat start at 0 and are computed by rotations (combat-stacks.md)."""

from __future__ import annotations

from dataclasses import replace
from fractions import Fraction as F
from pathlib import Path

import pytest

from lol_knowledge.damage import format_number
from lol_knowledge.errors import RotationError
from lol_knowledge.kit import load_kit, passive_contributions
from lol_knowledge.rotation import CritBase, _Rotation, evaluate_rotation, parse_steps
from lol_knowledge.scenario import target_from_values
from lol_knowledge.stats import (
    Label,
    build_stat_sheet,
    load_champion,
    load_issues,
    load_items,
    load_records,
    with_bonus,
)

ROOT = Path(__file__).resolve().parents[1]
KIT = load_kit(ROOT, "Zaahen")
RANKS = {"Q": 5, "W": 1, "E": 5, "R": 3}
CRIT = CritBase(F(2), Label.DERIVED, "test record")


def sheet(*items, level=16):
    return build_stat_sheet(
        load_champion(ROOT, "Zaahen"),
        level,
        list(items) if items and not isinstance(items[0], str) else load_items(ROOT, list(items)),
        load_issues(ROOT),
        {},
        load_records(ROOT),
        passive_contributions(KIT, RANKS),
    )


def target(kind="champion", armor=0):
    return target_from_values(F(armor), F(0), max_health=F(10**6), kind=kind)


def run(steps, *items, timeline=True, kind="champion", armor=0, data=None):
    return evaluate_rotation(
        KIT, sheet(*items) if data is None else data, RANKS, target(kind, armor),
        parse_steps(steps), CRIT, holder_range="melee", timeline=timeline,
    )  # fmt: skip


def rotation(*items, timeline=True, kind="champion"):
    return _Rotation(KIT, sheet(*items), RANKS, target(kind), CRIT, "melee", {}, timeline)


def interval(stacks, *items):
    data = with_bonus(sheet(*items), "attack_speed", F(8 * stacks, 100), "t", Label.DERIVED)
    return 1 / data["attack_speed"].total()


def times(outcome):
    return [step.time for step in outcome.steps]


def terminus_pen(part):
    """Terminus's share of the armor penetration sources of a part (Zaahen has 30 % of his own)."""
    sources = list(part.mitigation.modifiers.percent_penetration)
    sources.remove(F(3, 10))
    return sum(sources, start=F(0))


# Guinsoo's Seething Strike


def test_guinsoo_attack_speed_grows_one_stack_per_attack():
    outcome = run(" ".join(["attack"] * 5), "3124")
    gaps = [b - a for a, b in zip(times(outcome), times(outcome)[1:], strict=False)]
    assert gaps == [interval(1, "3124"), interval(2, "3124"), interval(3, "3124"),
                    interval(4, "3124")]  # fmt: skip
    assert outcome.label is Label.PENDING  # the attack timer with a changing attack speed


def test_guinsoo_stacks_expire_four_seconds_after_the_last_attack():
    outcome = run("attack attack wait:4 attack attack", "3124")
    assert times(outcome)[4] - times(outcome)[3] == interval(1, "3124")
    kept = run("attack attack wait:3.9 attack attack", "3124")
    assert times(kept)[4] - times(kept)[3] == interval(3, "3124")


def test_without_the_timeline_guinsoo_stacks_are_counted_and_never_expire():
    machine = rotation("3124", timeline=False)
    machine.run(parse_steps("attack attack attack attack attack"))
    (effect,) = machine.stacked
    assert machine.stacks[f"{effect.title}:attack_speed"] == 4
    machine._set_moment(F(100))
    bonus = machine.sheet["attack_speed_bonus"].contributions[-1]
    assert (bonus.value, bonus.note) == (F(32, 100), "4 stacks")


def test_the_stacks_count_from_the_next_step():
    machine = rotation("3124")
    machine.run(parse_steps("attack"))
    machine._set_moment(F(0))
    assert machine.sheet["attack_speed_bonus"].contributions[-1].note == "1 stack"
    fresh = rotation("3124")
    fresh._set_moment(F(0))
    assert fresh.sheet is fresh.base_sheet


# Terminus's Juxtaposition


def test_terminus_starts_light_and_alternates_with_dark():
    outcome = run(" ".join(["attack"] * 9), "3302", armor=100)
    pens = [terminus_pen(step.parts[0]) for step in outcome.steps]
    # Dark hits are the 2nd, 4th, 6th and 8th; each counts from the next attack, up to 3.
    assert pens == [0, 0, F(1, 10), F(1, 10), F(2, 10), F(2, 10), F(3, 10), F(3, 10), F(3, 10)]
    assert outcome.steps[2].parts[0].label is Label.PENDING
    assert outcome.steps[0].parts[0].label is not Label.PENDING


def test_terminus_light_hits_give_resistances_by_level():
    for level, armor in ((16, 8), (11, 7), (10, 6)):
        data = sheet(*load_items(ROOT, ["3302"]), level=level)
        machine = _Rotation(KIT, data, RANKS, target(), CRIT, "melee", {}, True)
        machine.run(parse_steps("attack attack attack"))
        machine._set_moment(F(1))
        bonus = machine.sheet["armor"].contributions[-1]
        assert bonus.value == 2 * armor
        assert bonus.label is Label.PENDING
        assert bonus.note.startswith("2 stacks; light and dark hits alternate")
        assert machine.sheet["magic_resist"].contributions[-1].value == 2 * armor


def test_terminus_stacks_last_five_seconds():
    late = run("attack attack wait:5 attack", "3302", armor=100)
    assert terminus_pen(late.steps[3].parts[0]) == 0
    kept = run("attack attack wait:4.9 attack", "3302", armor=100)
    assert terminus_pen(kept.steps[3].parts[0]) == F(1, 10)


def test_terminus_only_stacks_against_champions():
    machine = rotation("3302", kind="minion")
    machine.run(parse_steps("attack attack attack"))
    assert machine.stacks == {}
    assert machine.turns == {}


# Liandry's Suffering and Haunting Guise's Madness


def test_in_combat_increases_grow_each_whole_second_from_the_start():
    outcome = run("attack wait:1.9 attack wait:1.2 attack wait:5 attack", "3147")
    attacks = [step for step in outcome.steps if step.step.text == "attack"]
    assert [step.time for step in attacks] == [0, F("1.9"), F("3.1"), F("8.1")]
    dealt = [dict(step.parts[0].dealt).get("3147 madness", 0) for step in attacks]
    assert dealt == [0, 2, 6, 6]
    early = run("attack wait:0.99 Q.first_hit", "3147")
    assert early.steps[2].time == F("0.99")
    assert early.steps[2].parts[0].dealt == ()


def test_in_combat_increases_split_the_burns_on_whole_seconds():
    outcome = run("Q.first_hit wait:3 attack", "6653")
    pieces = [part for part in outcome.steps[2].parts if part.kind == "burn"]
    assert [part.source.split(") ")[1] for part in pieces] == [
        "from 0 s to 1 s",
        "from 1 s to 2 s",
        "from 2 s to 3 s",
    ]
    assert [dict(part.dealt).get("6653 suffering", 0) for part in pieces] == [0, 2, 4]


def test_in_combat_increases_need_a_champion():
    outcome = run("attack wait:5 attack", "3147", kind="minion")
    assert outcome.steps[2].parts[0].dealt == ()


# Malformed data


def _changed(item_id, effect_id, **changes):
    (item,) = load_items(ROOT, [item_id])
    effects = tuple(
        {**effect, **changes} if effect["id"] == effect_id else effect for effect in item.effects
    )
    return replace(item, effects=effects)


@pytest.mark.parametrize(
    ("item_id", "effect_id", "changes", "message"),
    [
        ("3124", "seething-strike", {"target": {"kind": "enemy_unit"}}, "only flat stats"),
        ("3147", "madness", {"limits": []}, "needs a maximum"),
        (
            "3147",
            "madness",
            {
                "components": [
                    {
                        "kind": "damage_modifier",
                        "direction": "taken",
                        "source": "all",
                        "mode": "percent",
                        "formula": {"op": "constant", "value": 2},
                    }
                ]
            },
            "only dealt modifiers grow in combat",
        ),  # fmt: skip
        (
            "3124",
            "phantom-hit",
            {"conditions": [{"kind": "stacks_full", "value": "nothing"}]},
            "stacks_full refers to no stacking effect",
        ),
    ],
)
def test_malformed_stacking_effects_are_errors(item_id, effect_id, changes, message):
    data = sheet(_changed(item_id, effect_id, **changes))
    with pytest.raises(RotationError, match=message):
        run("attack attack attack attack", data=data)


def test_without_the_timeline_terminus_stacks_still_count():
    outcome = run("attack attack attack", "3302", timeline=False, armor=100)
    assert terminus_pen(outcome.steps[2].parts[0]) == F(1, 10)


def test_burns_split_where_stacks_expire():
    # The dark hit (2nd attack) gives magic penetration until 5 s after it.
    outcome = run("attack attack wait:4 Q.first_hit wait:4 attack", "3302", "2508")
    second = outcome.steps[1].time
    pieces = [part for part in outcome.steps[-1].parts if part.kind == "burn"]
    # The light hit at 0 s also ends at 5 s: the burn splits there too.
    ends = [part.source.rsplit(" to ", 1)[1] for part in pieces]
    index = ends.index(f"{format_number(second + 5)} s")
    assert F(1, 10) in pieces[index].mitigation.modifiers.percent_penetration
    assert F(1, 10) not in pieces[index + 1].mitigation.modifiers.percent_penetration
    assert ends[0] == "5 s"
