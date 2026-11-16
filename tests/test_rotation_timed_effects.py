"""Burns over time and timed effects on the rotation timeline (timeline.md, rules 7 and 8)."""

from __future__ import annotations

import json
from dataclasses import replace
from fractions import Fraction as F
from pathlib import Path

import pytest

from lol_knowledge.cli import main
from lol_knowledge.errors import RotationError, StatsError
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
    with_amplifier,
    with_bonus,
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


def run(
    steps,
    *items,
    timeline=True,
    kind="champion",
    armor=0,
    mr=0,
    health=3000,
    current=None,
    holder="melee",
    data=None,
):
    target = target_from_values(
        F(armor),
        F(mr),
        max_health=F(health),
        current_health=None if current is None else F(current),
        kind=kind,
    )
    return evaluate_rotation(
        KIT,
        sheet(*items) if data is None else data,
        RANKS,
        target,
        parse_steps(steps),
        CRIT,
        holder_range=holder,
        timeline=timeline,
    )


def burns(step, prefix=""):
    return [part for part in step.parts if part.kind == "burn" and part.source.startswith(prefix)]


def interval(*items):
    return 1 / sheet(*items)["attack_speed"].total()


# Burns over time


def test_a_burn_is_spread_over_the_steps_and_ends_the_rotation():
    outcome = run("Q.first_hit attack attack", "6653")
    step = interval("6653")
    assert [len(burns(outcome.steps[index])) for index in range(4)] == [0, 0, 1, 1]
    (second,) = burns(outcome.steps[2])
    assert second.source == f"6653 torment (Tormento) from 0 s to {_n(step)} s"
    assert second.raw == 60 * step
    last = outcome.steps[-1]
    assert (last.index, last.step.text, last.name) == (4, "burns", "burns until 3 s")
    assert last.time == 3
    assert sum(part.raw for step in outcome.steps for part in burns(step)) == 180
    assert outcome.duration == 3
    assert outcome.damage_per_second == outcome.total / 3


def _n(value):
    from lol_knowledge.damage import format_number

    return format_number(value)


def test_applying_a_burn_again_restarts_its_duration():
    outcome = run("Q.first_hit wait:2 E.edge", "6653")
    assert sum(part.raw for step in outcome.steps for part in burns(step)) == 60 * 5
    assert outcome.steps[-1].name == "burns until 5 s"
    assert outcome.duration == 5


def test_waits_count_the_burn_damage_up_to_them():
    outcome = run("Q.first_hit wait:1 wait:1", "6653")
    assert [step.name for step in outcome.steps] == ["Q La guja de los Oscuros rank 5", "wait",
                                                     "wait", "burns until 3 s"]  # fmt: skip
    assert burns(outcome.steps[1]) == []
    (part,) = burns(outcome.steps[2])
    assert (part.raw, outcome.steps[2].time) == (60, 1)
    assert outcome.steps[2].health_after == outcome.steps[2].health_before - part.damage
    (rest,) = burns(outcome.steps[3])
    assert rest.raw == 120


def test_the_burn_damage_lands_before_the_step_reads_the_target_health():
    outcome = run("Q.first_hit wait:1 attack", "6653")
    attack = outcome.steps[2]
    assert attack.parts[0].kind == "burn"
    assert attack.health_before == outcome.steps[1].health_after
    assert attack.health_after == attack.health_before - attack.total


def test_a_burn_can_execute_on_the_final_step():
    probe = run("Q.first_hit", "6653", "6676", health=3000)
    hit = probe.steps[0].total
    outcome = run("Q.first_hit", "6653", "6676", health=3000, current=hit + 250)
    final = outcome.steps[-1]
    assert final.name == "burns until 3 s"
    assert [part.kind for part in final.parts] == ["burn", "execute"]
    assert final.health_after == 0
    assert outcome.lethal_step == 2


