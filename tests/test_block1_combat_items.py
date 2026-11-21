"""Comprehensive tests for Block 1 items: 1A combat passives, 1B stackables/Tear
transforms, 1C consumables (elixirs/potions), and 1D support/ally-synergy items.
"""

from __future__ import annotations

from fractions import Fraction
from pathlib import Path

import pytest

from lol_knowledge.damage import DamageType
from lol_knowledge.defense import evaluate_defense, parse_incoming
from lol_knowledge.errors import RotationError, StatsError
from lol_knowledge.kit import load_kit
from lol_knowledge.objects.legality import check_build, load_item_groups
from lol_knowledge.rotation import CritBase, evaluate_rotation, parse_steps
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
ISSUES = load_issues(ROOT)
DERIVED = load_records(ROOT)
GROUPS = load_item_groups(ROOT)
F = Fraction
CRIT_BASE = CritBase(F(2), Label.DERIVED, "test crit 2.0")


def _sheet(
    champ: str,
    level: int,
    items: tuple[str, ...] = (),
    inputs: dict[str, Fraction] | None = None,
):
    return build_stat_sheet(
        load_champion(ROOT, champ),
        level,
        load_items(ROOT, list(items)),
        ISSUES,
        {},
        DERIVED,
        inputs=inputs or {},
    )


def _target(
    armor: int = 0,
    mr: int = 0,
    hp: int = 3000,
    kind: str = "champion",
    shield: int = 0,
):
    return target_from_values(
        F(armor), F(mr), max_health=F(hp), current_health=F(hp), kind=kind, shield=F(shield)
    )


# --- 1B: Static passives, stackables, and Tear transformations ---


def test_malignance_dawncore_overlord_and_murder_sheet_passives() -> None:
    # 3118 Malignance Disdain: +20 ultimate haste
    s_mal = _sheet("Ahri", 11, ("3118",))
    assert s_mal["ultimate_haste"].total() == F(20)

    # 6621 Dawncore First Light: +15 AP & +2% HSP per 100% bonus base mana regen
    # 6621 alone has 100% mana regen -> +15 AP (45+15=60), +2% HSP (16+2=18%)
    s_dc = _sheet("Ahri", 11, ("6621",))
    assert s_dc["ability_power"].total() == F(60)
    assert s_dc["heal_and_shield_power"].total() == F(18, 100)
    # 6621 (100%) + 3504 Ardent (125%) = 225% -> +33.75 AP, +4.5% HSP
    s_dc2 = _sheet("Ahri", 11, ("6621", "3504"))
    assert s_dc2["ability_power"].total() == F(45 + 45) + F(225) * F(15, 100)
    assert s_dc2["heal_and_shield_power"].total() == F(26, 100) + F(225) * F(2, 10000)

    # 2501 Overlord's Retribution: 0% at full HP, +10% AD at <=30% HP
    s_full = _sheet("Garen", 11, ("2501",))
    s_low = _sheet("Garen", 11, ("2501",), {"attacker_health_percent": F(3, 10)})
    assert s_low["attack_damage"].total() == s_full["attack_damage"].total() * F(11, 10)

    # 3008 / 3168 Murder (+6% omnivamp at default 10 stacks) & 3168 Now and Forever
    s_3168_low = _sheet("Garen", 11, ("3168",), {"attacker_health_percent": F(4, 10)})
    assert s_3168_low["omnivamp"].total() == F(10, 100)  # 4% base + 6% Murder
    assert s_3168_low["heal_and_shield_power"].total() == F(12, 100)
    s_3168_custom = _sheet("Garen", 11, ("3008",), {"murder_stacks": F(5)})
    assert s_3168_custom["omnivamp"].total() == F(7, 100)  # 4% + 3%


