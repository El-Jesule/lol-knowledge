"""Life steal and omnivamp healing in rotations (life-steal-and-omnivamp.md)."""

from __future__ import annotations

import copy
import json
from fractions import Fraction as F
from pathlib import Path

import pytest

from lol_knowledge.cli import main
from lol_knowledge.errors import RotationError
from lol_knowledge.kit import load_kit
from lol_knowledge.rotation import NO_HEALING, CritBase, evaluate_rotation, parse_steps
from lol_knowledge.rotation_report import format_text, to_dict
from lol_knowledge.scenario import target_from_values
from lol_knowledge.stats import (
    Contribution,
    ItemData,
    ItemStat,
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
BORK = load_items(ROOT, ["3153"])[0]


def vamp(stat_id, value, label=Label.OFFICIAL):
    return (stat_id, Contribution(F(value), "bonus", f"test {stat_id}", label))


def attacker(items=(), extras=()):
    return build_stat_sheet(
        load_champion(ROOT, "Zaahen"),
        16,
        tuple(items),
        load_issues(ROOT),
        {},
        load_records(ROOT),
        tuple(extras),
    )


def target(kind="champion", health=5000, **kwargs):
    return target_from_values(F(100), F(50), max_health=F(health), kind=kind, **kwargs)


def run(sheet, steps, defender=None):
    return evaluate_rotation(
        KIT,
        sheet,
        RANKS,
        defender if defender is not None else target(),
        parse_steps(steps),
        CRIT,
        holder_range="melee",
    )


def on_hit_item(item_id, tag="keep"):
    """Blade of the Ruined King without stats and with the fogblade tag changed."""
    effects = copy.deepcopy([e for e in BORK.effects if e["id"] == "fogblade"])
    component = effects[0]["components"][0]
    if tag is None:
        component.pop("applies_life_steal")
    elif tag != "keep":
        component["applies_life_steal"] = tag
    return ItemData(item_id, f"test {item_id}", BORK.game_version, (), tuple(effects))


def life_steal_item(percent):
    stat = ItemStat("life_steal", "percent", F(percent), "ddragon_stat")
    return ItemData("1053", "test life steal", BORK.game_version, (stat,), ())


def parts(outcome, step=0):
    return outcome.steps[step].parts


def test_without_life_steal_or_omnivamp_nothing_heals():
    outcome = run(attacker(), "attack, Q.first_hit")
    assert all(part.healing is NO_HEALING for step in outcome.steps for part in step.parts)
    assert outcome.healing == 0
    assert outcome.healing_label is Label.OFFICIAL
    text = format_text(outcome, attacker(), target(), CRIT)
    assert "heal:" not in text and "step heal" not in text and "life steal" not in text
    report = to_dict(outcome, attacker(), target(), CRIT)
    assert report["healing"] == 0
    assert report["steps"][0]["parts"][0]["healing"]["amount"] == 0


def test_life_steal_heals_on_the_final_damage_of_an_attack():
    outcome = run(attacker([life_steal_item(15)]), "attack")
    (part,) = parts(outcome)
    assert part.healing.life_steal == F("0.15")
    assert part.healing.omnivamp == 0
    assert part.healing.amount == part.damage * F("0.15")
    assert part.healing.label is Label.DERIVED
    assert part.healing.notes == ()
    assert outcome.healing == outcome.steps[0].healing == part.healing.amount


def test_healing_uses_damage_after_the_damage_modifiers():
    modifier = {
        "id": "amp",
        "name": "amp",
        "trigger": {"event": "always"},
        "conditions": [],
        "evidence_confidence": "official",
        "model_status": "evaluable",
        "components": [
            {
                "kind": "damage_modifier",
                "direction": "dealt",
                "source": "all",
                "mode": "percent",
                "formula": {"op": "constant", "value": 20},
            }
        ],
    }
    amplifier = ItemData("9001", "amp", BORK.game_version, (), (modifier,))
    (part,) = parts(run(attacker([life_steal_item(10), amplifier]), "attack"))
    assert part.damage == part.mitigation.damage * F("1.2")
    assert part.healing.amount == part.damage * F("0.1")


def test_on_hit_damage_heals_when_the_catalog_says_so_with_its_source_label():
    attack, fogblade = parts(run(attacker([BORK]), "attack"))
    assert attack.healing.label is Label.DERIVED
    assert fogblade.kind == "on_hit"
    assert fogblade.healing.life_steal == F("0.1")
    assert fogblade.healing.amount == fogblade.damage * F("0.1")
    assert fogblade.healing.label is Label.PENDING  # the declaration is secondary


def test_a_corroborated_declaration_keeps_the_part_label():
    tag = copy.deepcopy(BORK.effects[0]["components"][0]["applies_life_steal"])
    tag["source"]["confidence"] = "corroborated"
    sheet = attacker([life_steal_item(10), on_hit_item("9002", tag)])
    _, on_hit = parts(run(sheet, "attack"))
    assert on_hit.healing.amount == on_hit.damage * F("0.1")
    assert on_hit.healing.label is Label.DERIVED


def test_on_hit_damage_declared_false_does_not_heal_and_is_not_flagged():
    tag = {"value": False, "source": {"confidence": "secondary"}}
    sheet = attacker([life_steal_item(10), on_hit_item("9002", tag)])
    _, on_hit = parts(run(sheet, "attack"))
    assert on_hit.healing.life_steal == 0 and on_hit.healing.amount == 0
    assert on_hit.healing.label is Label.DERIVED
    assert on_hit.healing.notes == ()


def test_undeclared_on_hit_damage_does_not_heal_and_is_pending():
    sheet = attacker([life_steal_item(10), on_hit_item("9002", None)])
    _, on_hit = parts(run(sheet, "attack"))
    assert on_hit.healing.amount == 0
    assert on_hit.healing.label is Label.PENDING
    assert on_hit.healing.notes == ("the catalog does not declare whether it applies life steal",)


def test_abilities_do_not_apply_life_steal_and_say_why():
    (part,) = parts(run(attacker([life_steal_item(10)]), "R"))
    assert part.kind == "ability"
    assert part.healing.amount == 0
    assert part.healing.label is Label.PENDING
    assert part.healing.notes == ("the kit does not declare whether it applies life steal",)


def test_omnivamp_heals_every_part_against_a_champion():
    sheet = attacker([on_hit_item("9002")], [vamp("omnivamp", "0.05")])
    outcome = run(sheet, "attack, R")
    healed = [part for step in outcome.steps for part in step.parts]
    assert [part.kind for part in healed] == ["attack", "on_hit", "ability"]
    for part in healed:
        assert part.healing.omnivamp == F("0.05")
        assert part.healing.life_steal == 0
        assert part.healing.amount == part.damage * F("0.05")
        assert part.healing.notes == ()
    assert healed[2].healing.label is Label.DERIVED
    assert outcome.healing == sum(part.healing.amount for part in healed)


def test_the_omnivamp_label_reaches_the_healing():
    sheet = attacker((), [vamp("omnivamp", "0.05", Label.PENDING)])
    (part,) = parts(run(sheet, "attack"))
    assert part.healing.label is Label.PENDING


def test_the_life_steal_label_reaches_the_healing():
    sheet = attacker((), [vamp("life_steal", "0.05", Label.PENDING)])
    (part,) = parts(run(sheet, "attack"))
    assert part.healing.amount == part.damage * F("0.05")
    assert part.healing.label is Label.PENDING


@pytest.mark.parametrize("kind", ["minion", "monster"])
def test_omnivamp_on_abilities_against_minions_and_monsters_is_pending(kind):
    sheet = attacker((), [vamp("omnivamp", "0.1")])
    outcome = run(sheet, "attack, R", target(kind))
    attack, ability = outcome.steps[0].parts[0], outcome.steps[1].parts[0]
    assert attack.healing.label is Label.DERIVED and attack.healing.notes == ()
    assert ability.healing.amount == ability.damage * F("0.1")
    assert ability.healing.label is Label.PENDING
    assert ability.healing.notes == (
        f"omnivamp against a {kind} is 33% for pets, damage over time and area spells; "
        "the kit does not say which, healed at 100%",
    )


def test_omnivamp_on_abilities_needs_the_target_kind():
    sheet = attacker((), [vamp("omnivamp", "0.1")])
    assert run(sheet, "attack", target(None)).healing > 0
    with pytest.raises(RotationError, match="omnivamp healing from an ability.*--target-kind"):
        run(sheet, "R", target(None))


def test_life_steal_and_omnivamp_add_up_on_the_same_damage_as_pending():
    sheet = attacker([life_steal_item(10)], [vamp("omnivamp", "0.05")])
    (part,) = parts(run(sheet, "attack"))
    assert part.healing.amount == part.damage * F("0.15")
    assert part.healing.label is Label.PENDING
    assert part.healing.notes == (
        "life steal and omnivamp on the same damage: their sum is not verified",
    )


def test_structures_give_no_healing():
    sheet = attacker([life_steal_item(10)], [vamp("omnivamp", "0.05")])
    (part,) = parts(run(sheet, "attack", target("structure")))
    assert part.healing.amount == 0
    assert part.healing.label is Label.PENDING
    assert part.healing.notes == ("no life steal or omnivamp healing against structures",)


def test_overkill_heals_on_the_full_damage_but_is_pending():
    sheet = attacker([life_steal_item(10)])
    outcome = run(sheet, "attack, attack", target(health=50))
    first, second = outcome.steps
    assert first.overkill and second.health_before == 0 and second.overkill
    assert first.healing == first.parts[0].damage * F("0.1")
    assert first.healing_label is Label.PENDING
    assert first.healing_notes == (
        "the step deals more damage than the target's remaining health; healing uses "
        "the full damage, which is not verified",
    )
    assert outcome.healing_label is Label.PENDING


def test_a_step_that_leaves_exactly_zero_health_is_not_overkill():
    sheet = attacker([life_steal_item(10)])
    damage = run(sheet, "attack").steps[0].total
    step = run(sheet, "attack", target(health=damage)).steps[0]
    assert step.health_after == 0 and not step.overkill
    assert step.healing_label is Label.DERIVED and step.healing_notes == ()


def test_overkill_without_healing_is_not_flagged():
    step = run(attacker(), "attack", target(health=10)).steps[0]
    assert step.overkill and step.healing_label is Label.OFFICIAL and step.healing_notes == ()


def test_reports_show_healing_per_part_step_and_total():
    sheet = attacker([BORK])
    defender = target(health=60)
    outcome = run(sheet, "attack, attack", defender)
    text = format_text(outcome, sheet, defender, CRIT)
    assert "life steal: 10% [Oficial], omnivamp: 0% [Oficial]" in text
    assert "      heal: (life steal 10% + omnivamp 0%) = " in text
    assert "  step heal " in text and "  heal note: the step deals more damage" in text
    assert "total heal: " in text
    report = to_dict(outcome, sheet, defender, CRIT)
    assert report["attacker"]["life_steal"] == {"value": 0.1, "label": "Oficial"}
    assert report["attacker"]["omnivamp"] == {"value": 0.0, "label": "Oficial"}
    step = report["steps"][0]
    assert step["exact_healing"] == str(outcome.steps[0].healing)
    assert step["healing_label"] == "Pendiente de verificación"
    assert step["parts"][1]["healing"]["life_steal"] == 0.1
    assert step["parts"][1]["healing"]["label"] == "Pendiente de verificación"
    assert report["exact_healing"] == str(outcome.healing)
    assert report["healing_label"] == "Pendiente de verificación"
    assert "lol-knowledge/mechanics/life-steal-and-omnivamp.md" in report["rules"]


def test_rotation_command_reports_healing(capsys):
    code = main(
        [
            "rotation",
            "--champion",
            "Zaahen",
            "--level",
            "16",
            "--learned",
            "R=3",
            "--item",
            "3153",
            "--attacker-range",
            "melee",
            "--steps",
            "attack",
            "--target-armor",
            "0",
            "--target-mr",
            "0",
            "--target-max-health",
            "3000",
            "--target-kind",
            "champion",
            "--json",
            "--root",
            str(ROOT),
        ]
    )
    assert code == 0
    report = json.loads(capsys.readouterr().out)
    attack, fogblade = report["steps"][0]["parts"]
    assert attack["healing"]["amount"] == pytest.approx(attack["damage"] * 0.1)
    assert fogblade["healing"]["amount"] == pytest.approx(fogblade["damage"] * 0.1)
    assert report["healing"] == pytest.approx(0.1 * report["total"])


def test_the_rule_is_derived_even_when_the_damage_is_official():
    sheet = build_stat_sheet(
        load_champion(ROOT, "Zaahen"), 1, (life_steal_item(10),), load_issues(ROOT)
    )
    (part,) = parts(run(sheet, "attack"))
    assert part.label is Label.OFFICIAL
    assert part.healing.label is Label.DERIVED


def test_a_pending_part_makes_its_healing_pending():
    sheet = attacker([life_steal_item(10)])
    pending_crit = CritBase(F(2), Label.PENDING, "test record")
    outcome = evaluate_rotation(
        KIT, sheet, RANKS, target(), parse_steps("attack:crit"), pending_crit, holder_range="melee"
    )
    (part,) = parts(outcome)
    assert part.label is Label.PENDING
    assert part.healing.label is Label.PENDING


def test_a_declaration_without_a_known_confidence_is_pending():
    sheet = attacker([life_steal_item(10), on_hit_item("9002", {"value": True, "source": {}})])
    _, on_hit = parts(run(sheet, "attack"))
    assert on_hit.healing.amount == on_hit.damage * F("0.1")
    assert on_hit.healing.label is Label.PENDING


def test_text_report_lists_healing_notes():
    sheet = attacker([life_steal_item(10), on_hit_item("9002", None)])
    defender = target()
    text = format_text(run(sheet, "attack", defender), sheet, defender, CRIT)
    assert "      heal note: the catalog does not declare whether it applies life steal" in text
