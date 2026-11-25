"""Tests for active Q/W/E/R shields, heals, damage reduction, and temporary stat steroids."""

from __future__ import annotations

import json
from fractions import Fraction as F
from pathlib import Path

import pytest

from lol_knowledge.cli import main as cli_main
from lol_knowledge.contract import execute_request
from lol_knowledge.damage import DamageType
from lol_knowledge.defense import IncomingHit, evaluate_defense
from lol_knowledge.errors import KitError, RotationError, StatsError
from lol_knowledge.formula import ABILITY_OPS, evaluate_formula, formula_issues
from lol_knowledge.kit import load_kit, parse_kit
from lol_knowledge.mcp_server import MCPServer
from lol_knowledge.rotation import CritBase, evaluate_rotation, parse_steps
from lol_knowledge.runes import load_runes
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
RECORDS = load_records(ROOT)
RUNES = load_runes(ROOT)
CRIT = CritBase(F(2), Label.DERIVED, "test record")


def _sheet(
    champ_id: str,
    level: int = 18,
    item_ids: tuple[str, ...] = (),
):
    champ = load_champion(ROOT, champ_id)
    items = tuple(load_items(ROOT, list(item_ids))) if item_ids else ()
    return build_stat_sheet(champ, level, items, ISSUES, {}, RECORDS)


def _target(armor: int = 80, mr: int = 60, hp: int = 3000):
    return target_from_values(F(armor), F(mr), max_health=F(hp), kind="champion")


def _hit(
    amount: int,
    dtype: DamageType = DamageType.PHYSICAL,
    *,
    already_mitigated: bool = False,
    time: F | None = None,
    source: str = "test hit",
) -> IncomingHit:
    return IncomingHit(
        "ability",
        dtype,
        F(amount),
        source,
        already_mitigated=already_mitigated,
        time=time,
        label=Label.OFFICIAL,
    )


# ---------------------------------------------------------------------------
# 1. Roster coverage & schema validation
# ---------------------------------------------------------------------------


def test_roster_active_effects_coverage_and_sanity():
    champs_dir = ROOT / "lol-knowledge" / "champions"
    champs_with_active = 0
    kinds: dict[str, int] = {}
    sample_stats = {
        "health": F(2000),
        "base_health": F(1500),
        "bonus_health": F(500),
        "max_health": F(2000),
        "current_health": F(1000),
        "missing_fraction_health": F(1, 2),
        "attack_damage": F(200),
        "base_attack_damage": F(100),
        "bonus_attack_damage": F(100),
        "ability_power": F(100),
        "armor": F(100),
        "base_armor": F(60),
        "bonus_armor": F(40),
        "magic_resist": F(80),
        "base_magic_resist": F(50),
        "bonus_magic_resist": F(30),
        "mana": F(800),
        "base_mana": F(500),
        "bonus_mana": F(300),
        "move_speed": F(380),
        "base_move_speed": F(335),
        "bonus_move_speed": F(45),
        "attack_speed": F(12, 10),
        "attack_speed_bonus": F(30),
        "crit_chance": F(1, 2),
        "lethality": F(18),
        "heal_and_shield_power": F(10),
        "ability_haste": F(20),
        "life_steal": F(10),
    }

    for kit_file in sorted(champs_dir.glob("*/kit.json")):
        kit = load_kit(ROOT, kit_file.parent.name)
        assert kit is not None
        has_any = False
        for ab in kit.abilities.values():
            for eff in ab.active_effects:
                has_any = True
                kinds[eff.kind] = kinds.get(eff.kind, 0) + 1
                assert formula_issues(eff.formula, ops=ABILITY_OPS) == []
                r1 = evaluate_formula(
                    eff.formula, sample_stats, rank=1, level=1, ops=ABILITY_OPS
                ).exact
                rm = evaluate_formula(
                    eff.formula, sample_stats, rank=ab.max_rank, level=18, ops=ABILITY_OPS
                ).exact
                assert r1 is not None and r1 > 0
                assert rm is not None and rm > 0
        if has_any:
            champs_with_active += 1

    assert champs_with_active >= 135
    assert kinds["shield"] >= 45
    assert kinds["heal"] >= 45
    assert kinds["damage_dealt_heal"] >= 8
    assert kinds["recent_damage_heal"] >= 2
    assert kinds["recent_damage_shield"] >= 3
    assert kinds["damage_taken_modifier"] >= 15
    assert kinds["dodge_attacks"] >= 3
    assert kinds["spell_shield"] >= 2
    assert kinds["block_first_hit"] >= 1
    assert kinds["invulnerable"] >= 5
    assert kinds["stat_bonus"] >= 160


