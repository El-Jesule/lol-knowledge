"""Comprehensive validation and spot-check tests for all published champion kits (CH-01)."""

from __future__ import annotations

from fractions import Fraction as F
from pathlib import Path

import pytest

from lol_knowledge.kit import ability_damage, load_kit, passive_contributions
from lol_knowledge.objects import load_catalog
from lol_knowledge.passives import sheet_passive_effects
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

ROOT = Path(__file__).resolve().parents[1]
CHAMPIONS_DIR = ROOT / "lol-knowledge" / "champions"
ISSUES = load_issues(ROOT)
RECORDS = load_records(ROOT)
CATALOG = load_catalog(ROOT)


def _published_kit_ids() -> list[str]:
    return sorted(path.parent.name for path in CHAMPIONS_DIR.glob("*/kit.json"))


def _sheet(
    champion_id: str,
    level: int,
    item_ids: tuple[str, ...] = (),
    *,
    learned: dict[str, int] | None = None,
    inputs: dict[str, F] | None = None,
    include_stacking: bool = True,
):
    champ = load_champion(ROOT, champion_id)
    loaded = load_items(ROOT, list(item_ids)) if item_ids else ()
    kit = load_kit(ROOT, champion_id)
    extras = list(passive_contributions(kit, learned or {})) if kit is not None else []
    passive_fx = sheet_passive_effects(kit, level, inputs, include_stacking=include_stacking)
    extras.extend(passive_fx.flats)
    return build_stat_sheet(
        champ,
        level,
        loaded,
        issues=ISSUES,
        derived=RECORDS,
        extras=extras,
        extra_amplifiers=passive_fx.amplifiers,
    )


def _target(
    *,
    armor: F = F(0),
    mr: F = F(0),
    max_health: F = F(2000),
    current_health: F = F(1000),
    kind: str = "champion",
) -> Target:
    return Target(
        armor=armor,
        magic_resist=mr,
        stats={"max_health": max_health, "current_health": current_health},
        label=Label.OFFICIAL,
        description="dummy",
        kind=kind,
    )


def test_published_kits_count_reaches_wave_3_target():
    ids = _published_kit_ids()
    assert len(ids) >= 129
    for expected in (
        "Ahri",
        "Zaahen",
        "Jax",
        "Darius",
        "Malphite",
        "Pantheon",
        "Annie",
        "Lux",
        "Veigar",
        "Syndra",
        "Ezreal",
        "Garen",
        "Brand",
        "Vayne",
        "Leona",
        "Nautilus",
        "Vladimir",
        "KogMaw",
        "Lillia",
        "Vex",
        "Gwen",
        "LeeSin",
        "Akali",
        "Caitlyn",
        "TahmKench",
        "Aatrox",
        "Fiora",
        "DrMundo",
        "KSante",
        "Nasus",
        "Briar",
        "Shyvana",
        "Viego",
        "JarvanIV",
        "Mel",
        "Hwei",
        "Naafiri",
        "Twitch",
        "Thresh",
        "Renata",
    ):
        assert expected in ids


