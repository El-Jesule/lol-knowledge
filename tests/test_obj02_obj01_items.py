"""Tests for OBJ-02 (Luden's Companion, Eclipse) and OBJ-01 Lote 1 (30 curated items)."""

from __future__ import annotations

from fractions import Fraction
from pathlib import Path

import pytest

from lol_knowledge.damage import DamageType
from lol_knowledge.defense import IncomingHit, evaluate_defense
from lol_knowledge.kit import load_kit
from lol_knowledge.rotation import CritBase, evaluate_rotation, parse_steps
from lol_knowledge.rotation_report import format_text, to_dict
from lol_knowledge.scenario import Target
from lol_knowledge.stats import (
    Label,
    ability_cooldowns,
    build_stat_sheet,
    load_champion,
    load_items,
    load_records,
)

ROOT = Path(__file__).resolve().parents[1]
RECORDS = load_records(ROOT)
CRIT_BASE = CritBase(Fraction(2), Label.DERIVED, "patch 26.1")


def _sheet(champion_id: str, level: int, item_ids: list[str] | tuple[str, ...] = ()):
    champ = load_champion(ROOT, champion_id)
    items = load_items(ROOT, list(item_ids))
    return build_stat_sheet(champ, level, items, derived=RECORDS)


def _target(
    hp: int = 2000,
    armor: int = 0,
    mr: int = 0,
    kind: str = "champion",
    item_ids: list[str] = (),
) -> Target:
    items = load_items(ROOT, list(item_ids)) if item_ids else ()
    return Target(
        armor=Fraction(armor),
        magic_resist=Fraction(mr),
        stats={"max_health": Fraction(hp), "current_health": Fraction(hp)},
        label=Label.OFFICIAL,
        description=f"{kind} {hp}hp {armor}ar {mr}mr",
        kind=kind,
        items=tuple(items),
    )


# ---------------------------------------------------------------------------
# OBJ-02: Luden's Companion (6655) & Eclipse (6692)
# ---------------------------------------------------------------------------


def test_ludens_companion_echo_distribution_and_cooldown() -> None:
    sheet = _sheet("Ahri", 9, ["6655"])
    kit = load_kit(ROOT, "Ahri")
    # 6655 gives 100 AP -> base shot = 75 + 0.05 * 100 = 80 magic damage
    base = Fraction(80)

    # 1 target: primary takes 1 full + 5 repeat at 20% = 2 * 80 = 160
    r1 = evaluate_rotation(
        kit,
        sheet,
        {"Q": 5, "W": 1, "E": 1, "R": 1},
        _target(),
        parse_steps("E"),
        CRIT_BASE,
        holder_range="ranged",
        target_count=1,
    )
    luden_parts_1 = [p for p in r1.steps[0].parts if "6655 echo" in p.source]
    assert len(luden_parts_1) == 1
    assert luden_parts_1[0].primary_damage == base * 2
    assert luden_parts_1[0].secondary_damage == 0
    assert r1.label is Label.DERIVED

    # 2 targets: primary takes 1 + 4*0.2 = 1.8x (144), 1 secondary takes 1.0x (80)
    r2 = evaluate_rotation(
        kit,
        sheet,
        {"Q": 5, "W": 1, "E": 1, "R": 1},
        _target(),
        parse_steps("E@2"),
        CRIT_BASE,
        holder_range="ranged",
        target_count=1,
    )
    luden_parts_2 = [p for p in r2.steps[0].parts if "6655 echo" in p.source]
    assert len(luden_parts_2) == 2
    assert luden_parts_2[0].primary_damage == base * Fraction(9, 5)
    assert luden_parts_2[1].hits_primary is False
    assert luden_parts_2[1].secondary_damage == base

    # 6 targets: primary takes 1.0x (80), 5 secondaries take 5 * 80 = 400
    r6 = evaluate_rotation(
        kit,
        sheet,
        {"Q": 5, "W": 1, "E": 1, "R": 1},
        _target(),
        parse_steps("E@6"),
        CRIT_BASE,
        holder_range="ranged",
        target_count=1,
    )
    luden_parts_6 = [p for p in r6.steps[0].parts if "6655 echo" in p.source]
    assert luden_parts_6[0].primary_damage == base
    assert luden_parts_6[1].secondary_damage == base * 5

    # Timeline 12 s cooldown: Q (t=0) procs, E (t=0) does not, wait:12, Q (t=12) procs again
    rt = evaluate_rotation(
        kit,
        sheet,
        {"Q": 5, "W": 1, "E": 1, "R": 1},
        _target(hp=5000),
        parse_steps("Q.out E wait:12 Q.out"),
        CRIT_BASE,
        holder_range="ranged",
        timeline=True,
    )
    procs = [any("6655 echo" in p.source for p in s.parts) for s in rt.steps]
    assert procs == [True, False, False, True]


