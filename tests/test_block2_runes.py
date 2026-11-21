"""Tests for Block 2: remaining 5 keystones, 6 minor runes (62/62 coverage), and defender runes."""

from __future__ import annotations

import json
from fractions import Fraction as F
from pathlib import Path

import pytest

from lol_knowledge.cli import main
from lol_knowledge.contract import execute_request
from lol_knowledge.defense import evaluate_defense, parse_incoming
from lol_knowledge.errors import RotationError
from lol_knowledge.kit import load_kit, passive_contributions
from lol_knowledge.mcp_server import _TARGET_SCHEMA
from lol_knowledge.rotation import evaluate_rotation, parse_steps
from lol_knowledge.runes import (
    item_haste_from_runes,
    load_runes,
    minor_rune_effects,
    scale_item_cooldown,
)
from lol_knowledge.scenario import target_from_values
from lol_knowledge.stats import (
    build_stat_sheet,
    load_champion,
    load_issues,
    load_items,
    load_records,
)

ROOT = Path(__file__).resolve().parents[1]
DATA = load_runes(ROOT)
assert DATA is not None
ISSUES = load_issues(ROOT)
RECORDS = load_records(ROOT)


def _sheet(
    champ_name: str,
    level: int,
    item_ids: list[str] = (),
    runes: list[int] = (),
    shards: list[int] = (),
    inputs: dict[str, F] | None = None,
    ranks: dict[str, int] | None = None,
    *,
    adaptive: str | None = None,
):
    champ = load_champion(ROOT, champ_name)
    items = load_items(ROOT, list(item_ids))
    kit = load_kit(ROOT, champ.id)
    extras = passive_contributions(kit, ranks or {}) if (kit and ranks) else ()
    fx = minor_rune_effects(
        runes,
        DATA,
        level=level,
        patch=champ.patch,
        items=items,
        inputs=inputs,
        adaptive=adaptive,
    )
    return build_stat_sheet(
        champ,
        level,
        items,
        ISSUES,
        {},
        RECORDS,
        (*extras, *fx.flats),
        fx.percents,
        fx.pending,
        extra_amplifiers=fx.amplifiers,
        extra_notes=fx.notes,
        move_speed_bonus_amp=fx.move_speed_bonus_amp,
        inputs=inputs,
    )


def _rotate(
    champ_name: str,
    level: int,
    steps_text: str,
    *,
    runes: list[int] = (),
    item_ids: list[str] = (),
    ranks: dict[str, int] | None = None,
    holder_range: str = "melee",
    target=None,
    inputs: dict[str, F] | None = None,
    timeline: bool = False,
    adaptive: str | None = None,
):
    champ = load_champion(ROOT, champ_name)
    kit = load_kit(ROOT, champ.id)
    assert kit is not None
    sheet = _sheet(
        champ_name,
        level,
        item_ids=item_ids,
        runes=runes,
        inputs=inputs,
        ranks=ranks,
        adaptive=adaptive,
    )
    if target is None:
        target = target_from_values(
            F(0), F(0), max_health=F(2000), current_health=F(2000), kind="champion"
        )
    ap_weight = RECORDS.value(champ.id, "adaptiveforceapweight") if RECORDS else None
    return evaluate_rotation(
        kit,
        sheet,
        ranks or {},
        target,
        parse_steps(steps_text),
        crit_base=None,
        holder_range=holder_range,
        inputs=inputs,
        timeline=timeline,
        runes=runes,
        rune_data=DATA,
        ap_weight=ap_weight,
    )


def _cli(capsys, *argv: str):
    code = main([*argv, "--root", str(ROOT)])
    return code, capsys.readouterr()


# ---------------------------------------------------------------------------
# 1. Full 62/62 Rune Coverage Verification
# ---------------------------------------------------------------------------


