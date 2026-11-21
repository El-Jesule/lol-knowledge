"""Defensive item passives in defense.py/survive and time_to_die optimization (catalog v27)."""

from __future__ import annotations

from fractions import Fraction as F
from pathlib import Path

from lol_knowledge.damage import DamageType, mitigate
from lol_knowledge.defense import evaluate_defense, parse_incoming
from lol_knowledge.optimizer import OptimizeConstraints, optimize_build
from lol_knowledge.stats import (
    Label,
    build_stat_sheet,
    load_champion,
    load_issues,
    load_items,
    load_records,
)

ROOT = Path(__file__).resolve().parents[1]


def _sheet(champ_id: str, level: int, item_ids: tuple[str, ...] = ()):
    champ = load_champion(ROOT, champ_id)
    items = load_items(ROOT, item_ids)
    issues = load_issues(ROOT)
    derived = load_records(ROOT)
    return build_stat_sheet(champ, level, items, issues, derived=derived)


# --- 1. 3082 Warden's Mail (Rock Solid: -15 flat on attacks, capped at 20%) ---


def test_wardens_mail_rock_solid_reduces_attacks_and_respects_20_percent_cap():
    sheet = _sheet("Garen", 11, ("3082",))
    armor = sheet["armor"].total()
    # Large attack (500 raw -> post-mitigation > 75): full -15 flat reduction
    big_post = mitigate(F(500), DamageType.PHYSICAL, armor).damage
    assert big_post > F(75)
    res_big = evaluate_defense(sheet, parse_incoming("attack:500"))
    assert res_big.steps[0].flat_reduced == F(15)
    assert res_big.steps[0].damage_after_flat == big_post - F(15)
    assert res_big.label is Label.DERIVED

    # Small attack (50 raw -> post-mitigation < 75): capped at 20% of post-mitigation damage!
    small_post = mitigate(F(50), DamageType.PHYSICAL, armor).damage
    assert small_post * F(20, 100) < F(15)
    res_small = evaluate_defense(sheet, parse_incoming("attack:50"))
    assert res_small.steps[0].flat_reduced == small_post * F(20, 100)

    # Non-attack physical hit (ability) is NOT reduced by Rock Solid
    res_ab = evaluate_defense(sheet, parse_incoming("ability:physical:500"))
    assert res_ab.steps[0].flat_reduced == F(0)


# --- 2. 6665 Jak'Sho, The Protean (+30% bonus armor & MR after 5 s in combat) ---


def test_jaksho_activates_30_percent_bonus_resists_after_5s_in_timeline():
    sheet = _sheet("Garen", 18, ("6665",))
    base_armor = sheet["armor"].total()
    bonus_armor = sheet["armor"].scoped("bonus")
    base_mr = sheet["magic_resist"].total()
    bonus_mr = sheet["magic_resist"].scoped("bonus")
    assert bonus_armor > 0 and bonus_mr > 0

    # Hit 1 at t=0 (inactive), hit 2 at t=4 (inactive), hit 3 at t=5 (ACTIVE)
    hits = parse_incoming("physical:500 wait:4 physical:500 wait:1 physical:500 magic:500")
    res = evaluate_defense(sheet, hits, timeline=True)
    h1, _, h2, _, h3, h4 = res.steps
    assert h1.incoming == mitigate(F(500), DamageType.PHYSICAL, base_armor).damage
    assert h2.incoming == mitigate(F(500), DamageType.PHYSICAL, base_armor).damage
    boosted_armor = base_armor + bonus_armor * F(30, 100)
    boosted_mr = base_mr + bonus_mr * F(30, 100)
    assert h3.incoming == mitigate(F(500), DamageType.PHYSICAL, boosted_armor).damage
    assert h4.incoming == mitigate(F(500), DamageType.MAGIC, boosted_mr).damage
    assert res.label is Label.DERIVED

    # Without --timeline, Jak'Sho honestly weakens the simulation to Pending
    no_tl = evaluate_defense(sheet, parse_incoming("physical:500"), timeline=False)
    assert no_tl.label is Label.PENDING


# --- 3. 4401 Force of Nature (Steadfast: +70 MR after 8 magic hits, 7 s window) ---