def test_eclipse_two_hit_combo_damage_shield_window_and_cooldown() -> None:
    sheet = _sheet("Garen", 9, ["6692"])  # melee, 60 bonus AD
    kit = load_kit(ROOT, "Garen")
    target = _target(hp=2000, armor=0, kind="champion")

    # 2 attacks trigger Eclipse on step 2: 8% * 2000 = 160 phys + shield 150 + 0.4*60 = 174
    res = evaluate_rotation(
        kit,
        sheet,
        {"Q": 5, "W": 1, "E": 1, "R": 1},
        target,
        parse_steps("attack attack"),
        CRIT_BASE,
        holder_range="melee",
    )
    assert not any("6692" in p.source for p in res.steps[0].parts)
    eclipse_parts = [p for p in res.steps[1].parts if "6692" in p.source]
    assert len(eclipse_parts) == 1
    assert eclipse_parts[0].primary_damage == Fraction(160)
    assert len(res.steps[1].shield_events) == 1
    assert res.steps[1].shield_events[0].amount == Fraction(174)
    assert res.label is Label.DERIVED

    # Ranged values: 5% * 2000 = 100 phys + shield 75 + 0.2*60 = 87
    ranged_sheet = _sheet("Caitlyn", 9, ["6692"])
    ranged_kit = load_kit(ROOT, "Caitlyn")
    res_r = evaluate_rotation(
        ranged_kit,
        ranged_sheet,
        {"Q": 5, "W": 1, "E": 1, "R": 1},
        target,
        parse_steps("attack attack"),
        CRIT_BASE,
        holder_range="ranged",
    )
    assert [p for p in res_r.steps[1].parts if "6692" in p.source][0].primary_damage == Fraction(
        100
    )
    assert res_r.steps[1].shield_events[0].amount == Fraction(87)

    # Timeline: wait:2 expires the 2 s combo window; wait:6 resets the 6 s cooldown
    res_win = evaluate_rotation(
        kit,
        sheet,
        {"Q": 5, "W": 1, "E": 1, "R": 1},
        _target(hp=5000),
        parse_steps("attack wait:2 attack attack wait:6 attack attack"),
        CRIT_BASE,
        holder_range="melee",
        timeline=True,
    )
    procced = [any("6692" in p.source for p in s.parts) for s in res_win.steps]
    # step 1 atk (hit 1), step 2 wait:2, step 3 atk (window expired -> hit 1),
    # step 4 atk (hit 2 -> PROC!), step 5 wait:6, step 6 atk (hit 1), step 7 atk (hit 2 -> PROC!)
    assert procced == [False, False, False, True, False, False, True]

    # Does not proc against minions
    res_minion = evaluate_rotation(
        kit,
        sheet,
        {"Q": 5, "W": 1, "E": 1, "R": 1},
        _target(hp=2000, kind="minion"),
        parse_steps("attack attack"),
        CRIT_BASE,
        holder_range="melee",
    )
    assert not any("6692" in p.source for s in res_minion.steps for p in s.parts)


# ---------------------------------------------------------------------------
# Secondary-only attack splash: Runaan's (3085) & Hydras / Tiamat
# ---------------------------------------------------------------------------


