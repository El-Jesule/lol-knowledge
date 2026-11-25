"""Comprehensive tests for the deterministic coupled 1v1 duel simulator."""

from __future__ import annotations

import json
from fractions import Fraction
from pathlib import Path

import pytest

from lol_knowledge.cli import main
from lol_knowledge.contract import execute_request
from lol_knowledge.duel import DuelFighterSpec, evaluate_duel
from lol_knowledge.duel_report import format_text, to_dict
from lol_knowledge.errors import RotationError
from lol_knowledge.kit import load_kit, passive_contributions
from lol_knowledge.mcp_server import MCPServer
from lol_knowledge.optimizer import OptimizeConstraints, optimize_build
from lol_knowledge.rotation import parse_steps
from lol_knowledge.stats import (
    build_stat_sheet,
    load_champion,
    load_issues,
    load_items,
    load_records,
)
from lol_knowledge.summoners import load_summoner_spells

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def env():
    return {
        "issues": load_issues(ROOT),
        "derived": load_records(ROOT),
        "summoners": load_summoner_spells(ROOT),
    }


def _make_fighter(
    env: dict,
    champion_id: str,
    level: int,
    *,
    items: list[str] = (),
    ranks: dict[str, int] | None = None,
    steps: str = "",
    priority_slots: tuple[str, ...] = ("R", "Q", "W", "E"),
    start_health: Fraction | None = None,
    start_shield: Fraction = Fraction(0),
    summoners: tuple[str, ...] = (),
    holder_range: str | None = None,
) -> DuelFighterSpec:
    champ = load_champion(ROOT, champion_id)
    kit = load_kit(ROOT, champ.id)
    assert kit is not None
    eff_ranks = ranks if ranks is not None else {"Q": 5, "W": 5, "E": 5, "R": 3}
    loaded_items = load_items(ROOT, list(items))
    sheet = build_stat_sheet(
        champ,
        level,
        loaded_items,
        env["issues"],
        None,
        env["derived"],
        passive_contributions(kit, eff_ranks),
    )
    if holder_range is None:
        atk_range = champ.stats.get("attackrange")
        holder_range = "melee" if (atk_range is not None and atk_range < 300) else "ranged"
    return DuelFighterSpec(
        sheet=sheet,
        kit=kit,
        ranks=eff_ranks,
        steps=parse_steps(steps) if steps else (),
        priority_slots=priority_slots,
        holder_range=holder_range,
        start_health=start_health,
        start_shield=start_shield,
        summoners=summoners,
        summoner_data=env["summoners"],
    )


def test_mirror_duel_simultaneous_mutual_kill(env) -> None:
    a = _make_fighter(env, "Jax", 11, ranks={"Q": 1, "W": 5, "E": 3, "R": 2}, steps="E.min, Q, W")
    b = _make_fighter(env, "Jax", 11, ranks={"Q": 1, "W": 5, "E": 3, "R": 2}, steps="E.min, Q, W")
    out = evaluate_duel(a, b, mode="scripted_then_attack", tie_break="simultaneous")
    assert out.winner == "draw_mutual_kill"
    assert out.fighter_a.remaining_health == 0
    assert out.fighter_b.remaining_health == 0
    assert out.fighter_a.damage_dealt == out.fighter_b.damage_dealt
    assert out.fighter_a.damage_taken == out.fighter_b.damage_taken
    assert out.fighter_a.actions_taken == out.fighter_b.actions_taken
    assert out.duration > 0


def test_asymmetric_duel_exact_symmetry_invariant(env) -> None:
    jax_e = _make_fighter(
        env, "Jax", 11, ranks={"Q": 1, "W": 5, "E": 3, "R": 2}, steps="E.min, Q, W"
    )
    jax_no_e = _make_fighter(env, "Jax", 11, ranks={"Q": 1, "W": 5, "E": 3, "R": 2}, steps="Q, W")
    ab = evaluate_duel(jax_e, jax_no_e, mode="scripted_then_attack", tie_break="simultaneous")
    ba = evaluate_duel(jax_no_e, jax_e, mode="scripted_then_attack", tie_break="simultaneous")
    assert ab.winner == "A"
    assert ba.winner == "B"
    assert ab.duration == ba.duration
    assert ab.fighter_a.remaining_health == ba.fighter_b.remaining_health
    assert ab.fighter_b.remaining_health == ba.fighter_a.remaining_health
    assert ab.fighter_a.damage_dealt == ba.fighter_b.damage_dealt
    assert ab.fighter_a.damage_taken == ba.fighter_b.damage_taken
    assert ab.fighter_a.actions_taken == ba.fighter_b.actions_taken