def test_force_of_nature_grants_70_mr_after_8_magic_hits_and_stacks_with_jaksho():
    sheet = _sheet("Garen", 18, ("4401",))
    base_mr = sheet["magic_resist"].total()
    # 9 magic hits in a row: hits 1..8 use base_mr; hit 9 uses base_mr + 70!
    hits = parse_incoming(" ".join(["magic:100"] * 9))
    res = evaluate_defense(sheet, hits, timeline=True)
    assert res.steps[7].incoming == mitigate(F(100), DamageType.MAGIC, base_mr).damage
    assert res.steps[8].incoming == mitigate(F(100), DamageType.MAGIC, base_mr + F(70)).damage
    assert res.label is Label.DERIVED

    # Combined 4401 + 6665: after 5 s AND 8 magic hits, Jak'Sho amplifies FoN's +70 bonus MR too!
    combo = _sheet("Garen", 18, ("4401", "6665"))
    c_mr = combo["magic_resist"].total()
    c_bonus_mr = combo["magic_resist"].scoped("bonus")
    combo_hits = parse_incoming(" ".join(["magic:50"] * 8) + " wait:5 magic:500")
    res_combo = evaluate_defense(combo, combo_hits, timeline=True)
    expected_mr = c_mr + F(70) + (c_bonus_mr + F(70)) * F(30, 100)
    assert res_combo.steps[-1].incoming == mitigate(F(500), DamageType.MAGIC, expected_mr).damage


# --- 4. 2525 Protoplasm Harness (Lifeline: +100..300 temp max HP + 5 s HoT) ---


def test_protoplasm_harness_lifeline_grants_temp_max_hp_and_5s_regen():
    # Garen L18 with 2525 + 3082 (+40 bonus armor) + 3065 (+50 bonus MR, +25% self-healing!)
    sheet = _sheet("Garen", 18, ("2525", "3082", "3065"))
    max_hp = sheet["health"].total()
    bonus_armor = sheet["armor"].scoped("bonus")
    bonus_mr = sheet["magic_resist"].scoped("bonus")
    # Hit takes Garen below 30% HP (e.g. true:max_hp * 0.8 -> would leave 20% < 30%)
    hit_amt = int(max_hp * F(8, 10))
    res = evaluate_defense(sheet, parse_incoming(f"true:{hit_amt}"), timeline=True)
    # Level 18: +300 temp max HP immediately prevents dying and adds +300 HP;
    # Over 5 s tail: heals (400 + 1.75*bonus_armor + 1.75*bonus_mr) * 1.25 (Spirit Visage)!
    raw_heal = F(400) + bonus_armor * F(175, 100) + bonus_mr * F(175, 100)
    assert res.survived
    assert res.total_healing > 0
    # After 5 s tail, temporary +300 max HP expires cleanly (health <= base max_hp)
    assert res.remaining_health <= max_hp
    # Verify exact raw heal recorded on the Protoplasm HealEvent
    proto_heals = [h for s in res.steps for h in s.heals if "2525 lifeline" in h.source]
    assert proto_heals and proto_heals[0].raw == raw_heal
    assert res.label is Label.DERIVED


# --- 5. 6333 Death's Dance (Ignore Pain: 30%/10% stagger as 3 s true bleed) ---


def test_deaths_dance_defers_30_percent_melee_and_computes_exact_bleed_time_to_die():
    # Melee champion (Garen) with 6333: defers 30% of physical/magic into 3 s true bleed
    sheet = _sheet("Garen", 18, ("6333",))
    max_hp = sheet["health"].total()
    armor = sheet["armor"].total()
    # Pick raw physical hit whose post-mitigation damage is exactly max_hp * 1.1:
    # Instant damage = 70% of (1.1 * max_hp) = 0.77 * max_hp -> leaves 0.23 * max_hp at t=0!
    # Deferred bleed = 30% of (1.1 * max_hp) = 0.33 * max_hp over 3 s (= 0.11 * max_hp / s)
    # Exact lethal bleed time: t_die = (0.23 * max_hp) / (0.11 * max_hp) = 23/11 s!
    post_target = max_hp * F(11, 10)
    raw_hit = post_target * (100 + armor) / 100
    res = evaluate_defense(sheet, parse_incoming(f"physical:{float(raw_hit):.12f}"), timeline=True)
    assert not res.survived
    assert res.steps[0].health_after > 0  # Survived the initial burst at t=0!
    assert res.time_to_die is not None
    assert abs(float(res.time_to_die) - (23 / 11)) < 1e-6
    assert res.label is Label.DERIVED

    # True damage is NOT staggered by Death's Dance
    true_res = evaluate_defense(sheet, parse_incoming("true:500"), timeline=True)
    assert true_res.steps[0].damage_after_flat == F(500)
    assert len(true_res.steps) == 1

    # Ranged champion (Ahri) defers 10% instead of 30%
    ranged = _sheet("Ahri", 18, ("6333",))
    r_armor = ranged["armor"].total()
    post_r = mitigate(F(500), DamageType.PHYSICAL, r_armor).damage
    res_r = evaluate_defense(ranged, parse_incoming("physical:500"), timeline=True)
    assert res_r.steps[0].damage_after_flat == post_r * F(90, 100)
    assert res_r.total_damage_taken == post_r  # Instant 90% + 3 s bleed 10% == 100%!