def test_stackables_dark_seal_mejais_hubris_roa_and_eternity() -> None:
    s_ds = _sheet("Ahri", 9, ("1082",), {"glory_stacks": F(10)})
    assert s_ds["ability_power"].total() == F(15 + 40)

    s_mj_base = _sheet("Ahri", 9, ("3041",), {"glory_stacks": F(0)})
    s_mj_25 = _sheet("Ahri", 9, ("3041",), {"glory_stacks": F(25)})
    assert s_mj_25["ability_power"].total() == F(20 + 125)
    assert s_mj_25["move_speed"].total() > s_mj_base["move_speed"].total()

    # 6697 Hubris: 15 + 3*stacks melee, x0.667 ranged
    s_hub_m = _sheet("Garen", 11, ("6697",), {"hubris_stacks": F(4)})
    s_hub_m0 = _sheet("Garen", 11, ("6697",))
    assert s_hub_m["attack_damage"].total() - s_hub_m0["attack_damage"].total() == F(27)
    s_hub_r = _sheet("Ahri", 11, ("6697",), {"hubris_stacks": F(4)})
    s_hub_r0 = _sheet("Ahri", 11, ("6697",))
    assert s_hub_r["attack_damage"].total() - s_hub_r0["attack_damage"].total() == (
        F(27) * F(667, 1000)
    )

    # 6657 RoA Timeless (+10 HP, +30 Mana, +3 AP per stack up to 10) + Eternity
    s_roa0 = _sheet("Ahri", 11, ("6657",))
    s_roa10 = _sheet("Ahri", 11, ("6657",), {"roa_stacks": F(10)})
    assert s_roa10["health"].total() - s_roa0["health"].total() == F(100)
    assert s_roa10["mana"].total() - s_roa0["mana"].total() == F(300)
    assert s_roa10["ability_power"].total() - s_roa0["ability_power"].total() == F(30)

    # Eternity cast heal (Ahri Q rank 5 costs 75 mana -> 25% = 18.75 <= 20)
    kit = load_kit(ROOT, "Ahri")
    assert kit is not None
    rot = evaluate_rotation(
        kit, s_roa10, {"Q": 5, "W": 1, "E": 1, "R": 1}, _target(), parse_steps("Q.both"), CRIT_BASE
    )
    et_heals = [h for st in rot.steps for h in st.heal_events if "6657 eternity" in h.source]
    assert et_heals and et_heals[0].raw > 0 and et_heals[0].raw <= F(20)


