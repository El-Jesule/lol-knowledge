"""Reverse defense / survival simulation tests (phase 43, MEC-08 and MEC-09)."""

from __future__ import annotations

import json
from fractions import Fraction as F
from pathlib import Path

import pytest

from lol_knowledge.cli import main
from lol_knowledge.defense import evaluate_defense, hits_from_rotation, parse_incoming
from lol_knowledge.errors import RotationError
from lol_knowledge.kit import load_kit
from lol_knowledge.rotation import evaluate_rotation, parse_steps
from lol_knowledge.runes import load_runes, minor_rune_effects
from lol_knowledge.scenario import target_from_sheet
from lol_knowledge.stats import (
    Label,
    build_stat_sheet,
    load_champion,
    load_issues,
    load_items,
    load_records,
)

ROOT = Path(__file__).resolve().parents[1]
DATA = load_runes(ROOT)
DERIVED = load_records(ROOT)
ISSUES = load_issues(ROOT)


def defender_sheet(
    champion_id: str = "Zaahen",
    level: int = 18,
    items: tuple[str, ...] = (),
    runes: list[int] = (),
):
    champ = load_champion(ROOT, champion_id)
    loaded = load_items(ROOT, items)
    extras = ()
    if runes:
        assert DATA is not None
        eff = minor_rune_effects(runes, DATA, level=level, patch=champ.patch, items=loaded)
        extras = eff.flats
    return build_stat_sheet(champ, level, loaded, ISSUES, {}, DERIVED, extras=extras)


def test_parse_incoming_handles_types_crits_waits_and_rejects_invalid():
    hits = parse_incoming("attack:300, attack:crit:500, physical:200, magic:150, true:80, wait:1.5")
    assert [h.kind for h in hits] == ["attack", "crit", "physical", "magic", "true", "wait"]
    assert hits[1].crit is True and hits[1].amount == 500
    assert hits[5].wait == F(3, 2)

    with pytest.raises(RotationError, match="empty"):
        parse_incoming("   ")
    with pytest.raises(RotationError, match="positive"):
        parse_incoming("true:-10")
    with pytest.raises(RotationError, match="unknown incoming token"):
        parse_incoming("fire:100")


def test_bone_plating_reduces_next_3_hits_including_true_damage_and_ignores_shield_only_hit():
    # Level 18 Bone Plating (8473) blocks 60 flat post-mitigation damage on the next 3 hits!
    sheet = defender_sheet("Ahri", 18, runes=[8473])
    hits = parse_incoming("true:100, true:100, true:100, true:40, true:100")
    out = evaluate_defense(sheet, hits, runes=[8473], rune_data=DATA)
    # Hit 1 triggers Bone Plating (not reduced: 100 dmg).
    # Hits 2, 3 reduce by 60 (40 dmg each); Hit 4 (40 dmg) reduces by 40 (floored at 0);
    # Hit 5 has 0 charges left -> full 100 dmg!
    assert [s.flat_reduced for s in out.steps] == [0, 60, 60, 40, 0]
    assert [s.damage_after_flat for s in out.steps] == [100, 40, 40, 0, 100]
    assert out.total_flat_reduced == 160
    assert out.label is Label.DERIVED

    # Hit absorbed purely by a shield does NOT activate Bone Plating (Bone_Plating rev 4072632).
    shielded = evaluate_defense(
        sheet,
        parse_incoming("true:100, true:100"),
        start_shield=F(150),
        runes=[8473],
        rune_data=DATA,
    )
    assert [s.flat_reduced for s in shielded.steps] == [0, 0]

    # Timeline: charges expire after 1.5 s (wait:2 lets Bone Plating expire before hit 2).
    expired = evaluate_defense(
        sheet,
        parse_incoming("true:100, wait:2, true:100"),
        runes=[8473],
        rune_data=DATA,
        timeline=True,
    )
    assert expired.steps[2].flat_reduced == 0


def test_explicit_flat_damage_reduction_input_floors_at_zero():
    sheet = defender_sheet("Ahri", 18)
    out = evaluate_defense(
        sheet,
        parse_incoming("true:50, true:15"),
        inputs={"flat_damage_reduction": F(25)},
    )
    assert [s.flat_reduced for s in out.steps] == [25, 15]
    assert out.total_damage_taken == 25


def test_steraks_gage_lifeline_triggers_before_30_percent_and_scales_with_hsp():
    # Zaahen lvl 18 with Sterak's Gage (3053, +400 bonus HP) + Redemption (3107, +10% HSP).
    sheet = defender_sheet("Zaahen", 18, items=("3053", "3107"))
    max_hp = sheet["health"].total()
    bonus_hp = sheet["health"].scoped("bonus")
    assert bonus_hp >= 400
    # Start at 40% HP; take true damage equal to 45% max HP (would kill without Lifeline!).
    start_hp = max_hp * F(4, 10)
    fatal_hit = max_hp * F(45, 100)
    out = evaluate_defense(
        sheet,
        parse_incoming(f"true:{fatal_hit}"),
        start_health=start_hp,
    )
    expected_shield = bonus_hp * F(6, 10) * (1 + sheet["heal_and_shield_power"].total())
    assert out.total_shield_granted == expected_shield
    assert out.steps[0].shield_absorbed == min(expected_shield, fatal_hit)
    assert out.survived is True
    assert out.remaining_health == start_hp - (fatal_hit - expected_shield)


