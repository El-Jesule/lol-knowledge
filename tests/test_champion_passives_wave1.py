"""Tests for Champion Passives Wave 1 (global conversions, DR, shields, stacking, heals, procs)."""

from __future__ import annotations

from fractions import Fraction as F
from pathlib import Path

import pytest

from lol_knowledge.defense import evaluate_defense, parse_incoming
from lol_knowledge.kit import load_kit, passive_contributions
from lol_knowledge.passives import sheet_passive_effects
from lol_knowledge.rotation import evaluate_rotation, parse_steps
from lol_knowledge.runes import load_runes
from lol_knowledge.scenario import target_from_values
from lol_knowledge.stats import (
    build_stat_sheet,
    load_champion,
    load_issues,
    load_items,
    load_records,
)

ROOT = Path(__file__).resolve().parents[1]
ISSUES = load_issues(ROOT)
RECORDS = load_records(ROOT)
RUNE_DATA = load_runes(ROOT)


def _sheet(
    champ_name: str,
    level: int,
    item_ids: tuple[str, ...] = (),
    *,
    inputs: dict[str, F] | None = None,
    ranks: dict[str, int] | None = None,
    include_stacking: bool = True,
):
    champ = load_champion(ROOT, champ_name)
    items = load_items(ROOT, list(item_ids))
    kit = load_kit(ROOT, champ.id)
    extras = passive_contributions(kit, ranks or {}) if (kit and ranks) else ()
    passive = sheet_passive_effects(kit, level, inputs, include_stacking=include_stacking)
    return build_stat_sheet(
        champ,
        level,
        items,
        ISSUES,
        {},
        RECORDS,
        (*extras, *passive.flats),
        passive.percents,
        extra_amplifiers=passive.amplifiers,
        extra_notes=passive.notes,
        inputs=inputs,
    )


def _rotate(
    champ_name: str,
    level: int,
    steps_text: str,
    *,
    item_ids: tuple[str, ...] = (),
    ranks: dict[str, int] | None = None,
    target=None,
    inputs: dict[str, F] | None = None,
    timeline: bool = True,
    runes: list[int] = (),
    holder_range: str | None = None,
):
    champ = load_champion(ROOT, champ_name)
    kit = load_kit(ROOT, champ.id)
    assert kit is not None
    sheet = _sheet(
        champ_name,
        level,
        item_ids,
        inputs=inputs,
        ranks=ranks,
        include_stacking=False,
    )
    if target is None:
        target = target_from_values(
            F(0), F(0), max_health=F(2000), current_health=F(2000), kind="champion"
        )
    if holder_range is None:
        atk_range = champ.stats.get("attackrange")
        holder_range = "melee" if (atk_range is not None and atk_range < 300) else "ranged"
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
        rune_data=RUNE_DATA if runes else None,
        allow_insufficient_resource=True,
    )


# ---------------------------------------------------------------------------
# 1. Global Champion Stat Conversions (Vladimir, Pyke, Ryze, Ornn, Rammus)
# ---------------------------------------------------------------------------


def test_vladimir_crimson_pact_bidirectional_no_recursion():
    # Needlessly Large Rod (1058: +65 AP) + Ruby Crystal (1028: +150 bonus HP)
    # Crimson Pact: +150/30 = +5 AP -> total AP = 70; +65 * 1.6 = +104 bonus HP -> bonus HP = 254.
    sheet = _sheet("Vladimir", 11, ("1058", "1028"))
    assert sheet["ability_power"].total() == F(70)
    assert sheet["health"].scoped("bonus") == F(254)


def test_pyke_gift_of_the_drowned_ones_converts_bonus_hp_to_ad():
    # Ruby Crystal (1028: +150 bonus HP) -> 0 bonus HP and +150/14 bonus AD
    plain = _sheet("Pyke", 11)
    with_hp = _sheet("Pyke", 11, ("1028",))
    assert with_hp["health"].scoped("bonus") == F(0)
    assert with_hp["health"].total() == plain["health"].total()
    assert with_hp["attack_damage"].total() - plain["attack_damage"].total() == F(150, 14)


