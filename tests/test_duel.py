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
from lol_knowledge.errors import KitError, RotationError
from lol_knowledge.kit import load_kit, parse_kit, passive_contributions
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


def test_cc_stun_lock_and_tenacity_reduction(env) -> None:
    # Pantheon W stuns 1.0 s: plain victim acts at 1.0 s; Mercs (3111, 30% tenacity) acts at 0.7 s
    panth = _make_fighter(env, "Pantheon", 11, ranks={"W": 5}, steps="W.leap")
    victim_plain = _make_fighter(env, "Garen", 11, ranks={"Q": 5}, steps="wait:0.1, Q")
    victim_mercs = _make_fighter(
        env, "Garen", 11, items=["3111"], ranks={"Q": 5}, steps="wait:0.1, Q"
    )

    out_plain = evaluate_duel(panth, victim_plain, mode="strict_scripted")
    out_mercs = evaluate_duel(panth, victim_mercs, mode="strict_scripted")

    b_q_plain = [ev.time for ev in out_plain.events if ev.actor == "B" and ev.action == "Q"]
    b_q_mercs = [ev.time for ev in out_mercs.events if ev.actor == "B" and ev.action == "Q"]
    assert b_q_plain == [Fraction(1)]
    assert b_q_mercs == [Fraction(7, 10)]


def test_cc_airborne_and_suppression_immune_to_tenacity(env) -> None:
    # Malphite R (1.5 s airborne) and Malzahar R (2.5 s suppression) ignore Mercury's Treads (3111)
    malph = _make_fighter(env, "Malphite", 11, ranks={"R": 2}, steps="R")
    malz = _make_fighter(env, "Malzahar", 11, ranks={"R": 2}, steps="R.beam")
    victim_mercs = _make_fighter(
        env, "Garen", 11, items=["3111"], ranks={"Q": 5}, steps="wait:0.1, Q"
    )

    out_air = evaluate_duel(malph, victim_mercs, mode="strict_scripted")
    out_sup = evaluate_duel(malz, victim_mercs, mode="strict_scripted")

    t_air = [ev.time for ev in out_air.events if ev.actor == "B" and ev.action == "Q"]
    t_sup = [ev.time for ev in out_sup.events if ev.actor == "B" and ev.action == "Q"]
    assert t_air == [Fraction(3, 2)]
    assert t_sup == [Fraction(5, 2)]


def test_cc_silence_blocks_abilities_but_allows_basic_attacks(env) -> None:
    # Garen Q silences for 1.5 s: in priority_loop, Jax attacks during silence and casts W at 1.5 s
    garen = _make_fighter(env, "Garen", 11, ranks={"Q": 5}, steps="Q")
    jax = _make_fighter(env, "Jax", 11, ranks={"W": 5}, steps="wait:0.1", priority_slots=("W",))
    out = evaluate_duel(garen, jax, mode="priority_loop", max_duration=Fraction(3))
    b_attacks_during_silence = [
        ev.time
        for ev in out.events
        if ev.actor == "B" and ev.action == "attack" and Fraction(0) < ev.time < Fraction(3, 2)
    ]
    b_w_times = [ev.time for ev in out.events if ev.actor == "B" and ev.action == "W"]
    assert b_attacks_during_silence  # basic attacks continue while silenced
    assert b_w_times and b_w_times[0] >= Fraction(3, 2)  # abilities wait until silence ends


def test_cc_blind_makes_basic_attacks_miss_while_abilities_hit(env) -> None:
    # Teemo Q blinds for 3.0 s at rank 5: Garen's attack misses (0 dmg), while Garen Q/E still hit
    teemo = _make_fighter(env, "Teemo", 11, ranks={"Q": 5}, steps="Q")
    garen = _make_fighter(env, "Garen", 11, ranks={"Q": 5}, steps="wait:0.5, attack, Q")
    out = evaluate_duel(teemo, garen, mode="strict_scripted")
    atk_ev = [ev for ev in out.events if ev.actor == "B" and ev.action == "attack"]
    q_ev = [ev for ev in out.events if ev.actor == "B" and ev.action == "Q"]
    assert len(atk_ev) == 1 and atk_ev[0].damage_dealt == 0
    assert len(q_ev) == 1 and q_ev[0].damage_dealt > 0


