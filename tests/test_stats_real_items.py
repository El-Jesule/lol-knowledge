"""Stat sheet and rotation paths exercised with real items of the generated catalog."""

from __future__ import annotations

from fractions import Fraction as F
from pathlib import Path

from lol_knowledge.kit import load_kit
from lol_knowledge.rotation import CritBase, evaluate_rotation, parse_steps
from lol_knowledge.scenario import target_from_values
from lol_knowledge.stats import (
    Label,
    build_stat_sheet,
    growth_multiplier,
    load_champion,
    load_issues,
    load_items,
    load_records,
)

ROOT = Path(__file__).resolve().parents[1]
CHAMPION = load_champion(ROOT, "Zaahen")
KIT = load_kit(ROOT, "Zaahen")


def sheet(level, *item_ids):
    return build_stat_sheet(
        CHAMPION, level, load_items(ROOT, list(item_ids)), load_issues(ROOT), {}, load_records(ROOT)
    )


def test_phantom_dancer_percent_speed_applies_after_mercurys_treads_and_is_soft_capped():
    speed = sheet(1, "3046", "3111")["move_speed"]
    assert speed.raw() == (345 + 45) * F("1.1")
    assert speed.total() == speed.raw() * F("0.8") + 83
    assert speed.soft_capped and speed.label is Label.DERIVED


def test_dorans_blade_gives_omnivamp_from_its_description():
    omnivamp = sheet(1, "1055")["omnivamp"]
    assert omnivamp.total() == F("0.025")
    assert omnivamp.label is Label.OFFICIAL
    assert omnivamp.contributions[0].source == "data:item:1055 ddragon_description (16.22.1)"


def test_spirit_visage_doubles_base_health_regeneration():
    regen = sheet(10, "3065")["health_regen"]
    base = F("7.5") + F("0.8") * growth_multiplier(10)
    assert regen.total() == 2 * base


def test_shurelyas_mana_regeneration_percent():
    regen = sheet(1, "2065")["mana_regen"]
    assert regen.total() == F("8.15") * F("2.25")


def test_spellslingers_shoes_flat_and_percent_magic_penetration():
    data = sheet(1, "3175")
    assert data["magic_penetration_flat"].total() == 20
    assert data["magic_penetration_percent"].total() == F("0.08")


def test_a_zero_in_the_description_stays_pending():
    crit = sheet(1, "3032")["crit_chance"]
    assert crit.total() == 0
    assert crit.label is Label.PENDING
    assert crit.contributions[-1].note.startswith("value unknown: the description shows 0")


def run(*item_ids):
    return evaluate_rotation(
        KIT,
        sheet(16, *item_ids),
        {"R": 3},
        target_from_values(F(100), F(50), max_health=F(3000), kind="champion"),
        parse_steps("attack"),
        CritBase(F(2), Label.DERIVED, "test"),
        holder_range="melee",
    )


def test_an_item_without_effects_keeps_the_rotation_label_and_heals():
    outcome = run("1055")
    (part,) = outcome.steps[0].parts
    assert part.healing.omnivamp == F("0.025")
    assert outcome.label is not Label.PENDING
    assert not any("effect review" in note for note in outcome.notes)


def test_an_item_with_unreviewed_effects_makes_the_rotation_pending():
    outcome = run("3046")
    assert outcome.label is Label.PENDING
    assert (
        "attacker 3046: effect review pending; effects missing from the catalog are not applied"
        in outcome.notes
    )
