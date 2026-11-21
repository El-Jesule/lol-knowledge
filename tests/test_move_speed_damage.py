"""Move-speed-to-damage coupling: Hecarim Warpath, Janna soft-cap bonus MS,
3170 Swiftmarch (Noxian Fervor), and timed combat MS buffs in rotations.
"""

from __future__ import annotations

from fractions import Fraction as F
from pathlib import Path

import pytest

from lol_knowledge.kit import ability_damage, load_kit, sheet_stats
from lol_knowledge.rotation import evaluate_rotation, parse_steps
from lol_knowledge.scenario import Target
from lol_knowledge.stats import (
    Label,
    build_stat_sheet,
    load_champion,
    load_issues,
    load_items,
    load_records,
    with_bonus,
    with_percent_bonus,
)
from lol_knowledge.stats.registry import move_speed_soft_cap
from stats_helpers import champion, item

ROOT = Path(__file__).resolve().parents[1]


def _real_sheet(champ_id: str, level: int, item_ids: tuple[str, ...] = ()):
    champ = load_champion(ROOT, champ_id)
    items = load_items(ROOT, item_ids)
    issues = load_issues(ROOT)
    derived = load_records(ROOT)
    return build_stat_sheet(champ, level, items, issues, derived=derived)


# --- 1. Hecarim passive: Warpath (12..24% effective bonus MS -> bonus AD) ---


def test_hecarim_warpath_without_bonus_ms_leaves_ad_official():
    sheet = build_stat_sheet(champion("Hecarim", stats={"movespeed": 345, "attackdamage": 66}), 1)
    ad = sheet["attack_damage"]
    assert ad.total() == 66
    assert ad.label is Label.OFFICIAL
    assert not any(c.derived_from_ms for c in ad.contributions)


@pytest.mark.parametrize(
    ("level", "ratio"),
    [
        (1, F(12, 100)),
        (2, F(12, 100)),
        (3, F(14, 100)),
        (5, F(14, 100)),
        (6, F(16, 100)),
        (8, F(16, 100)),
        (9, F(18, 100)),
        (11, F(18, 100)),
        (12, F(20, 100)),
        (14, F(20, 100)),
        (15, F(22, 100)),
        (17, F(22, 100)),
        (18, F(24, 100)),
    ],
)
def test_hecarim_warpath_level_breakpoints_from_client_16_23(level, ratio):
    # Base 345 + 50 flat = 395 (below 415 soft cap -> effective bonus MS = 50)
    hec = champion(
        "Hecarim", stats={"movespeed": 345, "attackdamage": 66, "attackdamageperlevel": 0}
    )
    sheet = build_stat_sheet(hec, level, [item("1", ("move_speed", "flat", 50))])
    assert sheet["attack_damage"].total() == 66 + F(50) * ratio
    assert sheet["attack_damage"].label is Label.DERIVED


def test_hecarim_warpath_uses_post_soft_cap_effective_bonus_ms():
    hec = champion(
        "Hecarim", stats={"movespeed": 345, "attackdamage": 66, "attackdamageperlevel": 0}
    )
    # Raw MS = (345 + 65) * 1.10 = 451 (first soft cap: 451 * 0.8 + 83 = 443.8)
    # Effective bonus MS = 443.8 - 345 = 98.8 (raw bonus would be 106)
    items = [item("1", ("move_speed", "flat", 65)), item("2", ("move_speed", "percent", 10))]
    sheet = build_stat_sheet(hec, 18, items)
    expected_total_ms = move_speed_soft_cap(F(410) * F("1.1"))
    assert expected_total_ms == F("443.8")
    effective_bonus = expected_total_ms - 345
    assert sheet["attack_damage"].total() == 66 + effective_bonus * F(24, 100)

    # Above second soft cap (> 490): raw = (345 + 100) * 1.25 = 556.25 -> 556.25/2 + 230 = 508.125
    items_high = [item("1", ("move_speed", "flat", 100)), item("2", ("move_speed", "percent", 25))]
    sheet_high = build_stat_sheet(hec, 18, items_high)
    expected_high_ms = move_speed_soft_cap(F(445) * F("1.25"))
    assert expected_high_ms == F("508.125")
    assert sheet_high["attack_damage"].total() == 66 + (expected_high_ms - 345) * F(24, 100)


# --- 2. Janna post-soft-cap bonus_move_speed in kit evaluation ---