def test_tear_manaflow_and_auto_transforms_3040_3042_3121_2530() -> None:
    # Partial stacks on 3003 Archangel's: +200 mana -> +2 AP from Awe (1% bonus mana)
    s_3003_0 = _sheet("Ahri", 11, ("3003",))
    s_3003_200 = _sheet("Ahri", 11, ("3003",), {"manaflow_stacks": F(200)})
    assert s_3003_200["mana"].total() - s_3003_0["mana"].total() == F(200)
    assert s_3003_200["ability_power"].total() - s_3003_0["ability_power"].total() == F(2)

    # 360 stacks auto-transforms 3003 -> 3040 Seraph's Embrace (1000 mana, 2% bonus mana AP,
    # 18% max mana Lifeline shield below 30% HP)
    s_3040 = _sheet("Ahri", 11, ("3003",), {"manaflow_stacks": F(360)})
    assert s_3040.items[0].id == "3040"
    assert s_3040["ability_power"].total() == F(70) + F(1000) * F(2, 100)
    max_hp = s_3040["health"].total()
    max_mana = s_3040["mana"].total()
    def_res = evaluate_defense(
        s_3040, parse_incoming(f"true:{int(max_hp * F(8, 10))}"), timeline=True
    )
    seraph_sh = [sh for st in def_res.steps for sh in st.shields_granted if "3040" in sh.source]
    assert seraph_sh and seraph_sh[0].raw == max_mana * F(18, 100)

    # 3004 -> 3042 Muramana at 360 stacks: Shock 1.2% max mana on-hit & 4% melee / 3% ranged ability
    s_3042 = _sheet("Garen", 11, ("3004",), {"manaflow_stacks": F(360)})
    assert s_3042.items[0].id == "3042"
    # Direct load of 3042 on Ahri (ranged)
    s_ahri_3042 = _sheet("Ahri", 11, ("3042",))
    kit = load_kit(ROOT, "Ahri")
    assert kit is not None
    rot = evaluate_rotation(
        kit,
        s_ahri_3042,
        {"Q": 5, "W": 1, "E": 1, "R": 1},
        _target(),
        parse_steps("attack E"),
        CRIT_BASE,
        holder_range="ranged",
    )
    a_mana = s_ahri_3042["mana"].total()
    shock_oh = [p for p in rot.steps[0].parts if "3042 shock-attack" in p.source]
    shock_ab = [p for p in rot.steps[1].parts if "3042 shock-ability" in p.source]
    assert shock_oh and shock_oh[0].raw == a_mana * F(12, 1000)
    assert shock_ab and shock_ab[0].raw == a_mana * F(3, 100)

    # Legality: 3042 is legal alone, illegal combined with 3004 or 3040
    assert GROUPS is not None
    assert check_build(["3042"], GROUPS, patch="16.23.1").legal
    assert not check_build(["3042", "3004"], GROUPS, patch="16.23.1").legal
    assert not check_build(["3042", "3040"], GROUPS, patch="16.23.1").legal

    # 3119 -> 3121 Fimbulwinter (15% bonus mana -> HP + Everlasting shield with +80% multi-target)
    s_3121 = _sheet("Ahri", 11, ("3119",), {"manaflow_stacks": F(360)})
    assert s_3121.items[0].id == "3121"
    rot_f = evaluate_rotation(
        kit,
        s_3121,
        {"Q": 5, "W": 1, "E": 1, "R": 1},
        _target(),
        parse_steps("E"),
        CRIT_BASE,
        holder_range="ranged",
        inputs={"target_impaired": F(1)},
        target_count=2,
    )
    f_sh = [sh for st in rot_f.steps for sh in st.shield_events if "3121 everlasting" in sh.source]
    assert f_sh and f_sh[0].raw > F(180)

    # 2526 -> 2530 Diadem of Songs (Consonance 0.8% max mana/s ally heal in timeline)
    s_2530 = _sheet("Ahri", 11, ("2526",), {"manaflow_stacks": F(360)})
    assert s_2530.items[0].id == "2530"
    rot_d = evaluate_rotation(
        kit,
        s_2530,
        {"Q": 5, "W": 1, "E": 1, "R": 1},
        _target(),
        parse_steps("E wait:2"),
        CRIT_BASE,
        timeline=True,
    )
    c_heals = [h for st in rot_d.steps for h in st.heal_events if "2530 consonance" in h.source]
    assert len(c_heals) == 2
    assert c_heals[0].raw == s_2530["mana"].total() * F(8, 1000)


# --- 1C: Combat Consumables (Elixirs & Potions) ---


