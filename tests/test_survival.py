"""Survival mechanics: heal & shield power, shields, Grievous Wounds and effect healing."""

from __future__ import annotations

import json
from fractions import Fraction as F
from pathlib import Path

import pytest

from lol_knowledge.cli import main
from lol_knowledge.errors import RotationError, StatsError
from lol_knowledge.kit import load_kit
from lol_knowledge.rotation import evaluate_rotation, parse_steps
from lol_knowledge.runes import load_runes, minor_rune_effects
from lol_knowledge.scenario import target_from_sheet, target_from_values
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
DATA = load_runes(ROOT)
DERIVED = load_records(ROOT)
ISSUES = load_issues(ROOT)


def simulate(
    champion_id: str,
    steps: str,
    *,
    level: int = 18,
    items: tuple[str, ...] = (),
    extra_items: tuple[ItemData, ...] = (),
    runes: list[int] = (),
    target_armor: int = 0,
    target_mr: int = 0,
    target_max_hp: int = 3000,
    target_current_hp: int | None = None,
    target_kind: str = "champion",
    target_shield: int = 0,
    target_shield_type: str = "normal",
    target_items: tuple[str, ...] | None = None,
    holder_range: str = "ranged",
    inputs: dict[str, F] | None = None,
    timeline: bool = False,
):
    champ = load_champion(ROOT, champion_id)
    kit = load_kit(ROOT, champion_id)
    loaded_items = (*load_items(ROOT, items), *extra_items)
    extras = ()
    if runes:
        assert DATA is not None
        eff = minor_rune_effects(runes, DATA, level=level, patch=champ.patch, items=loaded_items)
        extras = eff.flats
    sheet = build_stat_sheet(champ, level, loaded_items, ISSUES, {}, DERIVED, extras=extras)
    if target_items is not None:
        defender_champ = load_champion(ROOT, "Ahri")
        defender_sheet = build_stat_sheet(
            defender_champ,
            18,
            load_items(ROOT, target_items),
            ISSUES,
            {},
            DERIVED,
        )
        target = target_from_sheet(
            defender_sheet,
            current_health=None if target_current_hp is None else F(target_current_hp),
            shield=F(target_shield),
            shield_type=target_shield_type,
        )
    else:
        target = target_from_values(
            F(target_armor),
            F(target_mr),
            max_health=F(target_max_hp),
            current_health=F(target_max_hp if target_current_hp is None else target_current_hp),
            kind=target_kind,
            shield=F(target_shield),
            shield_type=target_shield_type,
        )
    ap_weight = DERIVED.value(champ.id, "adaptiveforceapweight")
    return evaluate_rotation(
        kit,
        sheet,
        {"Q": 5, "W": 5, "E": 5, "R": 3},
        target,
        parse_steps(steps),
        None,
        holder_range=holder_range,
        inputs=inputs,
        timeline=timeline,
        runes=runes,
        rune_data=DATA,
        ap_weight=ap_weight,
    )


def test_heal_and_shield_power_stacks_additively_from_items_and_revitalize():
    # 3107 Redemption (+10% HSP) + 3504 Ardent Censer (+10% HSP) + 8453 Revitalize (+5% HSP).
    champ = load_champion(ROOT, "Ahri")
    items = load_items(ROOT, ("3107", "3504"))
    assert DATA is not None
    eff = minor_rune_effects([8453], DATA, level=11, patch=champ.patch, items=items)
    sheet = build_stat_sheet(champ, 11, items, ISSUES, {}, DERIVED, extras=eff.flats)
    hsp = sheet["heal_and_shield_power"]
    assert hsp.total() == F(25, 100)
    assert hsp.label is Label.DERIVED


def test_jack_of_all_trades_counts_heal_and_shield_power_from_real_item():
    # 3107 Redemption has health, ability_haste, mana_regen, heal_and_shield_power -> 4 distinct.
    champ = load_champion(ROOT, "Ahri")
    items = load_items(ROOT, ("3107",))
    assert DATA is not None
    eff = minor_rune_effects([8316], DATA, level=11, patch=champ.patch, items=items)
    haste = [c for stat_id, c in eff.flats if stat_id == "ability_haste"]
    assert len(haste) == 1 and haste[0].value == 4


def test_target_normal_shield_absorbs_physical_magic_and_true_damage():
    # Ahri Q.both deals 135 magic + 135 true = 270 at rank 5 with 0 AP against 0 MR.
    # Target with 200 normal shield absorbs 200 and loses only 70 real health!
    out = simulate("Ahri", "Q.both", target_max_hp=1000, target_shield=200)
    assert out.total == 270
    assert out.total_shield_absorbed == 200
    assert out.remaining_shield == 0
    assert out.remaining_health == 930


