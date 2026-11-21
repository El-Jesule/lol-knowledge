"""Item actives executable as ``item:<id>`` rotation steps (catalog v26)."""

from __future__ import annotations

from fractions import Fraction as F
from pathlib import Path

import pytest

from lol_knowledge.errors import RotationError
from lol_knowledge.kit import load_kit
from lol_knowledge.optimizer import OptimizeConstraints, optimize_build
from lol_knowledge.rotation import evaluate_rotation, parse_steps
from lol_knowledge.scenario import Target
from lol_knowledge.stats import (
    Label,
    build_stat_sheet,
    load_champion,
    load_issues,
    load_items,
    load_records,
)
from lol_knowledge.stats.registry import move_speed_soft_cap

ROOT = Path(__file__).resolve().parents[1]


def _sheet(champ_id: str, level: int, item_ids: tuple[str, ...] = ()):
    champ = load_champion(ROOT, champ_id)
    items = load_items(ROOT, item_ids)
    issues = load_issues(ROOT)
    derived = load_records(ROOT)
    return build_stat_sheet(champ, level, items, issues, derived=derived)


def _run(
    champ_id: str,
    steps: str,
    item_ids: tuple[str, ...],
    *,
    level: int = 18,
    ranks: dict[str, int] | None = None,
    timeline: bool = True,
    target_kind: str = "champion",
    target_hp: int = 3000,
    target_count: int = 1,
    inputs: dict[str, F] | None = None,
):
    sheet = _sheet(champ_id, level, item_ids)
    kit = load_kit(ROOT, champ_id)
    target = Target(
        armor=F(0),
        magic_resist=F(0),
        stats={"max_health": F(target_hp), "current_health": F(target_hp)},
        label=Label.OFFICIAL,
        description="dummy",
        kind=target_kind,
    )
    return evaluate_rotation(
        kit,
        sheet,
        ranks or {"Q": 5, "W": 5, "E": 5, "R": 3},
        target,
        parse_steps(steps),
        None,
        holder_range=sheet.holder_range,
        inputs=inputs,
        timeline=timeline,
        target_count=target_count,
    )


# --- Parsing & error handling ---


def test_parse_steps_supports_item_actives_and_target_counts():
    steps = parse_steps("attack item:3074 item:3077@3 wait:1")
    assert steps[1].item_id == "3074" and steps[1].targets is None
    assert steps[2].item_id == "3077" and steps[2].targets == 3
    with pytest.raises(RotationError, match="target count must be at least 1"):
        parse_steps("item:3074@0")


def test_item_active_refuses_unequipped_or_non_combat_items():
    with pytest.raises(RotationError, match="item 3074 is not equipped"):
        _run("Garen", "item:3074", ("3077",))
    with pytest.raises(RotationError, match="no modelled combat active effect"):
        _run("Garen", "item:1036", ("1036",))
    with pytest.raises(RotationError, match="no modelled combat active effect"):
        _run("Ahri", "item:3157", ("3157",))


def test_item_active_cooldown_is_enforced_in_timeline():
    with pytest.raises(RotationError, match="item 3074 is on cooldown until 10 s"):
        _run("Garen", "item:3074 wait:5 item:3074", ("3074",))
    ok = _run("Garen", "item:3074 wait:10 item:3074", ("3074",))
    assert len(ok.steps) == 3
    assert ok.steps[0].total == ok.steps[2].total


def test_item_active_does_not_charge_spellblade():
    outcome = _run("Garen", "item:3077 attack", ("3077", "3057"))
    assert outcome.steps[1].name == "basic attack"
    assert not any("spellblade" in p.source for p in outcome.steps[1].parts)


# --- Group A: Direct AoE / Single-Target Damage Actives ---