def test_elixirs_require_level_9_and_apply_stats_damage_and_physical_vamp() -> None:
    # Level 8: Elixir of Iron does NOT apply
    s_l8 = _sheet("Garen", 8, ("2138",))
    s_l8_none = _sheet("Garen", 8)
    assert s_l8["health"].total() == s_l8_none["health"].total()

    # Level 9: 2138 Iron (+300 HP, +25% Tenacity)
    s_iron = _sheet("Garen", 9, ("2138",))
    s_none = _sheet("Garen", 9)
    assert s_iron["health"].total() - s_none["health"].total() == F(300)
    assert s_iron["tenacity"].total() == F(25, 100)

    # 2139 Sorcery (+50 AP, +15 flat mana regen/5s, +25 true dmg vs champ 5 s CD)
    s_sorc = _sheet("Ahri", 9, ("2139",))
    s_ahri = _sheet("Ahri", 9)
    assert s_sorc["ability_power"].total() == F(50)
    assert s_sorc["mana_regen"].total() - s_ahri["mana_regen"].total() == F(15)
    kit = load_kit(ROOT, "Ahri")
    assert kit is not None
    rot_s = evaluate_rotation(
        kit,
        s_sorc,
        {"Q": 5, "W": 1, "E": 1, "R": 1},
        _target(),
        parse_steps("attack wait:2 attack wait:4 attack"),
        CRIT_BASE,
        timeline=True,
    )
    sorc_procs = [p for st in rot_s.steps for p in st.parts if "2139 elixir-of-sorcery" in p.source]
    # Fires at t=0 and t=6 (5 s CD skips t=2)
    assert len(sorc_procs) == 2
    assert all(p.raw == F(25) and p.damage_type is DamageType.TRUE for p in sorc_procs)

    # 2140 Wrath (+30 AD, +12% physical vamp vs champions)
    s_wrath = _sheet("Garen", 9, ("2140",))
    g_kit = load_kit(ROOT, "Garen")
    assert g_kit is not None
    rot_w = evaluate_rotation(
        g_kit,
        s_wrath,
        {"Q": 5, "W": 1, "E": 1, "R": 1},
        _target(),
        parse_steps("attack"),
        CRIT_BASE,
    )
    w_heals = [h for st in rot_w.steps for h in st.heal_events if "2140" in h.source]
    assert w_heals and w_heals[0].raw == s_wrath["attack_damage"].total() * F(12, 100)


def test_potions_2003_and_2031_in_rotation_and_defense() -> None:
    kit = load_kit(ROOT, "Garen")
    assert kit is not None
    s_pot = _sheet("Garen", 5, ("2003",))
    rot = evaluate_rotation(
        kit,
        s_pot,
        {"Q": 3, "W": 1, "E": 1, "R": 0},
        _target(),
        parse_steps("item:2003 wait:5"),
        CRIT_BASE,
        timeline=True,
    )
    # 5 s of 8 HP/s = 40 HP
    assert rot.healing == F(40)

    # 2031 Refillable: 2 charges allowed, 3rd raises RotationError
    s_ref = _sheet("Garen", 5, ("2031",))
    with pytest.raises(RotationError, match="no charges left"):
        evaluate_rotation(
            kit,
            s_ref,
            {"Q": 3, "W": 1, "E": 1, "R": 0},
            _target(),
            parse_steps("item:2031 item:2031 item:2031"),
            CRIT_BASE,
        )

    # Defense with potion_active=1 (2003 heals 120 HP over 15 s tail)
    def_res = evaluate_defense(
        s_pot, parse_incoming("true:300"), inputs={"potion_active": F(1)}, timeline=True
    )
    assert def_res.total_healing == F(120)


# --- 1A: Direct Combat Passives ---


