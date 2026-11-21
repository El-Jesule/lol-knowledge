"""Tests for OBJ-01 completion: 218/218 items reviewed and 19 newly evaluable items."""

from __future__ import annotations

from fractions import Fraction
from pathlib import Path

import pytest

from lol_knowledge.damage import DamageType
from lol_knowledge.defense import IncomingHit, evaluate_defense
from lol_knowledge.errors import RotationError
from lol_knowledge.kit import load_kit
from lol_knowledge.objects import load_model
from lol_knowledge.rotation import CritBase, evaluate_rotation, parse_steps
from lol_knowledge.scenario import Target
from lol_knowledge.stats import Label, build_stat_sheet, load_champion, load_items, load_records

ROOT = Path(__file__).resolve().parents[1]
RECORDS = load_records(ROOT)
CRIT_BASE = CritBase(Fraction(2), Label.DERIVED, "patch 26.1")


def _sheet(champion_id: str, level: int, item_ids: list[str] | tuple[str, ...] = ()):
    champ = load_champion(ROOT, champion_id)
    items = load_items(ROOT, list(item_ids))
    return build_stat_sheet(champ, level, items, derived=RECORDS)


def _target(hp: int = 2000, armor: int = 100, mr: int = 100, kind: str = "champion") -> Target:
    return Target(
        armor=Fraction(armor),
        magic_resist=Fraction(mr),
        stats={"max_health": Fraction(hp), "current_health": Fraction(hp)},
        label=Label.OFFICIAL,
        description=f"{kind} {hp}hp {armor}ar {mr}mr",
        kind=kind,
    )


def test_all_218_items_have_complete_effect_review() -> None:
    model, _ = load_model(ROOT)
    objects = model["objects"]
    assert len(objects) == 218
    pending = [o["id"] for o in objects if o["effect_review"] != "complete"]
    assert pending == []


def test_black_cleaver_and_bloodletters_curse_percent_shred_stacking() -> None:
    # Black Cleaver (3071): -6% armor per physical hit up to 5 stacks (-30%)
    sheet_bc = _sheet("Garen", 11, ["3071"])
    kit_g = load_kit(ROOT, "Garen")
    assert kit_g is not None
    res_bc = evaluate_rotation(
        kit_g,
        sheet_bc,
        {"Q": 5, "W": 1, "E": 1, "R": 2},
        _target(hp=5000, armor=100, mr=0),
        parse_steps("attack attack attack attack attack attack"),
        CRIT_BASE,
        holder_range="melee",
    )
    # Step 1 hits 100 armor (0 stacks), ..., Step 6 hits 70 armor (5 stacks = -30%)
    eff_armors = [s.parts[0].mitigation.resistance.effective for s in res_bc.steps]
    assert eff_armors == [
        Fraction(100),
        Fraction(94),
        Fraction(88),
        Fraction(82),
        Fraction(76),
        Fraction(70),
    ]
    assert res_bc.label is Label.DERIVED

    # Bloodletter's Curse (8010): -7.5% MR per magic damaging ability up to 4 stacks (-30%)
    sheet_bl = _sheet("Ahri", 11, ["8010"])
    kit_a = load_kit(ROOT, "Ahri")
    assert kit_a is not None
    res_bl = evaluate_rotation(
        kit_a,
        sheet_bl,
        {"Q": 5, "W": 3, "E": 1, "R": 2},
        _target(hp=5000, armor=0, mr=100),
        parse_steps("attack E W.one Q.out"),
        CRIT_BASE,
        holder_range="ranged",
    )
    # Step 1 (physical basic attack) does NOT stack Bloodletter; Step 2 (E) hits 100 MR -> 1 stack;
    # Step 3 (W.one) hits 92.5 MR -> 2 stacks; Step 4 (Q.out) hits 85 MR -> 3 stacks
    assert res_bl.steps[1].parts[0].mitigation.resistance.effective == Fraction(100)
    assert res_bl.steps[2].parts[0].mitigation.resistance.effective == Fraction(185, 2)
    assert res_bl.steps[3].parts[0].mitigation.resistance.effective == Fraction(85)
    assert res_bl.label is Label.DERIVED