def test_target_magic_and_physical_shields_only_absorb_matching_damage_types():
    # Ahri Q.both = 135 magic + 135 true. Magic shield of 200 absorbs only 135 magic!
    magic = simulate(
        "Ahri", "Q.both", target_max_hp=1000, target_shield=200, target_shield_type="magic"
    )
    assert magic.total_shield_absorbed == 135
    assert magic.remaining_shield == 65
    assert magic.remaining_health == 865

    # Physical shield of 200 absorbs 0 of Q.both (magic + true), but absorbs a basic attack!
    phys = simulate(
        "Ahri",
        "Q.both, attack",
        target_max_hp=1000,
        target_shield=200,
        target_shield_type="physical",
    )
    assert phys.steps[0].shield_absorbed == 0
    assert phys.steps[0].health_after == 730
    assert phys.steps[1].shield_absorbed == phys.steps[1].total
    assert phys.steps[1].health_after == 730


def test_execute_bypasses_target_shield_and_checks_real_health():
    # The Collector (6676) executes below 5% max HP (50 HP on a 1000 HP target).
    # Target starts at 40 HP with a 500 normal shield: attack hits shield, real HP stays 40 (<50),
    # so Collector executes the 40 real HP cleanly bypassing the shield!
    out = simulate(
        "Zaahen",
        "attack",
        items=("6676",),
        target_max_hp=1000,
        target_current_hp=40,
        target_shield=500,
        holder_range="melee",
    )
    exec_parts = [p for p in out.steps[0].parts if p.kind == "execute"]
    assert len(exec_parts) == 1 and exec_parts[0].damage == 40
    assert out.remaining_health == 0 and out.lethal_step == 1


def test_grievous_wounds_reduces_vamp_and_effect_healing_by_40_percent_without_stacking():
    # 3072 Bloodthirster (15% life steal) + 2510 Dusk and Dawn (Spellblade heal) + 3107 (+10% HSP).
    base = simulate(
        "Zaahen",
        "Q.first_hit, attack",
        items=("3072", "2510", "3107"),
        holder_range="melee",
    )
    gw = simulate(
        "Zaahen",
        "Q.first_hit, attack",
        items=("3072", "2510", "3107"),
        holder_range="melee",
        inputs={"grievous_wounds": F(1)},
    )
    # Effect heal (Dusk and Dawn) scales with +10% HSP; life steal does NOT!
    dusk_base = base.steps[1].heal_events[0]
    assert dusk_base.amount == dusk_base.raw * F(11, 10)
    # Grievous Wounds reduces BOTH vamp and effect healing by exactly 40% (x 0.6).
    assert gw.grievous_wounds_applied is True
    assert gw.healing == base.healing * F(3, 5)
    assert gw.steps[1].heal_events[0].amount == dusk_base.amount * F(3, 5)


def test_thornmail_applies_grievous_wounds_before_triggering_attacks_life_steal():
    # Target wearing 3075 Thornmail applies 40% GW on the triggering basic attack itself!
    no_gw = simulate(
        "Zaahen",
        "attack",
        items=("3072",),
        target_items=(),
        holder_range="melee",
        timeline=True,
    )
    vs_thornmail = simulate(
        "Zaahen",
        "attack, wait:4, Q.first_hit",
        items=("3072",),
        target_items=("3075",),
        holder_range="melee",
        timeline=True,
    )
    assert vs_thornmail.grievous_wounds_applied is True
    # Attack 1 triggers Thornmail GW immediately -> healing is 60% of damage * life_steal!
    atk_part = vs_thornmail.steps[0].parts[0]
    assert atk_part.healing.amount == atk_part.damage * F(15, 100) * F(3, 5)
    assert any("Grievous Wounds" in note for note in atk_part.healing.notes)
    # Without Thornmail, full 100% life steal applies.
    no_gw_part = no_gw.steps[0].parts[0]
    assert no_gw_part.healing.amount == no_gw_part.damage * F(15, 100)


def test_attacker_health_tracks_effective_healing_capped_at_max_health():
    # Attacker starts at 99% HP: healing cannot exceed 1% missing HP!
    champ = load_champion(ROOT, "Zaahen")
    sheet = build_stat_sheet(champ, 18, load_items(ROOT, ("3072",)), ISSUES, {}, DERIVED)
    max_hp = sheet["health"].total()
    out = simulate(
        "Zaahen",
        "attack, attack",
        items=("3072",),
        holder_range="melee",
        inputs={"attacker_health_percent": F(99, 100)},
    )
    assert out.attacker_max_health == max_hp
    assert out.attacker_start_health == max_hp * F(99, 100)
    assert out.attacker_remaining_health == max_hp
    assert out.effective_healing == max_hp * F(1, 100)
    assert out.healing > out.effective_healing