def test_all_62_tree_runes_are_covered_none_left_unmodelled():
    tree_rune_ids = sorted(rid for tree in DATA.trees.values() for row in tree.rows for rid in row)
    assert len(tree_rune_ids) == 62
    for rid in tree_rune_ids:
        fx = minor_rune_effects([rid], DATA, level=11, patch="16.23.1")
        assert not any("effects not modelled" in msg for msg in fx.pending), (
            f"Rune {rid} ({DATA.runes[rid].key}) still reports effects not modelled: {fx.pending}"
        )


# ---------------------------------------------------------------------------
# 2. Keystones: Fleet Footwork, Phase Rush, Aftershock, Glacial, Spellbook
# ---------------------------------------------------------------------------


def test_fleet_footwork_melee_ranged_minion_and_statikk_energize():
    # Level 18 melee with 0 bonus AD, 0 AP -> Heal = 160
    melee = _rotate("Zaahen", 18, "attack", runes=[8021], holder_range="melee", timeline=True)
    assert melee.healing == F(160)
    assert any("8021" in e.source for e in melee.steps[0].heal_events)
    assert not any("8021" in note and "effects not modelled" in note for note in melee.notes)

    # Ranged multiplier x0.6 -> 160 * 0.6 = 96
    ranged = _rotate("Ahri", 18, "attack", runes=[8021], holder_range="ranged", timeline=True)
    assert ranged.healing == F(96)

    # Minion multiplier x0.15 -> 160 * 0.15 = 24
    minion = target_from_values(F(0), F(0), max_health=F(500), current_health=F(500), kind="minion")
    vs_minion = _rotate(
        "Zaahen", 18, "attack", runes=[8021], holder_range="melee", target=minion, timeline=True
    )
    assert vs_minion.healing == F(24)

    # Statikk Shiv (3087) gives +15 charge per attack -> 1st attack procs (resets to 0),
    # attacks 2..8 charge 7 * 15 = 105 -> 100, and 9th attack procs again!
    with_statikk = _rotate(
        "Zaahen",
        18,
        ", ".join(["attack"] * 9),
        runes=[8021],
        item_ids=["3087"],
        holder_range="melee",
        timeline=True,
    )
    fleet_procs = [
        step.index
        for step in with_statikk.steps
        if any("8021" in h.source for h in step.heal_events)
    ]
    assert fleet_procs == [1, 9]


def test_fleet_footwork_and_phase_rush_ms_boost_hecarim_warpath_ad():
    # Hecarim's passive Warpath converts bonus MS into bonus AD (12%..24% by level).
    # With Trinity Force (3078, +30% AS), attack 2 lands at < 1.0 s while Fleet Footwork's
    # +20% MS buff is active -> Attack 2 deals strictly more damage via Warpath!
    base = _rotate(
        "Hecarim",
        18,
        "attack, attack",
        runes=[],
        item_ids=["3078"],
        holder_range="melee",
        timeline=True,
    )
    fleet = _rotate(
        "Hecarim",
        18,
        "attack, attack",
        runes=[8021],
        item_ids=["3078"],
        holder_range="melee",
        timeline=True,
    )
    assert fleet.steps[0].total == base.steps[0].total
    assert fleet.steps[1].total > base.steps[1].total

    # Stormraider's Surge / Phase Rush (8230): dealing >= 25% of target max HP within 3 s
    # grants +48% MS (melee) for 4 s -> next attack gets massive Warpath bonus AD!
    squishy = target_from_values(
        F(0), F(0), max_health=F(400), current_health=F(400), kind="champion"
    )
    pr_base = _rotate(
        "Hecarim",
        18,
        "attack, attack",
        runes=[],
        holder_range="melee",
        target=squishy,
        timeline=True,
    )
    pr_run = _rotate(
        "Hecarim",
        18,
        "attack, attack",
        runes=[8230],
        holder_range="melee",
        target=squishy,
        timeline=True,
    )
    assert pr_run.steps[1].total > pr_base.steps[1].total
    assert any("8230" in note and "+48%" in note for note in pr_run.notes)

    # Against a tanky target where 1 hit is < 25% max HP, Phase Rush does NOT proc.
    tank = target_from_values(
        F(0), F(0), max_health=F(10000), current_health=F(10000), kind="champion"
    )
    no_proc = _rotate(
        "Hecarim", 18, "attack, attack", runes=[8230], holder_range="melee", target=tank
    )
    assert not any("8230" in note and "activated" in note for note in no_proc.notes)