def test_cc_taunt_blocks_abilities_allows_attacks(env) -> None:
    shen = _make_fighter(env, "Shen", 11, ranks={"E": 5}, steps="E")
    jax = _make_fighter(env, "Jax", 11, ranks={"W": 5}, steps="wait:0.2, attack, W")
    out = evaluate_duel(shen, jax, mode="strict_scripted")
    atk_t = [ev.time for ev in out.events if ev.actor == "B" and ev.action == "attack"]
    w_t = [ev.time for ev in out.events if ev.actor == "B" and ev.action == "W"]
    assert atk_t == [Fraction(1, 5)]  # attack allowed during taunt
    assert w_t == [Fraction(3, 2)]  # ability blocked until 1.5 s taunt ends


def test_cc_lulu_polymorph_and_sivir_spell_shield_intercept(env) -> None:
    # Lulu W (zero-damage 2.0 s polymorph) locks normal victim, but Sivir E blocks it and heals
    lulu = _make_fighter(env, "Lulu", 11, ranks={"W": 5}, steps="W")
    victim = _make_fighter(env, "Garen", 11, ranks={"Q": 5}, steps="wait:0.1, Q")
    out_locked = evaluate_duel(lulu, victim, mode="strict_scripted")
    assert [ev.time for ev in out_locked.events if ev.actor == "B" and ev.action == "Q"] == [
        Fraction(2)
    ]

    sivir = _make_fighter(
        env,
        "Sivir",
        11,
        ranks={"Q": 5, "E": 5},
        steps="E, wait:0.1, Q.pass",
        start_health=Fraction(800),
    )
    out_blocked = evaluate_duel(lulu, sivir, mode="strict_scripted")
    assert out_blocked.fighter_b.healing_done > 0
    q_times = [ev.time for ev in out_blocked.events if ev.actor == "B" and ev.action == "Q.pass"]
    assert q_times == [Fraction(1, 10)]


def test_cc_cleanse_vs_stun_and_suppression_and_tenacity_floor(env) -> None:
    # SummonerBoost clears Pantheon W stun immediately and reduces follow-up stun to 0.3 s floor
    panth = _make_fighter(env, "Pantheon", 11, ranks={"W": 5}, steps="W.leap")
    cleanser = _make_fighter(
        env,
        "Garen",
        11,
        ranks={"Q": 5},
        summoners=("SummonerBoost",),
        steps="wait:0.1, summoner:cleanse, Q",
    )
    out_cl = evaluate_duel(panth, cleanser, mode="strict_scripted")
    q_cl = [ev.time for ev in out_cl.events if ev.actor == "B" and ev.action == "Q"]
    assert q_cl == [Fraction(1, 10)]

    # SummonerBoost CANNOT cleanse Malzahar R suppression (2.5 s)
    malz = _make_fighter(env, "Malzahar", 11, ranks={"R": 2}, steps="R.beam")
    out_sup = evaluate_duel(malz, cleanser, mode="strict_scripted")
    q_sup = [ev.time for ev in out_sup.events if ev.actor == "B" and ev.action == "Q"]
    assert q_sup == [Fraction(5, 2)]

    # 75% Cleanse tenacity reduces a 1.0 s stun to max(0.3, 0.25) = 0.3 s minimum floor
    panth_late = _make_fighter(env, "Pantheon", 11, ranks={"W": 5}, steps="wait:0.2, W.leap")
    pre_cleanser = _make_fighter(
        env,
        "Garen",
        11,
        ranks={"Q": 5},
        summoners=("SummonerBoost",),
        steps="summoner:cleanse, wait:0.3, Q",
    )
    out_floor = evaluate_duel(panth_late, pre_cleanser, mode="strict_scripted")
    q_floor = [ev.time for ev in out_floor.events if ev.actor == "B" and ev.action == "Q"]
    assert q_floor == [Fraction(1, 2)]  # 0.2 s stun start + 0.3 s floor = 0.5 s