def test_tie_break_simultaneous_vs_a_first_vs_b_first(env) -> None:
    a = _make_fighter(env, "Garen", 11, ranks={"Q": 5}, steps="Q", start_health=Fraction(50))
    b = _make_fighter(env, "Garen", 11, ranks={"Q": 5}, steps="Q", start_health=Fraction(50))
    sim = evaluate_duel(a, b, tie_break="simultaneous")
    af = evaluate_duel(a, b, tie_break="a_first")
    bf = evaluate_duel(a, b, tie_break="b_first")
    assert sim.winner == "draw_mutual_kill"
    assert af.winner == "A"
    assert af.fighter_a.remaining_health == Fraction(50)
    assert af.fighter_b.actions_taken == 0
    assert bf.winner == "B"
    assert bf.fighter_b.remaining_health == Fraction(50)
    assert bf.fighter_a.actions_taken == 0


def test_modes_strict_scripted_and_priority_loop(env) -> None:
    a = _make_fighter(env, "Garen", 11, ranks={"Q": 5, "W": 1, "E": 3, "R": 2}, steps="Q")
    b = _make_fighter(env, "Garen", 11, ranks={"Q": 5, "W": 1, "E": 3, "R": 2}, steps="Q")
    strict = evaluate_duel(a, b, mode="strict_scripted")
    assert strict.winner == "draw_timeout"
    assert strict.fighter_a.actions_taken == 1
    assert strict.fighter_b.actions_taken == 1

    # priority_loop casts abilities off cooldown and mirrors when priority_slots match
    prio_a = _make_fighter(
        env, "Jax", 11, ranks={"Q": 1, "W": 5, "E": 3, "R": 2}, priority_slots=("W", "Q")
    )
    prio_b = _make_fighter(
        env, "Jax", 11, ranks={"Q": 1, "W": 5, "E": 3, "R": 2}, priority_slots=("W", "Q")
    )
    out_prio = evaluate_duel(prio_a, prio_b, mode="priority_loop")
    assert out_prio.winner == "draw_mutual_kill"
    # Verify priority_loop actually cast abilities (not just attacks)
    actions_a = {ev.action for ev in out_prio.events if ev.actor == "A"}
    assert "W" in actions_a and "Q" in actions_a and "attack" in actions_a

    # Compare priority_loop (casts W/Q) vs fighter with no learned abilities
    no_ranks_b = _make_fighter(env, "Jax", 11, ranks={})
    out_diff = evaluate_duel(prio_a, no_ranks_b, mode="priority_loop")
    assert out_diff.winner == "A"
    assert out_diff.fighter_a.remaining_health > 0


def test_jax_e_dodge_negates_basic_attacks_and_lifesteal(env) -> None:
    # Attacker with Bloodthirster hitting Jax during E gets 0 damage & 0 lifesteal
    jax = _make_fighter(env, "Jax", 11, ranks={"E": 5}, steps="E.min")
    vamp_b = _make_fighter(
        env,
        "Garen",
        11,
        items=["3072"],
        ranks={},
        steps="attack",
        start_health=Fraction(800),
    )
    out = evaluate_duel(jax, vamp_b, mode="strict_scripted")
    b_atk_events = [ev for ev in out.events if ev.actor == "B" and ev.action == "attack"]
    assert len(b_atk_events) == 1
    assert b_atk_events[0].damage_dealt == 0
    assert b_atk_events[0].healing_done == 0


def test_tryndamere_r_undying_wins_low_hp_duel(env) -> None:
    # Low HP Tryndamere without R loses; with R undying floor he survives 5 s and kills opponent
    tryn_no_r = _make_fighter(
        env, "Tryndamere", 11, ranks={"R": 2}, steps="", start_health=Fraction(150)
    )
    tryn_r = _make_fighter(
        env, "Tryndamere", 11, ranks={"R": 2}, steps="R", start_health=Fraction(150)
    )
    opp = _make_fighter(env, "Garen", 11, ranks={"Q": 5}, steps="Q", start_health=Fraction(250))

    lose_out = evaluate_duel(tryn_no_r, opp, mode="scripted_then_attack")
    win_out = evaluate_duel(tryn_r, opp, mode="scripted_then_attack")
    assert lose_out.winner == "B"
    assert win_out.winner == "A"
    assert win_out.fighter_a.remaining_health >= 1