def test_parse_kit_rejects_invalid_active_effects():
    base_kit = json.loads(
        (ROOT / "lol-knowledge" / "champions" / "Garen" / "kit.json").read_text("utf-8")
    )

    bad_kind = json.loads(json.dumps(base_kit))
    bad_kind["abilities"]["W"]["active_effects"] = [
        {
            "id": "x",
            "name": "x",
            "kind": "invalid_kind",
            "formula": {"op": "constant", "value": 10},
            "label": "Derivado",
            "source": "test",
        }
    ]
    with pytest.raises(KitError, match="kind must be one of"):
        parse_kit(bad_kind)

    missing_stat = json.loads(json.dumps(base_kit))
    missing_stat["abilities"]["W"]["active_effects"] = [
        {
            "id": "x",
            "name": "x",
            "kind": "stat_bonus",
            "formula": {"op": "constant", "value": 10},
            "label": "Derivado",
            "source": "test",
        }
    ]
    with pytest.raises(KitError, match="'stat' must be a non-empty string"):
        parse_kit(missing_stat)

    bad_dr_cap = json.loads(json.dumps(base_kit))
    bad_dr_cap["abilities"]["W"]["active_effects"] = [
        {
            "id": "x",
            "name": "x",
            "kind": "damage_taken_modifier",
            "mode": "flat",
            "damage_reduction_cap": 1.5,
            "formula": {"op": "constant", "value": 10},
            "label": "Derivado",
            "source": "test",
        }
    ]
    with pytest.raises(KitError, match="damage_reduction_cap"):
        parse_kit(bad_dr_cap)


# ---------------------------------------------------------------------------
# 2. Rotation: zero-damage utility casts, shields, heals & stat steroids
# ---------------------------------------------------------------------------


def test_zero_damage_utility_casts_grant_shield_charge_spellblade_and_trigger_shield_bash():
    kit = load_kit(ROOT, "Lux")
    assert kit is not None
    # Equip Sheen (3057) + Shield Bash (8401) to test Spellblade + Shield Bash interaction
    sheet = _sheet("Lux", level=11, item_ids=("3057",))
    out = evaluate_rotation(
        kit,
        sheet,
        {"Q": 5, "W": 5, "E": 5, "R": 2},
        _target(),
        parse_steps("W, attack"),
        CRIT,
        timeline=True,
        runes=(8401,),
        rune_data=RUNES,
    )
    assert len(out.steps[0].shield_events) == 1
    assert out.steps[0].shield_events[0].shield_type == "normal"
    assert out.steps[0].shield_events[0].amount > 0
    # Next attack gets both Sheen Spellblade AND Shield Bash (8401)
    sources = [p.source for p in out.steps[1].parts]
    assert any("3057" in s for s in sources)
    assert any("8401" in s for s in sources)


def test_tristana_q_over_100_percent_attack_speed_speeds_up_timeline():
    kit = load_kit(ROOT, "Tristana")
    assert kit is not None
    sheet = _sheet("Tristana", level=18)
    ranks = {"Q": 5, "W": 5, "E": 5, "R": 3}

    without_q = evaluate_rotation(
        kit, sheet, ranks, _target(), parse_steps("attack, attack, attack"), CRIT, timeline=True
    )
    with_q = evaluate_rotation(
        kit,
        sheet,
        ranks,
        _target(),
        parse_steps("Q, attack, attack, attack"),
        CRIT,
        timeline=True,
    )
    # Tristana Q R5 grants +120% AS (fraction 1.2 > 1.0) for 7 s, cutting attack interval sharply
    assert with_q.duration < without_q.duration