def test_aftershock_rotation_delayed_burst_and_defense_resists():
    # Without timeline: immediate magic burst on step 1 when target_impaired=1.
    # Level 18 + Warmog (3083: +1000 HP + 12% bonus HP Warmog's Vitality = 1120 bonus HP)
    # -> 120 + 0.08 * 1120 = 209.6 = 1048/5 magic damage (0 MR).
    imm = _rotate(
        "Zaahen",
        18,
        "attack",
        runes=[8439],
        item_ids=["3083"],
        inputs={"target_impaired": F(1)},
        timeline=False,
    )
    burst_parts = [p for p in imm.steps[0].parts if "8439" in p.source]
    assert len(burst_parts) == 1
    assert burst_parts[0].raw == F(1048, 5)
    assert burst_parts[0].damage_type.value == "magic"

    # With timeline: burst fires at t=2.5 s (delayed tail step), NOT at t=0.
    tl = _rotate(
        "Zaahen",
        18,
        "attack",
        runes=[8439],
        item_ids=["3083"],
        inputs={"target_impaired": F(1)},
        timeline=True,
    )
    assert not any("8439" in p.source for p in tl.steps[0].parts)
    delayed = [s for s in tl.steps if any("8439" in p.source for p in s.parts)]
    assert len(delayed) == 1
    assert delayed[0].time == F(5, 2)
    assert delayed[0].total == F(1048, 5)

    # In defense (`survive`): Aftershock grants +45 Armor & +45 MR (no bonus resists) for 2.5 s.
    def_sheet = _sheet("Zaahen", 1)
    hits = parse_incoming("physical:1000")
    without = evaluate_defense(def_sheet, hits, timeline=True)
    with_as = evaluate_defense(
        def_sheet,
        hits,
        runes=[8439],
        rune_data=DATA,
        inputs={"aftershock_active": F(1)},
        timeline=True,
    )
    assert with_as.total_damage_taken < without.total_damage_taken
    assert any("8439" in note for note in with_as.steps[0].notes)


def test_glacial_augment_slow_calculation_and_ally_damage_reduction():
    # Rotation with target_impaired=1 calculates exact freeze-zone slow and notes -15% ally DR.
    # Ahri level 11 with Rabadon (3089) has AP > 0 -> slow > 20%.
    rot = _rotate(
        "Ahri",
        11,
        "Q.out",
        runes=[8351],
        item_ids=["3089"],
        ranks={"Q": 5},
        holder_range="ranged",
        inputs={"target_impaired": F(1)},
        timeline=True,
    )
    assert any("8351" in note and "freeze zone" in note for note in rot.notes)
    assert not any("8351" in note and "effects not modelled" in note for note in rot.notes)

    # Defense (`survive`) with glacial_ally=1 reduces physical/magic incoming damage by 15% for 3 s.
    def_sheet = _sheet("Ahri", 11)
    hits = parse_incoming("magic:500")
    base = evaluate_defense(def_sheet, hits, timeline=True)
    with_glacial = evaluate_defense(def_sheet, hits, inputs={"glacial_ally": F(1)}, timeline=True)
    assert with_glacial.total_damage_taken == base.total_damage_taken * F(85, 100)


def test_unsealed_spellbook_is_informative_and_does_not_weaken_label():
    sheet = _sheet("Ahri", 11, runes=[8360])
    assert any("8360" in note for note in sheet.notes)
    assert not any("8360" in note for note in sheet.pending_effects)
    rot = _rotate("Ahri", 11, "Q.out", runes=[8360], ranks={"Q": 5}, holder_range="ranged")
    assert not any("8360" in note for note in rot.notes)


