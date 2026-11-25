"""Tests for LoL-Knowledge Engine v1.0 features (OPT-04, OPT-05, OBJ-12, MEC-21, OBJ-05)."""

from __future__ import annotations

import json
from fractions import Fraction
from pathlib import Path

import pytest

from lol_knowledge.cli import main
from lol_knowledge.contract import execute_request
from lol_knowledge.errors import RotationError, StatsError
from lol_knowledge.kit import load_kit
from lol_knowledge.mcp_server import MCPServer
from lol_knowledge.objects.legality import load_item_groups
from lol_knowledge.optimizer import (
    OptimizeConstraints,
    default_champion_rotation,
    optimize_build,
)
from lol_knowledge.optimizer import (
    format_text as format_optimize_text,
)
from lol_knowledge.rotation import evaluate_rotation, parse_steps
from lol_knowledge.scenario import target_from_values
from lol_knowledge.stats import (
    build_stat_sheet,
    load_champion,
    load_issues,
    load_items,
    load_records,
)
from lol_knowledge.upgrades import (
    ORNN_STAT_GOLD_EFFICIENCY,
    ORNN_TOTAL_GOLD_VALUE,
    elixir_contributions,
    ornn_upgrade_contributions,
)

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def env():
    return {
        "issues": load_issues(ROOT),
        "derived": load_records(ROOT),
        "groups": load_item_groups(ROOT),
    }


def test_elixirs_stats_aliases_and_errors(env, capsys) -> None:
    iron = elixir_contributions("iron", level=11)
    assert iron.elixir_id == "2138"
    assert iron.extra_gold == 500
    assert dict((k, c.value) for k, c in iron.flats) == {
        "health": Fraction(300),
        "tenacity": Fraction(25, 100),
    }

    sorc_mana = elixir_contributions("2139", level=11, uses_mana=True)
    sorc_nomana = elixir_contributions("brujería", level=11, uses_mana=False)
    assert dict((k, c.value) for k, c in sorc_mana.flats) == {"ability_power": Fraction(50)}
    assert len(sorc_mana.percents) == 1
    assert len(sorc_nomana.percents) == 0

    wrath = elixir_contributions("wrath", level=11)
    assert dict((k, c.value) for k, c in wrath.flats) == {"attack_damage": Fraction(30)}

    with pytest.raises(StatsError, match="unknown elixir"):
        elixir_contributions("not_an_elixir")

    # CLI & Contract parity for --elixir
    rc = main(
        [
            "stats",
            "--champion",
            "Garen",
            "--level",
            "11",
            "--elixir",
            "iron",
            "--json",
            "--root",
            str(ROOT),
        ]
    )
    assert rc == 0
    cli_data = json.loads(capsys.readouterr().out)
    assert cli_data["stats"]["tenacity"]["total"] == pytest.approx(0.25)

    c_resp = execute_request(
        {
            "schema": "lol-knowledge-contract/1",
            "operation": "stats",
            "params": {"champion": "Ahri", "level": 11, "elixir": "2139"},
        },
        ROOT,
    )
    assert c_resp["ok"] is True
    assert c_resp["result"]["stats"]["ability_power"]["total"] == pytest.approx(50.0)


def test_ornn_masterwork_exact_efficiencies_and_legality(env) -> None:
    # Rabadon (3089) has 1 eligible stat (ability_power): 1000 / 20 = +50 AP
    rab = load_items(ROOT, ["3089"])
    fx_rab = ornn_upgrade_contributions("3089", rab, level=13, item_groups=env["groups"])
    assert fx_rab.ornn_item_id == "3089"
    assert fx_rab.extra_gold == 0
    assert dict((k, c.value) for k, c in fx_rab.flats) == {
        "ability_power": ORNN_TOTAL_GOLD_VALUE / ORNN_STAT_GOLD_EFFICIENCY["ability_power"]
    }

    # Black Cleaver (3071) splits 1000 g equally across AD, HP, AH (333.33 g each)
    bc = load_items(ROOT, ["3071"])
    fx_bc = ornn_upgrade_contributions("3071", bc, level=13, item_groups=env["groups"])
    bc_map = {k: c.value for k, c in fx_bc.flats}
    assert set(bc_map) == {"attack_damage", "health", "ability_haste"}
    share = ORNN_TOTAL_GOLD_VALUE / 3
    for st_id, val in bc_map.items():
        assert val == share / ORNN_STAT_GOLD_EFFICIENCY[st_id]

    # Boots (3111) are not eligible; unequipped item is rejected
    boots = load_items(ROOT, ["3111"])
    with pytest.raises(StatsError, match="not eligible"):
        ornn_upgrade_contributions("3111", boots, level=13, item_groups=env["groups"])
    with pytest.raises(StatsError, match="equipped"):
        ornn_upgrade_contributions("3089", boots, level=13, item_groups=env["groups"])


