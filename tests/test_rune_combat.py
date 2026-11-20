"""Combat minor runes in rotations (phase 39, lol-knowledge/mechanics/runes.md)."""

from __future__ import annotations

import json
from fractions import Fraction as F
from pathlib import Path

import pytest

from lol_knowledge.cli import main
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
    load_records,
)

ROOT = Path(__file__).resolve().parents[1]
DATA = load_runes(ROOT)
SHARDS = [5008, 5008, 5011]


def run(capsys, *args):
    code = main([*args[:1], "--root", str(ROOT), *args[1:]])
    return code, capsys.readouterr()


def page_args(runes, shards=SHARDS):
    return [
        *(arg for rune in runes for arg in ("--rune", str(rune))),
        *(arg for shard in shards for arg in ("--shard", str(shard))),
    ]


def ahri_rotation(
    runes,
    steps,
    *,
    level=11,
    target_kind="champion",
    target_max_hp=2000,
    target_current_hp=None,
    target_armor=0,
    target_mr=0,
    holder_range="ranged",
    inputs=None,
    timeline=False,
    ranks=None,
):
    champ = load_champion(ROOT, "Ahri")
    kit = load_kit(ROOT, "Ahri")
    sheet = build_stat_sheet(champ, level, (), load_issues(ROOT), {}, load_records(ROOT))
    target = target_from_values(
        F(target_armor),
        F(target_mr),
        max_health=F(target_max_hp),
        current_health=F(target_max_hp if target_current_hp is None else target_current_hp),
        kind=target_kind,
    )
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
    )


def test_coup_de_grace_amplifies_only_below_40_percent_and_including_true_damage():
    # Ahri Q.back is true damage (135 base at rank 5, 0 AP).
    # At 800/2000 (exactly 40%): not below 40% -> 0%.
    at_40 = ahri_rotation([8014], "Q.back", target_max_hp=2000, target_current_hp=800)
    assert at_40.steps[0].parts[0].dealt == ()
    assert at_40.total == 135
    # At 799/2000 (< 40%): +8% including true damage!
    below_40 = ahri_rotation([8014], "Q.back", target_max_hp=2000, target_current_hp=799)
    part = below_40.steps[0].parts[0]
    assert part.dealt == (("rune:8014 CoupDeGrace", F(8)),)
    assert part.damage == F(135) * F(108, 100)
    assert below_40.label is Label.DERIVED
    # Non-champion target: does not apply and does not weaken.
    minion = ahri_rotation([8014], "Q.back", target_kind="minion", target_current_hp=500)
    assert minion.steps[0].parts[0].dealt == () and minion.label is Label.DERIVED


def test_cut_down_amplifies_above_60_percent_and_turns_off_after_hp_drops():
    # Start at 1300/2000 (65% > 60%): first Q.back (135 * 1.08 = 145.8) drops target to
    # 1154.2 (< 60%), so second Q.back gets 0% (135)!
    outcome = ahri_rotation([8017], "Q.back, Q.back", target_max_hp=2000, target_current_hp=1300)
    assert outcome.steps[0].parts[0].dealt == (("rune:8017 CutDown", F(8)),)
    assert outcome.steps[0].total == F(135) * F(108, 100)
    assert outcome.steps[1].parts[0].dealt == ()
    assert outcome.steps[1].total == 135
    assert outcome.label is Label.DERIVED