def test_ad_steroids_increase_subsequent_attack_damage():
    # Vayne R: flat bonus AD (+65 at R3); Aatrox R: percent AD (+40% at R3); Riven R: +20% AD
    for champ_id, cast_step in (
        ("Vayne", "R"),
        ("Aatrox", "R"),
        ("Riven", "R.wind_slash_min"),
    ):
        kit = load_kit(ROOT, champ_id)
        assert kit is not None
        sheet = _sheet(champ_id, level=16, item_ids=("1038",))  # B.F. Sword
        ranks = {"Q": 5, "W": 5, "E": 5, "R": 3}
        base = evaluate_rotation(kit, sheet, ranks, _target(), parse_steps("attack"), CRIT)
        buffed = evaluate_rotation(
            kit, sheet, ranks, _target(), parse_steps(f"{cast_step}, attack"), CRIT
        )
        assert buffed.steps[1].total > base.steps[0].total


def test_zaahen_q_case_scoping_and_darius_q_missing_hp_heal():
    z_kit = load_kit(ROOT, "Zaahen")
    assert z_kit is not None
    z_sheet = _sheet("Zaahen", level=18)
    z_out = evaluate_rotation(
        z_kit,
        z_sheet,
        {"Q": 5, "W": 5, "E": 5, "R": 3},
        _target(),
        parse_steps("Q.first_hit, Q.recast"),
        CRIT,
    )
    # Q1 heals 9% max HP; Q2 (recast) does not heal
    assert len(z_out.steps[0].heal_events) == 1
    assert z_out.steps[0].heal_events[0].amount == z_sheet["health"].total() * F("0.09")
    assert z_out.steps[1].heal_events == ()

    d_kit = load_kit(ROOT, "Darius")
    assert d_kit is not None
    d_sheet = _sheet("Darius", level=18)
    d_full = evaluate_rotation(
        d_kit, d_sheet, {"Q": 5, "W": 5, "E": 5, "R": 3}, _target(), parse_steps("Q.blade"), CRIT
    )
    assert d_full.healing == 0
    d_wounded = evaluate_rotation(
        d_kit,
        d_sheet,
        {"Q": 5, "W": 5, "E": 5, "R": 3},
        _target(),
        parse_steps("Q.blade"),
        CRIT,
        inputs={"champion_missing_health_fraction": F("0.5")},
    )
    assert d_wounded.healing == d_sheet["health"].total() * F("0.5") * F("0.17")


# ---------------------------------------------------------------------------
# 3. Defense simulation (survive): DR, shields, heals, HoTs, resists & HP ults
# ---------------------------------------------------------------------------


def test_alistar_r_percent_dr_reduces_physical_and_magic_but_not_true():
    kit = load_kit(ROOT, "Alistar")
    assert kit is not None
    sheet = _sheet("Alistar", level=16)
    ranks = {"Q": 5, "W": 5, "E": 5, "R": 3}
    hits = (
        _hit(1000, DamageType.PHYSICAL, already_mitigated=True, source="phys"),
        _hit(1000, DamageType.MAGIC, already_mitigated=True, source="mag"),
        _hit(500, DamageType.TRUE, already_mitigated=True, source="true"),
    )
    out = evaluate_defense(
        sheet,
        hits,
        enemy_description="test",
        kit=kit,
        defender_casts=("R",),
        defender_ranks=ranks,
    )
    # Rank 3 Alistar R = 75% DR -> 250 physical + 250 magic + 500 true = 1000 total
    assert out.steps[0].damage_after_flat == F(250)
    assert out.steps[1].damage_after_flat == F(250)
    assert out.steps[2].damage_after_flat == F(500)
    assert out.total_damage_taken == F(1000)


def test_garen_w_combines_dr_and_shield_and_expires_in_timeline():
    kit = load_kit(ROOT, "Garen")
    assert kit is not None
    sheet = _sheet("Garen", level=18)
    ranks = {"Q": 5, "W": 5, "E": 5, "R": 3}
    hits = (
        _hit(500, DamageType.PHYSICAL, already_mitigated=True, time=F(0), source="hit1"),
        _hit(500, DamageType.PHYSICAL, already_mitigated=True, time=F(5), source="hit2"),
    )
    out = evaluate_defense(
        sheet,
        hits,
        enemy_description="test",
        timeline=True,
        kit=kit,
        defender_casts=("W",),
        defender_ranks=ranks,
    )
    # At t=0: 41% DR -> 500 * 0.59 = 295, plus shield absorbs part of it
    assert out.steps[0].damage_after_flat == F(295)
    assert out.steps[0].shield_absorbed > 0
    # At t=5 (> 4 s duration): both DR and shield expired -> full 500 damage
    assert out.steps[1].damage_after_flat == F(500)
    assert out.steps[1].shield_absorbed == 0


