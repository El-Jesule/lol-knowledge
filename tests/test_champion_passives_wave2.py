"""Tests for Champion Passives Wave 2 (61 additional champions compiled from client 16.23)."""

from __future__ import annotations

import json
from fractions import Fraction as F
from pathlib import Path

from lol_knowledge.defense import evaluate_defense, parse_incoming
from lol_knowledge.kit import load_kit, passive_contributions
from lol_knowledge.passives import sheet_passive_effects
from lol_knowledge.rotation import evaluate_rotation, parse_steps
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
        allow_insufficient_resource=True,
    )


def test_wave2_passive_coverage_count():
    with_fx = [
        k.parent.name
        for k in sorted((ROOT / "lol-knowledge" / "champions").glob("*/kit.json"))
        if json.loads(k.read_text(encoding="utf-8"))["abilities"]["P"].get("passive_effects")
    ]
    assert len(with_fx) >= 123


def test_periodic_and_every_n_attack_passives():
    # Aatrox: Attack 1 procs Deathbringer Strike (10% max HP at lvl 18 = 200) + heals 200;
    # Attack 2 is on 10 s CD -> no proc!
    aa = _rotate("Aatrox", 18, "attack, attack")
    p1 = [p for p in aa.steps[0].parts if "deathbringer_strike" in p.source]
    assert len(p1) == 1 and p1[0].raw == F(200)
    assert aa.steps[0].heal_events
    assert not any("deathbringer_strike" in p.source for p in aa.steps[1].parts)

    # Caitlyn: 6th attack fires HeadshotBonusDamage
    cait = _rotate("Caitlyn", 18, ", ".join(["attack"] * 6))
    assert not any("headshot_proc" in p.source for p in cait.steps[4].parts)
    assert any("headshot_proc" in p.source for p in cait.steps[5].parts)

    # Master Yi: 4th attack fires Double Strike (50% AD)
    yi = _rotate("MasterYi", 11, "attack, attack, attack, attack")
    assert not any("double_strike" in p.source for p in yi.steps[2].parts)
    assert any("double_strike" in p.source for p in yi.steps[3].parts)

    # Sett: every 2nd attack fires RightPunchBonus
    sett = _rotate("Sett", 11, "attack, attack")
    assert not any("pit_grit_right_punch" in p.source for p in sett.steps[0].parts)
    assert any("pit_grit_right_punch" in p.source for p in sett.steps[1].parts)

    # Jarvan IV: attack 1 deals 8% of target current HP (1000 * 0.08 = 80)
    t1000 = target_from_values(
        F(0), F(0), max_health=F(2000), current_health=F(1000), kind="champion"
    )
    j4 = _rotate("JarvanIV", 11, "attack, attack", target=t1000)
    mc = [p for p in j4.steps[0].parts if "martial_cadence" in p.source]
    assert len(mc) == 1 and mc[0].raw == F(80)
    assert not any("martial_cadence" in p.source for p in j4.steps[1].parts)

    # Poppy: attack 1 deals Iron Ambassador magic damage AND grants ShieldValue shield
    poppy = _rotate("Poppy", 18, "attack")
    assert any("iron_ambassador_damage" in p.source for p in poppy.steps[0].parts)
    assert any("iron_ambassador_shield" in s.source for s in poppy.steps[0].shield_events)

    # Gangplank: attack 1 deals Trial by Fire true damage
    gp = _rotate("Gangplank", 18, "attack")
    tbf = [p for p in gp.steps[0].parts if "trial_by_fire" in p.source]
    assert len(tbf) == 1 and tbf[0].damage_type.value == "true" and tbf[0].raw == F(250)