def test_stormsurge_threshold_delay_and_cooldown() -> None:
    sheet = _sheet("Ahri", 11, ["4646"])  # 90 AP -> Squall = 125 + 9 = 134 magic
    kit = load_kit(ROOT, "Ahri")
    assert kit is not None

    # Below 25% of 5000 HP (1250) -> does NOT trigger
    low = evaluate_rotation(
        kit,
        sheet,
        {"Q": 5, "W": 3, "E": 1, "R": 2},
        _target(hp=5000, armor=0, mr=0),
        parse_steps("E"),
        CRIT_BASE,
        holder_range="ranged",
    )
    assert not any("4646 stormraider" in p.source for s in low.steps for p in s.parts)

    # Above 25% of 1000 HP (250) with timeline -> triggers delayed strike at t=2 s!
    high = evaluate_rotation(
        kit,
        sheet,
        {"Q": 5, "W": 3, "E": 1, "R": 2},
        _target(hp=1000, armor=0, mr=0),
        parse_steps("E Q.both"),
        CRIT_BASE,
        holder_range="ranged",
        timeline=True,
    )
    squall_parts = [p for s in high.steps for p in s.parts if "4646 stormraider" in p.source]
    assert len(squall_parts) == 1
    assert squall_parts[0].raw == Fraction(134)
    assert high.steps[-1].time == Fraction(2)
    assert high.label is Label.DERIVED


def test_navori_flickerblade_reduces_basic_ability_cooldown_in_timeline() -> None:
    kit = load_kit(ROOT, "Caitlyn")
    assert kit is not None
    # With Navori (6675), each basic attack reduces remaining Q/W/E CD by 15%
    sheet_no = _sheet("Caitlyn", 9, ["3046"])  # Phantom Dancer (similar AS, no refund)
    sheet_nav = _sheet("Caitlyn", 9, ["6675"])
    # Cast Q (rank 5 = 6 s CD), 4 attacks (~3 s), wait 1.5 s, cast Q again:
    # Without Navori Q is on cooldown (~4.5 s < 6 s); with Navori Q is ready!
    steps = parse_steps("Q.first attack attack attack attack wait:1.5 Q.first")
    with pytest.raises(RotationError, match="on cooldown"):
        evaluate_rotation(
            kit,
            sheet_no,
            {"Q": 5, "W": 1, "E": 1, "R": 1},
            _target(hp=5000),
            steps,
            CRIT_BASE,
            holder_range="ranged",
            timeline=True,
        )
    res_nav = evaluate_rotation(
        kit,
        sheet_nav,
        {"Q": 5, "W": 1, "E": 1, "R": 1},
        _target(hp=5000),
        steps,
        CRIT_BASE,
        holder_range="ranged",
        timeline=True,
    )
    assert res_nav.total > 0


def test_spirit_visage_amplifies_healing_and_shields_by_25_percent() -> None:
    kit = load_kit(ROOT, "Garen")
    assert kit is not None
    # Eclipse (6692) grants 174 shield on 2nd hit; +Spirit Visage (3065) = 174 * 1.25 = 217.5
    s_base = _sheet("Garen", 9, ["6692"])
    s_sv = _sheet("Garen", 9, ["6692", "3065"])
    r_base = evaluate_rotation(
        kit,
        s_base,
        {"Q": 5, "W": 1, "E": 1, "R": 1},
        _target(hp=2000, armor=0, mr=0),
        parse_steps("attack attack"),
        CRIT_BASE,
        holder_range="melee",
    )
    r_sv = evaluate_rotation(
        kit,
        s_sv,
        {"Q": 5, "W": 1, "E": 1, "R": 1},
        _target(hp=2000, armor=0, mr=0),
        parse_steps("attack attack"),
        CRIT_BASE,
        holder_range="melee",
    )
    assert r_sv.total_shield_granted == r_base.total_shield_granted * Fraction(5, 4)

    # Spirit Visage also amplifies Shieldbow Lifeline in defense.py by +25%
    s_sb_sv = _sheet("Caitlyn", 18, ["6673", "3065"])
    hp = s_sb_sv["health"].total()
    out = evaluate_defense(
        s_sb_sv,
        [
            IncomingHit(
                "ability", DamageType.PHYSICAL, hp * Fraction(4, 5), "burst", already_mitigated=True
            )
        ],
    )
    assert out.total_shield_granted == Fraction(560) * Fraction(5, 4)