def test_kayle_r_invulnerability_blocks_lethal_burst(env) -> None:
    kayle_no_r = _make_fighter(env, "Kayle", 11, ranks={"R": 2}, start_health=Fraction(100))
    kayle_r = _make_fighter(env, "Kayle", 11, ranks={"R": 2}, steps="R", start_health=Fraction(100))
    burst = _make_fighter(env, "Garen", 11, ranks={"Q": 5}, steps="Q")
    out_die = evaluate_duel(kayle_no_r, burst, mode="strict_scripted")
    out_live = evaluate_duel(kayle_r, burst, mode="strict_scripted")
    assert out_die.winner == "B"
    assert out_live.winner == "draw_timeout"
    assert out_live.fighter_a.remaining_health == Fraction(100)


def test_sivir_e_spell_shield_blocks_ability_and_heals(env) -> None:
    sivir = _make_fighter(env, "Sivir", 11, ranks={"E": 5}, steps="E", start_health=Fraction(800))
    mage = _make_fighter(env, "Ahri", 11, ranks={"Q": 5}, steps="Q.out")
    out = evaluate_duel(sivir, mage, mode="strict_scripted")
    assert out.fighter_b.damage_dealt == 0
    assert out.fighter_a.healing_done > 0
    assert out.fighter_a.remaining_health > Fraction(800)


def test_braum_e_blocks_first_hit(env) -> None:
    braum = _make_fighter(env, "Braum", 11, ranks={"E": 5}, steps="E")
    enemy = _make_fighter(env, "Garen", 11, ranks={"Q": 5}, steps="Q")
    out = evaluate_duel(braum, enemy, mode="strict_scripted")
    assert out.fighter_b.damage_dealt == 0
    assert out.fighter_a.remaining_health == out.fighter_a.start_health


def test_warwick_q_damage_dealt_heal_reduced_by_alistar_r_and_ignite(env) -> None:
    ww = _make_fighter(env, "Warwick", 11, ranks={"Q": 5}, steps="Q", start_health=Fraction(700))
    ali_plain = _make_fighter(env, "Alistar", 11, ranks={"R": 2}, steps="")
    ali_r = _make_fighter(env, "Alistar", 11, ranks={"R": 2}, steps="R")
    ali_ign = _make_fighter(
        env,
        "Alistar",
        11,
        ranks={"R": 2},
        summoners=("SummonerDot",),
        steps="summoner:ignite",
    )

    out_plain = evaluate_duel(ww, ali_plain, mode="strict_scripted")
    out_r = evaluate_duel(ww, ali_r, mode="strict_scripted")
    # Against Alistar R (-65% DR at rank 2), Warwick Q deals less damage and heals less
    assert out_plain.fighter_a.healing_done > 0
    assert out_r.fighter_a.damage_dealt < out_plain.fighter_a.damage_dealt
    assert out_r.fighter_a.healing_done < out_plain.fighter_a.healing_done

    # Ignite cast before WW Q applies Grievous Wounds (-40%) to WW's healing
    ww_delayed = _make_fighter(
        env, "Warwick", 11, ranks={"Q": 5}, steps="wait:1, Q", start_health=Fraction(700)
    )
    out_ign = evaluate_duel(ww_delayed, ali_ign, mode="strict_scripted")
    assert out_ign.fighter_a.healing_done > 0
    assert out_ign.fighter_a.healing_done < out_plain.fighter_a.healing_done


def test_sett_w_and_rengar_w_convert_live_recent_damage(env) -> None:
    # Sett takes Garen Q at t=0, then casts W at t=1 -> gets a live Grit shield from damage taken
    sett = _make_fighter(env, "Sett", 11, ranks={"W": 5}, steps="wait:1, W.center_base")
    garen = _make_fighter(env, "Garen", 11, ranks={"Q": 5}, steps="Q")
    out_sett = evaluate_duel(sett, garen, mode="strict_scripted")
    assert out_sett.fighter_a.shield_granted > 0

    # Rengar takes Garen Q at t=0, then casts W at t=1 -> heals 50% of live recent damage taken
    rengar = _make_fighter(env, "Rengar", 11, ranks={"W": 5}, steps="wait:1, W.base")
    out_rengar = evaluate_duel(rengar, garen, mode="strict_scripted")
    assert out_rengar.fighter_a.healing_done > 0