def test_cc_champion_cleanses_and_immunities(env) -> None:
    # Gangplank W cleanses Malzahar R suppression immediately
    malz = _make_fighter(env, "Malzahar", 11, ranks={"R": 2}, steps="R.beam")
    gp = _make_fighter(env, "Gangplank", 11, ranks={"Q": 5, "W": 5}, steps="wait:0.2, W, Q.shot")
    out_gp = evaluate_duel(malz, gp, mode="strict_scripted")
    assert [ev.time for ev in out_gp.events if ev.actor == "B" and ev.action == "Q.shot"] == [
        Fraction(1, 5)
    ]

    # Olaf R grants 3.0 s CC immunity, completely blocking Pantheon W stun
    panth = _make_fighter(env, "Pantheon", 11, ranks={"W": 5}, steps="wait:0.2, W.leap")
    olaf = _make_fighter(env, "Olaf", 11, ranks={"E": 5, "R": 2}, steps="R, wait:0.3, E")
    out_olaf = evaluate_duel(panth, olaf, mode="strict_scripted")
    assert [ev.time for ev in out_olaf.events if ev.actor == "B" and ev.action == "E"] == [
        Fraction(3, 10)
    ]

    # Fiora W (0.75 s Parry) blocks Pantheon W stun
    fiora = _make_fighter(env, "Fiora", 11, ranks={"Q": 5, "W": 5}, steps="W, wait:0.3, Q")
    out_fiora = evaluate_duel(panth, fiora, mode="strict_scripted")
    assert [ev.time for ev in out_fiora.events if ev.actor == "B" and ev.action == "Q"] == [
        Fraction(3, 10)
    ]


def test_cc_case_scoped_renekton_tf_and_vayne(env) -> None:
    victim = _make_fighter(env, "Garen", 11, ranks={"Q": 5}, steps="wait:0.1, Q")

    # Renekton W.basic stuns 0.75 s vs W.empowered stuns 1.5 s
    ren_base = _make_fighter(env, "Renekton", 11, ranks={"W": 5}, steps="W.basic")
    ren_emp = _make_fighter(env, "Renekton", 11, ranks={"W": 5}, steps="W.empowered")
    out_rb = evaluate_duel(ren_base, victim, mode="strict_scripted")
    out_re = evaluate_duel(ren_emp, victim, mode="strict_scripted")
    assert [ev.time for ev in out_rb.events if ev.actor == "B" and ev.action == "Q"] == [
        Fraction(3, 4)
    ]
    assert [ev.time for ev in out_re.events if ev.actor == "B" and ev.action == "Q"] == [
        Fraction(3, 2)
    ]

    # Twisted Fate W.gold_card stuns 2.0 s (rank 5); W.blue_card does NOT stun
    tf_gold = _make_fighter(env, "TwistedFate", 11, ranks={"W": 5}, steps="W.gold_card")
    tf_blue = _make_fighter(env, "TwistedFate", 11, ranks={"W": 5}, steps="W.blue_card")
    out_gold = evaluate_duel(tf_gold, victim, mode="strict_scripted")
    out_blue = evaluate_duel(tf_blue, victim, mode="strict_scripted")
    assert [ev.time for ev in out_gold.events if ev.actor == "B" and ev.action == "Q"] == [
        Fraction(2)
    ]
    assert [ev.time for ev in out_blue.events if ev.actor == "B" and ev.action == "Q"] == [
        Fraction(1, 10)
    ]

    # Vayne E.wall_stun stuns 1.5 s; Vayne E.hit does NOT stun
    vayne_wall = _make_fighter(env, "Vayne", 11, ranks={"E": 5}, steps="E.wall_stun")
    vayne_hit = _make_fighter(env, "Vayne", 11, ranks={"E": 5}, steps="E.hit")
    out_vw = evaluate_duel(vayne_wall, victim, mode="strict_scripted")
    out_vh = evaluate_duel(vayne_hit, victim, mode="strict_scripted")
    assert [ev.time for ev in out_vw.events if ev.actor == "B" and ev.action == "Q"] == [
        Fraction(3, 2)
    ]
    assert [ev.time for ev in out_vh.events if ev.actor == "B" and ev.action == "Q"] == [
        Fraction(1, 10)
    ]