def test_attacker_item_shield_scales_with_hsp_and_ignores_grievous_wounds():
    synthetic_shield_item = ItemData(
        id="9991",
        name="Test Shield",
        game_version="16.23.1",
        stats=(),
        effects=(
            {
                "id": "test-shield",
                "name": "Test Shield",
                "trigger": {"event": "on_hit"},
                "target": {"kind": "self"},
                "model_status": "evaluable",
                "evidence_confidence": "derived",
                "duration_seconds": 2,
                "components": [
                    {
                        "kind": "shield",
                        "mode": "absolute",
                        "target": {"kind": "self"},
                        "formula": {"op": "constant", "value": 100},
                    }
                ],
            },
        ),
        effect_review="complete",
    )
    # 3107 Redemption (+10% HSP) + Grievous Wounds active: shield is 110 (GW does NOT reduce it!).
    out = simulate(
        "Zaahen",
        "attack",
        items=("3107",),
        extra_items=(synthetic_shield_item,),
        holder_range="melee",
        inputs={"grievous_wounds": F(1)},
    )
    assert out.total_shield_granted == 110
    assert out.steps[0].shield_events[0].amount == 110


def test_invalid_shield_and_grievous_inputs_fail_cleanly():
    with pytest.raises(StatsError, match="target shield"):
        target_from_values(F(0), F(0), shield=F(-10))
    with pytest.raises(StatsError, match="shield type"):
        target_from_values(F(0), F(0), shield=F(100), shield_type="true")
    with pytest.raises(RotationError, match="grievous_wounds"):
        simulate("Ahri", "Q.out", inputs={"grievous_wounds": F(2)})


def test_cli_rotation_target_shield_json_output(capsys):
    code = main(
        [
            "rotation",
            "--root",
            str(ROOT),
            "--champion",
            "Ahri",
            "--level",
            "18",
            "--learned",
            "Q=5",
            "--target-armor",
            "0",
            "--target-mr",
            "0",
            "--target-max-health",
            "1000",
            "--target-shield",
            "200",
            "--target-shield-type",
            "magic",
            "--target-kind",
            "champion",
            "--steps",
            "Q.both",
            "--json",
        ]
    )
    captured = capsys.readouterr()
    assert code == 0, captured.err
    report = json.loads(captured.out)
    assert report["target"]["shield"] == 200.0
    assert report["target"]["shield_type"] == "magic"
    assert report["shield_absorbed"] == 135.0
    assert report["remaining_shield"] == 65.0
    assert report["remaining_health"] == 865.0


def test_revitalize_amplifies_vamp_effect_heals_and_shields_below_40_percent_hp():
    # Revitalize (8453): +5% HSP always (on effect heal & shield, NOT life steal) AND
    # +10% multiplicative below 40% attacker HP (on ALL healing including life steal + shields).
    synthetic_shield = ItemData(
        id="9992",
        name="Test Shield",
        game_version="16.23.1",
        stats=(),
        effects=(
            {
                "id": "test-shield",
                "name": "Test Shield",
                "trigger": {"event": "on_hit"},
                "target": {"kind": "self"},
                "model_status": "evaluable",
                "evidence_confidence": "derived",
                "components": [
                    {
                        "kind": "shield",
                        "mode": "absolute",
                        "target": {"kind": "self"},
                        "formula": {"op": "constant", "value": 100},
                    }
                ],
            },
        ),
        effect_review="complete",
    )
    high = simulate(
        "Zaahen",
        "attack",
        items=("3072",),
        extra_items=(synthetic_shield,),
        runes=[8453],
        holder_range="melee",
        inputs={"attacker_health_percent": F(8, 10)},
    )
    low = simulate(
        "Zaahen",
        "attack",
        items=("3072",),
        extra_items=(synthetic_shield,),
        runes=[8453],
        holder_range="melee",
        inputs={"attacker_health_percent": F(3, 10)},
    )
    # Above 40% HP: shield gets +5% HSP (105), life steal gets 1.0x.
    assert high.total_shield_granted == 105
    # Below 40% HP: shield gets 100 * 1.05 * 1.10 = 115.5; life steal gets 1.10x!
    assert low.total_shield_granted == F(100) * F(105, 100) * F(11, 10)
    assert low.healing == high.healing * F(11, 10)