def test_runaans_hurricane_bolts_crit_and_on_hit_repeat() -> None:
    sheet = _sheet("Jinx", 9, ["3085", "3153"])  # Runaan + BotRK (has life steal + on-hit)
    kit = load_kit(ROOT, "Jinx")
    ad = sheet["attack_damage"].total()

    # 1 target: no bolts
    r1 = evaluate_rotation(
        kit,
        sheet,
        {"Q": 5, "W": 1, "E": 1, "R": 1},
        _target(hp=2000),
        parse_steps("attack"),
        CRIT_BASE,
        holder_range="ranged",
        target_count=1,
    )
    assert r1.secondary_total == 0

    # 4 targets + crit: capped at 2 secondary targets, 60% AD * 2 (crit) = 1.2 * AD each
    # plus BotRK on-hit (6% current HP = 120) repeated on 2 secondary targets
    r4 = evaluate_rotation(
        kit,
        sheet,
        {"Q": 5, "W": 1, "E": 1, "R": 1},
        _target(hp=2000),
        parse_steps("attack:crit"),
        CRIT_BASE,
        holder_range="ranged",
        target_count=4,
    )
    bolts = [p for p in r4.steps[0].parts if p.source.startswith("3085 winds-fury")]
    assert len(bolts) == 1
    assert bolts[0].hits_primary is False
    assert bolts[0].targets_hit == 2
    assert bolts[0].primary_damage == 0
    assert bolts[0].secondary_damage == ad * Fraction(6, 10) * 2 * 2
    assert bolts[0].healing.life_steal == sheet["life_steal"].total()

    bolt_on_hits = [p for p in r4.steps[0].parts if "bolt by 3085" in p.source]
    assert len(bolt_on_hits) == 1
    assert bolt_on_hits[0].hits_primary is False
    assert bolt_on_hits[0].targets_hit == 2
    assert bolt_on_hits[0].secondary_damage == Fraction(120) * 2

    # Report formats secondary-only parts cleanly
    text = format_text(r4, sheet, _target(hp=2000), CRIT_BASE)
    assert "x2 secondary" in text
    data = to_dict(r4, sheet, _target(hp=2000), CRIT_BASE)
    assert any(p["hits_primary"] is False for p in data["steps"][0]["parts"])


def test_titanic_and_ravenous_hydra_cleave() -> None:
    sheet_t = _sheet("Garen", 9, ["3748"])
    kit = load_kit(ROOT, "Garen")
    max_hp = sheet_t["health"].total()

    rt = evaluate_rotation(
        kit,
        sheet_t,
        {"Q": 5, "W": 1, "E": 1, "R": 1},
        _target(hp=2000),
        parse_steps("attack"),
        CRIT_BASE,
        holder_range="melee",
        target_count=3,
    )
    cleave_parts = [p for p in rt.steps[0].parts if "3748 cleave" in p.source]
    assert len(cleave_parts) == 2
    primary_c = [p for p in cleave_parts if p.hits_primary][0]
    sec_c = [p for p in cleave_parts if not p.hits_primary][0]
    assert primary_c.primary_damage == max_hp * Fraction(1, 100)
    assert sec_c.secondary_damage == max_hp * Fraction(3, 100) * 2

    # Ravenous Hydra (3074): 40% total AD melee secondary splash that applies life steal
    sheet_r = _sheet("Garen", 9, ["3074"])
    ad = sheet_r["attack_damage"].total()
    rr = evaluate_rotation(
        kit,
        sheet_r,
        {"Q": 5, "W": 1, "E": 1, "R": 1},
        _target(hp=2000),
        parse_steps("attack"),
        CRIT_BASE,
        holder_range="melee",
        target_count=3,
    )
    rav_cleave = [p for p in rr.steps[0].parts if "3074 cleave" in p.source][0]
    assert rav_cleave.secondary_damage == ad * Fraction(4, 10) * 2
    assert rav_cleave.healing.life_steal == sheet_r["life_steal"].total()


# ---------------------------------------------------------------------------
# On-damage cooldown procs: Alternator (3145) & Scout's Slingshot (3144)
# ---------------------------------------------------------------------------