def test_without_the_timeline_burns_are_still_whole_and_once():
    outcome = run("Q.first_hit E.edge", "6653", timeline=False)
    assert [len(burns(step)) for step in outcome.steps] == [1, 0]
    assert burns(outcome.steps[0])[0].raw == 180


# Timed effects


def test_bloodsong_mark_amplifies_the_damage_after_the_spellblade_hit():
    outcome = run("Q.first_hit attack attack", "3877")
    empowered, after = outcome.steps[1], outcome.steps[2]
    assert all(part.dealt == () for part in empowered.parts)
    assert empowered.label is Label.PENDING
    assert after.parts[0].dealt == (("3877 bloodsong-mark", 8),)
    assert after.parts[0].label is Label.DERIVED
    ranged = run("Q.first_hit attack attack", "3877", holder="ranged")
    assert ranged.steps[2].parts[0].dealt == (("3877 bloodsong-mark", 5),)
    note = "3877 bloodsong-mark: starts after the hit that triggers it; whether that hit benefits is not verified"  # noqa: E501
    assert note in outcome.notes


def test_bloodsong_mark_lasts_four_seconds():
    outcome = run("Q.first_hit attack wait:4 attack", "3877")
    assert outcome.steps[3].time == 4
    assert outcome.steps[3].parts[0].dealt == ()
    just = run("Q.first_hit attack wait:3.9 attack:nospellblade", "3877")
    assert just.steps[3].parts[0].dealt == (("3877 bloodsong-mark", 8),)


def test_bloodsong_mark_only_marks_champions():
    outcome = run("Q.first_hit attack attack", "3877", kind="minion")
    assert outcome.steps[2].parts[0].dealt == ()
    assert outcome.steps[1].label is not Label.PENDING


def test_without_the_timeline_a_timed_effect_is_listed_and_weakens_only_if_it_can_apply():
    champion = run("attack", "3877", timeline=False)
    assert "attacker 3877 bloodsong-mark: lasts 4 s; applied only with --timeline" in champion.notes
    assert champion.label is Label.PENDING
    minion = run("attack", "3877", timeline=False, kind="minion")
    assert minion.label is not Label.PENDING


def test_cyclosword_lethality_lowers_the_armor_after_the_energized_hit():
    outcome = run("attack Q.first_hit wait:4 attack", "6699", armor=80)
    energized, ability, late = outcome.steps[0], outcome.steps[1], outcome.steps[3]
    lethality = sheet("6699")["lethality"].total()

    def flat(step):
        trace = step.parts[0].mitigation.resistance
        return trace.after_percent_penetration - trace.effective

    assert flat(energized) == lethality
    assert energized.label is Label.PENDING
    assert flat(ability) == lethality + 15
    assert flat(late) == lethality
    assert flat(run("attack Q.first_hit", "6699", armor=80, holder="ranged").steps[1]) == 22


def test_malignance_reduces_the_magic_resist_after_the_ultimate():
    outcome = run("R attack attack", "3118", mr=60)
    ultimate = outcome.steps[0]
    assert burns(ultimate) == []
    shredded = burns(outcome.steps[2], "3118 hatefog ")
    assert shredded
    for part in shredded:
        assert part.mitigation.resistance.initial == 60
        assert part.mitigation.resistance.effective == 50
        assert (
            "3118 hatefog-shred (Niebla del odio: resistencia mágica): target magic_resist -10"
            in part.notes
        )  # noqa: E501
    assert outcome.steps[-1].time == 3
    other = run("Q.first_hit attack", "3118", mr=60)
    assert all(burns(step) == [] for step in other.steps)
    assert all(part.mitigation.resistance.effective == 60 for step in other.steps
               for part in step.parts if part.damage_type.value == "magic")  # fmt: skip