def test_grasp_of_the_undying_heals_and_scales_with_hsp_and_grievous_wounds():
    champ = load_champion(ROOT, "Zaahen")
    items = load_items(ROOT, ("3107",))  # +10% HSP
    sheet = build_stat_sheet(champ, 18, items, ISSUES, {}, DERIVED)
    max_hp = sheet["health"].total()

    out = simulate(
        "Zaahen",
        "attack",
        items=("3107",),
        runes=[8437],
        holder_range="melee",
        inputs={"grasp_ready": F(1)},
    )
    assert len(out.steps[0].heal_events) == 1
    assert out.steps[0].heal_events[0].raw == max_hp * F(13, 1000)
    assert out.steps[0].heal_events[0].amount == max_hp * F(13, 1000) * F(11, 10)

    # Ranged penalty (0.4x) + Grievous Wounds (0.6x)
    ranged_gw = simulate(
        "Ahri",
        "attack",
        runes=[8437],
        holder_range="ranged",
        inputs={"grasp_ready": F(1), "grievous_wounds": F(1)},
    )
    ahri_hp = build_stat_sheet(load_champion(ROOT, "Ahri"), 18, (), ISSUES, {}, DERIVED)[
        "health"
    ].total()
    assert ranged_gw.steps[0].heal_events[0].amount == ahri_hp * F(13, 1000) * F(4, 10) * F(3, 5)


def test_shield_bash_fires_from_attacker_shield_or_explicit_input():
    # Explicit --input shield_amount=200 on Zaahen lvl 18 with Long Sword (1036 -> physical)
    # and 0 bonus HP: 30 + 0 + 0.15 * 200 = 60 physical damage on attack 1 (consumed, not attack 2).
    out = simulate(
        "Zaahen",
        "attack, attack",
        items=("1036",),
        runes=[8401],
        holder_range="melee",
        inputs={"shield_amount": F(200)},
    )
    sb1 = [p for p in out.steps[0].parts if p.kind == "rune"]
    sb2 = [p for p in out.steps[1].parts if p.kind == "rune"]
    assert len(sb1) == 1 and sb1[0].raw == 60 and sb1[0].label is Label.DERIVED
    assert sb2 == []


def test_taste_of_blood_heals_when_damaged_skips_at_full_hp_and_respects_20s_cooldown():
    # At full health (attacker_health_percent=1): does not trigger!
    full = simulate(
        "Ahri",
        "Q.out",
        items=("3089",),
        runes=[8139],
        inputs={"attacker_health_percent": F(1)},
    )
    assert full.steps[0].heal_events == ()

    # Damaged (0.5): heals 40 + 0.05 * 169 = 48.45, then 20s CD in timeline!
    damaged = simulate(
        "Ahri",
        "Q.out, wait:10, W.one, wait:10, E",
        items=("3089",),
        runes=[8139],
        inputs={"attacker_health_percent": F(1, 2)},
        timeline=True,
    )
    assert len(damaged.steps[0].heal_events) == 1
    assert damaged.steps[0].heal_events[0].raw == F(40) + F(5, 100) * F(169)
    assert damaged.steps[2].heal_events == ()  # t=10s (< 20s CD)
    assert len(damaged.steps[4].heal_events) == 1  # t=20s (CD ready)


def test_absorb_life_and_triumph_trigger_on_lethal_step():
    # Low-HP enemy champion killed by Ahri Q.both -> triggers both Absorb Life (23 at lvl 18)
    # and Triumph (2.5% max HP + 5% missing HP).
    champ = load_champion(ROOT, "Ahri")
    max_hp = build_stat_sheet(champ, 18, (), ISSUES, {}, DERIVED)["health"].total()

    out = simulate(
        "Ahri",
        "Q.both",
        runes=[9101, 9111],
        target_max_hp=1000,
        target_current_hp=100,
        inputs={"attacker_health_percent": F(1, 2)},
    )
    assert out.lethal_step == 1
    by_source = {ev.source: ev.raw for ev in out.steps[0].heal_events}
    assert any("AbsorbLife" in k and v == 23 for k, v in by_source.items())
    expected_triumph = max_hp * F(25, 1000) + (max_hp / 2) * F(5, 100)
    assert any("Triumph" in k and v == expected_triumph for k, v in by_source.items())

    # Non-lethal step triggers neither!
    alive = simulate("Ahri", "Q.out", runes=[9101, 9111], target_max_hp=3000)
    assert alive.lethal_step is None and alive.steps[0].heal_events == ()


def test_font_of_life_heals_when_target_impaired_with_ranged_penalty():
    missing = simulate("Ahri", "Q.out", runes=[8463], holder_range="ranged")
    assert missing.label is Label.PENDING and any("target_impaired" in n for n in missing.notes)

    ranged = simulate(
        "Ahri",
        "Q.out",
        runes=[8463],
        holder_range="ranged",
        inputs={"target_impaired": F(1)},
    )
    # Level 18 base heal = 50, ranged penalty x 0.7 = 35!
    assert len(ranged.steps[0].heal_events) == 1
    assert ranged.steps[0].heal_events[0].raw == 35
    assert ranged.steps[0].heal_events[0].label is Label.DERIVED
