"""Rotations: basic attacks, crits, item effects and the target's health over steps."""

from __future__ import annotations

import json
from fractions import Fraction as F
from pathlib import Path

import pytest

from lol_knowledge.cli import main
from lol_knowledge.errors import RotationError, StatsError
from lol_knowledge.kit import load_kit, passive_contributions
from lol_knowledge.rotation import (
    CritBase,
    Step,
    evaluate_rotation,
    parse_steps,
)
from lol_knowledge.scenario import evaluate_ability, target_from_sheet, target_from_values
from lol_knowledge.stats import (
    Contribution,
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


def sheet(champion="Zaahen", level=16, items=(), ranks=RANKS, extra_items=()):
    data = load_champion(ROOT, champion)
    extras = passive_contributions(KIT, ranks) if champion == "Zaahen" and ranks else ()
    return build_stat_sheet(
        data,
        level,
        (*load_items(ROOT, list(items)), *extra_items),
        load_issues(ROOT),
        {},
        load_records(ROOT),
        extras,
    )


def manual(armor=100, mr=50, health=3000, **kwargs):
    return target_from_values(F(armor), F(mr), max_health=F(health), **kwargs)


def run(attacker, target, steps, *, crit=CRIT, holder="melee", ranks=RANKS):
    return evaluate_rotation(
        KIT, attacker, ranks, target, parse_steps(steps), crit, holder_range=holder
    )


def item(item_id, *effects):
    return ItemData(item_id, f"test {item_id}", "16.22.1", (), tuple(effects))


def dealt_modifier(effect_id, percent, conditions=()):
    return {
        "id": effect_id,
        "name": effect_id,
        "trigger": {"event": "always"},
        "conditions": list(conditions),
        "evidence_confidence": "official",
        "model_status": "evaluable",
        "components": [
            {
                "kind": "damage_modifier",
                "direction": "dealt",
                "source": "all",
                "mode": "percent",
                "formula": {"op": "constant", "value": percent},
            }
        ],
    }


# Steps


def test_steps_are_read_in_order():
    steps = parse_steps("attack, Q.first_hit attack:crit\te.edge  R")
    assert steps == (
        Step("attack"),
        Step("Q.first_hit", "Q", "first_hit"),
        Step("attack:crit", crit=True),
        Step("e.edge", "E", "edge"),
        Step("R", "R"),
    )


@pytest.mark.parametrize("text", ["", " , ", "dance", "attack:miss", "X", "Q.", "Q.Edge"])
def test_bad_steps_are_rejected(text):
    with pytest.raises(RotationError):
        parse_steps(text)


# Basic attacks and crits


def test_basic_attack_is_total_attack_damage_mitigated():
    attacker = sheet()
    outcome = run(attacker, manual(), "attack")
    (step,) = outcome.steps
    (part,) = step.parts
    attack_damage = attacker["attack_damage"].total()
    assert part.kind == "attack"
    assert part.raw == attack_damage
    assert part.damage == attack_damage * F(100, 100 + 100 * F(7, 10))  # R rank 3: 30 % pen
    assert part.label is Label.DERIVED
    assert outcome.label is Label.DERIVED


def test_crit_adds_infinity_edge_to_the_base_multiplier():
    attacker = sheet(items=("3031",))
    (step,) = run(attacker, manual(armor=0), "attack:crit").steps
    (part,) = step.parts
    assert part.raw == attacker["attack_damage"].total() * F(23, 10)
    assert part.damage == part.raw
    assert part.label is Label.DERIVED
    assert "critical multiplier 2.3" in part.source


def test_crit_needs_a_base_multiplier():
    with pytest.raises(RotationError, match="no critical multiplier"):
        run(sheet(), manual(), "attack:crit", crit=None)
    # Steps without crits do not need it.
    assert run(sheet(), manual(), "attack", crit=None).total > 0


def test_a_record_multiplier_other_than_the_patch_is_flagged():
    other = CritBase(F(1), Label.DERIVED, "test record")
    (step,) = run(sheet(), manual(armor=0), "attack:crit", crit=other).steps
    (part,) = step.parts
    assert part.raw == sheet()["attack_damage"].total()
    assert part.label is Label.PENDING
    assert any("not the patch's 2" in note for note in part.notes)


def test_several_crit_damage_sources_are_pending():
    extra = ItemData("9001", "test", "16.22.1", load_items(ROOT, ["3031"])[0].stats)
    attacker = sheet(items=("3031",), extra_items=(extra,))
    (step,) = run(attacker, manual(armor=0), "attack:crit").steps
    assert step.parts[0].raw == attacker["attack_damage"].total() * F(26, 10)
    assert step.parts[0].label is Label.PENDING


def test_penetration_labels_reach_the_part():
    data = load_champion(ROOT, "Zaahen")
    pending = Contribution(F(10), "bonus", "test", Label.PENDING)
    attacker = build_stat_sheet(
        data, 16, (), load_issues(ROOT), {}, load_records(ROOT), (("lethality", pending),)
    )
    (step,) = run(attacker, manual(), "attack", ranks={}).steps
    assert step.parts[0].mitigation.resistance.effective == 90
    assert step.parts[0].label is Label.PENDING


# On-hit damage and current health


def test_blade_of_the_ruined_king_reads_health_before_each_attack():
    attacker = sheet(items=("3153",))
    outcome = run(attacker, manual(armor=0, health=2000, kind="champion"), "attack attack")
    first, second = outcome.steps
    assert [part.kind for part in first.parts] == ["attack", "on_hit"]
    assert first.parts[1].raw == F(9, 100) * 2000
    assert first.health_before == 2000
    assert second.health_before == 2000 - first.total
    assert second.parts[1].raw == F(9, 100) * second.health_before
    assert first.parts[1].label is Label.DERIVED  # wiki corroborated by the client
    assert outcome.label is Label.DERIVED


def test_ranged_holders_use_the_ranged_ratio():
    target = manual(armor=0, kind="champion")
    (step,) = run(sheet(items=("3153",)), target, "attack", holder="ranged").steps
    assert step.parts[1].raw == F(6, 100) * 3000


def test_on_hit_effects_need_the_holder_range():
    with pytest.raises(RotationError, match="--attacker-range"):
        run(sheet(items=("3153",)), manual(kind="champion"), "attack", holder=None)


def test_on_hit_does_not_crit():
    (step,) = run(sheet(items=("3153",)), manual(armor=0, kind="champion"), "attack:crit").steps
    assert step.parts[1].raw == F(9, 100) * 3000


def test_on_hit_cap_applies_only_to_minions_and_monsters():
    attacker = sheet(items=("3153",))
    for kind, expected in (("minion", 100), ("monster", 100), ("champion", 270)):
        target = manual(armor=0, kind=kind)
        (step,) = run(attacker, target, "attack").steps
        assert step.parts[1].raw == expected
    with pytest.raises(RotationError, match="--target-kind"):
        run(attacker, manual(armor=0), "attack")


def test_abilities_do_not_trigger_on_hit():
    (step,) = run(sheet(items=("3153",)), manual(), "R").steps
    assert [part.kind for part in step.parts] == ["ability"]


def test_current_health_formulas_of_abilities_read_the_carried_health():
    attacker = sheet()
    outcome = run(attacker, manual(), "R E.edge")
    r, e = outcome.steps
    assert e.health_before == 3000 - r.total
    # The edge's magic part scales with max health, which does not change.
    assert e.parts[1].raw == F(6, 100) * 3000


# Damage modifiers


def test_giant_slayer_scales_with_target_bonus_health():
    attacker = sheet(items=("3036",))
    target = manual(bonus_health=F(800), kind="champion")
    (step,) = run(attacker, target, "R").steps
    (part,) = step.parts
    assert part.dealt == (("3036 giant-slayer", F(8)),)
    assert part.damage == part.mitigation.damage * F(108, 100)
    assert part.label is Label.PENDING


def test_giant_slayer_caps_at_fifteen_percent():
    target = manual(health=4000, bonus_health=F(2000), kind="champion")
    (step,) = run(sheet(items=("3036",)), target, "R").steps
    assert step.parts[0].dealt == (("3036 giant-slayer", F(15)),)


def test_giant_slayer_applies_to_on_hit_damage_too():
    target = manual(bonus_health=F(500), kind="champion")
    (step,) = run(sheet(items=("3036", "3153")), target, "attack").steps
    assert [part.dealt for part in step.parts] == [(("3036 giant-slayer", F(5)),)] * 2


def test_giant_slayer_needs_bonus_health_and_a_champion():
    attacker = sheet(items=("3036",))
    with pytest.raises(RotationError, match="--target-bonus-health"):
        run(attacker, manual(kind="champion"), "R")
    with pytest.raises(RotationError, match="--target-kind"):
        run(attacker, manual(bonus_health=F(100)), "R")
    (step,) = run(attacker, manual(bonus_health=F(800), kind="monster"), "R").steps
    assert step.parts[0].dealt == ()


def test_damage_dealt_modifiers_add_up():
    extra = item("9002", dealt_modifier("a", 10), dealt_modifier("b", 20))
    (step,) = run(sheet(extra_items=(extra,)), manual(), "R").steps
    (part,) = step.parts
    assert part.dealt_factor == F(13, 10)
    assert part.damage == part.mitigation.damage * F(13, 10)
    assert part.label is Label.DERIVED


def test_target_items_reduce_attacks_and_crits_multiplicatively():
    defender = sheet("Ahri", 16, ("3047", "3143"), ranks=None)
    target = target_from_sheet(defender)
    outcome = run(sheet(), target, "attack attack:crit R")
    normal, crit, ability = outcome.steps
    assert normal.parts[0].taken == (("3047 plates", F(-10)),)
    assert crit.parts[0].taken == (("3047 plates", F(-10)), ("3143 resilience", F(-30)))
    assert crit.parts[0].taken_factor == F(63, 100)
    assert ability.parts[0].taken == ()
    assert any("humility" in note for note in outcome.notes)


def test_plates_on_on_hit_damage_is_pending():
    defender = sheet("Ahri", 16, ("3047",), ranks=None)
    (step,) = run(sheet(items=("3153",)), target_from_sheet(defender), "attack").steps
    attack, on_hit = step.parts
    assert on_hit.taken == ()
    assert on_hit.label is Label.PENDING
    assert any("on-hit" in note for note in on_hit.notes)


def test_unmodelled_conditions_are_refused():
    extra = item("9003", dealt_modifier("odd", 10, [{"kind": "target_is_stunned"}]))
    with pytest.raises(RotationError, match="target_is_stunned"):
        run(sheet(extra_items=(extra,)), manual(), "R")


def test_effects_that_could_change_damage_weaken_the_result():
    outcome = run(sheet(items=("3089",)), manual(), "R")
    assert outcome.label is Label.PENDING
    assert any("magic-orb" in note for note in outcome.notes)


def test_duplicate_items_are_refused():
    with pytest.raises(RotationError, match="listed twice"):
        run(sheet(items=("3153", "3153")), manual(), "attack")


# Abilities and health


def test_ability_steps_match_the_ability_scenario():
    attacker = sheet()
    target = manual()
    (step,) = run(attacker, target, "E.edge").steps
    expected = evaluate_ability(KIT, attacker, "E", 5, target, case="edge")
    assert step.total == expected.cases[0].total
    assert step.name.startswith("E ")


def test_ability_steps_need_a_rank_and_one_case():
    with pytest.raises(RotationError, match="--learned"):
        run(sheet(ranks={"R": 3}), manual(), "Q.first_hit", ranks={"R": 3})
    with pytest.raises(RotationError, match="E.center, E.edge"):
        run(sheet(), manual(), "E")


def test_lethal_step_and_overkill():
    outcome = run(sheet(), manual(armor=0, health=500), "R R")
    first, second = outcome.steps
    assert first.health_after == 0
    assert second.health_before == 0
    assert outcome.lethal_step == 1
    assert outcome.remaining_health == 0
    assert outcome.total == first.total + second.total


def test_a_rotation_needs_the_target_health():
    with pytest.raises(RotationError, match="--target-max-health"):
        run(sheet(), target_from_values(F(10), F(10)), "R")


def test_unknown_target_kinds_and_bad_bonus_health_are_rejected():
    with pytest.raises(StatsError, match="unknown target kind"):
        manual(kind="ward")
    with pytest.raises(StatsError, match="exceeds"):
        manual(health=100, bonus_health=F(200))
    with pytest.raises(StatsError, match="negative"):
        manual(bonus_health=F(-1))


# Command line


ZAAHEN = [
    "rotation",
    "--champion",
    "Zaahen",
    "--level",
    "16",
    "--learned",
    "E=5",
    "--learned",
    "R=3",
    "--root",
    str(ROOT),
]


def test_rotation_command_text(capsys):
    code = main(
        [
            *ZAAHEN,
            "--item",
            "3153",
            "--item",
            "3036",
            "--attacker-range",
            "melee",
            "--steps",
            "attack, E.edge, attack:crit, R",
            "--target-champion",
            "Ahri",
            "--target-level",
            "16",
            "--target-item",
            "3047",
        ]
    )
    out = capsys.readouterr().out
    assert code == 0
    assert "step 1 attack (basic attack)" in out
    assert "3153 fogblade" in out
    assert "3036 giant-slayer" in out
    assert "critical multiplier: 2 [Derivado]" in out
    assert "remaining health:" in out
    assert out.rstrip().endswith("(weakest input: Pendiente de verificación)")


def test_rotation_command_json(capsys):
    code = main(
        [
            *ZAAHEN,
            "--steps",
            "R attack",
            "--target-armor",
            "0",
            "--target-mr",
            "0",
            "--target-max-health",
            "1000",
            "--json",
        ]
    )
    report = json.loads(capsys.readouterr().out)
    assert code == 0
    assert [step["step"] for step in report["steps"]] == ["R", "attack"]
    assert report["steps"][0]["health_before"] == 1000
    assert report["target"]["kind"] is None
    assert report["attacker"]["critical_multiplier"]["value"] == 2
    assert report["total"] == pytest.approx(sum(step["total"] for step in report["steps"]))


def test_rotation_command_reports_missing_inputs(capsys):
    code = main(
        [
            *ZAAHEN,
            "--item",
            "3153",
            "--steps",
            "attack",
            "--target-armor",
            "50",
            "--target-mr",
            "50",
            "--target-max-health",
            "2000",
            "--target-kind",
            "champion",
        ]
    )
    assert code == 2
    assert "--attacker-range" in capsys.readouterr().err


# Critical strike damage reductions of passives (critical-strike.md, C10)


@pytest.mark.parametrize("champion_id", ["Yasuo", "Yone"])
def test_passive_reduces_total_crit_damage_by_five_percent(champion_id):
    attacker = sheet(champion_id, 18, ["3031"], ranks={})
    (part,) = run(attacker, manual(), "attack:crit", ranks={}).steps[0].parts
    multiplier = (2 + F("0.3")) * F("0.95")
    assert part.raw == attacker["attack_damage"].total() * multiplier
    assert "x critical multiplier 2.185" in part.source
    assert f"{champion_id}'s passive reduces total critical strike damage by 5%" in part.notes
    assert part.label is Label.DERIVED


def test_the_reduction_does_not_touch_normal_attacks():
    attacker = sheet("Yasuo", 18, ["3031"], ranks={})
    (part,) = run(attacker, manual(), "attack", ranks={}).steps[0].parts
    assert part.raw == attacker["attack_damage"].total()
    assert part.notes == ()


def test_the_reduction_is_derived_even_when_every_input_is_official():
    attacker = sheet("Yasuo", 1, ["3031"], ranks={})
    official = CritBase(F(2), Label.OFFICIAL, "test record")
    (part,) = run(attacker, manual(), "attack:crit", crit=official, ranks={}).steps[0].parts
    assert attacker["attack_damage"].label is Label.OFFICIAL
    assert part.label is Label.DERIVED