@pytest.mark.parametrize("champion_id", _published_kit_ids())
def test_every_published_kit_evaluates_all_cases_and_timeline_rotation(champion_id: str):
    kit = load_kit(ROOT, champion_id)
    assert kit is not None
    learned = {
        slot: ability.max_rank
        for slot, ability in kit.abilities.items()
        if slot in ("Q", "W", "E", "R")
    }
    # Give non-zero AD, AP, bonus HP and bonus Armor so every stat scaling evaluates cleanly.
    items = ("1058", "1037", "1028", "1031")
    target_stats = {
        "max_health": F(2000),
        "current_health": F(1000),
        "missing_fraction_health": F(1, 2),
    }

    for level in (11, 18):
        sheet = _sheet(champion_id, level, items, learned=learned)
        for slot, ability in kit.abilities.items():
            if not ability.cases:
                continue
            parts = ability_damage(
                kit,
                slot,
                ability.max_rank,
                sheet,
                target=target_stats,
            )
            assert parts, f"{champion_id} {slot} returned no parts"
            for part in parts:
                assert part.raw > 0, (
                    f"{champion_id} {slot}.{part.case}[{part.index}] raw={part.raw} <= 0"
                )

    # Also verify a real --timeline rotation using the first non-recast case of each active slot.
    sheet18 = _sheet(champion_id, 18, items, learned=learned, include_stacking=False)
    step_tokens: list[str] = ["attack"]
    for slot in ("Q", "W", "E", "R"):
        ability = kit.abilities.get(slot)
        if ability is None:
            continue
        non_recast = [case for case in ability.cases if not case.recast]
        if non_recast:
            step_tokens.append(f"{slot}.{non_recast[0].id}")
    # Kits with one active damage spell (e.g. Twitch: E + passive P) yield 2 steps.
    assert len(step_tokens) >= 2
    out = evaluate_rotation(
        kit,
        sheet18,
        learned,
        _target(armor=F(80), mr=F(60), max_health=F(2000), current_health=F(1000)),
        parse_steps(", ".join(step_tokens)),
        CATALOG,
        timeline=True,
        allow_insufficient_resource=True,
    )
    assert out.total > 0
    assert len(out.steps) == len(step_tokens)


def test_jax_ap_burst_rotation_with_rabadon_and_lich_bane():
    kit = load_kit(ROOT, "Jax")
    assert kit is not None
    # Roadmap showcase: AP-burst Jax at level 18 with Rabadon (3089) + Lich Bane (3100)
    learned = {"Q": 5, "W": 5, "E": 5, "R": 3}
    sheet = _sheet("Jax", 18, ("3089", "3100"), learned=learned)
    ap = sheet["ability_power"].total()
    # 130 (Rabadon) + 100 (Lich Bane) = 230, x 1.30 (Rabadon amp) = 299 AP
    assert ap == F(299)

    e_min = ability_damage(kit, "E", 5, sheet, case="min", target={"max_health": F(2000)})
    # 160 + 0.7 * 299 = 369.3 magic + 4% * 2000 = 80 magic
    assert sum(part.raw for part in e_min) == F(160) + F(7, 10) * ap + F(80)

    r_active = ability_damage(kit, "R", 3, sheet, case="active")
    # 250 + 1.0 * 299 = 549 magic
    assert r_active[0].raw == F(250) + ap

    rot = evaluate_rotation(
        kit,
        sheet,
        learned,
        _target(armor=F(0), mr=F(0), max_health=F(2000), current_health=F(2000)),
        parse_steps("Q.leap, W.empower, attack, E.min, R.active"),
        CATALOG,
    )
    assert rot.total > F(1800)


def test_passive_stats_on_annie_darius_pantheon_and_nocturne():
    annie_sheet = _sheet("Annie", 16, learned={"R": 3})
    assert annie_sheet["magic_penetration_percent"].total() == F(1, 5)

    darius_sheet = _sheet("Darius", 18, learned={"E": 5})
    assert darius_sheet["armor_penetration_percent"].total() == F(2, 5)

    pantheon_sheet = _sheet("Pantheon", 16, learned={"R": 3})
    assert pantheon_sheet["armor_penetration_percent"].total() == F(3, 10)

    nocturne_base = _sheet("Nocturne", 18)
    nocturne_w5 = _sheet("Nocturne", 18, learned={"W": 5})
    assert nocturne_w5["attack_speed_bonus"].total() - nocturne_base[
        "attack_speed_bonus"
    ].total() == F(1, 2)


def test_veigar_phenomenal_evil_stacks_apply_in_stats_and_ability():
    kit = load_kit(ROOT, "Veigar")
    assert kit is not None
    sheet0 = _sheet("Veigar", 18, inputs={"phenomenal_evil_stacks": F(0)})
    sheet200 = _sheet("Veigar", 18, inputs={"phenomenal_evil_stacks": F(200)})
    assert sheet0["ability_power"].total() == F(0)
    assert sheet200["ability_power"].total() == F(200)

    r_max_0 = ability_damage(kit, "R", 3, sheet0, case="max")[0].raw
    r_max_200 = ability_damage(kit, "R", 3, sheet200, case="max")[0].raw
    assert r_max_200 > r_max_0