# ---------------------------------------------------------------------------
# 3. Minor Runes: Approach Velocity, Unflinching, Nimbus Cloak, Cosmic Insight,
#    Triple Tonic, Time Warp Tonic
# ---------------------------------------------------------------------------


def test_minor_runes_approach_velocity_unflinching_nimbus_cloak_triple_tonic():
    # Approach Velocity (8410): +15% MS (own CC), +7.5% MS (ally CC)
    av_self = minor_rune_effects(
        [8410], DATA, level=11, patch="16.23.1", inputs={"target_impaired": F(1)}
    )
    assert [(s, c.value) for s, c in av_self.percents] == [("move_speed", F(15, 100))]
    av_ally = minor_rune_effects(
        [8410], DATA, level=11, patch="16.23.1", inputs={"target_impaired": F(1), "ally_cc": F(1)}
    )
    assert [(s, c.value) for s, c in av_ally.percents] == [("move_speed", F(15, 200))]

    # Unflinching (8242): +10 Armor & +10 MR when defender_impaired=1
    unf = minor_rune_effects(
        [8242], DATA, level=11, patch="16.23.1", inputs={"defender_impaired": F(1)}
    )
    assert [(s, c.value) for s, c in unf.flats] == [("armor", F(10)), ("magic_resist", F(10))]
    # Defense without double-counting when sheet already has Unflinching
    def_with_sheet = _sheet("Zaahen", 11, runes=[8242], inputs={"defender_impaired": F(1)})
    def_plain = _sheet("Zaahen", 11)
    hits = parse_incoming("physical:500")
    d_sheet = evaluate_defense(
        def_with_sheet, hits, runes=[8242], rune_data=DATA, inputs={"defender_impaired": F(1)}
    )
    d_dyn = evaluate_defense(
        def_plain, hits, runes=[8242], rune_data=DATA, inputs={"defender_impaired": F(1)}
    )
    assert d_sheet.total_damage_taken == d_dyn.total_damage_taken

    # Nimbus Cloak (8275): 15% (<100s), 35% (100..249s), 45% (>=250s)
    for cd, expected in ((F(90), F(15, 100)), (F(180), F(35, 100)), (F(300), F(45, 100))):
        nc = minor_rune_effects(
            [8275], DATA, level=11, patch="16.23.1", inputs={"summoner_spell_cd": cd}
        )
        assert [(s, c.value) for s, c in nc.percents] == [("move_speed", expected)]

    # Triple Tonic (8313): +25 adaptive force (15 AD / 25 AP) at level >= 6
    tt_low = minor_rune_effects(
        [8313],
        DATA,
        level=5,
        patch="16.23.1",
        inputs={"triple_tonic_force": F(1)},
        adaptive="ability_power",
    )
    assert tt_low.flats == ()
    tt_ap = minor_rune_effects(
        [8313],
        DATA,
        level=6,
        patch="16.23.1",
        inputs={"triple_tonic_force": F(1)},
        adaptive="ability_power",
    )
    assert [(s, c.value) for s, c in tt_ap.flats] == [("ability_power", F(25))]
    tt_ad = minor_rune_effects(
        [8313],
        DATA,
        level=6,
        patch="16.23.1",
        inputs={"triple_tonic_force": F(1)},
        adaptive="attack_damage",
    )
    assert [(s, c.value) for s, c in tt_ad.flats] == [("attack_damage", F(15))]