def test_reactive_non_threshold_shields_kaenic_chainlaced_and_armored_advance() -> None:
    # Kaenic Rookern (2504): 15% max HP magic shield on taking magic damage (not physical)
    s_kr = _sheet("Garen", 11, ["2504"])
    hp_kr = s_kr["health"].total()
    phys = IncomingHit("ability", DamageType.PHYSICAL, Fraction(300), "p", already_mitigated=True)
    magic = IncomingHit("ability", DamageType.MAGIC, Fraction(300), "m", already_mitigated=True)
    assert evaluate_defense(s_kr, [phys]).total_shield_granted == Fraction(0)
    out_kr = evaluate_defense(s_kr, [magic])
    assert out_kr.total_shield_granted == hp_kr * Fraction(15, 100)

    # Armored Advance (3174): Plated -10% attack dmg + 90..190 + 8% bonus HP physical shield
    s_aa = _sheet("Garen", 18, ["3174"])  # 0 bonus HP -> lvl 18 shield = 190
    out_aa = evaluate_defense(
        s_aa,
        [IncomingHit("attack", DamageType.PHYSICAL, Fraction(500), "aa", already_mitigated=True)],
    )
    assert out_aa.total_shield_granted == Fraction(190)

    # Chainlaced Crushers (3173): lvl 18 shield = 190 + 8% bonus HP magic shield
    s_cc = _sheet("Garen", 18, ["3173"])
    out_cc = evaluate_defense(s_cc, [magic])
    assert out_cc.total_shield_granted == Fraction(190)


def test_stat_conversions_endless_hunger_whispering_circlet_and_warmogs() -> None:
    # Endless Hunger (2517): 65 bonus AD -> melee 5 + 13%*65, ranged 5 + 10%*65 AH
    s_melee = _sheet("Garen", 9, ["2517"])
    assert s_melee["ability_haste"].total() == Fraction(5) + Fraction(65) * Fraction(13, 100)
    s_ranged = _sheet("Caitlyn", 9, ["2517"])
    assert s_ranged["ability_haste"].total() == Fraction(5) + Fraction(65) * Fraction(10, 100)

    # Whispering Circlet (2526): 8% flat HSP + 0.5% of 300 bonus mana (1.5%) = 9.5% HSP
    s_wc = _sheet("Ahri", 9, ["2526"])
    assert s_wc["heal_and_shield_power"].total() == Fraction(95, 1000)

    # Warmog's Armor (3083): 1000 flat HP + 12% of 1000 = 1120 bonus HP
    s_wm = _sheet("Garen", 9, ["3083"])
    assert s_wm["health"].scoped("bonus") == Fraction(1120)


