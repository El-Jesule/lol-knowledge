"""Tests for lol-knowledge-contract/1 (IA-01..IA-03) and local MCP server (IA-04)."""

from __future__ import annotations

import io
import json
from pathlib import Path

from lol_knowledge.cli import main as cli_main
from lol_knowledge.contract import CONTRACT_SCHEMA, execute_request
from lol_knowledge.mcp_server import MCP_PROTOCOL_VERSION, MCPServer

ROOT = Path(__file__).resolve().parents[1]


def test_contract_lookup_champion_items_and_runes() -> None:
    champ = execute_request(
        {
            "schema": CONTRACT_SCHEMA,
            "operation": "lookup",
            "params": {"entity": "champion", "champion": "Ahri"},
        },
        ROOT,
    )
    assert champ["ok"] is True
    assert champ["schema"] == CONTRACT_SCHEMA
    assert champ["result"]["id"] == "Ahri"
    assert champ["result"]["inferred_range"] == "ranged"
    assert "Q" in champ["result"]["kit"]["abilities"]

    items = execute_request(
        {
            "operation": "lookup",
            "params": {"entity": "items", "query": "Luden", "only_complete": True},
        },
        ROOT,
    )
    assert items["ok"] is True
    assert any(i["id"] == "6655" for i in items["result"]["items"])

    runes = execute_request(
        {"operation": "lookup", "params": {"entity": "runes", "query": "8112"}},
        ROOT,
    )
    assert runes["ok"] is True
    assert any(r["id"] == 8112 for r in runes["result"]["runes"])


def test_contract_stats_ability_rotation_survive_and_optimize() -> None:
    st = execute_request(
        {
            "schema": CONTRACT_SCHEMA,
            "operation": "stats",
            "params": {"champion": "Ahri", "level": 9, "items": ["6655"]},
        },
        ROOT,
    )
    assert st["ok"] is True
    assert st["result_label"] == "Calculado"
    assert st["explanation_contract"]["must_cite_labels"] is True
    assert st["result"]["stats"]["ability_power"]["total"] == 100.0

    ab = execute_request(
        {
            "operation": "ability",
            "params": {
                "champion": "Ahri",
                "level": 9,
                "ability": "E",
                "rank": 1,
                "items": ["6655"],
                "target": {"armor": 50, "mr": 50, "max_health": 1800, "kind": "champion"},
            },
        },
        ROOT,
    )
    assert ab["ok"] is True
    assert ab["result"]["cases"][0]["total"] > 0

    rot = execute_request(
        {
            "operation": "rotation",
            "params": {
                "champion": "Ahri",
                "level": 9,
                "steps": "E Q.both",
                "learned": {"Q": 5, "W": 1, "E": 1, "R": 1},
                "items": ["6655"],
                "target": {"armor": 50, "mr": 50, "max_health": 1800, "kind": "champion"},
            },
        },
        ROOT,
    )
    assert rot["ok"] is True
    assert rot["weakest_input_label"] == "Derivado"
    assert any("holder_range inferred" in a for a in rot["assumptions"])
    assert rot["result"]["total"] > 0

    surv = execute_request(
        {
            "operation": "survive",
            "params": {
                "champion": "Garen",
                "level": 11,
                "items": ["3156"],
                "incoming": "magic:2800",
            },
        },
        ROOT,
    )
    assert surv["ok"] is True
    assert surv["result"]["total_shield_granted"] > 0

    surv_enemy = execute_request(
        {
            "operation": "survive",
            "params": {
                "champion": "Garen",
                "level": 9,
                "items": ["3047"],
                "enemy": {
                    "champion": "Ahri",
                    "level": 9,
                    "items": ["6655"],
                    "learned": {"Q": 5, "W": 1, "E": 1, "R": 1},
                    "steps": "E Q.both",
                },
            },
        },
        ROOT,
    )
    assert surv_enemy["ok"] is True
    assert surv_enemy["result"]["survived"] is True

    opt = execute_request(
        {
            "operation": "optimize",
            "params": {
                "champion": "Garen",
                "level": 9,
                "objective": "effective_health_physical",
                "slots": 1,
                "budget": 3500,
                "top": 2,
                "beam_width": 6,
                "pool_limit": 8,
            },
        },
        ROOT,
    )
    assert opt["ok"] is True
    assert len(opt["result"]["verified_builds"]) == 2
    assert all(b["verified"] is True for b in opt["result"]["verified_builds"])
    assert all(b["verified"] is False for b in opt["result"]["pending_builds"])


