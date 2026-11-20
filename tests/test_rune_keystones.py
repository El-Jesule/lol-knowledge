"""Offensive keystones in rotations (phase 40, lol-knowledge/mechanics/runes.md)."""

from __future__ import annotations

import json
from fractions import Fraction as F
from pathlib import Path

import pytest

from lol_knowledge.cli import main
from lol_knowledge.damage import DamageType
from lol_knowledge.errors import RotationError
from lol_knowledge.kit import load_kit
from lol_knowledge.rotation import evaluate_rotation, parse_steps
from lol_knowledge.runes import load_runes
from lol_knowledge.scenario import target_from_values
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
SHARDS = [5008, 5008, 5011]


def simulate(
    champion_id,
    runes,
    steps,
    *,
    level=18,
    items=(),
    target_kind="champion",
    target_max_hp=3000,
    target_current_hp=None,
    target_armor=0,
    target_mr=0,
    holder_range="ranged",
    inputs=None,
    timeline=False,
    ranks=None,
):
    champ = load_champion(ROOT, champion_id)
    kit = load_kit(ROOT, champion_id)
    loaded_items = load_items(ROOT, items)
    sheet = build_stat_sheet(champ, level, loaded_items, ISSUES, {}, DERIVED)
    target = target_from_values(
        F(target_armor),
        F(target_mr),
        max_health=F(target_max_hp),
        current_health=F(target_max_hp if target_current_hp is None else target_current_hp),
        kind=target_kind,
    )
    ap_weight = DERIVED.value(champ.id, "adaptiveforceapweight")
    return evaluate_rotation(
        kit,
        sheet,
        ranks or {"Q": 5, "W": 5, "E": 5, "R": 3},
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


def test_electrocute_fires_on_3rd_hit_within_3s_and_respects_20s_cooldown():
    # Ahri lvl 18 with Rabadon (3089 -> 130 * 1.3 = 169 AP) -> magic adaptive damage:
    # 240 + 0.05 * 169 = 248.45
    out = simulate("Ahri", [8112], "Q.out, W.one, E", items=["3089"], timeline=True)
    assert not any(p.kind == "rune" for p in out.steps[0].parts)
    assert not any(p.kind == "rune" for p in out.steps[1].parts)
    procs = [p for p in out.steps[2].parts if p.kind == "rune"]
    assert len(procs) == 1
    assert procs[0].damage_type is DamageType.MAGIC
    assert procs[0].raw == F(240) + F(5, 100) * F(169)
    assert procs[0].label is Label.DERIVED

    # Window > 3s expires previous hits (no proc on 3rd hit).
    expired = simulate("Ahri", [8112], "Q.out, wait:4, W.one, E", items=["3089"], timeline=True)
    assert not any(p.kind == "rune" for step in expired.steps for p in step.parts)


def test_dark_harvest_requires_souls_and_fires_below_50_percent():
    missing = simulate("Ahri", [8128], "Q.out")
    assert missing.label is Label.PENDING
    assert any("dark_harvest_souls" in note for note in missing.notes)

    # Above 50% HP after hit: does not fire.
    high = simulate(
        "Ahri", [8128], "Q.out", target_max_hp=3000, target_current_hp=3000,
        inputs={"dark_harvest_souls": F(10)}, items=["3089"],
    )  # fmt: skip
    assert not any(p.kind == "rune" for p in high.steps[0].parts)

    # Below 50% HP: 30 + 11 * 10 + 0.05 * 169 = 148.45 magic damage!
    low = simulate(
        "Ahri", [8128], "Q.out", target_max_hp=3000, target_current_hp=1000,
        inputs={"dark_harvest_souls": F(10)}, items=["3089"],
    )  # fmt: skip
    procs = [p for p in low.steps[0].parts if p.kind == "rune"]
    assert len(procs) == 1 and procs[0].raw == F(140) + F(5, 100) * F(169)


def test_press_the_attack_bursts_on_3rd_attack_and_amplifies_subsequent_damage():
    # Zaahen lvl 18 (melee, bonus AD from Long Sword 1036 -> physical adaptive):
    # 3rd attack fires 160 physical burst; 4th step (Q.first_hit) gets +8% dealt!
    out = simulate(
        "Zaahen",
        [8005],
        "attack, attack, attack, Q.first_hit",
        items=["1036"],
        holder_range="melee",
    )
    burst = [p for p in out.steps[2].parts if p.kind == "rune"]
    assert len(burst) == 1
    assert burst[0].raw == 160 and burst[0].damage_type is DamageType.PHYSICAL
    assert burst[0].label is Label.DERIVED  # level 18 endpoint
    assert out.steps[3].parts[0].dealt == (("rune:8005 PressTheAttack", F(8)),)

    # Intermediate level (11) marks linear curve Pending.
    mid = simulate("Zaahen", [8005], "attack, attack, attack", level=11, items=["1036"])
    assert [p for p in mid.steps[2].parts if p.kind == "rune"][0].label is Label.PENDING


def test_conqueror_stacks_adaptive_force_and_heals_at_max_stacks():
    # Zaahen lvl 18 melee with Long Sword (1036 -> AD adaptive).
    # Each hit gives 2 stacks -> 6 hits reach 12 stacks (4.0 * 0.6 = 2.4 AD/stack -> +28.8 AD).
    # 7th attack deals +28.8 more AD AND heals 8% of its post-mitigation damage!
    out = simulate(
        "Zaahen",
        [8010],
        "attack, attack, attack, attack, attack, attack, attack",
        items=["1036"],
        holder_range="melee",
        timeline=True,
    )
    # Step 1 (0 stacks) vs Step 7 (12 stacks): +28.8 raw AD!
    assert out.steps[6].parts[0].raw - out.steps[0].parts[0].raw == F(144, 5)
    assert out.steps[5].healing == 0  # 10 stacks before step 6
    assert out.steps[6].healing == out.steps[6].total * F(8, 100)


def test_lethal_tempo_stacks_attack_speed_and_deals_on_hit_damage_at_max_stacks():
    # Zaahen lvl 18 melee with Long Sword (1036 -> physical adaptive):
    # Attacks 1..6 build 6 stacks (+36% AS); attack 7 deals bonus adaptive note damage:
    # 30 * (1 + bonus_AS_total)!
    out = simulate(
        "Zaahen",
        [8008],
        "attack, attack, attack, attack, attack, attack, attack",
        items=["1036"],
        holder_range="melee",
        timeline=True,
    )
    assert not any(p.kind == "rune" for s in out.steps[:6] for p in s.parts)
    procs = [p for p in out.steps[6].parts if p.kind == "rune"]
    assert len(procs) == 1 and procs[0].damage_type is DamageType.PHYSICAL
    assert procs[0].raw > 30  # amplified by bonus attack speed

    # Ranged marks client 16.23 tooltip-vs-calc discrepancy as Pending.
    ranged = simulate(
        "Ahri",
        [8008],
        "attack, attack, attack, attack, attack, attack, attack",
        items=["1036"],
        holder_range="ranged",
        timeline=True,
    )
    assert [p for p in ranged.steps[6].parts if p.kind == "rune"][0].label is Label.PENDING


def test_hail_of_blades_boosts_3_attacks_and_deals_true_damage():
    # Zaahen lvl 18 melee with Long Sword (+10 bAD):
    # Bonus true damage = 20 + 0.12 * 10 = 21.2 on attacks 1, 2, 3 (not 4)!
    out = simulate(
        "Zaahen",
        [9923],
        "attack, attack, attack, attack",
        items=["1036"],
        holder_range="melee",
        timeline=True,
    )
    assert [any(p.kind == "rune" for p in s.parts) for s in out.steps] == [True, True, True, False]
    proc = [p for p in out.steps[0].parts if p.kind == "rune"][0]
    assert proc.damage_type is DamageType.TRUE and proc.raw == F(20) + F(12, 100) * 10
    # Attacks 1->2 and 2->3 are faster than 3->4 because HoB adds +90% AS during the first 3 hits!
    dt_boosted = out.steps[1].time - out.steps[0].time
    dt_normal = out.steps[3].time - out.steps[2].time
    assert dt_boosted < dt_normal


def test_summon_aery_fires_once_and_warns_on_subsequent_hits():
    # Single step: clean Derivado proc (50 + 0.05 * 169 = 58.45 magic damage).
    one = simulate("Ahri", [8214], "Q.out", items=["3089"])
    procs = [p for p in one.steps[0].parts if p.kind == "rune"]
    assert len(procs) == 1 and procs[0].raw == F(50) + F(5, 100) * F(169)
    assert one.label is Label.DERIVED

    # Second step: cannot model return time -> warns and weakens.
    two = simulate("Ahri", [8214], "Q.out, W.one", items=["3089"])
    assert not any(p.kind == "rune" for p in two.steps[1].parts)
    assert two.label is Label.PENDING
    assert any("return travel time" in note for note in two.notes)


def test_arcane_comet_scales_with_distance_and_refunds_cooldown():
    missing = simulate("Ahri", [8229], "Q.out", items=["3089"])
    assert missing.label is Label.PENDING
    assert any("comet_distance" in note for note in missing.notes)

    # At distance 0: 100 + 0.05 * 169 = 108.45 (Derivado).
    d0 = simulate("Ahri", [8229], "Q.out", items=["3089"], inputs={"comet_distance": F(0)})
    p0 = [p for p in d0.steps[0].parts if p.kind == "rune"][0]
    assert p0.raw == F(100) + F(5, 100) * F(169) and p0.label is Label.DERIVED

    # At distance 750: +100% amp = 2x damage (Derivado).
    d750 = simulate("Ahri", [8229], "Q.out", items=["3089"], inputs={"comet_distance": F(750)})
    p750 = [p for p in d750.steps[0].parts if p.kind == "rune"][0]
    assert p750.raw == p0.raw * 2 and p750.label is Label.DERIVED

    # Timeline CD at lvl 18 is 8 s; hitting W.one at 0s refunds 20% -> ready at 6.4s!
    tl = simulate(
        "Ahri",
        [8229],
        "Q.out, W.one, wait:7, E",
        items=["3089"],
        inputs={"comet_distance": F(0)},
        timeline=True,
    )
    assert any(p.kind == "rune" for p in tl.steps[0].parts)
    assert not any(p.kind == "rune" for p in tl.steps[1].parts)
    assert any(p.kind == "rune" for p in tl.steps[3].parts)


def test_deathfire_touch_burns_and_amplifies_after_3_seconds():
    # Ahri lvl 18 with Rabadon (169 AP): dps = 12 + 0.025 * 169 = 16.225 magic/s.
    # Single-target duration=4s in timeline: 3s at 1x + 1s at 1.75x = 4.75 * 16.225!
    tl = simulate(
        "Ahri",
        [8992],
        "Q.out",
        items=["3089"],
        inputs={"deathfire_duration": F(4)},
        timeline=True,
    )
    assert len(tl.steps) == 2 and tl.steps[1].time == 4
    burns = [p for p in tl.steps[1].parts if p.kind == "burn"]
    assert len(burns) == 2  # split at 3.0 s!
    dps = F(12) + F(25, 1000) * F(169)
    assert burns[0].raw == dps * 3
    assert burns[1].raw == dps * F(7, 4)

    with pytest.raises(RotationError, match="deathfire_duration"):
        simulate("Ahri", [8992], "Q.out", inputs={"deathfire_duration": F(3)})


def test_first_strike_adds_7_percent_true_damage_without_double_amplifying():
    # Ahri Q.back rank 5 (135 true dmg) + Coup de Grace (+8% below 40% HP) = 145.8.
    # First Strike adds 7% of 145.8 as true damage (NOT amplified again by Coup de Grace!).
    out = simulate(
        "Ahri",
        [8369, 8014],
        "Q.back",
        target_max_hp=2000,
        target_current_hp=500,
        inputs={"first_strike": F(1)},
        timeline=True,
    )
    q_part, fs_part = out.steps[0].parts
    assert q_part.damage == F(135) * F(108, 100)
    assert fs_part.kind == "rune" and fs_part.damage_type is DamageType.TRUE
    assert fs_part.dealt == ()
    assert fs_part.damage == q_part.damage * F(7, 100)


def test_grasp_of_the_undying_scales_with_max_hp_and_ranged_penalty():
    missing = simulate("Zaahen", [8437], "attack", holder_range="melee")
    assert missing.label is Label.PENDING and any("grasp_ready" in n for n in missing.notes)

    melee = simulate("Zaahen", [8437], "attack", holder_range="melee", inputs={"grasp_ready": F(1)})
    proc_m = [p for p in melee.steps[0].parts if p.kind == "rune"][0]
    champ_hp = load_champion(ROOT, "Zaahen")
    sheet_m = build_stat_sheet(champ_hp, 18, (), ISSUES, {}, DERIVED)
    assert proc_m.damage_type is DamageType.MAGIC
    assert proc_m.raw == sheet_m["health"].total() * F(35, 1000)

    # Ranged has 40% effectiveness; if grasp_ready=0, charges after 4s in timeline!
    ranged = simulate(
        "Ahri",
        [8437],
        "attack, wait:4, attack",
        holder_range="ranged",
        inputs={"grasp_ready": F(0)},
        timeline=True,
    )
    assert not any(p.kind == "rune" for p in ranged.steps[0].parts)
    proc_r = [p for p in ranged.steps[2].parts if p.kind == "rune"][0]
    sheet_r = build_stat_sheet(load_champion(ROOT, "Ahri"), 18, (), ISSUES, {}, DERIVED)
    assert proc_r.raw == sheet_r["health"].total() * F(35, 1000) * F(4, 10)


def test_cli_full_legal_page_with_electrocute_resolves_without_unmodelled_runes(capsys):
    # Legal page where EVERY rune is modelled:
    # Domination: 8112 Electrocute, 8143 SuddenImpact, 8137 SixthSense, 8106 UltimateHunter
    # Sorcery: 8226 ManaflowBand, 8210 Transcendence
    page = [8112, 8143, 8137, 8106, 8226, 8210]
    code = main(
        [
            "rotation",
            "--root",
            str(ROOT),
            "--champion",
            "Ahri",
            "--level",
            "18",
            "--item",
            "3089",
            "--learned",
            "Q=5",
            "--learned",
            "W=5",
            "--learned",
            "E=5",
            "--target-armor",
            "0",
            "--target-mr",
            "0",
            "--target-max-health",
            "3000",
            "--target-kind",
            "champion",
            "--attacker-range",
            "ranged",
            "--steps",
            "Q.out, W.one, E",
            "--timeline",
            "--input",
            "sudden_impact=1",
            *(a for r in page for a in ("--rune", str(r))),
            *(a for s in SHARDS for a in ("--shard", str(s))),
            "--json",
        ]
    )
    captured = capsys.readouterr()
    assert code == 0, captured.err
    report = json.loads(captured.out)
    assert report["weakest_input_label"] == "Derivado"
    assert any(
        p["kind"] == "rune" and "8143 SuddenImpact" in p["source"]
        for p in report["steps"][0]["parts"]
    )
    assert any(
        p["kind"] == "rune" and "8112 Electrocute" in p["source"]
        for p in report["steps"][2]["parts"]
    )