def test_ryze_arcane_mastery_scales_max_mana_with_ap():
    # Needlessly Large Rod (1058: +65 AP) -> +6.5% max mana
    plain = _sheet("Ryze", 11)
    with_ap = _sheet("Ryze", 11, ("1058",))
    expected = plain["mana"].total() * (1 + F(65, 1000))
    assert with_ap["mana"].total() == expected


def test_ornn_living_forge_amplifies_bonus_hp_armor_mr():
    # Ruby Crystal (1028: +150 HP) + Chain Vest (1031: +40 Armor) + Negatron Cloak (1057: +45 MR)
    base = _sheet("Ornn", 13, ("1028", "1031", "1057"))
    # Default 0 masterworks -> +10% bonus HP/Armor/MR
    assert base["health"].scoped("bonus") == F(165)
    assert base["armor"].scoped("bonus") == F(44)
    assert base["magic_resist"].scoped("bonus") == F(495, 10)
    # 5 masterworks -> +30% bonus HP/Armor/MR
    mw5 = _sheet("Ornn", 18, ("1028", "1031", "1057"), inputs={"ornn_masterworks": F(5)})
    assert mw5["health"].scoped("bonus") == F(195)
    assert mw5["armor"].scoped("bonus") == F(52)
    assert mw5["magic_resist"].scoped("bonus") == F(585, 10)


def test_rammus_spiked_shell_converts_armor_and_mr_to_bonus_ad():
    sheet = _sheet("Rammus", 11, ("1031", "1057"))
    expected_bonus_ad = sheet["armor"].total() * F(15, 100) + sheet["magic_resist"].total() * F(
        15, 100
    )
    assert sheet["attack_damage"].scoped("bonus") == expected_bonus_ad


# ---------------------------------------------------------------------------
# 2. Defensive DR & Passive Shields (Kassadin, Fizz, Malphite, Blitz, Yasuo, Vi, Shen)
# ---------------------------------------------------------------------------


def test_kassadin_and_fizz_passive_damage_reduction_in_survive():
    # Kassadin: -10% magic damage, unaffected on physical
    k_sheet = _sheet("Kassadin", 11)
    k_kit = load_kit(ROOT, "Kassadin")
    magic_hits = parse_incoming("magic:500")
    phys_hits = parse_incoming("physical:500")
    k_no_kit = evaluate_defense(k_sheet, magic_hits)
    k_with_kit = evaluate_defense(k_sheet, magic_hits, kit=k_kit)
    assert k_with_kit.total_damage_taken == k_no_kit.total_damage_taken * F(9, 10)
    assert (
        evaluate_defense(k_sheet, phys_hits, kit=k_kit).total_damage_taken
        == evaluate_defense(k_sheet, phys_hits).total_damage_taken
    )

    # Fizz: 4 + 1% AP flat DR, capped at 50% of hit
    f_sheet = _sheet("Fizz", 11, ("1058",))  # 65 AP -> 4.65 flat DR
    f_kit = load_kit(ROOT, "Fizz")
    big = parse_incoming("physical:500")
    f_plain = evaluate_defense(f_sheet, big)
    f_dr = evaluate_defense(f_sheet, big, kit=f_kit)
    assert f_plain.total_damage_taken - f_dr.total_damage_taken == F(465, 100)