def test_contract_structured_errors_and_cli(tmp_path: Path, capsys) -> None:
    missing = execute_request(
        {"operation": "rotation", "params": {"champion": "Ahri", "level": 9}},
        ROOT,
    )
    assert missing["ok"] is False
    assert missing["error"]["code"] == "missing_input"
    assert "steps" in missing["error"]["missing_fields"]

    bad_schema = execute_request(
        {"schema": "wrong/99", "operation": "stats", "params": {"champion": "Ahri", "level": 9}},
        ROOT,
    )
    assert bad_schema["ok"] is False
    assert bad_schema["error"]["code"] == "invalid_input"

    illegal = execute_request(
        {
            "operation": "stats",
            "params": {"champion": "Garen", "level": 9, "items": ["3047", "3111"]},
        },
        ROOT,
    )
    assert illegal["ok"] is False
    assert illegal["error"]["code"] == "illegal_build"

    req_file = tmp_path / "req.json"
    req_file.write_text(
        json.dumps(
            {
                "schema": CONTRACT_SCHEMA,
                "operation": "stats",
                "params": {"champion": "Ahri", "level": 9, "items": ["6655"]},
            }
        ),
        encoding="utf-8",
    )
    rc = cli_main(["contract", "--input-file", str(req_file), "--root", str(ROOT)])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["ok"] is True
    assert out["result"]["stats"]["ability_power"]["total"] == 100.0


def test_mcp_server_stdio_roundtrip() -> None:
    server = MCPServer(ROOT)
    requests = [
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {"jsonrpc": "2.0", "id": 2, "method": "ping"},
        {"jsonrpc": "2.0", "id": 3, "method": "tools/list"},
        {
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {
                "name": "lol_lookup",
                "arguments": {"entity": "champion", "champion": "Ahri"},
            },
        },
        {
            "jsonrpc": "2.0",
            "id": 5,
            "method": "tools/call",
            "params": {
                "name": "lol_rotation",
                "arguments": {"champion": "Ahri", "level": 9},  # missing steps -> isError=True
            },
        },
        {"jsonrpc": "2.0", "id": 6, "method": "prompts/list"},
        {
            "jsonrpc": "2.0",
            "id": 7,
            "method": "prompts/get",
            "params": {
                "name": "translate_scenario",
                "arguments": {"question": "¿Cuánto daño hace Ahri nivel 9 con Luden?"},
            },
        },
        {"jsonrpc": "2.0", "id": 8, "method": "resources/list"},
        {
            "jsonrpc": "2.0",
            "id": 9,
            "method": "resources/read",
            "params": {"uri": "lol-knowledge://ai-layer"},
        },
        {"jsonrpc": "2.0", "id": 10, "method": "unknown/method"},
    ]
    raw_in = "\n".join(json.dumps(r, ensure_ascii=False) for r in requests) + "\n{broken json\n"
    in_buf = io.StringIO(raw_in)
    out_buf = io.StringIO()

    rc = server.serve_stdio(in_buf, out_buf)
    assert rc == 0

    responses = [json.loads(line) for line in out_buf.getvalue().splitlines() if line.strip()]
    # Notification produces no reply -> 10 request replies + 1 parse error = 11 responses.
    assert len(responses) == 11
    by_id = {r.get("id"): r for r in responses if r.get("id") is not None}

    init = by_id[1]["result"]
    assert init["protocolVersion"] == MCP_PROTOCOL_VERSION
    assert init["serverInfo"]["name"] == "lol-knowledge"
    assert CONTRACT_SCHEMA in init["instructions"]

    assert by_id[2]["result"] == {}

    tool_names = [t["name"] for t in by_id[3]["result"]["tools"]]
    assert tool_names == [
        "lol_lookup",
        "lol_stats",
        "lol_ability",
        "lol_rotation",
        "lol_survive",
        "lol_duel",
        "lol_optimize",
    ]

    lookup_res = by_id[4]["result"]
    assert lookup_res["isError"] is False
    assert lookup_res["structuredContent"]["ok"] is True
    assert lookup_res["structuredContent"]["result"]["id"] == "Ahri"

    missing_res = by_id[5]["result"]
    assert missing_res["isError"] is True
    assert missing_res["structuredContent"]["error"]["code"] == "missing_input"

    prompt_names = [p["name"] for p in by_id[6]["result"]["prompts"]]
    assert prompt_names == ["translate_scenario", "explain_result"]
    assert "Ahri" in by_id[7]["result"]["messages"][0]["content"]["text"]

    res_uris = [r["uri"] for r in by_id[8]["result"]["resources"]]
    assert "lol-knowledge://ai-layer" in res_uris
    assert "lol-knowledge-contract/1" in by_id[9]["result"]["contents"][0]["text"]

    assert by_id[10]["error"]["code"] == -32601
    parse_err = [r for r in responses if r.get("id") is None][0]
    assert parse_err["error"]["code"] == -32700


