"""Tests for Summoner's Rift summoner spells across stats, rotation, survive, optimize & MCP."""

from __future__ import annotations

import json
from fractions import Fraction as F
from pathlib import Path

import pytest

from lol_knowledge.cli import main as cli_main
from lol_knowledge.contract import execute_request
from lol_knowledge.defense import evaluate_defense, parse_incoming
from lol_knowledge.errors import RotationError, StatsError
from lol_knowledge.kit import load_kit
from lol_knowledge.mcp_server import MCPServer
from lol_knowledge.optimizer import OptimizeConstraints, optimize_build
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
from lol_knowledge.summoners import (
    barrier_shield,
    effective_cooldown,
    exhaust_values,
    ghost_ms,
    heal_amount,
    ignite_damage,
    load_summoner_spells,
    resolve_loadout,
    smite_damage,
    summoner_problems,
    summoner_sheet_effects,
    summoner_spell_haste,
)

ROOT = Path(__file__).resolve().parents[1]
ISSUES = load_issues(ROOT)
RECORDS = load_records(ROOT)
RUNE_DATA = load_runes(ROOT)
SUMMONERS = load_summoner_spells(ROOT)


def test_summoner_data_curves_aliases_legality_and_haste() -> None:
    assert SUMMONERS is not None
    assert len(SUMMONERS.spells) == 9
    assert SUMMONERS.matches_patch("16.23.1")

    # Alias / Spanish / accent-insensitive resolution
    assert SUMMONERS.resolve("ignite").id == "SummonerDot"
    assert SUMMONERS.resolve("Prender").id == "SummonerDot"
    assert SUMMONERS.resolve("extenuación").id == "SummonerExhaust"
    assert SUMMONERS.resolve("extenuacion").id == "SummonerExhaust"
    assert SUMMONERS.resolve("tp").id == "SummonerTeleport"

    # Exact client 16.23 level curves
    dot = SUMMONERS.resolve("ignite")
    assert ignite_damage(dot, 1) == F(70)
    assert ignite_damage(dot, 5) == F(150)
    assert ignite_damage(dot, 6) == F(175)
    assert ignite_damage(dot, 18) == F(475)

    bar = SUMMONERS.resolve("barrier")
    assert barrier_shield(bar, 1) == F(100)
    assert barrier_shield(bar, 18) == F(460)

    hl = SUMMONERS.resolve("heal")
    assert heal_amount(hl, 1) == F(80)
    assert heal_amount(hl, 18) == F(318)
    assert heal_amount(hl, 18, debuffed=True) == F(159)

    ex = SUMMONERS.resolve("exhaust")
    assert exhaust_values(ex) == (F(35, 100), F(40, 100), F(3))

    gh = SUMMONERS.resolve("ghost")
    assert ghost_ms(gh, 1) == (F(24, 100), F(10))
    assert ghost_ms(gh, 18) == (F(48, 100), F(10))

    sm = SUMMONERS.resolve("smite")
    assert smite_damage(sm, target_kind="monster", tier=0)[0] == F(600)
    assert smite_damage(sm, target_kind="monster", tier=1)[0] == F(1000)
    assert smite_damage(sm, target_kind="monster", tier=2)[0] == F(1400)
    assert smite_damage(sm, target_kind="champion", tier=1)[0] == F(40)
    with pytest.raises(StatsError, match="structures"):
        smite_damage(sm, target_kind="structure", tier=0)

    # Summoner Haste: Cosmic Insight (+18) + Ionian Boots (+10) = +28; Flash -> 300*100/128
    boots = load_items(ROOT, ["3158"])
    haste = summoner_spell_haste(boots, [8347], RUNE_DATA)
    assert haste == F(28)
    flash = SUMMONERS.resolve("flash")
    assert effective_cooldown(flash, level=11, summoner_haste=haste) == F(30000, 128)
    tp = SUMMONERS.resolve("teleport")
    assert effective_cooldown(tp, level=18, unleashed=True) == F(150)

    # Loadout legality: <= 2 unique spells
    with pytest.raises(StatsError, match="at most 2"):
        resolve_loadout(["flash", "ignite", "barrier"], SUMMONERS)
    with pytest.raises(StatsError, match="duplicate"):
        resolve_loadout(["flash", "SummonerFlash"], SUMMONERS)
    with pytest.raises(StatsError, match="unknown summoner spell"):
        resolve_loadout(["clairvoyance_fake"], SUMMONERS)

    # Validation helper rejects invalid schema
    assert summoner_problems({"schema": "wrong"})