def test_cc_effects_kit_schema_validation() -> None:
    base_doc = {
        "schema": "lol-champion-kit/1",
        "champion": "Test",
        "label": "Derivado",
        "game_version": "16.23",
        "content_version": "16.23.test",
        "abilities": {
            "Q": {
                "name": "Strike",
                "max_rank": 5,
                "cases": [],
                "passive_stats": [],
                "not_modelled": [],
                "cc_effects": [
                    {
                        "id": "q_stun",
                        "name": "Strike (aturdimiento)",
                        "kind": "not_a_cc",
                        "duration_formula": {"op": "constant", "value": 1.0},
                        "label": "Derivado",
                        "source": "test",
                    }
                ],
            }
        },
    }
    with pytest.raises(KitError, match="unknown kind"):
        parse_kit(base_doc)

    base_doc["abilities"]["Q"]["cc_effects"][0]["kind"] = "stun"
    base_doc["abilities"]["Q"]["cc_effects"][0]["case_ids"] = ["missing_case"]
    with pytest.raises(KitError, match="unknown case_ids"):
        parse_kit(base_doc)


def test_pure_cc_abilities_in_duel_and_priority_loop(env) -> None:
    """FIX-01: pure-CC abilities (Veigar E, Elise E, Viktor W, Renata R) work in duel."""
    veigar = _make_fighter(env, "Veigar", 11, ranks={"Q": 5, "W": 3, "E": 2, "R": 2}, steps="E, Q")
    victim = _make_fighter(env, "Garen", 11, ranks={"Q": 5}, steps="wait:0.1, Q")
    out = evaluate_duel(veigar, victim, mode="strict_scripted")
    # Veigar E at rank 2 stuns for 1.75 s -> Garen Q waits until 1.75 s
    b_q = [ev.time for ev in out.events if ev.actor == "B" and ev.action == "Q"]
    assert b_q == [Fraction(7, 4)]

    # priority_loop includes pure-CC slots (e.g. Elise E, Viktor W, Renata R)
    elise = _make_fighter(
        env, "Elise", 11, ranks={"E": 5}, steps="", priority_slots=("E",), holder_range="ranged"
    )
    out_prio = evaluate_duel(elise, victim, mode="priority_loop", max_duration=Fraction(4))
    assert any(ev.actor == "A" and ev.action == "E" for ev in out_prio.events)
    b_q_prio = [ev.time for ev in out_prio.events if ev.actor == "B" and ev.action == "Q"]
    assert b_q_prio == [Fraction(12, 5)]  # Elise E rank 5 stun = 2.4 s

    for champ, slot, expected_delay in (
        ("Viktor", "W", Fraction(3, 2)),
        ("Renata", "R", Fraction(7, 4)),
    ):
        caster = _make_fighter(env, champ, 11, ranks={slot: 2}, steps=slot, priority_slots=(slot,))
        res = evaluate_duel(caster, victim, mode="strict_scripted")
        assert any(ev.actor == "A" and ev.action == slot for ev in res.events)
        assert [ev.time for ev in res.events if ev.actor == "B" and ev.action == "Q"] == [
            expected_delay
        ]