def test_janna_kit_reads_effective_post_soft_cap_bonus_move_speed():
    janna_kit = load_kit(ROOT, "Janna")
    # With 3170 Swiftmarch (+65 flat) + 3046 Phantom Dancer (+10% MS):
    # Janna base MS 335 -> raw = (335 + 65) * 1.1 = 440 -> soft cap = 440 * 0.8 + 83 = 435
    sheet = _real_sheet("Janna", 18, ("3170", "3046"))
    ms = sheet["move_speed"]
    assert ms.soft_capped
    stats, _ = sheet_stats(sheet)
    effective_bonus = ms.total() - ms.scoped("base")
    assert effective_bonus < ms.scoped("bonus")
    assert stats["bonus_move_speed"] == effective_bonus

    # W (hit) at rank 5: 175 + 0.5 * AP + 0.3 * effective_bonus_ms
    w_part = ability_damage(janna_kit, "W", 5, sheet, case="hit")[0]
    expected_w = F(175) + F("0.5") * sheet["ability_power"].total() + F("0.3") * effective_bonus
    assert w_part.raw == expected_w


# --- 3. 3170 Swiftmarch (Noxian Fervor: 5% total MS -> Adaptive Force) ---


def test_swiftmarch_converts_5_percent_total_ms_to_ad_or_ap():
    # AD champion with bonus AD (3031 IE -> +75 AD) + 3170 Swiftmarch (+65 MS):
    # Zaahen base MS 345 + 65 = 410 (no soft cap); 5% of 410 = 20.5 adaptive -> 20.5 * 0.6 = 12.3 AD
    ad_sheet = _real_sheet("Zaahen", 18, ("3170", "3031"))
    base_only = _real_sheet("Zaahen", 18, ("3031",))
    ms_total = ad_sheet["move_speed"].total()
    assert ms_total == 410
    expected_bonus_ad = ms_total * F(5, 100) * F(3, 5)
    assert (
        ad_sheet["attack_damage"].total() - base_only["attack_damage"].total() == expected_bonus_ad
    )
    assert ad_sheet["ability_power"].total() == 0
    assert ad_sheet["attack_damage"].label is Label.DERIVED

    # AP champion with AP (3089 Rabadon -> +130 AP + 30% total AP) + 3170 Swiftmarch:
    # Ahri base MS 330 + 65 = 395; 5% of 395 = 19.75 AP, then amplified by Rabadon (+30%)!
    ap_sheet = _real_sheet("Ahri", 18, ("3170", "3089"))
    ms_ahri = ap_sheet["move_speed"].total()
    assert ms_ahri == 395
    swift_ap = ms_ahri * F(5, 100)
    assert ap_sheet["ability_power"].total() == (F(130) + swift_ap) * F("1.3")
    assert ap_sheet["ability_power"].label is Label.DERIVED


def test_swiftmarch_tie_breaker_is_pending_and_hecarim_warpath_resolves_to_ad():
    # Ahri with ONLY 3170 (0 bonus AD, 0 AP): tie-breaker uses adaptiveforceapweight -> AP [Pending]
    ahri_only = _real_sheet("Ahri", 1, ("3170",))
    assert ahri_only["ability_power"].total() == ahri_only["move_speed"].total() * F(5, 100)
    assert ahri_only["ability_power"].label is Label.PENDING

    # Hecarim with ONLY 3170: Warpath runs first -> bonus AD > 0 -> 3170 resolves to AD [Derived]!
    hec_only = _real_sheet("Hecarim", 18, ("3170",))
    ms = hec_only["move_speed"].total()
    warpath_ad = (ms - hec_only["move_speed"].scoped("base")) * F(24, 100)
    swift_ad = ms * F(5, 100) * F(3, 5)
    hec_bare = _real_sheet("Hecarim", 18)
    assert hec_only["attack_damage"].total() - hec_bare["attack_damage"].total() == (
        warpath_ad + swift_ad
    )
    assert hec_only["ability_power"].total() == 0
    assert hec_only["attack_damage"].label is Label.DERIVED