def test_summoner_exhaust_reduces_opponent_damage(env) -> None:
    a_plain = _make_fighter(env, "Garen", 11, ranks={}, steps="")
    a_exh = _make_fighter(
        env, "Garen", 11, ranks={}, summoners=("SummonerExhaust",), steps="summoner:exhaust"
    )
    b = _make_fighter(env, "Garen", 11, ranks={"Q": 5}, steps="Q")
    out_plain = evaluate_duel(a_plain, b, mode="strict_scripted")
    out_exh = evaluate_duel(a_exh, b, mode="strict_scripted")
    assert out_exh.fighter_b.damage_dealt < out_plain.fighter_b.damage_dealt
    assert out_exh.fighter_a.remaining_health > out_plain.fighter_a.remaining_health


def test_thornmail_reflects_damage_and_applies_grievous(env) -> None:
    tank = _make_fighter(env, "Garen", 11, items=["3075"], ranks={}, steps="")
    attacker = _make_fighter(
        env, "Garen", 11, items=["3072"], ranks={}, steps="attack", start_health=Fraction(900)
    )
    out = evaluate_duel(attacker, tank, mode="strict_scripted")
    assert out.fighter_a.damage_taken > 0  # Thornmail magic damage reflected onto attacker
    assert out.fighter_b.damage_dealt > 0


def test_guardian_angel_stasis_and_revive(env) -> None:
    ga_fighter = _make_fighter(env, "Jax", 11, items=["3026"], ranks={}, start_health=Fraction(80))
    opp = _make_fighter(env, "Garen", 11, ranks={"Q": 5}, steps="Q", start_health=Fraction(300))
    out = evaluate_duel(ga_fighter, opp, mode="scripted_then_attack", max_duration=Fraction(15))
    # GA fighter must NOT die at t=0; stasis pauses their actions until >= 4 s
    assert out.duration >= Fraction(4)
    # Any action by A after t=0 must occur at t >= 4 s (stasis pause)
    post_t0_a = [ev.time for ev in out.events if ev.actor == "A" and ev.time > 0]
    assert post_t0_a and min(post_t0_a) >= Fraction(4)


def test_max_duration_timeout_and_validation_errors(env) -> None:
    a = _make_fighter(env, "Braum", 11, ranks={})
    b = _make_fighter(env, "Braum", 11, ranks={})
    out = evaluate_duel(a, b, max_duration=Fraction(2))
    assert out.winner == "draw_timeout"
    assert out.duration == Fraction(2)

    with pytest.raises(RotationError, match="mode"):
        evaluate_duel(a, b, mode="bad_mode")
    with pytest.raises(RotationError, match="tie_break"):
        evaluate_duel(a, b, tie_break="bad_tie")
    with pytest.raises(RotationError, match="max_duration"):
        evaluate_duel(a, b, max_duration=Fraction(0))


def test_duel_report_format_and_dict(env) -> None:
    a = _make_fighter(env, "Jax", 11, ranks={"Q": 1, "W": 5, "E": 3}, steps="E.min, Q, W")
    b = _make_fighter(env, "Jax", 11, ranks={"Q": 1, "W": 5, "E": 3}, steps="Q, W")
    out = evaluate_duel(a, b)
    text = format_text(out)
    assert "Duel 1v1" in text
    assert "Winner: A (Jax)" in text
    data = to_dict(out)
    assert data["winner"] == "A"
    assert data["fighter_a"]["survived"] is True
    assert data["fighter_b"]["survived"] is False
    assert len(data["events"]) == len(out.events)


def test_cli_duel_text_and_json(capsys) -> None:
    rc = main(
        [
            "duel",
            "--a-champion",
            "Jax",
            "--a-level",
            "11",
            "--a-learned",
            "Q=1",
            "--a-learned",
            "W=5",
            "--a-learned",
            "E=3",
            "--a-steps",
            "E.min, Q, W",
            "--b-champion",
            "Jax",
            "--b-level",
            "11",
            "--b-learned",
            "Q=1",
            "--b-learned",
            "W=5",
            "--b-learned",
            "E=3",
            "--b-steps",
            "Q, W",
            "--json",
            "--root",
            str(ROOT),
        ]
    )
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["winner"] == "A"
    assert payload["fighter_a"]["champion_id"] == "Jax"