def test_optimizer_ornn_auto_upgrade_and_elixir(env) -> None:
    ahri = load_champion(ROOT, "Ahri")
    out_plain = optimize_build(
        ROOT,
        ahri,
        13,
        "effective_health_physical",
        constraints=OptimizeConstraints(slots=2, top=1, beam_width=4, pool_limit=6),
        issues=env["issues"],
        derived=env["derived"],
    )
    out_ornn = optimize_build(
        ROOT,
        ahri,
        13,
        "effective_health_physical",
        constraints=OptimizeConstraints(
            slots=2,
            top=1,
            beam_width=4,
            pool_limit=6,
            ornn_upgrade=True,
            elixir="iron",
        ),
        issues=env["issues"],
        derived=env["derived"],
    )
    assert out_ornn.verified_builds
    best = out_ornn.verified_builds[0]
    assert best.ornn_upgraded_item in best.items
    assert best.elixir == "2138"
    assert best.score > out_plain.verified_builds[0].score


def test_optimizer_purchase_curve_and_gold_checkpoints(env, capsys) -> None:
    garen = load_champion(ROOT, "Garen")
    out = optimize_build(
        ROOT,
        garen,
        11,
        "effective_health_physical",
        constraints=OptimizeConstraints(
            slots=3,
            top=1,
            beam_width=4,
            pool_limit=6,
            purchase_curve=True,
            gold_checkpoints=(3500, 7000),
        ),
        issues=env["issues"],
        derived=env["derived"],
    )
    assert len(out.purchase_curve) == 3
    assert [s.order for s in out.purchase_curve] == [1, 2, 3]
    # Cumulative gold and scores increase along the purchase curve
    assert out.purchase_curve[0].cumulative_gold < out.purchase_curve[1].cumulative_gold
    assert out.purchase_curve[1].cumulative_gold < out.purchase_curve[2].cumulative_gold
    assert out.purchase_curve[2].score == out.verified_builds[0].score
    assert all(s.delta_score > 0 and s.score_per_1000g > 0 for s in out.purchase_curve)

    # Gold checkpoints respect budgets and progress monotonically
    assert [cp.gold_budget for cp in out.gold_checkpoints] == [3500, 7000]
    assert out.gold_checkpoints[0].build is not None
    assert out.gold_checkpoints[1].build is not None
    assert out.gold_checkpoints[0].build.total_gold <= 3500
    assert out.gold_checkpoints[1].build.total_gold <= 7000
    assert out.gold_checkpoints[1].build.score >= out.gold_checkpoints[0].build.score

    text = format_optimize_text(out)
    assert "purchase curve (OPT-04):" in text
    assert "gold checkpoints (OPT-04):" in text

    # CLI + MCP parity
    rc = main(
        [
            "optimize",
            "--champion",
            "Garen",
            "--level",
            "11",
            "--objective",
            "effective_health_physical",
            "--slots",
            "2",
            "--top",
            "1",
            "--beam-width",
            "3",
            "--pool-limit",
            "5",
            "--purchase-curve",
            "--gold-checkpoints",
            "3500,7000",
            "--json",
            "--root",
            str(ROOT),
        ]
    )
    assert rc == 0
    cli_opt = json.loads(capsys.readouterr().out)
    assert len(cli_opt["purchase_curve"]) == 2
    assert len(cli_opt["gold_checkpoints"]) == 2

    server = MCPServer(ROOT)
    mcp_res = server.handle_message(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "lol_optimize",
                "arguments": {
                    "champion": "Garen",
                    "level": 11,
                    "objective": "effective_health_physical",
                    "slots": 2,
                    "top": 1,
                    "beam_width": 3,
                    "pool_limit": 5,
                    "purchase_curve": True,
                    "gold_checkpoints": [3500, 7000],
                    "ornn_upgrade": True,
                },
            },
        }
    )
    assert mcp_res is not None and mcp_res["result"]["isError"] is False
    mcp_env = json.loads(mcp_res["result"]["content"][0]["text"])
    assert mcp_env["ok"] is True
    assert len(mcp_env["result"]["purchase_curve"]) == 2
    assert len(mcp_env["result"]["gold_checkpoints"]) == 2