def test_dynamic_with_bonus_and_with_percent_bonus_stack_exact_ms_and_warpath():
    # Hecarim L18 (base MS 345) + Boots of Swiftness (3009, +55 flat -> 400):
    sheet = _real_sheet("Hecarim", 18, ("3009",))
    base_ms = sheet["move_speed"].scoped("base")
    bare_ad = _real_sheet("Hecarim", 18)["attack_damage"].total()
    assert sheet["move_speed"].total() == base_ms + 55

    # Add +20% MS (Hexplate) AND +20 flat MS (Trinity): order must not matter!
    s_pct_first = with_percent_bonus(sheet, "move_speed", F(20, 100), "hexplate", Label.DERIVED)
    s_both_a = with_bonus(s_pct_first, "move_speed", F(20), "trinity", Label.OFFICIAL)

    s_flat_first = with_bonus(sheet, "move_speed", F(20), "trinity", Label.OFFICIAL)
    s_both_b = with_percent_bonus(s_flat_first, "move_speed", F(20, 100), "hexplate", Label.DERIVED)

    expected_raw = (base_ms + 55 + 20) * F("1.2")
    expected_ms = move_speed_soft_cap(expected_raw)
    assert s_both_a["move_speed"].total() == expected_ms
    assert s_both_b["move_speed"].total() == expected_ms
    expected_ad = bare_ad + (expected_ms - base_ms) * F(24, 100)
    assert s_both_a["attack_damage"].total() == expected_ad
    assert s_both_b["attack_damage"].total() == expected_ad


# --- 4. Dynamic timed MS item effects in timeline rotations ---


def _run_rotation(
    champ_id: str,
    steps: str,
    item_ids: tuple[str, ...],
    *,
    level: int = 18,
    ranks: dict[str, int] | None = None,
    timeline: bool = True,
):
    sheet = _real_sheet(champ_id, level, item_ids)
    kit = load_kit(ROOT, champ_id)
    target = Target(
        armor=F(0),
        magic_resist=F(0),
        stats={"max_health": F(3000), "current_health": F(3000)},
        label=Label.OFFICIAL,
        description="dummy",
        kind="champion",
    )
    return evaluate_rotation(
        kit,
        sheet,
        ranks or {"Q": 5, "W": 5, "E": 5, "R": 3},
        target,
        parse_steps(steps),
        None,
        holder_range=sheet.holder_range,
        timeline=timeline,
    )


def test_hecarim_trinity_go_increases_q_damage_in_timeline():
    before = _run_rotation("Hecarim", "Q", ("3078",))
    after = _run_rotation("Hecarim", "attack Q", ("3078",))
    q_before = before.steps[0].total
    q_after = after.steps[1].total
    # Hecarim base MS 345 -> +20 = 365 (no soft cap), Warpath L18 = 24% -> +4.8 bonus AD
    # Q ratio = 0.9 bonus AD -> +4.32 exact physical damage gain!
    assert q_after - q_before == F(20) * F(24, 100) * F(9, 10)


def test_hecarim_hexplate_overdrive_grants_both_as_and_ms_in_timeline():
    # R opens BOTH +50% AS and +20% MS for 8 s (30 s cooldown):
    before = _run_rotation("Hecarim", "Q", ("3073",))
    after = _run_rotation("Hecarim", "R Q attack attack", ("3073",))
    q_before = before.steps[0].total
    q_after = after.steps[1].total
    # Base MS 345 * 1.2 = 414 (no soft cap) -> +69 bonus MS -> 69 * 0.24 = +16.56 AD -> Q +14.904
    assert q_after - q_before == F(345) * F(20, 100) * F(24, 100) * F(9, 10)
    # Also verify +50% AS sped up the gap between the two attacks!
    t_atk1 = after.steps[2].time
    t_atk2 = after.steps[3].time
    assert t_atk1 is not None and t_atk2 is not None
    base_as = _real_sheet("Hecarim", 18, ("3073",))["attack_speed"].total()
    assert (t_atk2 - t_atk1) < F(1) / base_as


def test_hecarim_black_cleaver_fervor_and_phage_rage_in_timeline():
    # 3071 Black Cleaver: physical damage triggers fervor (+20 melee MS for 2 s)
    bc_q_only = _run_rotation("Hecarim", "Q", ("3071",))
    bc_after_atk = _run_rotation("Hecarim", "attack Q", ("3071",))
    # Target armor is 0, so Carve doesn't change mitigation; all Q gain is Warpath from Fervor +20!
    assert bc_after_atk.steps[1].total - bc_q_only.steps[0].total == (F(20) * F(24, 100) * F(9, 10))

    # 3044 Phage: attack triggers rage (+20 melee MS for 2 s)
    ph_q_only = _run_rotation("Hecarim", "Q", ("3044",))
    ph_after_atk = _run_rotation("Hecarim", "attack Q", ("3044",))
    assert ph_after_atk.steps[1].total - ph_q_only.steps[0].total == (F(20) * F(24, 100) * F(9, 10))