def test_sundered_sky_unending_despair_heartsteel_dead_mans_and_statikk() -> None:
    g_kit = load_kit(ROOT, "Garen")
    assert g_kit is not None

    # 6610 Sundered Sky: forced crit at 80% normal crit (1.6x) + 90% base AD + 4% missing HP heal
    s_ss = _sheet("Garen", 11, ("6610",))
    rot_ss = evaluate_rotation(
        g_kit,
        s_ss,
        {"Q": 5, "W": 1, "E": 1, "R": 1},
        _target(),
        parse_steps("attack attack"),
        CRIT_BASE,
        holder_range="melee",
        inputs={"attacker_health_percent": F(1, 2)},
    )
    ad = s_ss["attack_damage"].total()
    base_ad = s_ss["attack_damage"].scoped("base")
    max_hp = s_ss["health"].total()
    assert rot_ss.steps[0].parts[0].raw == ad * F(8, 5)  # 1.6x
    assert rot_ss.steps[1].parts[0].raw == ad  # on 10 s CD
    ss_heals = [h for h in rot_ss.steps[0].heal_events if "6610" in h.source]
    assert ss_heals and ss_heals[0].raw == base_ad * F(9, 10) + (max_hp / 2) * F(4, 100)

    # 2502 Unending Despair: 3% bonus HP magic AoE at t=4 s on 2 targets, heals 250% dealt
    s_ud = _sheet("Garen", 11, ("2502",))
    rot_ud = evaluate_rotation(
        g_kit,
        s_ud,
        {"Q": 5, "W": 1, "E": 1, "R": 1},
        _target(mr=0),
        parse_steps("attack wait:4"),
        CRIT_BASE,
        timeline=True,
        target_count=2,
    )
    ud_parts = [p for st in rot_ud.steps for p in st.parts if "2502 anguish" in p.source]
    ud_heals = [h for st in rot_ud.steps for h in st.heal_events if "2502 anguish" in h.source]
    expected_single = F(400) * F(3, 100)  # 400 bonus HP * 3% = 12
    assert ud_parts and ud_parts[0].damage == expected_single * 2
    assert ud_heals and ud_heals[0].raw == expected_single * 2 * F(5, 2)

    # 3084 Heartsteel: 70 + 6% max HP after 3 s charge
    s_hs = _sheet("Garen", 11, ("3084",))
    rot_hs = evaluate_rotation(
        g_kit,
        s_hs,
        {"Q": 5, "W": 1, "E": 1, "R": 1},
        _target(),
        parse_steps("attack"),
        CRIT_BASE,
        inputs={"heartsteel_charged": F(1)},
    )
    hs_parts = [p for p in rot_hs.steps[0].parts if "3084" in p.source]
    assert hs_parts and hs_parts[0].raw == F(70) + s_hs["health"].total() * F(6, 100)

    # 3742 Dead Man's Plate: 40 + 100% base AD on attack 1, 0 on attack 2
    s_dmp = _sheet("Garen", 11, ("3742",))
    rot_dmp = evaluate_rotation(
        g_kit,
        s_dmp,
        {"Q": 5, "W": 1, "E": 1, "R": 1},
        _target(),
        parse_steps("attack attack"),
        CRIT_BASE,
    )
    dmp_p1 = [p for p in rot_dmp.steps[0].parts if "3742" in p.source]
    dmp_p2 = [p for p in rot_dmp.steps[1].parts if "3742" in p.source]
    assert dmp_p1 and dmp_p1[0].raw == F(40) + s_dmp["attack_damage"].scoped("base")
    assert not dmp_p2

    # 3087 Statikk Shiv: 60 magic dmg vs champ bouncing up to 6 targets at L11 (cap 6)
    s_ssv = _sheet("Garen", 11, ("3087",))
    rot_ssv = evaluate_rotation(
        g_kit,
        s_ssv,
        {"Q": 5, "W": 1, "E": 1, "R": 1},
        _target(),
        parse_steps("attack"),
        CRIT_BASE,
        target_count=5,
    )
    st_parts = [p for p in rot_ssv.steps[0].parts if "3087 electrospark" in p.source]
    assert st_parts and st_parts[0].raw == F(60) and st_parts[0].damage == F(300)