def test_tiamat_ravenous_profane_and_stridebreaker_actives():
    # 3077 Tiamat: 75% total AD physical AoE
    s_tiamat = _sheet("Garen", 18, ("3077",))
    r_tiamat = _run("Garen", "item:3077@3", ("3077",))
    expected_tiamat = s_tiamat["attack_damage"].total() * F(75, 100)
    assert r_tiamat.steps[0].primary_total == expected_tiamat
    assert r_tiamat.steps[0].total == expected_tiamat * 3
    assert r_tiamat.label is Label.DERIVED

    # 3074 Ravenous Hydra: 80% total AD physical AoE WITH 100% life steal
    s_rav = _sheet("Garen", 18, ("3074",))
    r_rav = _run("Garen", "item:3074@2", ("3074",))
    expected_rav = s_rav["attack_damage"].total() * F(80, 100)
    assert r_rav.steps[0].primary_total == expected_rav
    assert r_rav.steps[0].total == expected_rav * 2
    ls_rate = s_rav["life_steal"].total()
    assert ls_rate > 0
    assert r_rav.steps[0].healing == expected_rav * 2 * ls_rate

    # 6698 Profane Hydra: 80% total AD physical AoE
    s_prof = _sheet("Garen", 18, ("6698",))
    r_prof = _run("Garen", "item:6698", ("6698",))
    assert r_prof.steps[0].total == s_prof["attack_damage"].total() * F(80, 100)

    # 6631 Stridebreaker: 80% total AD physical AoE
    s_stride = _sheet("Garen", 18, ("6631",))
    r_stride = _run("Garen", "item:6631", ("6631",))
    assert r_stride.steps[0].total == s_stride["attack_damage"].total() * F(80, 100)


def test_rocketbelt_and_gunblade_actives():
    # 3152 Hextech Rocketbelt: 135 + 15% AP magic AoE
    s_rb = _sheet("Ahri", 18, ("3152",))
    r_rb = _run("Ahri", "item:3152@2", ("3152",))
    expected_rb = F(135) + s_rb["ability_power"].total() * F(15, 100)
    assert r_rb.steps[0].primary_total == expected_rb
    assert r_rb.steps[0].total == expected_rb * 2

    # 3146 Hextech Gunblade: linear_by_level(175..253) + 30% AP single-target magic vs champion
    s_gb_l1 = _sheet("Ahri", 1, ("3146",))
    r_gb_l1 = _run("Ahri", "item:3146", ("3146",), level=1)
    assert r_gb_l1.steps[0].total == F(175) + s_gb_l1["ability_power"].total() * F(30, 100)

    s_gb_l18 = _sheet("Ahri", 18, ("3146",))
    r_gb_l18 = _run("Ahri", "item:3146@3", ("3146",), level=18)
    # Single target (aoe: false) -> even with @3, hits only 1 target!
    assert r_gb_l18.steps[0].total == F(253) + s_gb_l18["ability_power"].total() * F(30, 100)

    # Against minion, champion-only condition skips damage
    r_gb_minion = _run("Ahri", "item:3146", ("3146",), target_kind="minion")
    assert r_gb_minion.steps[0].total == 0


def test_redemption_locket_and_mikael_actives():
    # 3107 Redemption: 10% target max HP true damage vs champion + 150..350 self-heal * (1 + HSP)
    s_red = _sheet("Ahri", 18, ("3107",))
    r_red = _run("Ahri", "item:3107", ("3107",), level=18, target_hp=4000)
    assert r_red.steps[0].total == F(400)  # 10% of 4000 true damage
    hsp = s_red["heal_and_shield_power"].total()
    assert hsp == F(10, 100)
    assert r_red.steps[0].healing == F(350) * (1 + hsp)

    # 3190 Locket of the Iron Solari: 290 at L1..8, 360 at L18 self-shield * (1 + HSP)
    r_loc_l1 = _run("Ahri", "item:3190", ("3190",), level=1)
    r_loc_l18 = _run("Ahri", "item:3190", ("3190",), level=18)
    assert r_loc_l1.steps[0].shield_events[0].amount == F(290)
    assert r_loc_l18.steps[0].shield_events[0].amount == F(360)

    # 3222 Mikael's Blessing: 100..250 self-heal scaled by HSP and Grievous Wounds
    s_mik = _sheet("Ahri", 18, ("3222",))
    mik_hsp = s_mik["heal_and_shield_power"].total()
    r_mik = _run("Ahri", "item:3222", ("3222",), level=18)
    assert r_mik.steps[0].healing == F(250) * (1 + mik_hsp)
    r_mik_gw = _run("Ahri", "item:3222", ("3222",), level=18, inputs={"grievous_wounds": F(1)})
    assert r_mik_gw.steps[0].healing == F(250) * (1 + mik_hsp) * F(6, 10)