def test_summoner_sheet_buffs_ghost_heal_teleport_and_cleanse() -> None:
    assert SUMMONERS is not None
    champ = load_champion(ROOT, "Garen")
    base = build_stat_sheet(champ, 18, [], ISSUES, {}, RECORDS)
    specs, _ = resolve_loadout(["ghost", "cleanse"], SUMMONERS)
    fx = summoner_sheet_effects(
        specs,
        SUMMONERS,
        level=18,
        patch=champ.patch,
        inputs={"ghost_active": F(1), "cleanse_active": F(1)},
    )
    boosted = build_stat_sheet(
        champ, 18, [], ISSUES, {}, RECORDS, fx.flats, fx.percents, extra_notes=fx.notes
    )
    assert boosted["move_speed"].total() > base["move_speed"].total()
    assert boosted["tenacity"].total() == F(3, 4)


def test_summoner_spells_in_rotation_ignite_smite_barrier_heal_ghost_and_exhaust() -> None:
    assert SUMMONERS is not None
    ahri = load_champion(ROOT, "Ahri")
    ahri_kit = load_kit(ROOT, "Ahri")
    assert ahri_kit is not None
    sheet = build_stat_sheet(ahri, 18, [], ISSUES, {}, RECORDS)
    champ_target = target_from_values(F(80), F(60), max_health=F(2500), kind="champion")

    # 1. Ignite non-timeline: exact 475 true damage at level 18, zero vamp even with omnivamp item
    rot_ig = evaluate_rotation(
        ahri_kit,
        sheet,
        {"Q": 5},
        champ_target,
        parse_steps("summoner:ignite"),
        None,
        holder_range="ranged",
        summoners=["flash", "ignite"],
        summoner_data=SUMMONERS,
    )
    assert rot_ig.total == F(475)
    assert rot_ig.healing == F(0)

    # 2. Ignite with --timeline spreads over 5 s and finishes in tail burn totaling 475
    rot_ig_tl = evaluate_rotation(
        ahri_kit,
        sheet,
        {"Q": 5},
        champ_target,
        parse_steps("summoner:ignite"),
        None,
        holder_range="ranged",
        timeline=True,
        summoners=["flash", "ignite"],
        summoner_data=SUMMONERS,
    )
    assert rot_ig_tl.total == F(475)
    assert rot_ig_tl.duration == F(5)

    # 3. Ignite refuses non-champion targets; duplicate cast rejected; unequipped summoner rejected
    monster_target = target_from_values(F(40), F(40), max_health=F(3000), kind="monster")
    with pytest.raises(RotationError, match="only target champions"):
        evaluate_rotation(
            ahri_kit,
            sheet,
            {},
            monster_target,
            parse_steps("summoner:ignite"),
            None,
            summoner_data=SUMMONERS,
        )
    with pytest.raises(RotationError, match="only be cast once"):
        evaluate_rotation(
            ahri_kit,
            sheet,
            {},
            champ_target,
            parse_steps("summoner:ignite, summoner:ignite"),
            None,
            summoner_data=SUMMONERS,
        )
    with pytest.raises(RotationError, match="not in equipped summoners"):
        evaluate_rotation(
            ahri_kit,
            sheet,
            {},
            champ_target,
            parse_steps("summoner:ignite"),
            None,
            summoners=["flash", "barrier"],
            summoner_data=SUMMONERS,
        )

    # 4. Smite: 1400 true damage to monster at tier 2, 40 true damage to champion
    rot_smite_m = evaluate_rotation(
        ahri_kit,
        sheet,
        {},
        monster_target,
        parse_steps("summoner:smite"),
        None,
        inputs={"smite_tier": F(2)},
        summoner_data=SUMMONERS,
    )
    assert rot_smite_m.total == F(1400)
    rot_smite_c = evaluate_rotation(
        ahri_kit,
        sheet,
        {},
        champ_target,
        parse_steps("summoner:smite"),
        None,
        inputs={"smite_tier": F(1)},
        summoner_data=SUMMONERS,
    )
    assert rot_smite_c.total == F(40)

    # 5. Barrier grants 460 shield at lvl 18 + triggers Shield Bash (8401) on following attack!
    rot_bar = evaluate_rotation(
        ahri_kit,
        sheet,
        {},
        champ_target,
        parse_steps("summoner:barrier, attack"),
        None,
        holder_range="ranged",
        runes=[8437, 8401, 8473, 8451, 9111, 9104],
        rune_data=RUNE_DATA,
        summoner_data=SUMMONERS,
    )
    assert rot_bar.total_shield_granted == F(460)
    assert any("8401" in p.source for p in rot_bar.steps[1].parts)

    # 6. Heal restores 318 HP at lvl 18 (halved with heal_debuffed=1)
    rot_heal = evaluate_rotation(
        ahri_kit,
        sheet,
        {},
        champ_target,
        parse_steps("summoner:heal"),
        None,
        summoner_data=SUMMONERS,
    )
    assert rot_heal.healing == F(318)
    rot_heal_deb = evaluate_rotation(
        ahri_kit,
        sheet,
        {},
        champ_target,
        parse_steps("summoner:heal"),
        None,
        inputs={"heal_debuffed": F(1)},
        summoner_data=SUMMONERS,
    )
    assert rot_heal_deb.healing == F(159)

    # 7. Ghost boosts Hecarim's passive AD from MS on the following basic attack!
    heca = load_champion(ROOT, "Hecarim")
    heca_kit = load_kit(ROOT, "Hecarim")
    assert heca_kit is not None
    heca_sheet = build_stat_sheet(heca, 18, [], ISSUES, {}, RECORDS)
    heca_plain = evaluate_rotation(
        heca_kit, heca_sheet, {}, champ_target, parse_steps("attack"), None, holder_range="melee"
    )
    heca_ghost = evaluate_rotation(
        heca_kit,
        heca_sheet,
        {},
        champ_target,
        parse_steps("summoner:ghost, attack"),
        None,
        holder_range="melee",
        summoner_data=SUMMONERS,
    )
    assert heca_ghost.total > heca_plain.total

    # 8. Attacker exhausted=1 reduces physical/magic by 35% and leaves true damage untouched
    rot_q_plain = evaluate_rotation(
        ahri_kit,
        sheet,
        {"Q": 5},
        champ_target,
        parse_steps("Q.both"),
        None,
        holder_range="ranged",
        summoner_data=SUMMONERS,
    )
    rot_q_ex = evaluate_rotation(
        ahri_kit,
        sheet,
        {"Q": 5},
        champ_target,
        parse_steps("Q.both"),
        None,
        holder_range="ranged",
        inputs={"exhausted": F(1)},
        summoner_data=SUMMONERS,
    )
    # Q.both[0] is magic (reduced 35%), Q.both[1] is true (untouched!)
    assert rot_q_ex.steps[0].parts[0].damage == rot_q_plain.steps[0].parts[0].damage * F(65, 100)
    assert rot_q_ex.steps[0].parts[1].damage == rot_q_plain.steps[0].parts[1].damage