def test_leona_w_flat_dr_cap_and_armor_mr_steroid():
    kit = load_kit(ROOT, "Leona")
    assert kit is not None
    sheet = _sheet("Leona", level=18)
    ranks = {"Q": 5, "W": 5, "E": 5, "R": 3}
    raw_hits = (
        _hit(50, DamageType.PHYSICAL, source="raw_small"),
        _hit(500, DamageType.PHYSICAL, source="raw_large"),
    )
    base_out = evaluate_defense(sheet, raw_hits, enemy_description="test", kit=kit)
    w_out = evaluate_defense(
        sheet,
        raw_hits,
        enemy_description="test",
        kit=kit,
        defender_casts=("W",),
        defender_ranks=ranks,
    )
    # Small hit post-mitigation is < 48, so 50% flat DR cap enforces half remaining
    assert w_out.steps[0].flat_reduced == w_out.steps[0].incoming * F("0.5")
    # Large hit post-mitigation is > 48, so full 24 flat DR applies
    assert w_out.steps[1].flat_reduced == F(24)
    # Bonus armor from Leona W strictly lowers mitigated incoming damage too
    assert w_out.steps[1].incoming < base_out.steps[1].incoming


def test_morgana_e_and_galio_w_damage_type_specific_shields_and_dr():
    m_kit = load_kit(ROOT, "Morgana")
    assert m_kit is not None
    m_sheet = _sheet("Morgana", level=18)
    m_hits = (
        _hit(200, DamageType.PHYSICAL, already_mitigated=True, source="phys"),
        _hit(200, DamageType.MAGIC, already_mitigated=True, source="mag"),
    )
    m_out = evaluate_defense(
        m_sheet,
        m_hits,
        enemy_description="test",
        kit=m_kit,
        defender_casts=("E=5",),
    )
    # Black Shield is magic-only: physical bypasses shield, magic is fully absorbed
    assert m_out.steps[0].shield_absorbed == 0
    assert m_out.steps[1].shield_absorbed == F(200)

    g_kit = load_kit(ROOT, "Galio")
    assert g_kit is not None
    g_sheet = _sheet("Galio", level=18)
    g_hits = (
        _hit(1000, DamageType.PHYSICAL, already_mitigated=True, source="phys"),
        _hit(1000, DamageType.MAGIC, already_mitigated=True, source="mag"),
    )
    g_out = evaluate_defense(
        g_sheet,
        g_hits,
        enemy_description="test",
        kit=g_kit,
        defender_casts=("W=5",),
    )
    # Galio W gives twice as much magic DR as physical DR, plus passive magic shield
    assert g_out.steps[1].damage_after_flat < g_out.steps[0].damage_after_flat
    assert g_out.steps[0].shield_absorbed == 0
    assert g_out.steps[1].shield_absorbed > 0


def test_mundo_r_hot_and_nasus_r_hp_resist_steroids_in_timeline():
    m_kit = load_kit(ROOT, "DrMundo")
    assert m_kit is not None
    m_sheet = _sheet("DrMundo", level=16)
    hits = tuple(
        _hit(400, DamageType.PHYSICAL, already_mitigated=True, time=F(i * 2), source=f"hit{i}")
        for i in range(5)
    )
    base_m = evaluate_defense(m_sheet, hits, enemy_description="test", timeline=True, kit=m_kit)
    ult_m = evaluate_defense(
        m_sheet,
        hits,
        enemy_description="test",
        timeline=True,
        kit=m_kit,
        defender_casts=("R=3",),
    )
    assert ult_m.total_healing > 0
    assert ult_m.remaining_health > base_m.remaining_health

    n_kit = load_kit(ROOT, "Nasus")
    assert n_kit is not None
    n_sheet = _sheet("Nasus", level=16)
    raw_hits = tuple(_hit(600, DamageType.PHYSICAL, time=F(i), source=f"hit{i}") for i in range(6))
    base_n = evaluate_defense(n_sheet, raw_hits, enemy_description="test", timeline=True, kit=n_kit)
    ult_n = evaluate_defense(
        n_sheet,
        raw_hits,
        enemy_description="test",
        timeline=True,
        kit=n_kit,
        defender_casts=("R=3",),
    )
    assert ult_n.remaining_health > base_n.remaining_health