def test_passive_defensive_shields_in_survive_and_rotation():
    # Malphite: 10% max HP shield on taking damage
    m_sheet = _sheet("Malphite", 11)
    m_kit = load_kit(ROOT, "Malphite")
    m_out = evaluate_defense(m_sheet, parse_incoming("true:500"), kit=m_kit)
    assert m_out.total_shield_granted == m_sheet["health"].total() * F(1, 10)

    # Blitzcrank: 35% max mana shield when projected HP drops below 30% max HP
    b_sheet = _sheet("Blitzcrank", 11)
    b_kit = load_kit(ROOT, "Blitzcrank")
    b_high = evaluate_defense(b_sheet, parse_incoming("true:100"), kit=b_kit)
    assert b_high.total_shield_granted == F(0)
    b_low = evaluate_defense(b_sheet, parse_incoming("true:400"), start_health=F(500), kit=b_kit)
    assert b_low.total_shield_granted == b_sheet["mana"].total() * F(35, 100)

    # Yasuo: stat-progression shield (125 at level 1, 600 at level 18)
    y1 = evaluate_defense(
        _sheet("Yasuo", 1), parse_incoming("true:300"), kit=load_kit(ROOT, "Yasuo")
    )
    y18 = evaluate_defense(
        _sheet("Yasuo", 18), parse_incoming("true:300"), kit=load_kit(ROOT, "Yasuo")
    )
    assert y1.total_shield_granted == F(125)
    assert y18.total_shield_granted == F(600)

    # Vi: 10% max HP shield on ability cast in rotation + procs Shield Bash (8401)!
    vi_rot = _rotate("Vi", 11, "Q.min, attack", ranks={"Q": 5}, runes=[8401])
    assert vi_rot.steps[0].shield_events
    assert any("8401" in p.source for p in vi_rot.steps[1].parts)


# ---------------------------------------------------------------------------
# 3. Stacking Stats, At-Max Procs, Stat Bonuses, Heals, Resources & Procs
# ---------------------------------------------------------------------------


def test_stacking_passives_darius_only_at_max_irelia_and_volibear():
    # Darius: Noxian Might grants +0 AD on stacks 1..4 and full +NoxianMightBonusAD at stack 5!
    d4 = _sheet("Darius", 18, inputs={"hemorrhage_stacks": F(4)})
    d5 = _sheet("Darius", 18, inputs={"hemorrhage_stacks": F(5)})
    assert d5["attack_damage"].total() - d4["attack_damage"].total() == F(210)
    # In rotation: 5 hits vs champion activate Noxian Might for hit 6!
    d_rot = _rotate("Darius", 18, "attack, attack, attack, attack, attack, attack")
    assert d_rot.steps[4].total == d_rot.steps[0].total
    assert d_rot.steps[5].total - d_rot.steps[0].total == F(210)

    # Irelia: hitting 4 abilities fills Ionian Fervor -> next attack auto-procs OnHitBonus magic!
    ir_rot = _rotate(
        "Irelia",
        11,
        "Q.dash, E.stun, W.min, R.barrage, attack",
        ranks={"Q": 5, "W": 5, "E": 5, "R": 2},
    )
    assert any("ionian_fervor_on_hit" in p.source for p in ir_rot.steps[4].parts)

    # Volibear: AP scales attack speed per stack, and 5th stack unlocks ChainLightningDamage on hit!
    v_rot = _rotate(
        "Volibear",
        11,
        "attack, attack, attack, attack, attack, attack",
        item_ids=("1058",),
    )
    assert not any("relentless_storm_lightning" in p.source for p in v_rot.steps[0].parts)
    assert any("relentless_storm_lightning" in p.source for p in v_rot.steps[5].parts)