def test_true_damage_and_percent_hp_spot_checks_darius_garen_vayne_syndra():
    # Darius R: rank 3 base = 375 + 0.75 * bonus_ad; max_stacks = 2x base
    darius_kit = load_kit(ROOT, "Darius")
    assert darius_kit is not None
    darius_sheet = _sheet("Darius", 18, ("1038",))  # B.F. Sword = +40 bonus AD
    r_base = ability_damage(darius_kit, "R", 3, darius_sheet, case="base")[0].raw
    r_max = ability_damage(darius_kit, "R", 3, darius_sheet, case="max_stacks")[0].raw
    assert r_base == F(375) + F(3, 4) * F(40)
    assert r_max == r_base * 2

    # Garen R: rank 3 = 275 + 35% of missing health (50% of 2000 = 1000 -> 625 true)
    garen_kit = load_kit(ROOT, "Garen")
    assert garen_kit is not None
    garen_sheet = _sheet("Garen", 18)
    garen_r = ability_damage(
        garen_kit,
        "R",
        3,
        garen_sheet,
        case="execute",
        target={"max_health": F(2000), "missing_fraction_health": F(1, 2)},
    )[0]
    assert garen_r.damage_type == "true"
    assert garen_r.raw == F(625)

    # Vayne W: rank 5 = 10% of 2000 max HP = 200 true damage
    vayne_kit = load_kit(ROOT, "Vayne")
    assert vayne_kit is not None
    vayne_w = ability_damage(
        vayne_kit, "W", 5, _sheet("Vayne", 18), case="proc", target={"max_health": F(2000)}
    )[0]
    assert vayne_w.damage_type == "true"
    assert vayne_w.raw == F(200)

    # Syndra W evolved has both magic and true damage parts
    syndra_kit = load_kit(ROOT, "Syndra")
    assert syndra_kit is not None
    syndra_w = ability_damage(syndra_kit, "W", 5, _sheet("Syndra", 18, ("1058",)), case="evolved")
    assert [part.damage_type for part in syndra_w] == ["magic", "true"]
    assert all(part.raw > 0 for part in syndra_w)


def test_wave_2_spot_checks_vladimir_kogmaw_lillia_vex_fiddlesticks_nunu_kayle():
    # Vladimir E has an 8% max-health cost applied in rotation (MEC-01)
    vlad_kit = load_kit(ROOT, "Vladimir")
    assert vlad_kit is not None
    vlad_sheet = _sheet("Vladimir", 18, ("1058",))
    vlad_hp = vlad_sheet["health"].total()
    vlad_rot = evaluate_rotation(
        vlad_kit,
        vlad_sheet,
        {"E": 5},
        _target(mr=F(0), max_health=F(2000), current_health=F(2000)),
        parse_steps("E.max"),
        CATALOG,
        inputs={"attacker_health_percent": F(1)},
    )
    assert vlad_rot.steps[0].resource_cost is not None
    assert vlad_rot.steps[0].resource_cost.resource == "health"
    assert vlad_rot.steps[0].resource_cost.amount == vlad_hp * F(2, 25)  # 8% max HP

    # KogMaw Q passive grants +25% attack_speed_bonus at rank 5; W deals 6% + 1.5%/100 AP max HP
    kog_base = _sheet("KogMaw", 18)
    kog_q5 = _sheet("KogMaw", 18, learned={"Q": 5})
    assert kog_q5["attack_speed_bonus"].total() - kog_base["attack_speed_bonus"].total() == F(1, 4)
    kog_kit = load_kit(ROOT, "KogMaw")
    assert kog_kit is not None
    kog_w = ability_damage(
        kog_kit, "W", 5, kog_base, case="on_hit", target={"max_health": F(2000)}
    )[0]
    assert kog_w.damage_type == "magic"
    assert kog_w.raw == F(120)  # 6% of 2000

    # Lillia Q outer edge deals both magic and true damage
    lillia_kit = load_kit(ROOT, "Lillia")
    assert lillia_kit is not None
    lillia_q = ability_damage(lillia_kit, "Q", 5, _sheet("Lillia", 18, ("1058",)), case="outer")
    assert [part.damage_type for part in lillia_q] == ["magic", "true"]

    # Vex R has R1 + R2 recast compiled via colon-scoped tooltip placeholders
    vex_kit = load_kit(ROOT, "Vex")
    assert vex_kit is not None
    assert [c.id for c in vex_kit.ability("R").cases] == ["bolt", "recast"]
    assert vex_kit.ability("R").case("recast").recast is True

    # Fiddlesticks Q scales with target current_health and doubles when feared
    fiddle_kit = load_kit(ROOT, "Fiddlesticks")
    assert fiddle_kit is not None
    fiddle_sheet = _sheet("Fiddlesticks", 18)
    f_norm = ability_damage(
        fiddle_kit, "Q", 5, fiddle_sheet, case="normal", target={"current_health": F(1000)}
    )[0]
    f_fear = ability_damage(
        fiddle_kit, "Q", 5, fiddle_sheet, case="feared", target={"current_health": F(1000)}
    )[0]
    assert f_norm.raw == F(60)  # 6% of 1000 current HP
    assert f_fear.raw == F(120)  # 12% of 1000 current HP

    # Nunu Q deals 1200 true damage to minions/monsters at rank 5
    nunu_kit = load_kit(ROOT, "Nunu")
    assert nunu_kit is not None
    nunu_q = ability_damage(nunu_kit, "Q", 5, _sheet("Nunu", 18), case="minion_monster")[0]
    assert nunu_q.damage_type == "true"
    assert nunu_q.raw == F(1200)

    # Kayle E active execute includes missing-health magic damage
    kayle_kit = load_kit(ROOT, "Kayle")
    assert kayle_kit is not None
    kayle_e = ability_damage(
        kayle_kit,
        "E",
        5,
        _sheet("Kayle", 18),
        case="active_execute",
        target={"max_health": F(2000), "missing_fraction_health": F(1, 2)},
    )
    assert len(kayle_e) == 2
    assert kayle_e[1].raw == F(100)  # 10% of 1000 missing HP at 0 AP


