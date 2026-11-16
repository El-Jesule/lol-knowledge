"""Attack counters and Energized in rotations (attack-counters.md)."""

from __future__ import annotations

from fractions import Fraction as F
from pathlib import Path

from lol_knowledge.kit import load_kit, passive_contributions
from lol_knowledge.rotation import CritBase, _could_apply, evaluate_rotation, parse_steps
from lol_knowledge.scenario import target_from_values
from lol_knowledge.stats import (
    ItemData,
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


def run(steps, *items, level=16, holder="melee", kind="champion", health=5000):
    target = target_from_values(F(100), F(50), max_health=F(health), kind=kind)
    return evaluate_rotation(
        KIT,
        sheet(*items, level=level),
        RANKS,
        target,
        parse_steps(steps),
        CRIT,
        holder_range=holder,
    )


def parts(step, prefix):
    return [part for part in step.parts if part.source.startswith(prefix)]


# Every Nth attack


def test_kraken_fires_on_every_third_attack_only():
    outcome = run("attack attack Q.first_hit attack attack attack attack", "6672")
    fired = [index for index, step in enumerate(outcome.steps, 1) if parts(step, "6672")]
    assert fired == [4, 7]  # abilities do not count
    (part,) = parts(outcome.steps[3], "6672 bring-it-down")
    missing = 1 - outcome.steps[3].health_before / 5000
    assert part.raw == (150 + 5 * 8) * (1 + F("0.75") * missing)  # level 16
    assert outcome.label is not Label.PENDING  # the missing-health increase is applied


def test_kraken_level_breakpoints_and_ranged_multiplier():
    melee_step = run("attack attack attack", "6672", level=9).steps[2]
    ranged_step = run("attack attack attack", "6672", level=8, holder="ranged").steps[2]
    (melee,) = parts(melee_step, "6672")
    (ranged,) = parts(ranged_step, "6672")
    assert melee.raw == 155 * (1 + F("0.75") * (1 - melee_step.health_before / 5000))
    assert ranged.raw == 150 * F("0.8") * (1 + F("0.75") * (1 - ranged_step.health_before / 5000))


def test_guinsoo_repeats_the_on_hit_effects_every_third_attack_at_full_stacks():
    # Stacks from 0: the 4th attack completes them and counts, so the 6th repeats.
    outcome = run(" ".join(["attack"] * 9), "3124", "3115")
    sixth = outcome.steps[5]
    repeated = [part for part in sixth.parts if "again by 3124 phantom-hit" in part.source]
    assert [part.source.split(" (")[0] for part in repeated] == ["3124 wrath", "3115 icathian-bite"]
    assert all(part.label is Label.PENDING for part in repeated)
    hits = [step.index for step in outcome.steps
            if any("again by" in part.source for part in step.parts)]  # fmt: skip
    assert hits == [6, 9]
    assert "attacker 3124 phantom-hit: excluded, not applied" not in outcome.notes


def test_hullbreaker_against_champions_and_structures():
    outcome = run("attack attack attack attack attack", "3181")
    (part,) = parts(outcome.steps[4], "3181 skipper")
    stats = sheet("3181")
    expected = stats["attack_damage"].scoped("base") * F("1.2") + stats["health"].total() / 20
    assert part.raw == expected
    assert outcome.label is not Label.PENDING
    structure = run("attack attack attack attack attack", "3181", kind="structure")
    assert not parts(structure.steps[4], "3181")
    assert structure.label is Label.PENDING


def test_counters_ignore_time_windows():
    assert (
        "attack counters ignore their time windows (stacks expiring)" in run("attack", "6672").notes
    )


# Energized


def test_energized_fires_once_on_the_first_attack():
    outcome = run("attack attack Q.first_hit attack", "3094")
    assert outcome.steps[0].name == "basic attack (Energized)"
    (part,) = parts(outcome.steps[0], "3094 sharpshooter")
    assert (part.raw, part.damage_type.value) == (40, "magic")
    assert not any(parts(step, "3094") for step in outcome.steps[1:])
    assert (
        "Energized starts ready and fires once; recharging by moving and attacking is not modelled"
        in outcome.notes
    )


def test_cyclosword_ability_damage_triggers_energized_against_champions():
    outcome = run("Q.first_hit attack", "6699", health=4000)
    first = outcome.steps[0]
    assert first.name.endswith("(Energized)")
    (part,) = parts(first, "6699 firmament")
    assert part.raw == 4000 * F("0.09")
    assert not parts(outcome.steps[1], "6699")
    assert "6699 galvanize: the ability's damage to a champion triggered Energized" in (
        outcome.notes
    )
    assert outcome.label is Label.PENDING  # the 4-second lethality is not applied


def test_cyclosword_against_a_minion_waits_for_an_attack_and_is_capped():
    outcome = run("Q.first_hit attack", "6699", kind="minion", health=4000)
    assert not parts(outcome.steps[0], "6699")
    (part,) = parts(outcome.steps[1], "6699 firmament")
    assert part.raw == 200


def test_statikk_and_several_energized_items_are_pending():
    assert run("attack", "3087").label is Label.PENDING
    outcome = run("attack", "3094", "6699")
    assert "several Energized items: whether their Energized effects stack is not verified" in (
        outcome.notes
    )
    assert outcome.label is Label.PENDING


# Skipped effects and the target kind


def test_a_condition_on_the_target_kind_limits_weakening():
    champion_only = {"conditions": [{"kind": "target_is_champion"}]}
    assert _could_apply(champion_only, None)
    assert _could_apply(champion_only, "champion")
    assert not _could_apply(champion_only, "minion")
    assert _could_apply({"conditions": [{"kind": "on_hit"}]}, "minion")


def test_terminus_stacks_are_left_out_of_the_stat_sheet():
    assert sheet("3302", level=11)["armor"].scoped("bonus") == 0
    assert sheet("3302", level=11)["armor_penetration_percent"].total() == (
        sheet(level=11)["armor_penetration_percent"].total()
    )


def test_without_galvanize_an_ability_does_not_use_energized():
    outcome = run("Q.first_hit attack", "3094")
    assert not parts(outcome.steps[0], "3094")
    assert parts(outcome.steps[1], "3094 sharpshooter")


def test_only_on_hit_and_on_attack_effects_count_attacks():
    energized = {
        "id": "zap",
        "name": "zap",
        "trigger": {"event": "energized"},
        "stacks": {"required": 3, "window_seconds": None, "max_stacks": None},
        "conditions": [{"kind": "on_hit"}],
        "evidence_confidence": "official",
        "model_status": "evaluable",
        "components": [
            {
                "kind": "damage",
                "damage_type": "magic",
                "conditions": [{"kind": "on_hit"}],
                "formula": {"op": "constant", "value": 10},
            }
        ],
    }
    data = build_stat_sheet(
        load_champion(ROOT, "Zaahen"),
        16,
        (ItemData("9100", "test", "16.22.1", (), (energized,)),),
        load_issues(ROOT),
        {},
        load_records(ROOT),
        passive_contributions(KIT, RANKS),
    )
    target = target_from_values(F(100), F(50), max_health=F(5000), kind="champion")
    outcome = evaluate_rotation(
        KIT, data, RANKS, target, parse_steps("attack attack attack"), CRIT, holder_range="melee"
    )
    fired = [index for index, step in enumerate(outcome.steps, 1) if parts(step, "9100")]
    assert fired == [1]