def test_optimizer_auto_rotation_without_steps(env, capsys) -> None:
    ahri = load_champion(ROOT, "Ahri")
    kit = load_kit(ROOT, "Ahri")
    assert kit is not None
    auto = default_champion_rotation(kit, {"Q": 5, "W": 5, "E": 1, "R": 2})
    assert any(s.slot == "Q" for s in auto)
    assert any(s.slot is None for s in auto)

    # Optimize DPS with NO steps provided -> auto-generates standard rotation
    target = target_from_values(Fraction(60), Fraction(50), max_health=Fraction(2000))
    out = optimize_build(
        ROOT,
        ahri,
        11,
        "dps",
        constraints=OptimizeConstraints(slots=1, top=1, beam_width=3, pool_limit=5),
        issues=env["issues"],
        derived=env["derived"],
        kit=kit,
        ranks={"Q": 5, "W": 5, "E": 1, "R": 2},
        target=target,
        steps=(),
        holder_range="ranged",
    )
    assert out.auto_steps
    assert out.all_builds

    # CLI parity without --steps
    rc = main(
        [
            "optimize",
            "--champion",
            "Ahri",
            "--level",
            "11",
            "--objective",
            "dps",
            "--slots",
            "1",
            "--top",
            "1",
            "--beam-width",
            "3",
            "--pool-limit",
            "5",
            "--learned",
            "Q=5",
            "--learned",
            "W=5",
            "--target-armor",
            "60",
            "--target-mr",
            "50",
            "--target-max-health",
            "2000",
            "--json",
            "--root",
            str(ROOT),
        ]
    )
    assert rc == 0
    cli_auto = json.loads(capsys.readouterr().out)
    assert cli_auto["auto_steps"]
    assert cli_auto["all_builds"]


def test_rotation_timeline_windows_and_cli_contract(env, capsys) -> None:
    jax = load_champion(ROOT, "Jax")
    kit = load_kit(ROOT, "Jax")
    assert kit is not None
    sheet = build_stat_sheet(jax, 11, [], env["issues"], None, env["derived"])
    target = target_from_values(Fraction(60), Fraction(50), max_health=Fraction(3000))
    steps = parse_steps("attack, attack, attack, attack, attack, attack")
    out = evaluate_rotation(kit, sheet, {}, target, steps, None, timeline=True)
    w2 = out.window(Fraction(2))
    w5 = out.window(Fraction(5))
    assert w2.seconds == Fraction(2)
    assert w5.seconds == Fraction(5)
    assert w2.total > 0
    assert w5.total >= w2.total
    assert w2.damage_per_second == w2.total / 2
    assert w5.steps_count >= w2.steps_count

    # Non-timeline outcome rejects window()
    out_no_tl = evaluate_rotation(kit, sheet, {}, target, steps, None, timeline=False)
    with pytest.raises(RotationError, match="timeline"):
        out_no_tl.window(Fraction(2))

    # CLI --window + Contract windows parity
    rc = main(
        [
            "rotation",
            "--champion",
            "Jax",
            "--level",
            "11",
            "--steps",
            "attack, attack, attack, attack, attack",
            "--timeline",
            "--window",
            "2",
            "--window",
            "4",
            "--target-armor",
            "60",
            "--target-mr",
            "50",
            "--target-max-health",
            "3000",
            "--json",
            "--root",
            str(ROOT),
        ]
    )
    assert rc == 0
    rep = json.loads(capsys.readouterr().out)
    assert [w["seconds"] for w in rep["windows"]] == [2.0, 4.0]
    assert rep["windows"][1]["total"] >= rep["windows"][0]["total"]

    c_resp = execute_request(
        {
            "schema": "lol-knowledge-contract/1",
            "operation": "rotation",
            "params": {
                "champion": "Jax",
                "level": 11,
                "steps": "attack, attack, attack, attack, attack",
                "timeline": True,
                "windows": [2, 4],
                "target": {"armor": 60, "mr": 50, "max_health": 3000},
            },
        },
        ROOT,
    )
    assert c_resp["ok"] is True
    assert len(c_resp["result"]["windows"]) == 2


def test_guinsoo_phantom_hit_adds_kraken_stack(env) -> None:
    jax = load_champion(ROOT, "Jax")
    kit = load_kit(ROOT, "Jax")
    assert kit is not None
    items_both = load_items(ROOT, ["3124", "6672"])
    sheet_both = build_stat_sheet(jax, 11, items_both, env["issues"], None, env["derived"])
    target = target_from_values(Fraction(60), Fraction(50), max_health=Fraction(5000))
    # 8 attacks: Guinsoo reaches full stacks on atk 4, fires Phantom Hit on atk 6 ->
    # Kraken fires on atk 3, atk 6 (normal 3rd stack) and extra Phantom Hit stack speeds next proc.
    steps = parse_steps(", ".join(["attack"] * 8))
    out = evaluate_rotation(
        kit,
        sheet_both,
        {},
        target,
        steps,
        None,
        holder_range="melee",
        timeline=True,
    )
    kraken_procs = [p for s in out.steps for p in s.parts if "6672" in p.source]
    # Without Phantom Hit, 8 attacks give floor(8/3) = 2 Kraken procs;
    # with Guinsoo Phantom Hit extra stack (at atk 6 -> fires again at atk 8), >= 3 procs.
    assert len(kraken_procs) >= 3
