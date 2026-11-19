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
    format_text,
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
    assert omnivamp.contributions[0].source == "data:item:1055 ddragon_description (16.23.1)"


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


def test_yun_tal_has_a_confirmed_zero_and_full_stacks():
    crit = sheet(1, "3032")["crit_chance"]
    assert crit.total() == F(1, 4)
    assert crit.label is Label.DERIVED
    zero, stacks = crit.contributions[-2:]
    assert (zero.value, zero.label) == (0, Label.OFFICIAL)
    assert zero.note.startswith("confirmed zero: the item has no crit chance stat")
    assert (stacks.value, stacks.label, stacks.note) == (
        F(1, 4),
        Label.DERIVED,
        "scenario: maximum stacks",
    )
    assert stacks.source == "data:item:3032 effect practice-makes-lethal (16.23.1)"
    lines = format_text(sheet(1, "3032")).splitlines()
    assert "  crit_chance: 25% (base 0% + bonus 25%) [Derivado] (scenario: maximum stacks)" in lines


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


def test_a_scenario_effect_is_left_to_the_sheet_and_flurry_weakens_the_rotation():
    outcome = run("3032")
    assert (
        "attacker 3032 practice-makes-lethal: applied by the stat sheet (scenario max_stacks)"
        in outcome.notes
    )
    assert "attacker 3032 flurry: lasts 6 s; applied only with --timeline" in outcome.notes
    assert outcome.label is Label.PENDING


# Damage effects of the catalog (phase 24)


def test_rabadon_amplifies_the_total_ability_power():
    ap = sheet(1, "3089", "3115")["ability_power"]
    flat = 130 + 80
    assert ap.total() == flat * F("1.3")
    amplifier = ap.contributions[-1]
    assert (amplifier.value, amplifier.note) == (flat * F("0.3"), "30% of the total")
    assert amplifier.source == "data:item:3089 effect magic-orb (16.23.1)"
    assert ap.label is Label.DERIVED


def test_in_combat_stacks_of_terminus_and_guinsoo_are_not_sheet_stats():
    data = sheet(11, "3302", "3124")
    assert data["armor_penetration_percent"].total() == 0
    assert data["magic_penetration_percent"].total() == 0
    assert data["armor"].scoped("bonus") == 0
    assert all("stacks" not in item.note for item in data["attack_speed_bonus"].contributions)


def test_on_hit_damage_of_the_new_items():
    outcome = run("1043", "3115", "3302", "3091")
    attack, *on_hits = outcome.steps[0].parts
    raw = {part.source.split(" (")[0]: part.raw for part in on_hits}
    stats = sheet(16, "1043", "3115", "3302", "3091")
    ap = stats["ability_power"].total()
    bonus_ad = stats["attack_damage"].scoped("bonus")
    assert raw == {
        "1043 sting": 15,
        "3115 icathian-bite": 15 + ap * F("0.15"),
        "3302 shadow": 30 + bonus_ad / 10 + ap / 10,
        "3091 fray": 45,
    }
    assert [part.damage_type.value for part in on_hits] == ["physical", "magic", "magic", "magic"]
    assert outcome.label is not Label.PENDING


def test_guinsoo_stacks_are_computed_by_the_rotation():
    outcome = run("3124")
    assert "attacker 3124 phantom-hit: excluded, not applied" not in outcome.notes
    assert not any("3124 seething-strike" in note for note in outcome.notes)
    assert outcome.label is not Label.PENDING