def test_bastionbreaker_zazzak_stormrazor_cull_and_helping_hand() -> None:
    # Bastionbreaker (2520): 18 lethality -> melee true dmg = 40 + 1.5*18 = 67; ranged = 33.5
    kit_g = load_kit(ROOT, "Garen")
    assert kit_g is not None
    r_bb = evaluate_rotation(
        kit_g,
        _sheet("Garen", 9, ["2520"]),
        {"Q": 5, "W": 1, "E": 1, "R": 1},
        _target(hp=2000, armor=100, mr=100),
        parse_steps("R"),
        CRIT_BASE,
        holder_range="melee",
    )
    bb_parts = [p for p in r_bb.steps[0].parts if "2520 shaped-charge" in p.source]
    assert len(bb_parts) == 1
    assert bb_parts[0].primary_damage == Fraction(67)

    # Zaz'Zak's Realmspike (3871): 10 + 15% AP (0) + 3% * 2000 = 70 magic damage
    kit_a = load_kit(ROOT, "Ahri")
    assert kit_a is not None
    r_zz = evaluate_rotation(
        kit_a,
        _sheet("Ahri", 9, ["3871"]),
        {"Q": 5, "W": 1, "E": 1, "R": 1},
        _target(hp=2000, armor=0, mr=0),
        parse_steps("E"),
        CRIT_BASE,
        holder_range="ranged",
    )
    zz_parts = [p for p in r_zz.steps[0].parts if "3871 void-explosion" in p.source]
    assert len(zz_parts) == 1
    assert zz_parts[0].primary_damage == Fraction(70)

    # Stormrazor (3095): 100 magic Energized damage
    r_sr = evaluate_rotation(
        kit_a,
        _sheet("Ahri", 9, ["3095"]),
        {"Q": 5, "W": 1, "E": 1, "R": 1},
        _target(hp=2000, armor=0, mr=0),
        parse_steps("attack"),
        CRIT_BASE,
        holder_range="ranged",
    )
    sr_parts = [p for p in r_sr.steps[0].parts if "3095 bolt" in p.source]
    assert len(sr_parts) == 1 and sr_parts[0].primary_damage == Fraction(100)

    # Cull (1083): heals 3 HP on-hit
    r_cull = evaluate_rotation(
        kit_a,
        _sheet("Ahri", 9, ["1083"]),
        {"Q": 5, "W": 1, "E": 1, "R": 1},
        _target(hp=2000, armor=0, mr=0),
        parse_steps("attack"),
        CRIT_BASE,
        holder_range="ranged",
    )
    assert r_cull.healing == Fraction(3)

    # Doran's Shield (1054): +5 physical on-hit vs minion, 0 vs champion
    r_m = evaluate_rotation(
        kit_a,
        _sheet("Ahri", 9, ["1054"]),
        {"Q": 5, "W": 1, "E": 1, "R": 1},
        _target(hp=500, armor=0, mr=0, kind="minion"),
        parse_steps("attack"),
        CRIT_BASE,
        holder_range="ranged",
    )
    assert any("1054 helping-hand" in p.source and p.raw == Fraction(5) for p in r_m.steps[0].parts)


@pytest.mark.parametrize(
    "item_id", ["3137", "3102", "3814", "3116", "6694", "3142", "4629", "3072", "6333"]
)
def test_curated_non_damage_utility_items_do_not_weaken_rotations(item_id: str) -> None:
    kit = load_kit(ROOT, "Caitlyn")
    assert kit is not None
    res = evaluate_rotation(
        kit,
        _sheet("Caitlyn", 9, [item_id]),
        {"Q": 5, "W": 1, "E": 1, "R": 1},
        _target(hp=2000),
        parse_steps("attack"),
        CRIT_BASE,
        holder_range="ranged",
    )
    assert res.label is not Label.PENDING


@pytest.mark.parametrize("item_id", ["4628", "2523", "3146", "3152", "6610", "1082", "3041"])
def test_excluded_combat_effect_items_honestly_weaken_rotations(item_id: str) -> None:
    kit = load_kit(ROOT, "Ahri")
    assert kit is not None
    res = evaluate_rotation(
        kit,
        _sheet("Ahri", 9, [item_id]),
        {"Q": 5, "W": 1, "E": 1, "R": 1},
        _target(hp=2000),
        parse_steps("E"),
        CRIT_BASE,
        holder_range="ranged",
    )
    assert res.label is Label.PENDING