def test_wave_3_spot_checks_fiora_drmundo_nasus_jarvaniv_thresh_shyvana_viego_twitch_hwei_renata():
    # Fiora P deals 3% + 4%/100 bonus AD max HP true damage; 4 vitals = 4x
    fiora_kit = load_kit(ROOT, "Fiora")
    assert fiora_kit is not None
    fiora_sheet = _sheet("Fiora", 18, ("1038",))  # B.F. Sword = +40 bonus AD -> 4.6% max HP
    vital = ability_damage(
        fiora_kit, "P", 1, fiora_sheet, case="vital", target={"max_health": F(2000)}
    )[0]
    four_vitals = ability_damage(
        fiora_kit, "P", 1, fiora_sheet, case="r_four_vitals", target={"max_health": F(2000)}
    )[0]
    assert vital.damage_type == "true"
    assert vital.raw == F(92)  # (0.03 + 0.0004 * 40) * 2000 = 0.046 * 2000 = 92
    assert four_vitals.damage_type == "true"
    assert four_vitals.raw == vital.raw * 4

    # DrMundo Q & E declare flat health costs; Q deals 30% target current HP magic at rank 5
    mundo_kit = load_kit(ROOT, "DrMundo")
    assert mundo_kit is not None
    mundo_sheet = _sheet("DrMundo", 18)
    mundo_rot = evaluate_rotation(
        mundo_kit,
        mundo_sheet,
        {"Q": 5, "E": 5},
        _target(mr=F(0), max_health=F(2000), current_health=F(1000)),
        parse_steps("Q.cleaver, E.hit"),
        CATALOG,
    )
    assert mundo_rot.steps[0].resource_cost is not None
    assert mundo_rot.steps[0].resource_cost.resource == "health"
    assert mundo_rot.steps[0].resource_cost.amount == F(90)
    assert mundo_rot.steps[0].parts[0].raw == F(300)  # 30% of 1000 current HP
    assert mundo_rot.steps[1].resource_cost is not None
    assert mundo_rot.steps[1].resource_cost.resource == "health"
    assert mundo_rot.steps[1].resource_cost.amount == F(70)

    # Nasus P grants 10/15/20% passive life steal at levels 1/7/13; R aura deals 5% max HP/s at 0 AP
    assert _sheet("Nasus", 1)["life_steal"].total() == F(1, 10)
    assert _sheet("Nasus", 7)["life_steal"].total() == F(3, 20)
    assert _sheet("Nasus", 13)["life_steal"].total() == F(1, 5)
    nasus_kit = load_kit(ROOT, "Nasus")
    assert nasus_kit is not None
    nasus_r = ability_damage(
        nasus_kit, "R", 3, _sheet("Nasus", 18), case="aura_dps", target={"max_health": F(2000)}
    )[0]
    assert nasus_r.damage_type == "magic"
    assert nasus_r.raw == F(100)  # 5% of 2000

    # JarvanIV E grants +30% passive attack speed at rank 5; P deals 8% current HP physical
    j4_base = _sheet("JarvanIV", 18)
    j4_e5 = _sheet("JarvanIV", 18, learned={"E": 5})
    assert j4_e5["attack_speed_bonus"].total() - j4_base["attack_speed_bonus"].total() == F(3, 10)
    j4_kit = load_kit(ROOT, "JarvanIV")
    assert j4_kit is not None
    j4_p = ability_damage(
        j4_kit, "P", 1, j4_base, case="strike", target={"current_health": F(1000)}
    )[0]
    assert j4_p.damage_type == "physical"
    assert j4_p.raw == F(80)

    # Thresh P grants +1 armor and +1 AP per soul (--input souls)
    thresh0 = _sheet("Thresh", 18, inputs={"souls": F(0)})
    thresh50 = _sheet("Thresh", 18, inputs={"souls": F(50)})
    assert thresh50["armor"].total() - thresh0["armor"].total() == F(50)
    assert thresh50["ability_power"].total() - thresh0["ability_power"].total() == F(50)

    # Shyvana P grants +0.3 armor and +0.3 MR per stack (--input passive_stacks)
    shyv0 = _sheet("Shyvana", 18, inputs={"passive_stacks": F(0)})
    shyv10 = _sheet("Shyvana", 18, inputs={"passive_stacks": F(10)})
    assert shyv10["armor"].total() - shyv0["armor"].total() == F(3)
    assert shyv10["magic_resist"].total() - shyv0["magic_resist"].total() == F(3)

    # Viego R combines flat physical AD + % missing health physical
    viego_kit = load_kit(ROOT, "Viego")
    assert viego_kit is not None
    viego_r = ability_damage(
        viego_kit,
        "R",
        3,
        _sheet("Viego", 18),
        case="strike",
        target={"max_health": F(2000), "missing_fraction_health": F(1, 2)},
    )
    assert [p.damage_type for p in viego_r] == ["physical", "physical"]
    assert viego_r[1].raw == F(200)  # 20% of 1000 missing HP at 0 bonus AD

    # Twitch E max_stacks deals both physical and magic damage
    twitch_kit = load_kit(ROOT, "Twitch")
    assert twitch_kit is not None
    twitch_e = ability_damage(
        twitch_kit, "E", 5, _sheet("Twitch", 18, ("1058", "1038")), case="max_stacks"
    )
    assert [p.damage_type for p in twitch_e] == ["physical", "magic"]
    assert all(p.raw > 0 for p in twitch_e)

    # Hwei Q QQ deals flat magic + 7% target max HP magic at rank 5
    hwei_kit = load_kit(ROOT, "Hwei")
    assert hwei_kit is not None
    hwei_qq = ability_damage(
        hwei_kit, "Q", 5, _sheet("Hwei", 18), case="qq", target={"max_health": F(2000)}
    )
    assert [p.damage_type for p in hwei_qq] == ["magic", "magic"]
    assert hwei_qq[1].raw == F(140)  # 7% of 2000

    # Renata P applies % max HP magic damage
    renata_kit = load_kit(ROOT, "Renata")
    assert renata_kit is not None
    renata_p = ability_damage(
        renata_kit, "P", 1, _sheet("Renata", 18), case="mark_apply", target={"max_health": F(2000)}
    )[0]
    assert renata_p.damage_type == "magic"
    assert renata_p.raw > F(40)