def test_summoner_spells_in_survive_and_optimize() -> None:
    assert SUMMONERS is not None
    lux = load_champion(ROOT, "Lux")
    sheet = build_stat_sheet(lux, 18, [], ISSUES, {}, RECORDS)

    # 1. Barrier absorbs 460 at lvl 18 and expires after 2.5 s in --timeline
    hits_timed = parse_incoming("magic:300, wait:3, magic:300")
    plain = evaluate_defense(sheet, hits_timed, timeline=True)
    bar = evaluate_defense(
        sheet, hits_timed, timeline=True, summoners=["barrier"], summoner_data=SUMMONERS
    )
    assert bar.total_shield_granted == F(460)
    assert bar.steps[0].shield_absorbed == bar.steps[0].damage_after_flat
    # Hit at t=3s happens after Barrier's 2.5 s duration expired -> 0 shield absorbed!
    assert bar.steps[2].shield_absorbed == F(0)
    assert bar.remaining_health > plain.remaining_health

    # 2. Exhaust reduces physical/magic by 35% for 3 s, expires at 3.5 s, never reduces true damage
    hits_ex = parse_incoming("magic:500, true:200, wait:3.5, magic:500")
    ex_plain = evaluate_defense(sheet, hits_ex, timeline=True)
    ex_def = evaluate_defense(
        sheet, hits_ex, timeline=True, summoners=["exhaust"], summoner_data=SUMMONERS
    )
    assert ex_def.steps[0].damage_after_flat == ex_plain.steps[0].damage_after_flat * F(65, 100)
    assert ex_def.steps[1].damage_after_flat == ex_plain.steps[1].damage_after_flat  # true dmg!
    assert ex_def.steps[3].damage_after_flat == ex_plain.steps[3].damage_after_flat  # after 3 s!

    # 3. Heal triggers reactively after non-lethal hit from full HP and proactively when damaged
    hits_two = parse_incoming("magic:600, magic:600")
    h_plain = evaluate_defense(sheet, hits_two, timeline=True)
    h_def = evaluate_defense(
        sheet, hits_two, timeline=True, summoners=["heal"], summoner_data=SUMMONERS
    )
    assert h_def.total_healing == F(318)
    assert h_def.remaining_health - h_plain.remaining_health == F(318)

    # 4. Cleanse emits clear cleanse/tenacity note
    cl_def = evaluate_defense(
        sheet, parse_incoming("magic:300"), summoners=["cleanse"], summoner_data=SUMMONERS
    )
    assert any("SummonerBoost" in n for n in cl_def.notes)

    # 5. Optimizer time_to_die honors summoners=["barrier", "exhaust"]
    cfg = OptimizeConstraints(
        slots=1, budget=3200, only_verified=True, top=1, beam_width=4, pool_limit=6
    )
    opt_plain = optimize_build(
        ROOT,
        lux,
        18,
        "time_to_die",
        constraints=cfg,
        derived=RECORDS,
        incoming_hits=parse_incoming("magic:1200, magic:1200"),
        timeline=True,
    )
    opt_summ = optimize_build(
        ROOT,
        lux,
        18,
        "time_to_die",
        constraints=cfg,
        derived=RECORDS,
        incoming_hits=parse_incoming("magic:1200, magic:1200"),
        timeline=True,
        summoners=["barrier", "exhaust"],
    )
    assert opt_summ.verified_builds[0].score > opt_plain.verified_builds[0].score