# --- 6. 3869 Celestial Opposition (-35%/-25% physical & magic DR for 2 s, 18 s CD) ---


def test_celestial_opposition_reduces_physical_and_magic_for_2s_with_18s_cooldown():
    sheet = _sheet("Garen", 18, ("3869",))
    armor = sheet["armor"].total()
    base_post = mitigate(F(500), DamageType.PHYSICAL, armor).damage
    # Hit 1 at t=0 (-35%), Hit 2 at t=1.5 (-35%), Hit 3 at t=2.5 (expired!)
    # wait 16 s -> Hit 4 at t=18.5 (off 18 s CD -> -35% again!)
    hits = parse_incoming(
        "physical:500 wait:1.5 physical:500 wait:1 physical:500 wait:16 physical:500 true:200"
    )
    res = evaluate_defense(sheet, hits, timeline=True)
    h1, _, h2, _, h3, _, h4, h_true = res.steps
    assert h1.incoming == base_post * F(65, 100)
    assert h2.incoming == base_post * F(65, 100)
    assert h3.incoming == base_post
    assert h4.incoming == base_post * F(65, 100)
    # True damage is NOT reduced by Celestial Opposition
    assert h_true.incoming == F(200)
    assert res.label is Label.DERIVED


# --- 7. Spell Shields (3102 Banshee's, 3814 Edge of Night, 4632 Verdant Barrier) ---


def test_spell_shields_block_first_ability_and_respect_cooldown():
    # 3102 Banshee's Veil (40 s CD): blocks first ability, ignores attacks, blocks again at t=40 s
    sheet = _sheet("Ahri", 18, ("3102",))
    hits = parse_incoming(
        "attack:200 ability:magic:600 ability:magic:600 wait:40 ability:magic:600"
    )
    res = evaluate_defense(sheet, hits, timeline=True)
    atk, ab1, ab2, _, ab3 = res.steps
    assert atk.incoming > 0  # Attacks do NOT break spell shield
    assert ab1.incoming == F(0)  # Blocked!
    assert ab2.incoming > 0  # On 40 s cooldown!
    assert ab3.incoming == F(0)  # Off cooldown at t=40 s -> blocked again!
    assert res.label is Label.DERIVED

    # 3814 Edge of Night (40 s CD) and 4632 Verdant Barrier (60 s CD)
    for iid in ("3814", "4632"):
        s = _sheet("Ahri", 18, (iid,))
        r = evaluate_defense(s, parse_incoming("ability:physical:500"), timeline=True)
        assert r.steps[0].incoming == F(0)


# --- 8. Optimizer integration: time_to_die verifies all 9 while EHP stays honest ---


def test_optimizer_time_to_die_verifies_jaksho_deaths_dance_and_protoplasm():
    champ = load_champion(ROOT, "Garen")
    issues = load_issues(ROOT)
    derived = load_records(ROOT)
    hits = parse_incoming("physical:600 wait:2 magic:600 wait:4 physical:800")

    for iid in ("6665", "6333", "2525", "4401", "3082", "3869"):
        ttd = optimize_build(
            ROOT,
            champ,
            18,
            "time_to_die",
            constraints=OptimizeConstraints(
                slots=1,
                required_items=(iid,),
                only_verified=True,
                tier="all",
            ),
            issues=issues,
            derived=derived,
            incoming_hits=hits,
            timeline=True,
        )
        assert ttd.verified_builds and ttd.verified_builds[0].items == (iid,)
        assert ttd.pending_builds == ()