def test_fiendhunter_hexoptics_horizon_serpents_bloodthirster_feast_sabotage() -> None:
    a_kit = load_kit(ROOT, "Ahri")
    g_kit = load_kit(ROOT, "Garen")
    assert a_kit is not None and g_kit is not None

    # 2512 Fiendhunter: after R, non-crit -> 1.6x, natural crit -> 2.0x + 15% true damage
    s_fb = _sheet("Garen", 11, ("2512",))
    rot_fb = evaluate_rotation(
        g_kit,
        s_fb,
        {"Q": 5, "W": 1, "E": 1, "R": 1},
        _target(),
        parse_steps("R attack attack:crit"),
        CRIT_BASE,
        holder_range="melee",
    )
    fb_ad = s_fb["attack_damage"].total()
    assert rot_fb.steps[1].parts[0].raw == fb_ad * F(8, 5)
    assert rot_fb.steps[2].parts[0].raw == fb_ad * F(2)
    true_parts = [p for p in rot_fb.steps[2].parts if p.damage_type is DamageType.TRUE]
    assert true_parts and true_parts[0].raw == fb_ad * F(2) * F(15, 100)

    # 2523 Hexoptics C44: +10% attack damage at 500 distance, +5% at 250 distance
    s_c44 = _sheet("Ahri", 11, ("2523",))
    rot_c44_250 = evaluate_rotation(
        a_kit,
        s_c44,
        {"Q": 5, "W": 1, "E": 1, "R": 1},
        _target(),
        parse_steps("attack"),
        CRIT_BASE,
        inputs={"target_distance": F(250)},
    )
    assert rot_c44_250.steps[0].parts[0].damage == s_c44["attack_damage"].total() * F(105, 100)

    # 4628 Horizon Focus: +10% damage at >=600 distance (applies to triggering ability too!)
    s_hf = _sheet("Ahri", 11, ("4628",))
    rot_hf_far = evaluate_rotation(
        a_kit,
        s_hf,
        {"Q": 5, "W": 1, "E": 1, "R": 1},
        _target(),
        parse_steps("E"),
        CRIT_BASE,
        inputs={"target_distance": F(700)},
    )
    rot_hf_near = evaluate_rotation(
        a_kit,
        s_hf,
        {"Q": 5, "W": 1, "E": 1, "R": 1},
        _target(),
        parse_steps("E"),
        CRIT_BASE,
        inputs={"target_distance": F(400)},
    )
    assert rot_hf_far.total == rot_hf_near.total * F(11, 10)

    # 6695 Serpent's Fang: 50% melee shield shred in rotation AND defense
    s_sf = _sheet("Garen", 11, ("6695",))
    rot_sf = evaluate_rotation(
        g_kit,
        s_sf,
        {"Q": 5, "W": 1, "E": 1, "R": 1},
        _target(shield=400),
        parse_steps("attack"),
        CRIT_BASE,
        holder_range="melee",
    )
    # 400 shield shredded 50% -> 200 remaining before absorbing attack
    assert rot_sf.steps[0].shield_shredded == F(200)
    def_sf = evaluate_defense(
        _sheet("Garen", 11),
        parse_incoming("true:250"),
        start_shield=F(400),
        inputs={"shield_reaver": F(1, 2)},
    )
    # 400 shield -> 200 after 50% shred -> absorbs 200, 50 hits HP!
    assert def_sf.steps[0].shield_absorbed == F(200)
    assert def_sf.steps[0].health_damage == F(50)

    # 3072 Bloodthirster: excess life steal at full HP becomes Ichor Shield (cap 210 at L11)
    s_bt = _sheet("Garen", 11, ("3072",))
    rot_bt = evaluate_rotation(
        g_kit,
        s_bt,
        {"Q": 5, "W": 1, "E": 1, "R": 1},
        _target(),
        parse_steps("attack"),
        CRIT_BASE,
        inputs={"attacker_health_percent": F(1)},
    )
    bt_sh = [sh for sh in rot_bt.steps[0].shield_events if "3072 ichor-shield" in sh.source]
    assert bt_sh and bt_sh[0].raw == s_bt["attack_damage"].total() * F(15, 100)

    # 2517 Endless Hunger Feast (+15% omnivamp) & 2520 Bastionbreaker Sabotage (300 + 25*lethality)
    s_eh = _sheet("Garen", 11, ("2517",))
    rot_eh = evaluate_rotation(
        g_kit,
        s_eh,
        {"Q": 5, "W": 1, "E": 1, "R": 1},
        _target(),
        parse_steps("attack"),
        CRIT_BASE,
        inputs={"takedown": F(1)},
    )
    # 5% base omnivamp + 15% Feast = 20% omnivamp
    assert rot_eh.steps[0].parts[0].healing.omnivamp == F(20, 100)
    assert rot_eh.steps[0].parts[0].healing.amount == s_eh["attack_damage"].total() * F(20, 100)

    s_bb = _sheet("Garen", 11, ("2520",))
    rot_bb = evaluate_rotation(
        g_kit,
        s_bb,
        {"Q": 5, "W": 1, "E": 1, "R": 1},
        _target(kind="structure"),
        parse_steps("attack"),
        CRIT_BASE,
        holder_range="melee",
        inputs={"takedown": F(1)},
    )
    sab = [p for p in rot_bb.steps[0].parts if "2520 sabotage" in p.source]
    assert sab and sab[0].raw == F(300) + F(25) * F(18)