def test_blackfire_raises_ability_power_while_the_torch_burns():
    ability_power = sheet("2503")["ability_power"].total()
    outcome = run("Q.first_hit E.edge", "2503")
    (part,) = burns(outcome.steps[-1])
    # Applied again by E while Blackfire (opened by Q) is in force: 4 % more ability power.
    assert part.raw == (20 + F(2, 100) * ability_power * F(104, 100)) * 3
    assert part.label is Label.DERIVED


def test_a_burn_keeps_its_applied_damage_per_second_and_flags_a_change():
    ability_power = sheet("2503")["ability_power"].total()
    outcome = run("Q.first_hit", "2503")
    (part,) = burns(outcome.steps[-1])
    assert part.raw == (20 + F(2, 100) * ability_power) * 3
    assert part.label is Label.PENDING
    assert "whether the game updates it is not verified" in part.notes[0]


def test_blackfire_ends_with_the_burn():
    outcome = run("Q.first_hit wait:3 E.edge", "2503")
    (part,) = burns(outcome.steps[-1])
    ability_power = sheet("2503")["ability_power"].total()
    assert part.raw == (20 + F(2, 100) * ability_power) * 3


def test_a_timed_effect_ending_splits_the_burns():
    outcome = run("Q.first_hit attack wait:3 E.edge wait:2 attack:nospellblade", "6653", "3877")
    pieces = burns(outcome.steps[-2])
    assert [part.source.split(") ")[1] for part in pieces] == [
        "from 3 s to 4 s",
        "from 4 s to 5 s",
    ]
    assert "3877 bloodsong-mark" in dict(pieces[0].dealt)
    assert "3877 bloodsong-mark" not in dict(pieces[1].dealt)
    assert pieces[0].raw == pieces[1].raw == 60


# Stat sheet bonuses


def test_with_bonus_adds_a_temporary_contribution():
    base = sheet("6699")
    data = with_bonus(base, "lethality", F(15), "test", Label.DERIVED)
    assert data["lethality"].total() == base["lethality"].total() + 15
    assert data["lethality"].contributions[-1].source == "test"
    assert base["lethality"].total() == 10
    with pytest.raises(StatsError, match="only additive amounts"):
        with_bonus(base, "attack_speed_bonus", F(1, 10), "test", Label.DERIVED)
    with pytest.raises(StatsError, match="only additive amounts"):
        with_bonus(base, "crit_chance", F(1, 10), "test", Label.DERIVED)


def test_with_amplifier_uses_the_total_without_other_amplifiers():
    plain = with_amplifier(sheet("2503"), "ability_power", F(4), "test", Label.DERIVED)
    assert plain["ability_power"].total() == 80 * F(104, 100)
    assert plain["ability_power"].label is Label.DERIVED
    base = sheet("2503", "3089")
    flat = sum(
        (item.value for item in base["ability_power"].contributions if not item.amplifier),
        start=F(0),
    )
    both = with_amplifier(base, "ability_power", F(4), "test", Label.DERIVED)
    assert both["ability_power"].total() == base["ability_power"].total() + flat * F(4, 100)
    assert both["ability_power"].contributions[-1].label is Label.PENDING
    assert both["ability_power"].label is Label.PENDING


# Malformed timed effects


def _with_effect(item_id, effect_id, **changes):
    (item,) = load_items(ROOT, [item_id])
    effects = []
    for effect in item.effects:
        if effect["id"] == effect_id:
            effect = {**effect, **changes}
        effects.append(effect)
    return replace(item, effects=tuple(effects))


def _sheet_with(item):
    return build_stat_sheet(
        load_champion(ROOT, "Zaahen"),
        16,
        [item],
        load_issues(ROOT),
        {},
        load_records(ROOT),
        passive_contributions(KIT, RANKS),
    )