def test_reactive_missing_hp_heal_triggers_after_taking_damage():
    kit = load_kit(ROOT, "Darius")
    assert kit is not None
    sheet = _sheet("Darius", level=18)
    hits = (
        _hit(1000, DamageType.PHYSICAL, already_mitigated=True, source="hit1"),
        _hit(500, DamageType.PHYSICAL, already_mitigated=True, source="hit2"),
    )
    out = evaluate_defense(sheet, hits, enemy_description="test", kit=kit, defender_casts=("Q=5",))
    # After hit1 (-1000 HP), Darius Q reacts and heals 17% of 1000 missing HP = 170 HP!
    assert out.total_healing == F(170)


def test_invalid_defender_cast_raises_stats_error():
    kit = load_kit(ROOT, "Garen")
    assert kit is not None
    sheet = _sheet("Garen", level=11)
    hits = (_hit(100, DamageType.PHYSICAL),)
    with pytest.raises(StatsError, match="specify rank"):
        evaluate_defense(sheet, hits, enemy_description="test", kit=kit, defender_casts=("E",))
    with pytest.raises(StatsError, match="no modelled active_effects"):
        evaluate_defense(sheet, hits, enemy_description="test", kit=kit, defender_casts=("E=5",))
    with pytest.raises(StatsError, match="rank must be"):
        evaluate_defense(sheet, hits, enemy_description="test", kit=kit, defender_casts=("W=9",))


# ---------------------------------------------------------------------------
# 4. CLI, Optimizer, Contract & MCP parity
# ---------------------------------------------------------------------------


def test_cli_contract_mcp_and_optimizer_support_defender_casts(capsys):
    # CLI survive --defender-cast vs plain
    rc_base = cli_main(
        [
            "survive",
            "--champion",
            "Alistar",
            "--level",
            "16",
            "--incoming",
            "physical:1000",
            "--json",
        ]
    )
    assert rc_base == 0
    base_payload = json.loads(capsys.readouterr().out)
    rc = cli_main(
        [
            "survive",
            "--champion",
            "Alistar",
            "--level",
            "16",
            "--learned",
            "R=3",
            "--defender-cast",
            "R",
            "--incoming",
            "physical:1000",
            "--json",
        ]
    )
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["total_damage_taken"] == pytest.approx(base_payload["total_damage_taken"] * 0.25)

    # Contract lookup exposes active_effects
    lk = execute_request(
        {"operation": "lookup", "params": {"entity": "champion", "champion": "Garen"}},
        ROOT,
    )
    assert lk["ok"] is True
    w_effects = lk["result"]["kit"]["abilities"]["W"]["active_effects"]
    assert {e["id"] for e in w_effects} == {"courage_dr", "courage_shield"}

    # Contract survive & MCP lol_survive
    surv = execute_request(
        {
            "operation": "survive",
            "params": {
                "champion": "Garen",
                "level": 18,
                "learned": {"W": 5},
                "defender_casts": ["W"],
                "incoming": "physical:1000",
            },
        },
        ROOT,
    )
    assert surv["ok"] is True
    assert surv["result"]["total_shield_granted"] > 0

    server = MCPServer(ROOT)

    def _mcp_call(name: str, arguments: dict) -> dict:
        reply = server.handle_message(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {"name": name, "arguments": arguments},
            }
        )
        assert reply is not None
        res = reply["result"]
        assert res["isError"] is False, res
        return res["structuredContent"]

    mcp_surv = _mcp_call(
        "lol_survive",
        {
            "champion": "Alistar",
            "level": 16,
            "learned": {"R": 3},
            "defender_casts": ["R"],
            "incoming": "physical:1000",
        },
    )
    assert mcp_surv["ok"] is True
    assert mcp_surv["result"]["total_damage_taken"] == pytest.approx(
        base_payload["total_damage_taken"] * 0.25
    )

    # Optimizer with defender_casts (contract + MCP)
    opt_plain = execute_request(
        {
            "operation": "optimize",
            "params": {
                "champion": "Alistar",
                "level": 16,
                "objective": "time_to_die",
                "incoming": "physical:1000, wait:1, physical:1000",
                "timeline": True,
                "slots": 1,
                "budget": 3200,
                "only_verified": True,
                "top": 1,
                "beam_width": 4,
                "pool_limit": 6,
            },
        },
        ROOT,
    )
    assert opt_plain["ok"] is True
    mcp_opt = _mcp_call(
        "lol_optimize",
        {
            "champion": "Alistar",
            "level": 16,
            "objective": "time_to_die",
            "incoming": "physical:1000, wait:1, physical:1000",
            "timeline": True,
            "slots": 1,
            "budget": 3200,
            "only_verified": True,
            "top": 1,
            "beam_width": 4,
            "pool_limit": 6,
            "defender_casts": ["R=3"],
        },
    )
    assert mcp_opt["ok"] is True
    assert (
        mcp_opt["result"]["verified_builds"][0]["metrics"]["total_damage_taken"]
        < opt_plain["result"]["verified_builds"][0]["metrics"]["total_damage_taken"]
    )