def test_kaisa_brand_hwei_mordekaiser_qiyana_and_after_ability_passives():
    # Kai'Sa: on-hit PBaseDamage on every attack + 5th hit pops Plasma (% missing HP)
    kaisa = _rotate("Kaisa", 11, "attack, attack, attack, attack, attack")
    assert any("second_skin_on_hit" in p.source for p in kaisa.steps[0].parts)
    assert not any("second_skin_plasma_pop" in p.source for p in kaisa.steps[3].parts)
    assert any("second_skin_plasma_pop" in p.source for p in kaisa.steps[4].parts)

    # Brand: every ability hit applies 2% max HP burn, 3rd ability hit detonates ExplosionDamage!
    brand = _rotate("Brand", 18, "Q, W.ablaze, E", ranks={"Q": 5, "W": 5, "E": 5})
    assert any("blaze_burn" in p.source for p in brand.steps[0].parts)
    assert not any("blaze_explosion" in p.source for p in brand.steps[1].parts)
    assert any("blaze_explosion" in p.source for p in brand.steps[2].parts)

    # Hwei: 2nd ability hit against champion detonates Signature of the Visionary
    hwei = _rotate("Hwei", 11, "Q.qq, E.ee", ranks={"Q": 5, "E": 5})
    assert not any("signature_of_the_visionary" in p.source for p in hwei.steps[0].parts)
    assert any("signature_of_the_visionary" in p.source for p in hwei.steps[1].parts)

    # Qiyana: on_any_hit triggers on first damaging ability OR attack
    qi = _rotate("Qiyana", 11, "E, attack", ranks={"E": 5})
    assert any("royal_privilege" in p.source for p in qi.steps[0].parts)
    assert not any("royal_privilege" in p.source for p in qi.steps[1].parts)

    # Mordekaiser: on-hit 40% AP + 3 champion hits activate PassiveMovementSpeed!
    morde = _rotate("Mordekaiser", 11, "attack, attack, attack", item_ids=("1058",))
    on_hit = [p for p in morde.steps[0].parts if "darkness_rise_on_hit" in p.source]
    assert len(on_hit) == 1 and on_hit[0].raw == F(26)  # 40% of 65 AP

    # Ambessa (after_ability + energy), Lucian (after_ability), Lux (after_ability), Taric
    amb = _rotate("Ambessa", 11, "Q.sweep_edge, attack", ranks={"Q": 5})
    assert any("drakehounds_step_damage" in p.source for p in amb.steps[1].parts)
    assert any("drakehounds_step_energy" in r.source for r in amb.steps[1].resource_events)

    luc = _rotate("Lucian", 18, "Q, attack", ranks={"Q": 5})
    assert any("lightslinger_second_shot" in p.source for p in luc.steps[1].parts)

    lux = _rotate("Lux", 11, "Q, attack", ranks={"Q": 5})
    assert any("illumination_proc" in p.source for p in lux.steps[1].parts)

    taric = _rotate("Taric", 11, "E, attack, attack, attack", ranks={"E": 5})
    assert any("bravado" in p.source for p in taric.steps[1].parts)
    assert not any("bravado" in p.source for p in taric.steps[2].parts)


def test_malzahar_dr_kennen_energy_heals_stats_and_ms_passives():
    # Malzahar: Void Shift reduces 1st incoming hit by 90% in survive, then goes on CD!
    m_sheet = _sheet("Malzahar", 11)
    m_kit = load_kit(ROOT, "Malzahar")
    hits = parse_incoming("magic:500, magic:500")
    m_plain = evaluate_defense(m_sheet, hits, timeline=True)
    m_vs = evaluate_defense(m_sheet, hits, timeline=True, kit=m_kit)
    assert m_vs.steps[0].damage_after_flat == m_plain.steps[0].damage_after_flat * F(1, 10)
    assert m_vs.steps[1].damage_after_flat == m_plain.steps[1].damage_after_flat

    # Kennen: 3rd ability hit restores 25 energy!
    ken = _rotate("Kennen", 11, "Q, W.active, E", ranks={"Q": 5, "W": 5, "E": 5})
    assert not any("mark_of_the_storm_energy" in r.source for r in ken.steps[1].resource_events)
    assert any("mark_of_the_storm_energy" in r.source for r in ken.steps[2].resource_events)

    # Zac: ability hit heals 4%..8% max HP (level 18 -> 8%)
    zac = _rotate("Zac", 18, "W", ranks={"W": 5})
    z_sheet = _sheet("Zac", 18)
    assert zac.healing == z_sheet["health"].total() * F(8, 100)

    # Morgana (+18% omnivamp), Neeko (+20% magic pen), Nilah (permanent +7.5% HSP),
    # Kled (Skaarl +1400 HP at lvl 18), Varus (+30% AS), Rumble (+100% AS at lvl 18)
    assert _sheet("Morgana", 11, inputs={"morgana_soul_siphon": F(1)})["omnivamp"].total() == F(
        18, 100
    )
    assert _sheet("Neeko", 11, inputs={"neeko_disguised": F(1)})[
        "magic_penetration_percent"
    ].total() == F(20, 100)
    assert _sheet("Nilah", 11)["heal_and_shield_power"].total() == F(75, 1000)
    k0 = _sheet("Kled", 18)
    k1 = _sheet("Kled", 18, inputs={"skaarl_mounted": F(1)})
    assert k1["health"].total() - k0["health"].total() == F(1400)
    v0 = _sheet("Varus", 11)
    v1 = _sheet("Varus", 11, inputs={"varus_champion_takedown": F(1)})
    assert v1["attack_speed_bonus"].total() - v0["attack_speed_bonus"].total() == F(30, 100)

    # Conditional Move-Speed passives (Samira 6 style stacks, Soraka +90% MS, Jayce +30 flat MS)
    sam0 = _sheet("Samira", 18)
    sam6 = _sheet("Samira", 18, inputs={"samira_style_grade": F(6)})
    assert sam6["move_speed"].total() > sam0["move_speed"].total()
    sor0 = _sheet("Soraka", 11)
    sor1 = _sheet("Soraka", 11, inputs={"soraka_salvation": F(1)})
    assert sor1["move_speed"].total() > sor0["move_speed"].total()
    jay0 = _sheet("Jayce", 11)
    jay1 = _sheet("Jayce", 11, inputs={"jayce_transform": F(1)})
    assert jay1["move_speed"].total() > jay0["move_speed"].total()