def test_last_stand_scales_linearly_from_60_to_30_percent_and_flags_exact_boundary():
    missing = ahri_rotation([8299], "Q.back")
    assert missing.label is Label.PENDING
    assert any("attacker_health_percent" in note for note in missing.notes)

    above = ahri_rotation([8299], "Q.back", inputs={"attacker_health_percent": F(7, 10)})
    assert above.steps[0].parts[0].dealt == () and above.label is Label.DERIVED

    exact_60 = ahri_rotation([8299], "Q.back", inputs={"attacker_health_percent": F(6, 10)})
    assert exact_60.steps[0].parts[0].dealt == (("rune:8299 LastStand", F(5)),)
    assert exact_60.label is Label.PENDING

    mid_45 = ahri_rotation([8299], "Q.back", inputs={"attacker_health_percent": F(45, 100)})
    assert mid_45.steps[0].parts[0].dealt == (("rune:8299 LastStand", F(8)),)
    assert mid_45.label is Label.DERIVED

    low_20 = ahri_rotation([8299], "Q.back", inputs={"attacker_health_percent": F(2, 10)})
    assert low_20.steps[0].parts[0].dealt == (("rune:8299 LastStand", F(11)),)
    assert low_20.label is Label.DERIVED


def test_axiom_arcanist_amplifies_only_r_and_requires_ultimate_aoe_only_when_r_is_cast():
    # Without R in rotation: does not weaken!
    no_r = ahri_rotation([8224], "Q.out")
    assert no_r.steps[0].parts[0].dealt == ()
    assert no_r.label is Label.DERIVED

    # With R and missing ultimate_aoe: weakens and explains input.
    missing = ahri_rotation([8224], "R.dash")
    assert missing.label is Label.PENDING
    assert any("ultimate_aoe" in note for note in missing.notes)

    # Single-target (+12%) vs AoE (+8%), and Q is untouched!
    st = ahri_rotation([8224], "Q.out, R.dash", inputs={"ultimate_aoe": F(0)})
    assert st.steps[0].parts[0].dealt == ()
    assert st.steps[1].parts[0].dealt == (("rune:8224 NullifyingOrb", F(12)),)
    assert st.label is Label.DERIVED

    aoe = ahri_rotation([8224], "R.dash", inputs={"ultimate_aoe": F(1)})
    assert aoe.steps[0].parts[0].dealt == (("rune:8224 NullifyingOrb", F(8)),)


def test_scorch_fires_once_without_timeline_and_delays_1s_with_10s_cd_in_timeline():
    # At level 18 Scorch deals 40 magic damage (0 MR -> 40).
    no_tl = ahri_rotation([8237], "Q.out, Q.out", level=18)
    assert len(no_tl.steps[0].parts) == 2
    scorch = no_tl.steps[0].parts[1]
    assert scorch.kind == "rune" and scorch.raw == 40 and scorch.damage == 40
    assert len(no_tl.steps[1].parts) == 1  # only fires once without --timeline

    # With --timeline: Q at 0s schedules Scorch at 1s (CD until 10s);
    # Q at 8s is still on Scorch CD; Q at 16s schedules a second Scorch at 17s!
    tl = ahri_rotation([8237], "Q.out, wait:8, Q.out, wait:8, Q.out", level=18, timeline=True)
    # Step 1 (0s): Q only; Step 2 (wait:8): nothing at 0s; Step 3 (8s): Scorch@1s + Q;
    # Step 4 (wait:8): nothing at 8s; Step 5 (16s): Q only (Scorch was on CD at 8s, now
    # re-armed at 16s -> schedules Scorch@17s); Step 6 (trailing at 17s): Scorch@17s!
    assert len(tl.steps[0].parts) == 1
    assert any(p.kind == "rune" and "at 1 s" in p.source for p in tl.steps[2].parts)
    assert not any(p.kind == "rune" for p in tl.steps[4].parts)
    assert len(tl.steps) == 6
    assert tl.steps[5].time == 17
    assert tl.steps[5].parts[0].kind == "rune" and tl.steps[5].parts[0].raw == 40