def test_dorans_shield_warmogs_and_guardian_angel_in_defense() -> None:
    # 1054 Doran's Shield: melee 40 max over 8 s scaled by missing HP fraction
    s_ds = _sheet("Garen", 1, ("1054",))
    max_hp = s_ds["health"].total()
    half = max_hp / 2
    res_ds = evaluate_defense(s_ds, parse_incoming(f"true:{float(half):.6f}"), timeline=True)
    ds_heals = [h for st in res_ds.steps for h in st.heals if "1054 enduring-focus" in h.source]
    assert ds_heals and abs(float(ds_heals[0].raw) - 20.0) < 1e-4

    # 3083 Warmog's Heart: bonus HP >= 2000 (3083 + 3084 reaches 2000+ with 12% amp)
    s_wm = _sheet("Garen", 18, ("3083", "3084"))
    assert s_wm["health"].scoped("bonus") >= F(2000)
    res_wm = evaluate_defense(s_wm, parse_incoming("true:1000 wait:10"), timeline=True)
    # 8 s OOC delay -> 2 s of 3% max HP/s = 6% max HP!
    wm_heals = [h for st in res_wm.steps for h in st.heals if "3083 warmogs-heart" in h.source]
    assert wm_heals and wm_heals[0].raw == s_wm["health"].total() * F(6, 100)

    # 3026 Guardian Angel: lethal hit -> 4 s stasis (immune at t=2) + 50% base HP revive
    s_ga = _sheet("Garen", 18, ("3026",))
    res_ga = evaluate_defense(s_ga, parse_incoming("true:9999 wait:2 true:9999"), timeline=True)
    assert res_ga.survived
    assert res_ga.remaining_health == s_ga["health"].scoped("base") / 2
    assert res_ga.steps[2].incoming == F(0)


# --- 1D: Support & Ally-Synergy Items ---