def test_rotation_rejects_ability_without_cases_or_active_effects():
    # Verify normal guard still blocks abilities that have neither cases nor active_effects
    kit = load_kit(ROOT, "Garen")
    assert kit is not None
    # Garen W has cases=() and active_effects=(courage_dr, courage_shield) -> MUST succeed!
    sheet = _sheet("Garen", level=11)
    out = evaluate_rotation(
        kit, sheet, {"Q": 5, "W": 5, "E": 5, "R": 2}, _target(), parse_steps("W"), CRIT
    )
    assert len(out.steps[0].shield_events) == 1
    assert any("defensive damage reduction" in n for n in out.notes)

    # An ability with neither cases nor active_effects raises RotationError
    raw = json.loads(
        (ROOT / "lol-knowledge" / "champions" / "Garen" / "kit.json").read_text("utf-8")
    )
    raw["abilities"]["W"]["active_effects"] = []
    empty_kit = parse_kit(raw)
    with pytest.raises(RotationError, match="no modelled damage cases or active effects"):
        evaluate_rotation(
            empty_kit, sheet, {"Q": 5, "W": 5, "E": 5, "R": 2}, _target(), parse_steps("W"), CRIT
        )


# ---------------------------------------------------------------------------
# 5. Combat-dependent mechanics: damage-dealt heals, stored damage, dodge/block/invuln
# ---------------------------------------------------------------------------


def test_damage_dealt_heals_scale_from_post_mitigation_step_damage():
    # Warwick Q R5: heals 75% of post-mitigation Q damage
    ww_kit = load_kit(ROOT, "Warwick")
    assert ww_kit is not None
    ww_out = evaluate_rotation(
        ww_kit,
        _sheet("Warwick", level=18),
        {"Q": 5, "W": 5, "E": 5, "R": 3},
        _target(),
        parse_steps("Q"),
        CRIT,
    )
    assert ww_out.healing == ww_out.steps[0].total * F("0.75")

    # Zaahen R R3: heals 33% of post-mitigation R damage
    z_kit = load_kit(ROOT, "Zaahen")
    assert z_kit is not None
    z_out = evaluate_rotation(
        z_kit,
        _sheet("Zaahen", level=18),
        {"Q": 5, "W": 5, "E": 5, "R": 3},
        _target(),
        parse_steps("R"),
        CRIT,
    )
    assert z_out.healing == z_out.steps[0].total * F("0.33")

    # Camille W: outer heals 100% of part[1] (bonus max-HP damage) ONLY; inner heals 0
    c_kit = load_kit(ROOT, "Camille")
    assert c_kit is not None
    c_sheet = _sheet("Camille", level=18)
    c_ranks = {"Q": 5, "W": 5, "E": 5, "R": 3}
    c_inner = evaluate_rotation(c_kit, c_sheet, c_ranks, _target(), parse_steps("W.inner"), CRIT)
    assert c_inner.healing == 0
    c_outer = evaluate_rotation(c_kit, c_sheet, c_ranks, _target(), parse_steps("W.outer"), CRIT)
    assert c_outer.healing == c_outer.steps[0].parts[1].damage
    assert c_outer.healing < c_outer.steps[0].total

    # Briar W.snack_attack: heals 40% of damage dealt + AttackMaxHPHeal (5% max HP)
    b_kit = load_kit(ROOT, "Briar")
    assert b_kit is not None
    b_sheet = _sheet("Briar", level=18)
    b_out = evaluate_rotation(
        b_kit,
        b_sheet,
        {"Q": 5, "W": 5, "E": 5, "R": 3},
        _target(),
        parse_steps("W.snack_attack"),
        CRIT,
    )
    expected_briar = b_out.steps[0].total * F("0.40") + b_sheet["health"].total() * F("0.05")
    assert b_out.healing == expected_briar