# --- Group B: Titanic Hydra attack reset & empowered Cleave ---


def test_titanic_hydra_resets_attack_timer_and_replaces_passive_cleave_on_next_attack():
    s = _sheet("Garen", 18, ("3748",))
    max_hp = s["health"].total()
    ad = s["attack_damage"].total()
    # attack (t=0) -> item:3748 (t=0, resets attack timer!) -> attack (t=0, empowered 4%/9%!)
    # -> attack (t=1/AS, back to passive 1%/3%!)
    out = _run("Garen", "attack item:3748 attack attack", ("3748",), target_count=3)
    atk1, active_step, atk2, atk3 = out.steps
    assert atk1.time == F(0)
    assert active_step.time == F(0) and active_step.total == F(0)
    assert atk2.time == F(0)  # Auto-attack reset!
    assert atk3.time is not None and atk3.time > F(0)

    # Primary on-hit: atk1 = AD + 1% HP; atk2 = AD + 4% HP (NOT 1% + 4%!); atk3 = AD + 1% HP
    assert atk1.primary_total == ad + max_hp * F(1, 100)
    assert atk2.primary_total == ad + max_hp * F(4, 100)
    assert atk3.primary_total == ad + max_hp * F(1, 100)

    # Secondary splash (2 secondary targets): atk1 = 2 * 3% HP; atk2 = 2 * 9% HP; atk3 = 2 * 3% HP
    assert atk1.secondary_total == 2 * max_hp * F(3, 100)
    assert atk2.secondary_total == 2 * max_hp * F(9, 100)
    assert atk3.secondary_total == 2 * max_hp * F(3, 100)


# --- Group C: Timed MS & Ability-Damage Actives ---


def test_youmuu_shurelya_and_mercurial_boost_hecarim_warpath_in_timeline():
    # 3142 Youmuu: +20% melee MS for 6 s (melee) / +15% for 4 s (ranged)
    q_base = _run("Hecarim", "Q", ("3142",))
    q_buffed = _run("Hecarim", "item:3142 Q", ("3142",))
    q_expired = _run("Hecarim", "item:3142 wait:6.5 Q", ("3142",))
    # Youmuu static +4% MS, active +20% -> total 24% on base 345 = 427.8 -> soft cap
    ms_base = move_speed_soft_cap(F(345) * F("1.04"))
    ms_active = move_speed_soft_cap(F(345) * F("1.24"))
    expected_gain = (ms_active - ms_base) * F(24, 100) * F(9, 10)
    assert q_buffed.steps[1].total - q_base.steps[0].total == expected_gain
    assert q_expired.steps[2].total == q_base.steps[0].total

    # Ranged champion (Janna) gets 4 s duration on 3142 (expires at 4.5 s, active at 3.5 s)
    j_active = _run("Janna", "item:3142 wait:3.5 W.hit", ("3142",))
    j_expired = _run("Janna", "item:3142 wait:4.5 W.hit", ("3142",))
    assert j_active.steps[2].total > j_expired.steps[2].total

    # 2065 Shurelya (+30% MS for 4 s) and 3139 Mercurial (+50% MS for 2 s) boost Hecarim Q
    sh_base = _run("Hecarim", "Q", ("2065",))
    sh_buff = _run("Hecarim", "item:2065 Q", ("2065",))
    assert sh_buff.steps[1].total > sh_base.steps[0].total

    mc_base = _run("Hecarim", "Q", ("3139",))
    mc_buff = _run("Hecarim", "item:3139 Q", ("3139",))
    assert mc_buff.steps[1].total > mc_base.steps[0].total