def test_hecarim_stormrazor_bolt_ms_boosts_followup_q_in_timeline():
    # 3095 Stormrazor: energized attack deals 100 magic AND grants +45% MS for 1.5 s
    sr_q_only = _run_rotation("Hecarim", "Q", ("3095",))
    sr_after_atk = _run_rotation("Hecarim", "attack Q", ("3095",))
    # 345 * 1.45 = 500.25 -> soft cap (> 490) = 500.25/2 + 230 = 480.125 -> bonus MS = 135.125
    expected_ms = move_speed_soft_cap(F(345) * F("1.45"))
    expected_q_gain = (expected_ms - 345) * F(24, 100) * F(9, 10)
    assert sr_after_atk.steps[1].total - sr_q_only.steps[0].total == expected_q_gain


def test_janna_cosmic_drive_and_crimson_lucidity_boost_tailwind_on_hit():
    # 4629 Cosmic Drive: magic damage to champion -> +20 flat MS for 4 s
    # 3171 Crimson Lucidity: damaging ability to champion -> +8% ranged MS for 4 s
    # Compare attack before W vs attack after W:
    atk_before = _run_rotation("Janna", "attack", ("4629", "3171"))
    after_w = _run_rotation("Janna", "W.hit attack", ("4629", "3171"))
    assert after_w.steps[1].total > atk_before.steps[0].total


def test_swiftmarch_with_cosmic_drive_and_rabadon_boosts_ap_dynamically_in_timeline():
    # Ahri with 3170 Swiftmarch + 4629 Cosmic Drive + 3089 Rabadon:
    # W triggers Cosmic Drive (+20 flat MS -> * 1.04 -> soft-cap -> 5% AP -> * 1.3 Rabadon)
    e_before = _run_rotation("Ahri", "E", ("3170", "4629", "3089"))
    e_after = _run_rotation("Ahri", "W.one E", ("3170", "4629", "3089"))
    assert e_after.steps[1].total > e_before.steps[0].total


# --- 5. Label honesty without --timeline ---


def test_timed_ms_without_timeline_only_weakens_ms_scaling_builds():
    # Non-MS-scaling champion (Zaahen) + 3078 Trinity Force without --timeline:
    # +20 MS does NOT affect Zaahen's damage -> NOT weakened to Pending!
    zaahen_trinity = _run_rotation("Zaahen", "Q.first_hit attack", ("3078",), timeline=False)
    assert zaahen_trinity.label is not Label.PENDING

    # Hecarim + 3078 Trinity Force without --timeline:
    # +20 MS DOES affect Hecarim's Warpath AD -> MUST be weakened to Pending!
    hecarim_trinity = _run_rotation("Hecarim", "attack Q", ("3078",), timeline=False)
    assert hecarim_trinity.label is Label.PENDING

    # Zaahen + 3170 Swiftmarch + 3078 Trinity Force without --timeline:
    # 3170 turns +20 MS into AD -> MUST be weakened to Pending!
    zaahen_swift_trinity = _run_rotation(
        "Zaahen", "Q.first_hit attack", ("3170", "3078"), timeline=False
    )
    assert zaahen_swift_trinity.label is Label.PENDING

    # Non-MS-scaling champion (Zaahen) + 3095 Stormrazor WITH --timeline:
    # energized +45% MS does not change Zaahen's hit damage -> stays Derived (not Pending)!
    zaahen_sr = _run_rotation("Zaahen", "attack", ("3095",), timeline=True)
    assert zaahen_sr.label is not Label.PENDING


def test_trinity_go_expires_after_2_seconds_in_timeline():
    q_only = _run_rotation("Hecarim", "Q", ("3078",))
    after_expiry = _run_rotation("Hecarim", "attack wait:2.5 Q", ("3078",))
    assert after_expiry.steps[2].total == q_only.steps[0].total


def test_swiftmarch_does_not_leak_adaptive_tiebreaker_into_rune_shards(capsys):
    from lol_knowledge.cli import main

    # Ahri with ONLY 3170 Swiftmarch + Adaptive shard 5008 (0 flat AD, 0 flat AP):
    # Both 3170 and shard 5008 must keep Pendiente de verificación (tie-breaker), not Derivado!
    code = main(
        [
            "stats",
            "--root",
            str(ROOT),
            "--champion",
            "Ahri",
            "--level",
            "1",
            "--item",
            "3170",
            "--shard",
            "5008",
            "--allow-illegal-build",
        ]
    )
    assert code == 0
    out = capsys.readouterr().out
    assert "ability_power:" in out
    assert "[Pendiente de verificación]" in out