def test_cheap_shot_and_sudden_impact_deal_true_damage_with_cooldowns():
    # Missing inputs weaken without crashing, even when target_kind is omitted.
    missing = ahri_rotation([8126, 8143], "Q.out", target_kind=None)
    assert missing.label is Label.PENDING
    assert any("target_impaired" in note for note in missing.notes)
    assert any("sudden_impact" in note for note in missing.notes)

    # Inactive (=0): cleanly resolved, 0 procs.
    off = ahri_rotation(
        [8126, 8143],
        "Q.out",
        target_kind=None,
        inputs={"target_impaired": F(0), "sudden_impact": F(0)},
    )
    assert len(off.steps[0].parts) == 1 and off.label is Label.DERIVED

    # Active (=1) at level 18: Cheap Shot = 45 true (4s CD), Sudden Impact = 80 true (10s CD).
    tl = ahri_rotation(
        [8126, 8143],
        "attack, wait:5, attack, wait:6, attack",
        level=18,
        inputs={"target_impaired": F(1), "sudden_impact": F(1)},
        timeline=True,
    )
    # Step 1 (0s): both fire (45 + 80)
    s1_runes = [p for p in tl.steps[0].parts if p.kind == "rune"]
    assert [p.raw for p in s1_runes] == [45, 80]
    # Step 3 (5s): Cheap Shot off 4s CD (fires 45), Sudden Impact still on 10s CD
    s3_runes = [p for p in tl.steps[2].parts if p.kind == "rune"]
    assert [p.raw for p in s3_runes] == [45]
    # Step 5 (11s): both off CD again (45 + 80); Sudden Impact notes re-armed assumption
    s5_runes = [p for p in tl.steps[4].parts if p.kind == "rune"]
    assert [p.raw for p in s5_runes] == [45, 80]
    assert any("armed again" in note for note in s5_runes[1].notes)


def test_demolish_fires_on_third_attack_against_structures_only():
    # Against champion: does not apply and does not require --attacker-range.
    vs_champ = ahri_rotation([8446], "attack, attack, attack", holder_range=None)
    assert all(p.kind == "attack" for step in vs_champ.steps for p in step.parts)
    assert vs_champ.label is Label.DERIVED

    # Against structure without range: refuses to guess.
    with pytest.raises(RotationError, match="attacker-range"):
        ahri_rotation([8446], "attack", target_kind="structure", holder_range=None)

    # Against structure (ranged): 50 + 20% of Ahri lvl 11 max HP (1502.6) = 350.52 physical.
    vs_turret = ahri_rotation(
        [8446],
        "attack, attack, attack, attack, attack, attack",
        target_kind="structure",
        target_max_hp=5000,
        holder_range="ranged",
        timeline=True,
    )
    # Fires on attack 3, then 30s CD blocks attacks 4-6!
    assert [any(p.kind == "rune" for p in s.parts) for s in vs_turret.steps] == [
        False,
        False,
        True,
        False,
        False,
        False,
    ]
    proc = [p for p in vs_turret.steps[2].parts if p.kind == "rune"][0]
    assert proc.raw == F(50) + F(2, 10) * F(15026, 10)


def test_target_kind_is_required_by_champion_and_structure_combat_runes():
    for rune_id in (8014, 8017, 8237, 8446):
        with pytest.raises(RotationError, match="--target-kind"):
            ahri_rotation([rune_id], "Q.out", target_kind=None)
    with pytest.raises(RotationError, match="--target-kind"):
        ahri_rotation([8143], "Q.out", target_kind=None, inputs={"sudden_impact": F(1)})