def test_hextech_alternator_and_scouts_slingshot() -> None:
    kit = load_kit(ROOT, "Ahri")
    sheet_alt = _sheet("Ahri", 9, ["3145"])
    r_alt = evaluate_rotation(
        kit,
        sheet_alt,
        {"Q": 5, "W": 1, "E": 1, "R": 1},
        _target(hp=2000),
        parse_steps("attack E"),
        CRIT_BASE,
        holder_range="ranged",
    )
    alt_parts = [p for s in r_alt.steps for p in s.parts if "3145 revved" in p.source]
    assert len(alt_parts) == 1
    assert alt_parts[0].primary_damage == Fraction(65)

    # Scout's Slingshot (3144): 40 magic damage, 40 s CD reduced by 1 s per attack
    sheet_s = _sheet("Jinx", 9, ["3144"])
    kit_j = load_kit(ROOT, "Jinx")
    # step 1 attack (t=0) triggers 3144 (ready at 40 s).
    # 2 more attacks reduce ready by 2 s -> ready at 38 s!
    r_s = evaluate_rotation(
        kit_j,
        sheet_s,
        {"Q": 5, "W": 1, "E": 1, "R": 1},
        _target(hp=5000),
        parse_steps("attack attack attack wait:38 attack"),
        CRIT_BASE,
        holder_range="ranged",
        timeline=True,
    )
    slingshot_steps = [any("3144 bullseye" in p.source for p in s.parts) for s in r_s.steps]
    assert slingshot_steps == [True, False, False, False, True]


# ---------------------------------------------------------------------------
# Aura burns (OBJ-08) & Riftmaker / Abyssal Mask
# ---------------------------------------------------------------------------


def test_immolate_burns_on_attack_and_target_kind_scaling() -> None:
    sheet = _sheet("Garen", 9, ["3068"])  # Sunfire: 350 bonus HP -> 20 + 0.015 * 350 = 25.25/s
    kit = load_kit(ROOT, "Garen")
    expected_dps = Fraction(20) + Fraction(350) * Fraction(3, 200)

    r_champ = evaluate_rotation(
        kit,
        sheet,
        {"Q": 5, "W": 1, "E": 1, "R": 1},
        _target(hp=2000, kind="champion"),
        parse_steps("attack"),
        CRIT_BASE,
        holder_range="melee",
    )
    burn_c = [p for p in r_champ.steps[0].parts if "3068 immolate" in p.source][0]
    assert burn_c.primary_damage == expected_dps * 3

    r_minion = evaluate_rotation(
        kit,
        sheet,
        {"Q": 5, "W": 1, "E": 1, "R": 1},
        _target(hp=2000, kind="minion"),
        parse_steps("attack"),
        CRIT_BASE,
        holder_range="melee",
    )
    burn_m = [p for p in r_minion.steps[0].parts if "3068 immolate" in p.source][0]
    assert burn_m.primary_damage == expected_dps * Fraction(3, 2) * 3

    r_monster = evaluate_rotation(
        kit,
        sheet,
        {"Q": 5, "W": 1, "E": 1, "R": 1},
        _target(hp=2000, kind="monster"),
        parse_steps("attack"),
        CRIT_BASE,
        holder_range="melee",
    )
    burn_j = [p for p in r_monster.steps[0].parts if "3068 immolate" in p.source][0]
    assert burn_j.primary_damage == expected_dps * Fraction(9, 5) * 3


def test_riftmaker_conversion_and_abyssal_mask_magic_amp() -> None:
    # Riftmaker (4633): 70 AP + 2% of 350 HP = 77 AP; +Rabadon (130 AP, x1.3) = 207 * 1.3
    sheet_rm = _sheet("Ahri", 9, ["4633", "3089"])
    assert sheet_rm["ability_power"].total() == Fraction(207) * Fraction(13, 10)

    # Abyssal Mask (8020): +12% magic damage vs champions, 0% on physical attacks
    sheet_am = _sheet("Ahri", 9, ["8020"])
    kit = load_kit(ROOT, "Ahri")
    r_am = evaluate_rotation(
        kit,
        sheet_am,
        {"Q": 5, "W": 1, "E": 1, "R": 1},
        _target(hp=2000, kind="champion"),
        parse_steps("attack E"),
        CRIT_BASE,
        holder_range="ranged",
    )
    assert r_am.steps[0].parts[0].dealt == ()  # physical basic attack
    assert ("8020 unmake", Fraction(12)) in r_am.steps[1].parts[0].dealt  # magic E