def test_support_items_ardent_staff_helia_mandate_dream_sleigh_vow_cryptbloom_bandlepipes() -> None:
    a_kit = load_kit(ROOT, "Ahri")
    assert a_kit is not None

    # 3504 Ardent + 6616 Staff + 6620 Helia triggered by ally heal active item:3107 Redemption
    s_sup = _sheet("Ahri", 11, ("3504", "6616", "6620", "3107"))
    rot_sup = evaluate_rotation(
        a_kit,
        s_sup,
        {"Q": 5, "W": 1, "E": 1, "R": 1},
        _target(),
        parse_steps("E item:3107 attack"),
        CRIT_BASE,
        timeline=True,
    )
    # Helia stored 30% of E's pre-mitigation damage and discharged it as ally heal on item:3107
    helia_h = [h for h in rot_sup.steps[1].heal_events if "6620 soul-siphon" in h.source]
    assert helia_h and helia_h[0].raw == rot_sup.steps[0].parts[0].raw * F(3, 10)
    # Ardent Sanctify granted +20 magic on-hit on the subsequent attack
    ardent_oh = [p for p in rot_sup.steps[2].parts if "3504 sanctify" in p.source]
    assert ardent_oh and ardent_oh[0].raw == F(20)

    # 4005 Imperial Mandate (+7% vulnerability on target_impaired=1)
    s_im = _sheet("Ahri", 11, ("4005",))
    rot_im1 = evaluate_rotation(
        a_kit,
        s_im,
        {"Q": 5, "W": 1, "E": 1, "R": 1},
        _target(),
        parse_steps("E"),
        CRIT_BASE,
        inputs={"target_impaired": F(1)},
    )
    rot_im0 = evaluate_rotation(
        a_kit,
        s_im,
        {"Q": 5, "W": 1, "E": 1, "R": 1},
        _target(),
        parse_steps("E"),
        CRIT_BASE,
        inputs={"target_impaired": F(0)},
    )
    assert rot_im1.total == rot_im0.total * F(107, 100)

    # 3870 Dream Maker: purple bubble (90 at L11) + blue bubble flat DR (110 at L11)
    s_dm = _sheet("Ahri", 11, ("3870",))
    rot_dm = evaluate_rotation(
        a_kit,
        s_dm,
        {"Q": 5, "W": 1, "E": 1, "R": 1},
        _target(),
        parse_steps("attack"),
        CRIT_BASE,
        inputs={"dream_maker_active": F(1)},
    )
    dm_p = [p for p in rot_dm.steps[0].parts if "3870 dream-maker" in p.source]
    assert dm_p and dm_p[0].raw == F(90)
    def_dm = evaluate_defense(
        s_dm, parse_incoming("attack:500"), inputs={"dream_maker_active": F(1)}
    )
    assert def_dm.steps[0].flat_reduced == F(110)

    # 3876 Solstice Sleigh (125 at L11) + 2524 Bandlepipes (+30% melee / +20.01% ranged AS)
    s_sl = _sheet("Ahri", 11, ("3876", "2524"))
    rot_sl = evaluate_rotation(
        a_kit,
        s_sl,
        {"Q": 5, "W": 1, "E": 1, "R": 1},
        _target(),
        parse_steps("E attack"),
        CRIT_BASE,
        holder_range="ranged",
        inputs={"target_impaired": F(1), "ally_present": F(1)},
    )
    sl_h = [h for st in rot_sl.steps for h in st.heal_events if "3876 going-sledding" in h.source]
    assert sl_h and sl_h[0].raw == F(125)

    # 3109 Knight's Vow (12% ally damage heal + 14% ally damage taken redirect)
    s_kv = _sheet("Garen", 11, ("3109",))
    g_kit = load_kit(ROOT, "Garen")
    assert g_kit is not None
    rot_kv = evaluate_rotation(
        g_kit,
        s_kv,
        {"Q": 5, "W": 1, "E": 1, "R": 1},
        _target(),
        parse_steps("attack"),
        CRIT_BASE,
        inputs={"worthy_ally_damage": F(1000)},
    )
    kv_h = [h for h in rot_kv.steps[0].heal_events if "3109 sacrifice" in h.source]
    assert kv_h and kv_h[0].raw == F(120)
    def_kv = evaluate_defense(
        s_kv, parse_incoming("true:100"), inputs={"worthy_ally_damage_taken": F(1000)}
    )
    # 14% of 1000 = 140 redirected + 100 direct = 240 HP lost
    assert s_kv["health"].total() - def_kv.remaining_health == F(240)

    # 3137 Cryptbloom: 100 + 20% AP healing nova on champion kill
    s_cb = _sheet("Ahri", 11, ("3137",))
    rot_cb = evaluate_rotation(
        a_kit,
        s_cb,
        {"Q": 5, "W": 1, "E": 1, "R": 1},
        _target(hp=50),
        parse_steps("E"),
        CRIT_BASE,
    )
    cb_h = [h for h in rot_cb.steps[0].heal_events if "3137 life-from-death" in h.source]
    assert cb_h and cb_h[0].raw == F(100) + F(75) * F(2, 10)


def test_invalid_stack_inputs_raise_stats_error() -> None:
    with pytest.raises(StatsError, match="glory_stacks"):
        _sheet("Ahri", 9, ("1082",), {"glory_stacks": F(11)})
    with pytest.raises(StatsError, match="manaflow_stacks"):
        _sheet("Ahri", 9, ("3003",), {"manaflow_stacks": F(400)})
    with pytest.raises(StatsError, match="roa_stacks"):
        _sheet("Ahri", 9, ("6657",), {"roa_stacks": F(-1)})