def test_cosmic_insight_scales_item_cooldowns_in_rotation_and_defense():
    assert item_haste_from_runes([8347], DATA) == F(10)
    assert scale_item_cooldown(F(10), F(10)) == F(100, 11)

    # Ravenous Hydra (3074) active has 10 s CD -> with Cosmic Insight (+10 item haste)
    # CD is 100/11 ≈ 9.091 s. Casting item:3074, waiting 9.2 s, casting item:3074 again:
    # WITHOUT Cosmic Insight -> raises RotationError (on cooldown until 10 s).
    # WITH Cosmic Insight -> 2nd cast fires!
    with pytest.raises(RotationError, match="cooldown until 10 s"):
        _rotate(
            "Zaahen",
            11,
            "item:3074, wait:9.2, item:3074",
            runes=[],
            item_ids=["3074"],
            timeline=True,
        )
    with_ci = _rotate(
        "Zaahen",
        11,
        "item:3074, wait:9.2, item:3074",
        runes=[8347],
        item_ids=["3074"],
        timeline=True,
    )
    assert with_ci.steps[2].total > F(0)

    # Defense: Edge of Night (3814) spell shield CD is 40 s -> with Cosmic Insight
    # CD is 40/1.1 ≈ 36.36 s. Two ability hits 37 s apart: without Cosmic Insight only
    # 1st is blocked; with Cosmic Insight BOTH are blocked!
    def_sheet = _sheet("Zaahen", 11, item_ids=["3814"])
    hits = parse_incoming("ability:magic:400, wait:37, ability:magic:400")
    d_no_ci = evaluate_defense(def_sheet, hits, timeline=True)
    d_ci = evaluate_defense(def_sheet, hits, runes=[8347], rune_data=DATA, timeline=True)
    assert d_no_ci.total_damage_taken > F(0)
    assert d_ci.total_damage_taken == F(0)


def test_time_warp_tonic_upfront_heal_in_rotation_and_defense():
    # Health Potion (2003): 120 HP over 15 s (8 HP/s).
    # With Time Warp Tonic (8352): 40% (48 HP) immediate + 60% (72 HP) over 15 s (4.8 HP/s).
    # After item:2003 + wait:5:
    #   Normal: 5 * 8 = 40 HP
    #   Time Warp Tonic: 48 + 5 * 4.8 = 72 HP
    normal = _rotate(
        "Zaahen", 11, "item:2003, wait:5, attack", runes=[], item_ids=["2003"], timeline=True
    )
    twt = _rotate(
        "Zaahen", 11, "item:2003, wait:5, attack", runes=[8352], item_ids=["2003"], timeline=True
    )
    assert normal.healing == F(40)
    assert twt.healing == F(72)
    assert any("Time Warp Tonic" in h.source for h in twt.steps[0].heal_events)

    # Defense (`survive`): lethal hit of 400 HP when defender has 380 HP + Health Potion (2003).
    # Without Time Warp Tonic: dies immediately at t=0 (potion heals over time after hit).
    # With Time Warp Tonic: 48 HP immediate heal at t=0 -> survives!
    def_sheet = _sheet("Ahri", 1, item_ids=["2003"])
    hits = parse_incoming("true:400")
    d_norm = evaluate_defense(
        def_sheet, hits, start_health=F(380), inputs={"potion_active": F(1)}, timeline=True
    )
    d_twt = evaluate_defense(
        def_sheet,
        hits,
        start_health=F(380),
        runes=[8352],
        rune_data=DATA,
        inputs={"potion_active": F(1)},
        timeline=True,
    )
    assert not d_norm.survived
    assert d_twt.survived


# ---------------------------------------------------------------------------
# 4. Defender Runes & Shards (CLI, Rotation, Contract JSON, MCP)
# ---------------------------------------------------------------------------