def test_guardian_requires_ally_input_and_grants_scaled_shield_on_threshold():
    sheet = defender_sheet("Ahri", 18, items=("3107",), runes=[8465])
    # Missing guardian_ally weakens to Pending
    missing = evaluate_defense(sheet, parse_incoming("true:200"), runes=[8465], rune_data=DATA)
    assert missing.label is Label.PENDING and any("guardian_ally" in n for n in missing.notes)

    # With guardian_ally=1: at lvl 18 threshold is 165; hit of 200 triggers Guardian!
    active = evaluate_defense(
        sheet,
        parse_incoming("true:200"),
        runes=[8465],
        rune_data=DATA,
        inputs={"guardian_ally": F(1)},
    )
    ap_val = sheet["ability_power"].total()
    bonus_hp = sheet["health"].scoped("bonus")
    hsp = sheet["heal_and_shield_power"].total()
    expected = (F(150) + ap_val * F(2, 10) + bonus_hp * F(6, 100)) * (1 + hsp)
    assert active.total_shield_granted == expected
    assert active.steps[0].shield_absorbed == expected
    assert active.steps[0].health_damage == F(200) - expected


def test_second_wind_regenerates_missing_hp_ignores_hsp_and_is_reduced_by_grievous_wounds():
    # Level 18 Ahri with Redemption (+10% HSP) and Second Wind (8444):
    # Takes 500 true damage -> missing HP = 500 -> 4% over 10 s = 20 HP (HSP does NOT amplify it!).
    sheet = defender_sheet("Ahri", 18, items=("3107",), runes=[8444])
    no_gw = evaluate_defense(
        sheet,
        parse_incoming("true:500"),
        runes=[8444],
        rune_data=DATA,
        timeline=True,
    )
    assert no_gw.total_healing == 20
    assert no_gw.remaining_health == sheet["health"].total() - 480

    # With Grievous Wounds (-40%): heals 20 * 0.6 = 12 HP!
    with_gw = evaluate_defense(
        sheet,
        parse_incoming("true:500"),
        runes=[8444],
        rune_data=DATA,
        inputs={"grievous_wounds": F(1)},
        timeline=True,
    )
    assert with_gw.total_healing == 12


def test_thornmail_reflect_and_steelcaps_randuin_apply_to_manual_attacks():
    # Defender with 3047 Plated Steelcaps (-10% attack), 3143 Randuin (-30% crit) and 3075 Thornmail
    sheet = defender_sheet("Zaahen", 18, items=("3047", "3143", "3075"))
    bonus_armor = sheet["armor"].scoped("bonus")
    out = evaluate_defense(sheet, parse_incoming("attack:crit:1000"))
    # Reactive Thornmail raw magic damage = 20 + 10% bonus armor
    assert out.total_reactive_damage == F(20) + bonus_armor * F(1, 10)
    # Mitigated crit is reduced by both Plated Steelcaps (-10%) and Randuin (-30%) -> x0.63!
    armor = sheet["armor"].total()
    mit_only = F(1000) * F(100) / (F(100) + armor)
    assert out.steps[0].incoming == mit_only * F(9, 10) * F(7, 10)


def test_reverse_simulation_from_enemy_champion_rotation_and_time_to_die():
    # Enemy Ahri lvl 18 with Rabadon attacks low-HP Zaahen lvl 16 with Sterak's Gage
    def_sheet = defender_sheet("Zaahen", 16, items=("3053",))
    enemy_champ = load_champion(ROOT, "Ahri")
    enemy_kit = load_kit(ROOT, "Ahri")
    enemy_sheet = build_stat_sheet(
        enemy_champ, 18, load_items(ROOT, ("3089",)), ISSUES, {}, DERIVED
    )
    rot = evaluate_rotation(
        enemy_kit,
        enemy_sheet,
        {"Q": 5, "W": 5, "E": 5, "R": 3},
        target_from_sheet(def_sheet),
        parse_steps("Q.both, wait:1, W.all, E, R.dash"),
        None,
        holder_range="ranged",
        timeline=True,
    )
    hits = hits_from_rotation(rot)
    # Start defender low enough to die at t=1s
    out = evaluate_defense(def_sheet, hits, start_health=F(300), timeline=True)
    assert out.survived is False
    assert out.lethal_step is not None
    assert out.time_to_die is not None
    assert out.total_shield_granted > 0  # Sterak's Lifeline triggered!


def test_cli_survive_manual_and_enemy_champion_json(capsys):
    # Manual incoming hits via CLI with Bone Plating + Sterak
    code = main(
        [
            "survive",
            "--root",
            str(ROOT),
            "--champion",
            "Zaahen",
            "--level",
            "18",
            "--item",
            "3053",
            "--rune",
            "8437",
            "--rune",
            "8401",
            "--rune",
            "8473",
            "--rune",
            "8453",
            "--rune",
            "9104",
            "--rune",
            "8014",
            "--shard",
            "5008",
            "--shard",
            "5008",
            "--shard",
            "5011",
            "--incoming",
            "true:100, true:100, true:100",
            "--json",
        ]
    )
    captured = capsys.readouterr()
    assert code == 0, captured.err
    report = json.loads(captured.out)
    assert report["total_flat_reduced"] == 120.0
    assert report["survived"] is True

    # Enemy champion rotation via CLI
    code2 = main(
        [
            "survive",
            "--root",
            str(ROOT),
            "--champion",
            "Zaahen",
            "--level",
            "16",
            "--item",
            "3053",
            "--enemy-champion",
            "Ahri",
            "--enemy-level",
            "18",
            "--enemy-item",
            "3089",
            "--enemy-learned",
            "Q=5",
            "--enemy-learned",
            "W=5",
            "--enemy-learned",
            "E=5",
            "--enemy-range",
            "ranged",
            "--steps",
            "Q.both, W.all, E",
            "--timeline",
            "--json",
        ]
    )
    cap2 = capsys.readouterr()
    assert code2 == 0, cap2.err
    rep2 = json.loads(cap2.out)
    assert rep2["total_damage_taken"] > 0
    assert rep2["defender"]["champion"] == "Zaahen"