def test_recent_damage_shields_and_heals_and_minimum_baseline():
    # Mordekaiser W in rotation (0 stored damage): guaranteed 5% max HP minimum shield
    m_kit = load_kit(ROOT, "Mordekaiser")
    assert m_kit is not None
    m_sheet = _sheet("Mordekaiser", level=18)
    m_rot = evaluate_rotation(
        m_kit, m_sheet, {"Q": 5, "W": 5, "E": 5, "R": 3}, _target(), parse_steps("W"), CRIT
    )
    min_sh = m_sheet["health"].total() * F("0.05")
    assert len(m_rot.steps[0].shield_events) == 1
    assert m_rot.steps[0].shield_events[0].amount == min_sh

    # Mordekaiser W in survive on a single hit: grants guaranteed 5% min shield before hit
    m_surv_single = evaluate_defense(
        m_sheet,
        (_hit(500, DamageType.PHYSICAL, already_mitigated=True),),
        enemy_description="test",
        kit=m_kit,
        defender_casts=("W=5",),
    )
    assert m_surv_single.total_shield_granted == min_sh
    assert m_surv_single.total_shield_absorbed == min_sh

    # Rengar W in survive: heals 50% of damage taken on hit 1
    r_kit = load_kit(ROOT, "Rengar")
    assert r_kit is not None
    r_sheet = _sheet("Rengar", level=18)
    r_out = evaluate_defense(
        r_sheet,
        (
            _hit(600, DamageType.PHYSICAL, already_mitigated=True, time=F(0)),
            _hit(200, DamageType.PHYSICAL, already_mitigated=True, time=F(1)),
        ),
        enemy_description="test",
        timeline=True,
        kit=r_kit,
        defender_casts=("W=5",),
    )
    assert r_out.total_healing == F(300)

    # Sett W in survive: stores 100% of hit 1 damage (up to 50% max HP) as shield for hit 2
    s_kit = load_kit(ROOT, "Sett")
    assert s_kit is not None
    s_sheet = _sheet("Sett", level=18)
    s_out = evaluate_defense(
        s_sheet,
        (
            _hit(800, DamageType.PHYSICAL, already_mitigated=True, time=F(0)),
            _hit(500, DamageType.PHYSICAL, already_mitigated=True, time=F(1)),
        ),
        enemy_description="test",
        timeline=True,
        kit=s_kit,
        defender_casts=("W=5",),
    )
    assert s_out.total_shield_granted == F(800)
    assert s_out.steps[1].shield_absorbed == F(500)
    assert s_out.steps[1].health_damage == 0

    # Tahm Kench E R5 (47% grey health) in survive: converts 47% of hit 1 damage to shield
    tk_kit = load_kit(ROOT, "TahmKench")
    assert tk_kit is not None
    tk_sheet = _sheet("TahmKench", level=18)
    tk_out = evaluate_defense(
        tk_sheet,
        (
            _hit(1000, DamageType.PHYSICAL, already_mitigated=True, time=F(0)),
            _hit(400, DamageType.PHYSICAL, already_mitigated=True, time=F(1)),
        ),
        enemy_description="test",
        timeline=True,
        kit=tk_kit,
        defender_casts=("E=5",),
    )
    assert tk_out.total_shield_granted == F(470)
    assert tk_out.steps[1].shield_absorbed == F(400)