def test_contract_and_mcp_lol_duel() -> None:
    params = {
        "fighter_a": {
            "champion": "Jax",
            "level": 11,
            "learned": {"Q": 1, "W": 5, "E": 3},
            "steps": "E.min, Q, W",
        },
        "fighter_b": {
            "champion": "Jax",
            "level": 11,
            "learned": {"Q": 1, "W": 5, "E": 3},
            "steps": "Q, W",
        },
        "mode": "scripted_then_attack",
        "tie_break": "simultaneous",
    }
    env_resp = execute_request(
        {"schema": "lol-knowledge-contract/1", "operation": "duel", "params": params},
        ROOT,
    )
    assert env_resp["ok"] is True
    assert env_resp["result_label"] == "Calculado"
    assert env_resp["result"]["winner"] == "A"

    server = MCPServer(ROOT)
    tools_reply = server.handle_message({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    assert tools_reply is not None
    tool_names = {t["name"] for t in tools_reply["result"]["tools"]}
    assert "lol_duel" in tool_names

    call_reply = server.handle_message(
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {"name": "lol_duel", "arguments": params},
        }
    )
    assert call_reply is not None
    assert call_reply["result"]["isError"] is False
    mcp_payload = json.loads(call_reply["result"]["content"][0]["text"])
    assert mcp_payload["ok"] is True
    assert mcp_payload["result"]["winner"] == "A"


def test_optimizer_objective_duel_api_cli_and_contract(env, capsys) -> None:
    jax = load_champion(ROOT, "Jax")
    jax_kit = load_kit(ROOT, "Jax")
    assert jax_kit is not None
    enemy = _make_fighter(
        env, "Garen", 11, items=["3071"], ranks={"Q": 5, "W": 1, "E": 3, "R": 2}, steps="Q"
    )
    out = optimize_build(
        ROOT,
        jax,
        11,
        "duel",
        constraints=OptimizeConstraints(slots=1, budget=3500, top=2, beam_width=4, pool_limit=6),
        issues=env["issues"],
        derived=env["derived"],
        kit=jax_kit,
        ranks={"Q": 1, "W": 5, "E": 3, "R": 2},
        steps=parse_steps("E.min, Q, W"),
        holder_range="melee",
        duel_enemy=enemy,
        duel_mode="scripted_then_attack",
    )
    assert out.objective == "duel"
    assert len(out.all_builds) >= 1
    assert out.all_builds[0].metrics["winner"] in {"A", "B", "draw_mutual_kill", "draw_timeout"}

    # CLI parity for optimize --objective duel
    rc = main(
        [
            "optimize",
            "--champion",
            "Jax",
            "--level",
            "11",
            "--objective",
            "duel",
            "--slots",
            "1",
            "--budget",
            "3500",
            "--top",
            "1",
            "--beam-width",
            "3",
            "--pool-limit",
            "5",
            "--learned",
            "Q=1",
            "--learned",
            "W=5",
            "--learned",
            "E=3",
            "--steps",
            "E.min, Q, W",
            "--enemy-champion",
            "Garen",
            "--enemy-level",
            "11",
            "--enemy-learned",
            "Q=5",
            "--enemy-steps",
            "Q",
            "--json",
            "--root",
            str(ROOT),
        ]
    )
    assert rc == 0
    cli_opt = json.loads(capsys.readouterr().out)
    assert cli_opt["objective"] == "duel"
    assert cli_opt["all_builds"]

    # Contract & MCP parity for optimize objective="duel"
    c_resp = execute_request(
        {
            "schema": "lol-knowledge-contract/1",
            "operation": "optimize",
            "params": {
                "champion": "Jax",
                "level": 11,
                "objective": "duel",
                "slots": 1,
                "budget": 3500,
                "top": 1,
                "beam_width": 3,
                "pool_limit": 5,
                "learned": {"Q": 1, "W": 5, "E": 3},
                "steps": "E.min, Q, W",
                "enemy": {
                    "champion": "Garen",
                    "level": 11,
                    "learned": {"Q": 5},
                    "steps": "Q",
                },
            },
        },
        ROOT,
    )
    assert c_resp["ok"] is True
    assert c_resp["result"]["objective"] == "duel"
    assert c_resp["result"]["all_builds"]