@pytest.mark.parametrize(
    ("item_id", "effect_id", "component", "message"),
    [
        ("3877", "bloodsong-mark", {"direction": "taken"}, "only dealt modifiers"),
        ("3877", "bloodsong-mark", {"source": "attack"}, "only dealt modifiers"),
        ("3877", "bloodsong-mark", {"mode": "flat"}, "only percent damage modifiers"),
        ("6699", "firmament-lethality", {"mode": "ratio"}, "only flat or total-percent"),
        ("2503", "blackfire", {"scope": "bonus"}, "only flat or total-percent"),
        ("3118", "hatefog-shred", {"stat": "health"}, "only flat target resistance"),
        ("3118", "hatefog-shred", {"mode": "percent"}, "only flat target resistance"),
    ],
)
def test_malformed_timed_effects_are_errors(item_id, effect_id, component, message):
    (item,) = load_items(ROOT, [item_id])
    (effect,) = [entry for entry in item.effects if entry["id"] == effect_id]
    changed = _with_effect(
        item_id, effect_id, components=[{**effect["components"][0], **component}]
    )
    with pytest.raises(RotationError, match=message):
        run("attack", data=_sheet_with(changed))


def test_cli_reports_the_final_burn_step(capsys):
    args = [
        "rotation", "--champion", "Zaahen", "--level", "16", "--learned", "Q=5",
        "--item", "6653", "--steps", "Q.first_hit", "--timeline", "--target-armor", "0",
        "--target-mr", "0", "--target-max-health", "3000", "--target-kind", "champion",
        "--root", str(ROOT),
    ]  # fmt: skip
    assert main(args) == 0
    out = capsys.readouterr().out
    assert "step 2 burns (burns until 3 s) at 3 s: health" in out
    assert "(6653 torment (Tormento) from 0 s to 3 s)" in out
    assert "duration 3 s" in out
    assert main([*args, "--json"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert [step["step"] for step in report["steps"]] == ["Q.first_hit", "burns"]
    assert report["timeline"]["duration"] == 3


def test_a_burn_that_ended_between_steps_adds_nothing_more():
    outcome = run("Q.first_hit wait:5 attack", "6653")
    assert outcome.steps[-1].step.text == "attack"
    assert [part.source.split(") ")[1] for part in burns(outcome.steps[-1])] == ["from 0 s to 3 s"]
    assert outcome.duration == 5


def test_a_burn_starts_at_the_step_that_applies_it():
    outcome = run("attack attack Q.first_hit attack", "6653")
    start = outcome.steps[2].time
    assert start == interval("6653")
    (first,) = burns(outcome.steps[3])
    assert first.source.split(") ")[1].startswith(f"from {_n(start)} s")
    assert sum(part.raw for step in outcome.steps for part in burns(step)) == 180


def test_the_execute_reads_the_health_before_the_step_burns():
    steps = "Q.first_hit wait:1.5 attack"
    probe = run(steps, "6653", "6676")
    hit, (burn, *_), attack = probe.steps[0].total, probe.steps[2].parts, probe.steps[2]
    # After the step, 200 health is left: above the 150 (5 %) execute threshold.
    current = hit + attack.total + 200
    outcome = run(steps, "6653", "6676", current=current)
    assert burn.kind == "burn"
    assert [part.kind for part in outcome.steps[2].parts] == [part.kind for part in attack.parts]
    assert outcome.steps[2].health_after == 200


def test_stat_labels_reach_the_burns():
    outcome = run("Q.first_hit E.edge", "2503", "3089")
    (part,) = burns(outcome.steps[-1])
    assert part.notes == ()
    assert part.label is Label.PENDING  # Blackfire with Rabadon's Deathcap


def test_a_damaging_ability_trigger_needs_damage(monkeypatch):
    target = target_from_values(F(0), F(60), max_health=F(3000), kind="champion")
    rotation = _Rotation(KIT, sheet("3118"), RANKS, target, CRIT, "melee", {}, timeline=True)
    monkeypatch.setattr(_Rotation, "_ability", lambda self, step, stats: ("silent R", []))
    outcome = rotation.run(parse_steps("R"))
    assert rotation.windows == {}
    assert [step.name for step in outcome.steps] == ["silent R"]