# ---------------------------------------------------------------------------
# Stat conversions & haste passives (2501, 3003, 3004, 3119, 3161, 3073, 2512)
# ---------------------------------------------------------------------------


def test_stat_conversion_items_and_manaless_champion() -> None:
    # Overlord's Bloodmail (2501): 550 bonus HP -> +13.75 bonus AD (+ 40 flat = 53.75 bonus AD)
    s_ob = _sheet("Garen", 9, ["2501"])
    assert s_ob["attack_damage"].scoped("bonus") == Fraction(40) + Fraction(550) * Fraction(
        25, 1000
    )

    # Archangel's Staff (3003): 70 AP + 1% of 600 bonus mana = 76 AP on mana champ
    s_aa = _sheet("Ahri", 9, ["3003"])
    assert s_aa["ability_power"].total() == Fraction(76)
    # On manaless Garen, mana is 0 -> 70 AP (no crash!)
    s_aa_garen = _sheet("Garen", 9, ["3003"])
    assert s_aa_garen["ability_power"].total() == Fraction(70)

    # Manamune (3004): 35 flat AD + 2% of total mana
    s_mm = _sheet("Ezreal", 9, ["3004"])
    expected_mm_bonus = Fraction(35) + s_mm["mana"].total() * Fraction(2, 100)
    assert s_mm["attack_damage"].scoped("bonus") == expected_mm_bonus

    # Winter's Approach (3119): 550 flat HP + 15% of 500 bonus mana = 625 bonus HP
    s_wa = _sheet("Blitzcrank", 9, ["3119"])
    assert s_wa["health"].scoped("bonus") == Fraction(550) + Fraction(75)


def test_shojin_basic_haste_and_focused_will_stacks() -> None:
    sheet = _sheet("Ahri", 9, ["3161"])
    assert sheet["basic_ability_haste"].total() == Fraction(25)
    cds = ability_cooldowns(sheet)
    cd_by_slot = {s.slot: s for s in cds.spells}
    # Basic ability Q gets 25 haste (0.8x CD), ultimate R gets 0 haste (1.0x CD)
    assert cd_by_slot["Q"].effective[0] == cd_by_slot["Q"].base[0] * Fraction(100, 125)
    assert cd_by_slot["R"].effective[0] == cd_by_slot["R"].base[0]

    # Focused Will: 1st ability = 0 stacks, 2nd = +3%, 3rd = +6%, attack = 0%
    kit = load_kit(ROOT, "Ahri")
    res = evaluate_rotation(
        kit,
        sheet,
        {"Q": 5, "W": 1, "E": 1, "R": 1},
        _target(hp=3000),
        parse_steps("E W.one Q.out attack"),
        CRIT_BASE,
        holder_range="ranged",
    )
    assert res.steps[0].parts[0].dealt == ()
    assert ("3161 focused-will (1x)", Fraction(3)) in res.steps[1].parts[0].dealt
    assert ("3161 focused-will (2x)", Fraction(6)) in res.steps[2].parts[0].dealt
    assert res.steps[3].parts[0].dealt == ()  # basic attack is not amplified


def test_hexplate_and_fiendhunter_ultimate_haste_and_overdrive() -> None:
    sheet_hex = _sheet("Garen", 9, ["3073"])
    assert sheet_hex["ultimate_haste"].total() == Fraction(30)
    cds = ability_cooldowns(sheet_hex)
    cd_by_slot = {s.slot: s for s in cds.spells}
    assert cd_by_slot["R"].effective[0] == cd_by_slot["R"].base[0] * Fraction(100, 130)
    assert cd_by_slot["Q"].effective[0] == cd_by_slot["Q"].base[0]

    # Fiendhunter Bolts (2512) also grants +30 ultimate haste
    sheet_fb = _sheet("Jinx", 9, ["2512"])
    assert sheet_fb["ultimate_haste"].total() == Fraction(30)

    # Overdrive (+50% melee AS for 8 s after casting R) speeds up attacks in timeline
    kit = load_kit(ROOT, "Garen")
    no_r = evaluate_rotation(
        kit,
        sheet_hex,
        {"Q": 5, "W": 1, "E": 1, "R": 1},
        _target(hp=5000),
        parse_steps("attack attack"),
        CRIT_BASE,
        holder_range="melee",
        timeline=True,
    )
    with_r = evaluate_rotation(
        kit,
        sheet_hex,
        {"Q": 5, "W": 1, "E": 1, "R": 1},
        _target(hp=5000),
        parse_steps("R attack attack"),
        CRIT_BASE,
        holder_range="melee",
        timeline=True,
    )
    assert with_r.steps[2].time is not None and no_r.steps[1].time is not None
    assert with_r.steps[2].time < no_r.steps[1].time