def test_summoner_spells_cli_contract_and_mcp_roundtrip(capsys) -> None:
    # 1. CLI rotation with --summoner and summoner:ignite
    rc = cli_main(
        [
            "rotation",
            "--champion",
            "Ahri",
            "--level",
            "18",
            "--learned",
            "Q=5",
            "--steps",
            "Q.both, summoner:ignite",
            "--summoner",
            "flash",
            "--summoner",
            "ignite",
            "--target-armor",
            "80",
            "--target-mr",
            "60",
            "--target-max-health",
            "2500",
            "--target-kind",
            "champion",
            "--root",
            str(ROOT),
            "--json",
        ]
    )
    assert rc == 0
    rot_json = json.loads(capsys.readouterr().out)
    assert rot_json["steps"][1]["total"] == 475.0

    # 2. Contract lookup entity="summoners"
    lk = execute_request({"operation": "lookup", "params": {"entity": "summoners"}}, ROOT)
    assert lk["ok"] is True
    assert lk["result"]["total_summoners"] == 9

    # 3. MCP server tools/list & lol_survive with summoners
    server = MCPServer(ROOT)
    tools_reply = server.handle_message(
        {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}
    )
    assert tools_reply is not None
    by_name = {t["name"]: t["inputSchema"]["properties"] for t in tools_reply["result"]["tools"]}
    assert "summoners" in by_name["lol_lookup"]["entity"]["enum"]
    for tname in ("lol_stats", "lol_ability", "lol_rotation", "lol_survive", "lol_optimize"):
        assert "summoners" in by_name[tname]

    surv_reply = server.handle_message(
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {
                "name": "lol_survive",
                "arguments": {
                    "champion": "Lux",
                    "level": 18,
                    "summoners": ["barrier", "exhaust"],
                    "incoming": "magic:1000",
                    "timeline": True,
                },
            },
        }
    )
    assert surv_reply is not None
    res = surv_reply["result"]
    assert res["isError"] is False
    assert res["structuredContent"]["result"]["total_shield_granted"] == 460.0