def test_actualizer_boosts_ability_damage_but_not_basic_attacks():
    # 2522 Actualizer: +(15 + 0.005 * bonus_mana)% ability damage for 8 s
    s = _sheet("Ahri", 18, ("2522",))
    bonus_mana = s["mana"].scoped("bonus")
    assert bonus_mana > 0
    expected_pct = F(15) + F("0.005") * bonus_mana

    base = _run("Ahri", "E attack", ("2522",))
    buffed = _run("Ahri", "item:2522 E attack", ("2522",))
    # E (ability) is boosted by expected_pct%
    assert buffed.steps[1].total == base.steps[0].total * (1 + expected_pct / 100)
    # attack (basic attack) is NOT boosted by ability-only Actualizer modifier
    assert buffed.steps[2].total == base.steps[1].total


def test_uncast_evaluable_active_adds_note_without_weakening_rotation():
    # Casting only Q with 3074 equipped does not falsely mark Q as Pending; notes item:3074
    out = _run("Garen", "Q", ("3074",))
    assert out.label is not Label.PENDING
    assert any("use step item:3074" in note for note in out.notes)


# --- Optimizer integration: --use-item-actives ---


def test_optimizer_use_item_actives_scores_hydra_and_rocketbelt_burst():
    champ = load_champion(ROOT, "Garen")
    kit = load_kit(ROOT, "Garen")
    issues = load_issues(ROOT)
    derived = load_records(ROOT)
    target = Target(
        armor=F(50),
        magic_resist=F(50),
        stats={"max_health": F(2500), "current_health": F(2500)},
        label=Label.OFFICIAL,
        description="dummy",
        kind="champion",
    )
    steps = parse_steps("attack Q")
    without_actives = optimize_build(
        ROOT,
        champ,
        18,
        "rotation_damage",
        constraints=OptimizeConstraints(
            slots=1,
            required_items=("3074",),
            only_verified=True,
            use_item_actives=False,
        ),
        issues=issues,
        derived=derived,
        kit=kit,
        ranks={"Q": 5, "W": 5, "E": 5, "R": 3},
        target=target,
        steps=steps,
        holder_range="melee",
        timeline=True,
    )
    with_actives = optimize_build(
        ROOT,
        champ,
        18,
        "rotation_damage",
        constraints=OptimizeConstraints(
            slots=1,
            required_items=("3074",),
            only_verified=True,
            use_item_actives=True,
        ),
        issues=issues,
        derived=derived,
        kit=kit,
        ranks={"Q": 5, "W": 5, "E": 5, "R": 3},
        target=target,
        steps=steps,
        holder_range="melee",
        timeline=True,
    )
    # 3074 is now verified_clean and lands in verified_builds!
    assert without_actives.verified_builds and with_actives.verified_builds
    assert with_actives.verified_builds[0].score > without_actives.verified_builds[0].score


def test_cli_and_contract_support_item_actives_and_use_item_actives(capsys):
    from lol_knowledge.cli import main
    from lol_knowledge.contract import execute_request

    code = main(
        [
            "rotation",
            "--root",
            str(ROOT),
            "--champion",
            "Garen",
            "--level",
            "18",
            "--learned",
            "Q=5",
            "--item",
            "3748",
            "--attacker-range",
            "melee",
            "--steps",
            "attack item:3748 attack",
            "--timeline",
            "--target-armor",
            "0",
            "--target-mr",
            "0",
            "--target-max-health",
            "3000",
            "--target-kind",
            "champion",
        ]
    )
    assert code == 0
    out = capsys.readouterr().out
    assert "item 3748 (Creciente titánico)" in out
    assert "Creciente titánico" in out

    resp = execute_request(
        {
            "operation": "optimize",
            "params": {
                "champion": "Ahri",
                "level": 18,
                "objective": "rotation_damage",
                "slots": 1,
                "required_items": ["3152"],
                "only_verified": True,
                "use_item_actives": True,
                "steps": "E",
                "learned": {"E": 5},
                "timeline": True,
                "target": {"kind": "champion", "armor": 0, "mr": 0, "max_health": 2500},
            },
        },
        ROOT,
    )
    assert resp["ok"] is True
    verified = resp["result"]["verified_builds"]
    assert verified and verified[0]["items"] == ["3152"]
    # Score includes E damage + 3152 Rocketbelt Supersonic active (135 + 15% AP)
    e_only = _run("Ahri", "E", ("3152",)).total
    assert verified[0]["score"] > float(e_only)