# ---------------------------------------------------------------------------
# Utility & Grievous Wounds items do not weaken rotations
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("item_id", ["3046", "3033", "3165", "6609", "3123", "3916"])
def test_utility_and_grievous_items_do_not_weaken_rotations(item_id: str) -> None:
    sheet = _sheet("Caitlyn", 9, [item_id])
    kit = load_kit(ROOT, "Caitlyn")
    res = evaluate_rotation(
        kit,
        sheet,
        {"Q": 5, "W": 1, "E": 1, "R": 1},
        _target(hp=2000),
        parse_steps("attack"),
        CRIT_BASE,
        holder_range="ranged",
    )
    assert res.label is not Label.PENDING


# ---------------------------------------------------------------------------
# Lifeline (6673, 3156, 3155) & Bramble Vest Thorns (3076)
# ---------------------------------------------------------------------------


def test_shieldbow_maw_hexdrinker_lifeline_and_bramble_thorns() -> None:
    # Immortal Shieldbow (6673) on ranged Caitlyn lvl 18 -> 560 normal shield
    s_sb = _sheet("Caitlyn", 18, ["6673"])
    hp_sb = s_sb["health"].total()
    hit_big = IncomingHit(
        "ability", DamageType.PHYSICAL, hp_sb * Fraction(4, 5), "burst", already_mitigated=True
    )
    out_sb = evaluate_defense(s_sb, [hit_big])
    assert out_sb.total_shield_granted == Fraction(560)
    assert out_sb.steps[0].shields_granted[0].shield_type == "normal"

    # Maw of Malmortius (3156) on melee Garen: 60 bonus AD -> 200 + 1.5*60 = 290 magic shield
    s_maw = _sheet("Garen", 11, ["3156"])
    hp_maw = s_maw["health"].total()
    phys_hit = IncomingHit(
        "ability", DamageType.PHYSICAL, hp_maw * Fraction(4, 5), "phys", already_mitigated=True
    )
    magic_hit = IncomingHit(
        "ability", DamageType.MAGIC, hp_maw * Fraction(4, 5), "magic", already_mitigated=True
    )
    assert evaluate_defense(s_maw, [phys_hit]).total_shield_granted == Fraction(0)
    out_maw = evaluate_defense(s_maw, [magic_hit])
    assert out_maw.total_shield_granted == Fraction(290)
    assert out_maw.steps[0].shields_granted[0].shield_type == "magic"

    # Hexdrinker (3155) on ranged Caitlyn lvl 1 -> 82.5 magic shield
    s_hex = _sheet("Caitlyn", 1, ["3155"])
    hp_hex = s_hex["health"].total()
    m_hit = IncomingHit(
        "ability", DamageType.MAGIC, hp_hex * Fraction(4, 5), "magic", already_mitigated=True
    )
    out_hex = evaluate_defense(s_hex, [m_hit])
    assert out_hex.total_shield_granted == Fraction(165, 2)

    # Bramble Vest (3076) on target applies 40% Grievous Wounds when attacked
    s_atk = _sheet("Caitlyn", 9, ["3153"])  # has life steal
    kit_c = load_kit(ROOT, "Caitlyn")
    r_bramble = evaluate_rotation(
        kit_c,
        s_atk,
        {"Q": 5, "W": 1, "E": 1, "R": 1},
        _target(hp=2000, item_ids=["3076"]),
        parse_steps("attack"),
        CRIT_BASE,
        holder_range="ranged",
    )
    assert r_bramble.grievous_wounds_applied is True