def test_readme_darius_vs_garen_duel_across_cli_contract_and_mcp(capsys) -> None:
    """Verify the README Darius vs Garen duel passes across CLI, Contract JSON, and MCP."""
    rc = main(
        [
            "duel",
            "--a-champion",
            "Darius",
            "--a-level",
            "11",
            "--a-item",
            "3078",
            "--a-range",
            "melee",
            "--a-learned",
            "Q=5",
            "--a-learned",
            "W=1",
            "--a-learned",
            "E=3",
            "--a-learned",
            "R=2",
            "--a-steps",
            "attack, W, Q.blade, R.base",
            "--b-champion",
            "Garen",
            "--b-level",
            "11",
            "--b-item",
            "3078",
            "--b-range",
            "melee",
            "--b-learned",
            "Q=5",
            "--b-learned",
            "W=1",
            "--b-learned",
            "E=3",
            "--b-learned",
            "R=2",
            "--b-steps",
            "Q, E.tick, R",
            "--json",
            "--root",
            str(ROOT),
        ]
    )
    assert rc == 0
    cli_duel = json.loads(capsys.readouterr().out)
    assert cli_duel["winner"] == "A"

    duel_params = {
        "fighter_a": {
            "champion": "Darius",
            "level": 11,
            "items": ["3078"],
            "range": "melee",
            "learned": {"Q": 5, "W": 1, "E": 3, "R": 2},
            "steps": "attack, W, Q.blade, R.base",
        },
        "fighter_b": {
            "champion": "Garen",
            "level": 11,
            "items": ["3078"],
            "range": "melee",
            "learned": {"Q": 5, "W": 1, "E": 3, "R": 2},
            "steps": "Q, E.tick, R",
        },
    }
    c_resp = execute_request(
        {"schema": "lol-knowledge-contract/1", "operation": "duel", "params": duel_params},
        ROOT,
    )
    assert c_resp["ok"] is True
    assert c_resp["result"]["winner"] == "A"
    assert c_resp["result"]["duration"] == cli_duel["duration"]

    server = MCPServer(ROOT)
    mcp_reply = server.handle_message(
        {
            "jsonrpc": "2.0",
            "id": 99,
            "method": "tools/call",
            "params": {"name": "lol_duel", "arguments": duel_params},
        }
    )
    assert mcp_reply is not None
    mcp_res = mcp_reply["result"]
    assert mcp_res["isError"] is False
    assert mcp_res["structuredContent"]["result"]["winner"] == "A"
    assert mcp_res["structuredContent"]["result"]["duration"] == cli_duel["duration"]

    # Pure-CC ability (Veigar E) across CLI, Contract JSON, and MCP (FIX-01)
    rc_cc = main(
        [
            "duel",
            "--a-champion",
            "Veigar",
            "--a-level",
            "11",
            "--a-learned",
            "Q=5",
            "--a-learned",
            "E=2",
            "--a-steps",
            "E, Q",
            "--b-champion",
            "Garen",
            "--b-level",
            "11",
            "--b-learned",
            "Q=5",
            "--b-steps",
            "wait:0.1, Q",
            "--mode",
            "strict_scripted",
            "--json",
            "--root",
            str(ROOT),
        ]
    )
    assert rc_cc == 0
    cli_cc = json.loads(capsys.readouterr().out)
    veigar_params = {
        "fighter_a": {
            "champion": "Veigar",
            "level": 11,
            "learned": {"Q": 5, "E": 2},
            "steps": "E, Q",
        },
        "fighter_b": {
            "champion": "Garen",
            "level": 11,
            "learned": {"Q": 5},
            "steps": "wait:0.1, Q",
        },
        "mode": "strict_scripted",
    }
    c_cc = execute_request(
        {"schema": "lol-knowledge-contract/1", "operation": "duel", "params": veigar_params},
        ROOT,
    )
    assert c_cc["ok"] is True
    assert c_cc["result"]["duration"] == cli_cc["duration"]
    mcp_cc = server.handle_message(
        {
            "jsonrpc": "2.0",
            "id": 100,
            "method": "tools/call",
            "params": {"name": "lol_duel", "arguments": veigar_params},
        }
    )
    assert mcp_cc is not None
    assert mcp_cc["result"]["isError"] is False
    assert mcp_cc["result"]["structuredContent"]["result"]["duration"] == cli_cc["duration"]