def test_cli_ability_keeps_combat_runes_pending_while_rotation_applies_them(capsys):
    # Sorcery (8230 PhaseRush unmodelled, 8224 Axiom, 8210 Transcendence, 8237 Scorch) +
    # Precision (9104 Alacrity, 8014 CoupDeGrace)
    page = [8230, 8224, 8210, 8237, 9104, 8014]
    common = [
        "--champion",
        "Ahri",
        "--level",
        "11",
        "--target-armor",
        "0",
        "--target-mr",
        "0",
        "--target-max-health",
        "2000",
        *page_args(page),
        "--json",
    ]
    # `ability` does not apply combat minor runes -> weakens label to Pendiente de verificación,
    # even without a keystone (using only stat + combat minor runes with --allow-illegal-build).
    code, captured = run(
        capsys,
        "ability",
        "--champion",
        "Ahri",
        "--level",
        "11",
        "--target-armor",
        "0",
        "--target-mr",
        "0",
        "--target-max-health",
        "2000",
        "--ability",
        "R",
        "--rank",
        "3",
        "--case",
        "dash",
        "--rune",
        "8014",
        "--shard",
        "5008",
        "--shard",
        "5008",
        "--shard",
        "5011",
        "--allow-illegal-build",
        "--json",
    )
    assert code == 0, captured.err
    assert json.loads(captured.out)["weakest_input_label"] == "Pendiente de verificación"

    # `stats` notes combat runes as applied in rotation.
    code, captured = run(
        capsys, "stats", "--champion", "Ahri", "--level", "11", *page_args(page), "--json"
    )
    assert code == 0, captured.err
    stats_notes = json.loads(captured.out)["notes"]
    assert "rune 8014 Golpe de gracia: combat effect (applied in rotation)" in stats_notes

    # `rotation` applies Coup de Grace (+8%), Axiom Arcanist (+12% on R), and Scorch!
    code, captured = run(
        capsys,
        "rotation",
        *common,
        "--learned",
        "R=3",
        "--target-kind",
        "champion",
        "--target-current-health",
        "500",
        "--steps",
        "R.dash",
        "--input",
        "ultimate_aoe=0",
    )
    assert code == 0, captured.err
    rot_report = json.loads(captured.out)
    step = rot_report["steps"][0]
    # R part gets additive +8% (Coup) + +12% (Axiom) = +20% dealt!
    r_part = step["parts"][0]
    assert r_part["dealt_modifiers"] == [
        {"effect": "rune:8014 CoupDeGrace", "percent": 8.0},
        {"effect": "rune:8224 NullifyingOrb", "percent": 12.0},
    ]
    # Scorch part fires as a rune proc and gets +8% from Coup de Grace (NOT Axiom).
    scorch_part = step["parts"][1]
    assert scorch_part["kind"] == "rune"
    assert scorch_part["dealt_modifiers"] == [{"effect": "rune:8014 CoupDeGrace", "percent": 8.0}]
    # Only unmodelled keystone 8230 remains in not_applied!
    assert any("8230" in note for note in rot_report["not_applied"])
    assert not any("8014" in note for note in rot_report["not_applied"])
    assert not any("8237" in note for note in rot_report["not_applied"])


@pytest.mark.parametrize(
    ("rune_id", "steps", "inputs"),
    [
        (8224, "R.dash", {"ultimate_aoe": F(2)}),
        (8126, "Q.out", {"target_impaired": F(2)}),
        (8143, "Q.out", {"sudden_impact": F(2)}),
    ],
)
def test_invalid_combat_rune_inputs_raise_rotation_error(rune_id, steps, inputs):
    with pytest.raises(RotationError, match="between 0 and 1"):
        ahri_rotation([rune_id], steps, inputs=inputs)


def test_rune_procs_heal_with_omnivamp_but_not_life_steal():
    from lol_knowledge.stats import Contribution

    champ = load_champion(ROOT, "Ahri")
    kit = load_kit(ROOT, "Ahri")
    extras = [
        ("life_steal", Contribution(F(1, 10), "bonus", "test", Label.DERIVED)),
        ("omnivamp", Contribution(F(1, 10), "bonus", "test", Label.DERIVED)),
    ]
    sheet = build_stat_sheet(champ, 18, (), load_issues(ROOT), {}, load_records(ROOT), extras)
    target = target_from_values(F(0), F(0), max_health=F(2000), kind="champion")
    outcome = evaluate_rotation(
        kit,
        sheet,
        {"Q": 5},
        target,
        parse_steps("Q.out"),
        None,
        holder_range="ranged",
        runes=[8237],
        rune_data=DATA,
    )
    scorch = outcome.steps[0].parts[1]
    assert scorch.kind == "rune" and scorch.damage == 40
    assert scorch.healing.life_steal == 0
    assert scorch.healing.omnivamp == F(1, 10)
    assert scorch.healing.amount == 4