def test_stat_bonus_passives_aphelios_tryndamere_gnar_syndra_jinx():
    # Aphelios: 6 ranks of AD (+24), AS (+54%), Lethality (+27)
    aph0 = _sheet("Aphelios", 18)
    aph6 = _sheet(
        "Aphelios",
        18,
        inputs={
            "aphelios_ad_ranks": F(6),
            "aphelios_as_ranks": F(6),
            "aphelios_lethality_ranks": F(6),
        },
    )
    assert aph6["attack_damage"].total() - aph0["attack_damage"].total() == F(24)
    assert aph6["attack_speed_bonus"].total() - aph0["attack_speed_bonus"].total() == F(54, 100)
    assert aph6["lethality"].total() == F(27)

    # Tryndamere: 100 Fury -> 50% crit chance
    tryn = _sheet("Tryndamere", 11, inputs={"tryndamere_fury": F(100)})
    assert tryn["crit_chance"].total() == F(1, 2)

    # Gnar: Mega-Gnar level 18 adds +831 HP, +54.5 Armor, +63 MR, +48.5 AD
    g_mini = _sheet("Gnar", 18)
    g_mega = _sheet("Gnar", 18, inputs={"mega_gnar": F(1)})
    assert g_mega["health"].total() - g_mini["health"].total() == F(831)
    assert g_mega["armor"].total() - g_mini["armor"].total() == F(545, 10)
    assert g_mega["magic_resist"].total() - g_mini["magic_resist"].total() == F(63)
    assert g_mega["attack_damage"].total() - g_mini["attack_damage"].total() == F(485, 10)

    # Syndra: 120 splinters -> +15% total AP
    s0 = _sheet("Syndra", 11, ("1058",))
    s1 = _sheet("Syndra", 11, ("1058",), inputs={"syndra_transcendent": F(1)})
    assert s1["ability_power"].total() == s0["ability_power"].total() * F(115, 100)

    # Jinx: Get Excited -> +25% AS & +175% MS (soft-capped!)
    j0 = _sheet("Jinx", 11)
    j1 = _sheet("Jinx", 11, inputs={"get_excited": F(1)})
    assert j1["attack_speed_bonus"].total() - j0["attack_speed_bonus"].total() == F(1, 4)
    assert j1["move_speed"].total() > j0["move_speed"].total()


def test_heals_resources_and_auto_damage_procs():
    # Cho'Gath: killing a target heals CarnivoreHeal AND restores CarnivoreMana!
    weak = target_from_values(F(0), F(0), max_health=F(50), current_health=F(50), kind="minion")
    cho = _rotate("Chogath", 18, "attack", target=weak)
    assert cho.healing == F(52)
    assert any("carnivore_mana" in ev.source for ev in cho.steps[0].resource_events)

    # Xin Zhao: 3rd attack deals bonus physical damage AND heals!
    xin = _rotate("XinZhao", 11, "attack, attack, attack")
    assert any("determination_damage" in p.source for p in xin.steps[2].parts)
    assert any("determination_heal" in h.source for h in xin.steps[2].heal_events)

    # Zed: Contempt for the Weak triggers below 50% target HP, NOT at 80% HP
    high_hp = target_from_values(
        F(0), F(0), max_health=F(1000), current_health=F(800), kind="champion"
    )
    low_hp = target_from_values(
        F(0), F(0), max_health=F(1000), current_health=F(400), kind="champion"
    )
    zed_hi = _rotate("Zed", 18, "attack", target=high_hp)
    zed_lo = _rotate("Zed", 18, "attack", target=low_hp)
    assert not any("contempt_for_the_weak" in p.source for p in zed_hi.steps[0].parts)
    zed_procs = [p for p in zed_lo.steps[0].parts if "contempt_for_the_weak" in p.source]
    assert len(zed_procs) == 1
    assert zed_procs[0].raw == F(100)  # 10% of 1000 max HP at level 18

    # Ekko (3-hit), Akshan (3-hit + shield), Riven (after_ability)
    ekko = _rotate("Ekko", 11, "attack, attack, attack")
    assert any("z_drive_resonance" in p.source for p in ekko.steps[2].parts)

    akshan = _rotate("Akshan", 11, "attack, attack, attack")
    assert any("dirty_fighting_proc" in p.source for p in akshan.steps[2].parts)
    assert any("dirty_fighting_shield" in s.source for s in akshan.steps[2].shield_events)

    riven = _rotate("Riven", 11, "Q.slash, attack", ranks={"Q": 5})
    assert any("runic_blade" in p.source for p in riven.steps[1].parts)

    # Corki: 20% AD bonus true damage on attacks
    corki = _rotate("Corki", 11, "attack")
    c_true = [p for p in corki.steps[0].parts if "hextech_munitions_true" in p.source]
    assert len(c_true) == 1
    assert c_true[0].damage_type.value == "true"
    assert c_true[0].raw == pytest.approx(float(corki.steps[0].parts[0].raw * F(1, 5)))