def test_dodge_attacks_spell_shield_block_first_hit_and_invulnerability():
    # Jax E: dodges basic attack & crit for 2 s, reduces ability by 25%, expires at t=3
    j_kit = load_kit(ROOT, "Jax")
    assert j_kit is not None
    j_sheet = _sheet("Jax", level=18)
    j_hits = (
        IncomingHit(
            "attack", DamageType.PHYSICAL, F(400), "aa1", already_mitigated=True, time=F(0)
        ),
        IncomingHit(
            "crit", DamageType.PHYSICAL, F(600), "crit1", already_mitigated=True, time=F(1)
        ),
        _hit(400, DamageType.MAGIC, already_mitigated=True, time=F(1), source="aoe"),
        IncomingHit(
            "attack", DamageType.PHYSICAL, F(400), "aa2", already_mitigated=True, time=F(3)
        ),
    )
    j_out = evaluate_defense(
        j_sheet, j_hits, enemy_description="test", timeline=True, kit=j_kit, defender_casts=("E=5",)
    )
    assert j_out.steps[0].health_damage == 0
    assert j_out.steps[1].health_damage == 0
    assert j_out.steps[2].damage_after_flat == F(300)  # 400 * (1 - 0.25)
    assert j_out.steps[3].health_damage == F(400)

    # Sivir E: blocks first ability (0 damage) & triggers heal when wounded; attack passes through
    sv_kit = load_kit(ROOT, "Sivir")
    assert sv_kit is not None
    sv_sheet = _sheet("Sivir", level=18)
    sv_hits = (
        IncomingHit("attack", DamageType.PHYSICAL, F(300), "aa", already_mitigated=True, time=F(0)),
        _hit(500, DamageType.MAGIC, already_mitigated=True, time=F("0.5"), source="spell1"),
        _hit(500, DamageType.MAGIC, already_mitigated=True, time=F("1.0"), source="spell2"),
    )
    sv_out = evaluate_defense(
        sv_sheet,
        sv_hits,
        enemy_description="test",
        timeline=True,
        kit=sv_kit,
        defender_casts=("E=5",),
    )
    assert sv_out.steps[0].health_damage == F(300)
    assert sv_out.steps[1].health_damage == 0
    assert sv_out.steps[1].heals  # Sivir E heal fired on spell block!
    assert sv_out.steps[2].health_damage == F(500)  # Spell shield already consumed

    # Braum E R5: blocks first hit completely (0), reduces second hit by 55% DR
    br_kit = load_kit(ROOT, "Braum")
    assert br_kit is not None
    br_sheet = _sheet("Braum", level=18)
    br_out = evaluate_defense(
        br_sheet,
        (
            _hit(1000, DamageType.PHYSICAL, already_mitigated=True, time=F(0)),
            _hit(1000, DamageType.PHYSICAL, already_mitigated=True, time=F(1)),
        ),
        enemy_description="test",
        timeline=True,
        kit=br_kit,
        defender_casts=("E=5",),
    )
    assert br_out.steps[0].health_damage == 0
    assert br_out.steps[1].damage_after_flat == F(450)  # 1000 * (1 - 0.55)

    # Kayle R: invulnerable to physical, magic & true for 2.5 s; normal damage at t=3
    k_kit = load_kit(ROOT, "Kayle")
    assert k_kit is not None
    k_sheet = _sheet("Kayle", level=16)
    k_out = evaluate_defense(
        k_sheet,
        (
            _hit(5000, DamageType.TRUE, already_mitigated=True, time=F(0)),
            _hit(500, DamageType.MAGIC, already_mitigated=True, time=F(2)),
            _hit(500, DamageType.PHYSICAL, already_mitigated=True, time=F(3)),
        ),
        enemy_description="test",
        timeline=True,
        kit=k_kit,
        defender_casts=("R=3",),
    )
    assert k_out.steps[0].health_damage == 0
    assert k_out.steps[1].health_damage == 0
    assert k_out.steps[2].health_damage == F(500)

    # Tryndamere R R3 (70 HP floor for 5 s): survives lethal true damage until t=5, dies at t=6
    tr_kit = load_kit(ROOT, "Tryndamere")
    assert tr_kit is not None
    tr_sheet = _sheet("Tryndamere", level=16)
    tr_out = evaluate_defense(
        tr_sheet,
        (
            _hit(9999, DamageType.TRUE, already_mitigated=True, time=F(0)),
            _hit(9999, DamageType.TRUE, already_mitigated=True, time=F(4)),
            _hit(500, DamageType.TRUE, already_mitigated=True, time=F(6)),
        ),
        enemy_description="test",
        timeline=True,
        kit=tr_kit,
        defender_casts=("R=3",),
    )
    assert tr_out.steps[0].health_after == F(70)
    assert tr_out.steps[1].health_after == F(70)
    assert tr_out.steps[2].health_after == 0
    assert tr_out.time_to_die == F(6)