def test_defender_bone_plating_and_conditioning_in_cli_rotation(capsys):
    # Target: Ahri level 11 with Resolve page including Bone Plating (8473) & Conditioning (8429)
    # vs Zaahen (Q, E learned) dealing 4 rapid hits within 1.5 s, plus 1 hit after wait:2.
    def_page = ["8437", "8446", "8429", "8451", "8009", "8014"]
    bp_page = ["8437", "8446", "8473", "8451", "8009", "8014"]
    # Use tenacity shard (5013) so target max HP stays identical between plain & bp_page
    # (otherwise +65 HP shard increases Zaahen's % max HP E.edge damage before Bone Plating).
    shards = ["5008", "5008", "5013"]

    def _target_args(runes):
        out = ["--target-champion", "Ahri", "--target-level", "11"]
        for r in runes:
            out += ["--target-rune", r]
        for s in shards:
            out += ["--target-shard", s]
        return out

    base_cmd = [
        "rotation",
        "--champion",
        "Zaahen",
        "--level",
        "11",
        "--learned",
        "Q=5",
        "--learned",
        "E=5",
        "--steps",
        "attack, Q.first_hit, E.edge, attack, wait:2, attack",
        "--timeline",
        "--input",
        "game_minutes=12",
        "--input",
        "overgrowth_units=0",
        "--json",
    ]
    code0, cap0 = _cli(capsys, *base_cmd, "--target-champion", "Ahri", "--target-level", "11")
    assert code0 == 0, cap0.err
    rep_plain = json.loads(cap0.out)

    # Conditioning (8429 at 12 min) increases target Armor -> less damage on every attack.
    code1, cap1 = _cli(capsys, *base_cmd, *_target_args(def_page))
    assert code1 == 0, cap1.err
    rep_cond = json.loads(cap1.out)
    assert rep_cond["total"] < rep_plain["total"]

    # Bone Plating (8473 at target level 11): reduction = 30 + (60 - 30) * 10 / 17 = 810/17 ≈ 47.647
    # Step 0 procs Bone Plating (full damage); Steps 1, 2, 3 (within 1.5 s) each reduced by 810/17;
    # Step 5 (after wait:2 -> Bone Plating expired & on 55 s CD) takes full damage!
    code2, cap2 = _cli(capsys, *base_cmd, *_target_args(bp_page))
    assert code2 == 0, cap2.err
    rep_bp = json.loads(cap2.out)
    assert rep_bp["steps"][0]["total"] == pytest.approx(rep_plain["steps"][0]["total"])
    expected_reduction = float(F(30) + F(30) * F(10, 17))
    for i in (1, 2, 3):
        assert rep_plain["steps"][i]["total"] - rep_bp["steps"][i]["total"] == pytest.approx(
            expected_reduction, abs=1e-4
        )
    assert rep_bp["steps"][5]["total"] == pytest.approx(rep_plain["steps"][5]["total"])


def test_defender_rune_without_target_champion_errors(capsys):
    code, cap = _cli(
        capsys,
        "ability",
        "--champion",
        "Ahri",
        "--level",
        "11",
        "--ability",
        "Q",
        "--rank",
        "5",
        "--target-armor",
        "50",
        "--target-mr",
        "50",
        "--target-rune",
        "8473",
    )
    assert code == 2
    assert "--target-rune" in cap.err


def test_defender_runes_in_contract_and_mcp_schema():
    assert "runes" in _TARGET_SCHEMA["properties"]
    assert "shards" in _TARGET_SCHEMA["properties"]
    assert "inputs" in _TARGET_SCHEMA["properties"]

    plain_req = {
        "operation": "rotation",
        "params": {
            "champion": "Zaahen",
            "level": 11,
            "steps": "attack, attack",
            "timeline": True,
            "target": {"champion": "Ahri", "level": 11},
        },
    }
    bp_req = {
        "operation": "rotation",
        "params": {
            "champion": "Zaahen",
            "level": 11,
            "steps": "attack, attack",
            "timeline": True,
            "allow_illegal_build": True,
            "target": {
                "champion": "Ahri",
                "level": 11,
                "runes": [8473],
                "shards": [5011],
            },
        },
    }
    res_plain = execute_request(plain_req, ROOT)
    res_bp = execute_request(bp_req, ROOT)
    assert res_plain["ok"] and res_bp["ok"]
    # Step 2 reduced by Bone Plating (target level 11: 810/17)
    diff = res_plain["result"]["steps"][1]["total"] - res_bp["result"]["steps"][1]["total"]
    assert diff == pytest.approx(float(F(30) + F(30) * F(10, 17)), abs=1e-4)
    # Target max HP increased by +65 from Health shard (5011)
    assert res_bp["result"]["target"]["stats"]["max_health"] - res_plain["result"]["target"][
        "stats"
    ]["max_health"] == pytest.approx(65.0)