def test_mcp_and_contract_target_and_enemy_runes_parity() -> None:
    server = MCPServer(ROOT)
    tools_reply = server.handle_message(
        {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}
    )
    assert tools_reply is not None
    by_name = {
        tool["name"]: tool["inputSchema"]["properties"] for tool in tools_reply["result"]["tools"]
    }

    for tool_name in ("lol_ability", "lol_rotation", "lol_optimize"):
        target_props = by_name[tool_name]["target"]["properties"]
        assert "runes" in target_props and "shards" in target_props
    for tool_name in ("lol_survive", "lol_optimize"):
        enemy_props = by_name[tool_name]["enemy"]["properties"]
        assert {"runes", "shards", "inputs"} <= set(enemy_props)

    bone_plating_page = [8437, 8446, 8473, 8451, 9111, 9104]
    electrocute_page = [8112, 8139, 8140, 8135, 8226, 8237]
    shards = [5008, 5008, 5011]

    def _call(name: str, arguments: dict) -> dict:
        reply = server.handle_message(
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {"name": name, "arguments": arguments},
            }
        )
        assert reply is not None
        res = reply["result"]
        assert res["isError"] is False, res
        return res["structuredContent"]

    # 1. lol_rotation with target.runes (Bone Plating) + target.shards (+65 flat HP)
    rot_plain = _call(
        "lol_rotation",
        {
            "champion": "Ahri",
            "level": 9,
            "learned": {"Q": 5, "W": 2, "E": 1},
            "steps": "E, Q.both, W.all",
            "timeline": True,
            "target": {"champion": "Lux", "level": 9},
        },
    )
    rot_bp = _call(
        "lol_rotation",
        {
            "champion": "Ahri",
            "level": 9,
            "learned": {"Q": 5, "W": 2, "E": 1},
            "steps": "E, Q.both, W.all",
            "timeline": True,
            "target": {
                "champion": "Lux",
                "level": 9,
                "runes": bone_plating_page,
                "shards": shards,
            },
        },
    )
    assert rot_bp["result"]["total"] < rot_plain["result"]["total"]

    # 2. lol_survive with enemy.runes (Electrocute) + enemy.shards
    surv_plain = _call(
        "lol_survive",
        {
            "champion": "Garen",
            "level": 9,
            "timeline": True,
            "enemy": {
                "champion": "Ahri",
                "level": 9,
                "learned": {"Q": 5, "W": 2, "E": 1},
                "steps": "E, Q.both, W.all",
            },
        },
    )
    surv_runes = _call(
        "lol_survive",
        {
            "champion": "Garen",
            "level": 9,
            "timeline": True,
            "enemy": {
                "champion": "Ahri",
                "level": 9,
                "learned": {"Q": 5, "W": 2, "E": 1},
                "steps": "E, Q.both, W.all",
                "runes": electrocute_page,
                "shards": shards,
            },
        },
    )
    assert surv_runes["result"]["total_damage_taken"] > surv_plain["result"]["total_damage_taken"]

    # 3. lol_optimize rotation_damage with target.runes + target.shards
    opt_plain = _call(
        "lol_optimize",
        {
            "champion": "Ahri",
            "level": 9,
            "objective": "rotation_damage",
            "slots": 1,
            "budget": 3200,
            "only_verified": True,
            "top": 1,
            "beam_width": 4,
            "pool_limit": 6,
            "learned": {"Q": 5, "W": 2, "E": 1},
            "steps": "E, Q.both, W.all",
            "timeline": True,
            "target": {"champion": "Lux", "level": 9},
        },
    )
    opt_bp = _call(
        "lol_optimize",
        {
            "champion": "Ahri",
            "level": 9,
            "objective": "rotation_damage",
            "slots": 1,
            "budget": 3200,
            "only_verified": True,
            "top": 1,
            "beam_width": 4,
            "pool_limit": 6,
            "learned": {"Q": 5, "W": 2, "E": 1},
            "steps": "E, Q.both, W.all",
            "timeline": True,
            "target": {
                "champion": "Lux",
                "level": 9,
                "runes": bone_plating_page,
                "shards": shards,
            },
        },
    )
    assert (
        opt_bp["result"]["verified_builds"][0]["score"]
        < (opt_plain["result"]["verified_builds"][0]["score"])
    )

    # 4. lol_optimize time_to_die with enemy (including enemy.runes & enemy.shards)
    opt_ttd = _call(
        "lol_optimize",
        {
            "champion": "Garen",
            "level": 9,
            "objective": "time_to_die",
            "slots": 1,
            "budget": 3200,
            "only_verified": True,
            "top": 1,
            "beam_width": 4,
            "pool_limit": 6,
            "timeline": True,
            "enemy": {
                "champion": "Ahri",
                "level": 9,
                "items": ["6655"],
                "learned": {"Q": 5, "W": 2, "E": 1},
                "steps": "E, Q.both, W.all",
                "runes": electrocute_page,
                "shards": shards,
            },
        },
    )
    assert opt_ttd["ok"] is True
    assert opt_ttd["result"]["verified_builds"]
