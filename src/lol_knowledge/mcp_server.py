"""Local Model Context Protocol (MCP) server over stdio (IA-04, DEC-02).

Pure Python standard library (JSON-RPC 2.0 newline-delimited frames on stdin/stdout).
Never writes logs to stdout; all diagnostics go to stderr.
Every tool executes through ``lol_knowledge.contract.execute_request`` so every
response conforms to ``lol-knowledge-contract/1`` with explicit labels,
assumptions and not-modelled declarations (IA-01..IA-03).
"""

from __future__ import annotations

import json
import logging
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any, TextIO

from . import __version__
from .contract import CONTRACT_SCHEMA, execute_request

LOGGER = logging.getLogger(__name__)

MCP_PROTOCOL_VERSION = "2024-11-05"
SERVER_NAME = "lol-knowledge"

SERVER_INSTRUCTIONS = (
    "LoL-Knowledge deterministic League of Legends calculator (contract "
    f"{CONTRACT_SCHEMA}). Rules: "
    "(1) NEVER compute League stats, damage, EHP, survival or build rankings mentally; "
    "always call the matching lol_* tool. "
    "(2) Use lol_lookup first if you need exact champion case names, item IDs or rune IDs. "
    "(3) If required scenario parameters (level, target resistances/health, learned ranks, "
    "steps, budget) are missing from the user's question, either ask the user or state "
    "them explicitly as assumptions. "
    "(4) When explaining any result, ALWAYS report result_label, weakest_input_label "
    "(Oficial / Derivado / Pendiente de verificación), assumptions, and not_modelled, "
    "and keep verified_builds strictly separate from pending_builds."
)

_TARGET_SCHEMA: dict[str, Any] = {
    "type": "object",
    "description": (
        "Enemy target: either {champion, level, items?, runes?, shards?, inputs?} "
        "or {armor, mr, max_health?, kind?}."
    ),
    "properties": {
        "champion": {"type": "string"},
        "level": {"type": "integer", "minimum": 1, "maximum": 18},
        "items": {"type": "array", "items": {"type": "string"}},
        "runes": {"type": "array", "items": {"type": "integer"}},
        "shards": {"type": "array", "items": {"type": "integer"}},
        "inputs": {"type": "object", "additionalProperties": {"type": "number"}},
        "armor": {"type": "number"},
        "mr": {"type": "number"},
        "max_health": {"type": "number"},
        "current_health": {"type": "number"},
        "bonus_health": {"type": "number"},
        "kind": {"type": "string", "enum": ["champion", "minion", "monster", "structure"]},
        "shield": {"type": "number"},
        "shield_type": {"type": "string", "enum": ["normal", "physical", "magic"]},
    },
}

_ENEMY_SCHEMA: dict[str, Any] = {
    "type": "object",
    "description": (
        "Enemy attacker rotation: {champion, level, steps, items?, runes?, shards?, "
        "summoners?, learned?, range?, inputs?}."
    ),
    "properties": {
        "champion": {"type": "string"},
        "level": {"type": "integer", "minimum": 1, "maximum": 18},
        "items": {"type": "array", "items": {"type": "string"}},
        "runes": {"type": "array", "items": {"type": "integer"}},
        "shards": {"type": "array", "items": {"type": "integer"}},
        "summoners": {"type": "array", "items": {"type": "string"}},
        "learned": {"type": "object", "additionalProperties": {"type": "integer"}},
        "steps": {"type": "string"},
        "range": {"type": "string", "enum": ["melee", "ranged"]},
        "inputs": {"type": "object", "additionalProperties": {"type": "number"}},
    },
}

TOOLS: tuple[dict[str, Any], ...] = (
    {
        "name": "lol_lookup",
        "description": (
            "Search or inspect champions (including exact kit ability cases and inputs), "
            "purchasable items (IDs, gold, effect_review status), runes/shards or summoner spells."
        ),
        "inputSchema": {
            "type": "object",
            "required": ["entity"],
            "properties": {
                "entity": {"type": "string", "enum": ["champion", "items", "runes", "summoners"]},
                "champion": {
                    "type": "string",
                    "description": "Champion name/id when entity='champion'.",
                },
                "query": {
                    "type": "string",
                    "description": "Substring filter for items, runes or summoners.",
                },
                "only_complete": {
                    "type": "boolean",
                    "description": "Only items with effect_review='complete'.",
                },
                "limit": {"type": "integer", "minimum": 1, "maximum": 100},
            },
        },
    },
    {
        "name": "lol_stats",
        "description": (
            "Compute a champion's exact stat sheet, effective health, ability and summoner "
            "cooldowns, and resource pool for a given level, items, runes and summoners."
        ),
        "inputSchema": {
            "type": "object",
            "required": ["champion", "level"],
            "properties": {
                "champion": {"type": "string"},
                "level": {"type": "integer", "minimum": 1, "maximum": 18},
                "items": {"type": "array", "items": {"type": "string"}},
                "runes": {"type": "array", "items": {"type": "integer"}},
                "shards": {"type": "array", "items": {"type": "integer"}},
                "summoners": {"type": "array", "items": {"type": "string"}},
                "learned": {"type": "object", "additionalProperties": {"type": "integer"}},
                "inputs": {"type": "object", "additionalProperties": {"type": "number"}},
                "assume": {"type": "object", "additionalProperties": {"type": "string"}},
                "allow_illegal_build": {"type": "boolean"},
            },
        },
    },
    {
        "name": "lol_ability",
        "description": (
            "Compute post-mitigation damage of one champion ability rank against a target "
            "(supports multi-target via target_count)."
        ),
        "inputSchema": {
            "type": "object",
            "required": ["champion", "level", "ability", "rank", "target"],
            "properties": {
                "champion": {"type": "string"},
                "level": {"type": "integer", "minimum": 1, "maximum": 18},
                "ability": {"type": "string", "enum": ["Q", "W", "E", "R"]},
                "rank": {"type": "integer", "minimum": 1, "maximum": 6},
                "case": {"type": "string"},
                "items": {"type": "array", "items": {"type": "string"}},
                "runes": {"type": "array", "items": {"type": "integer"}},
                "shards": {"type": "array", "items": {"type": "integer"}},
                "summoners": {"type": "array", "items": {"type": "string"}},
                "learned": {"type": "object", "additionalProperties": {"type": "integer"}},
                "inputs": {"type": "object", "additionalProperties": {"type": "number"}},
                "assume": {"type": "object", "additionalProperties": {"type": "string"}},
                "allow_illegal_build": {"type": "boolean"},
                "target": _TARGET_SCHEMA,
                "target_count": {"type": "integer", "minimum": 1},
            },
        },
    },
    {
        "name": "lol_rotation",
        "description": (
            "Simulate an ordered combat rotation (basic attacks, ability casts, item actives, "
            "summoner:<name> casts, waits) with passives, runes, burns, shields, healing, "
            "resources and multi-target splash."
        ),
        "inputSchema": {
            "type": "object",
            "required": ["champion", "level", "steps", "target"],
            "properties": {
                "champion": {"type": "string"},
                "level": {"type": "integer", "minimum": 1, "maximum": 18},
                "steps": {
                    "type": "string",
                    "description": 'E.g. "E Q.both W.all summoner:ignite" or "R.dash@3".',
                },
                "learned": {"type": "object", "additionalProperties": {"type": "integer"}},
                "items": {"type": "array", "items": {"type": "string"}},
                "runes": {"type": "array", "items": {"type": "integer"}},
                "shards": {"type": "array", "items": {"type": "integer"}},
                "summoners": {"type": "array", "items": {"type": "string"}},
                "attacker_range": {"type": "string", "enum": ["melee", "ranged"]},
                "timeline": {"type": "boolean"},
                "target": _TARGET_SCHEMA,
                "target_count": {"type": "integer", "minimum": 1},
                "inputs": {"type": "object", "additionalProperties": {"type": "number"}},
                "assume": {"type": "object", "additionalProperties": {"type": "string"}},
                "allow_illegal_build": {"type": "boolean"},
                "attacker_resource": {"type": "number"},
                "allow_insufficient_resource": {"type": "boolean"},
            },
        },
    },
    {
        "name": "lol_survive",
        "description": (
            "Reverse defense simulation: check whether a champion survives incoming hits or an "
            "enemy rotation, including champion defensive passives, summoner spells (Barrier, "
            "Heal, Exhaust, Cleanse), Lifeline shields, Guardian, Bone Plating, Second Wind "
            "and Thorns."
        ),
        "inputSchema": {
            "type": "object",
            "required": ["champion", "level"],
            "properties": {
                "champion": {"type": "string"},
                "level": {"type": "integer", "minimum": 1, "maximum": 18},
                "items": {"type": "array", "items": {"type": "string"}},
                "runes": {"type": "array", "items": {"type": "integer"}},
                "shards": {"type": "array", "items": {"type": "integer"}},
                "summoners": {"type": "array", "items": {"type": "string"}},
                "incoming": {
                    "type": "string",
                    "description": 'Manual hits, e.g. "attack:500, magic:350".',
                },
                "enemy": _ENEMY_SCHEMA,
                "defender_health": {"type": "number"},
                "defender_shield": {"type": "number"},
                "defender_shield_type": {"type": "string", "enum": ["normal", "physical", "magic"]},
                "timeline": {"type": "boolean"},
                "inputs": {"type": "object", "additionalProperties": {"type": "number"}},
                "assume": {"type": "object", "additionalProperties": {"type": "string"}},
                "allow_illegal_build": {"type": "boolean"},
            },
        },
    },
    {
        "name": "lol_optimize",
        "description": (
            "Search legal Summoner's Rift builds optimizing a measurable objective "
            "(rotation_damage, dps, effective_health_*, time_to_die, healing). "
            "Separates verified (Oficial/Derivado) builds from Pendiente de verificación builds."
        ),
        "inputSchema": {
            "type": "object",
            "required": ["champion", "level", "objective"],
            "properties": {
                "champion": {"type": "string"},
                "level": {"type": "integer", "minimum": 1, "maximum": 18},
                "objective": {
                    "type": "string",
                    "enum": [
                        "rotation_damage",
                        "dps",
                        "effective_health_physical",
                        "effective_health_magic",
                        "effective_health_mixed",
                        "time_to_die",
                        "healing",
                    ],
                },
                "budget": {"type": "integer", "minimum": 0},
                "slots": {"type": "integer", "minimum": 1, "maximum": 6},
                "required_items": {"type": "array", "items": {"type": "string"}},
                "forbidden_items": {"type": "array", "items": {"type": "string"}},
                "require_boots": {"type": "boolean"},
                "tier": {"type": "string", "enum": ["completed", "all"]},
                "only_verified": {"type": "boolean"},
                "use_item_actives": {"type": "boolean"},
                "top": {"type": "integer", "minimum": 1, "maximum": 20},
                "beam_width": {"type": "integer", "minimum": 1, "maximum": 64},
                "pool_limit": {"type": "integer", "minimum": 4, "maximum": 64},
                "damage_mix_physical": {"type": "number"},
                "steps": {"type": "string"},
                "learned": {"type": "object", "additionalProperties": {"type": "integer"}},
                "attacker_range": {"type": "string", "enum": ["melee", "ranged"]},
                "target": _TARGET_SCHEMA,
                "target_count": {"type": "integer", "minimum": 1},
                "incoming": {"type": "string"},
                "enemy": _ENEMY_SCHEMA,
                "timeline": {"type": "boolean"},
                "runes": {"type": "array", "items": {"type": "integer"}},
                "shards": {"type": "array", "items": {"type": "integer"}},
                "summoners": {"type": "array", "items": {"type": "string"}},
                "inputs": {"type": "object", "additionalProperties": {"type": "number"}},
                "assume": {"type": "object", "additionalProperties": {"type": "string"}},
                "allow_illegal_build": {"type": "boolean"},
            },
        },
    },
)

TOOL_TO_OPERATION: dict[str, str] = {
    "lol_lookup": "lookup",
    "lol_stats": "stats",
    "lol_ability": "ability",
    "lol_rotation": "rotation",
    "lol_survive": "survive",
    "lol_optimize": "optimize",
}

PROMPTS: tuple[dict[str, Any], ...] = (
    {
        "name": "translate_scenario",
        "description": (
            "Translate a natural-language League question into a structured "
            "lol-knowledge-contract/1 call (IA-02)."
        ),
        "arguments": [
            {
                "name": "question",
                "description": "The user's natural-language League of Legends question.",
                "required": True,
            }
        ],
    },
    {
        "name": "explain_result",
        "description": (
            "Explain a lol-knowledge-contract/1 JSON output citing labels, assumptions "
            "and not_modelled honestly (IA-03)."
        ),
        "arguments": [
            {
                "name": "envelope_json",
                "description": "The JSON envelope returned by a lol_* tool.",
                "required": True,
            }
        ],
    },
)

RESOURCES: tuple[dict[str, str], ...] = (
    {
        "uri": "lol-knowledge://index",
        "name": "LoL-Knowledge Index",
        "description": "Knowledge base routing index (lol-knowledge/INDEX.md).",
        "mimeType": "text/markdown",
        "rel_path": "lol-knowledge/INDEX.md",
    },
    {
        "uri": "lol-knowledge://ai-layer",
        "name": "AI Contract and MCP Guide",
        "description": (
            "Specification of lol-knowledge-contract/1, IA-02/IA-03 rules and MCP server setup."
        ),
        "mimeType": "text/markdown",
        "rel_path": "lol-knowledge/ai-layer.md",
    },
)


def _rpc_result(msg_id: Any, result: dict[str, Any]) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": msg_id, "result": result}


def _rpc_error(msg_id: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": msg_id, "error": {"code": code, "message": message}}


class MCPServer:
    """Stateless local MCP JSON-RPC 2.0 handler backed by ``execute_request``."""

    def __init__(self, root: Path) -> None:
        self.root = root

    def handle_message(self, message: Mapping[str, Any]) -> dict[str, Any] | None:
        if not isinstance(message, Mapping) or message.get("jsonrpc") != "2.0":
            return _rpc_error(
                message.get("id") if isinstance(message, Mapping) else None,
                -32600,
                "Invalid Request",
            )
        method = message.get("method")
        msg_id = message.get("id")
        is_notification = "id" not in message

        if not isinstance(method, str):
            return None if is_notification else _rpc_error(msg_id, -32600, "Missing method")

        if is_notification:
            # Notifications (e.g. notifications/initialized, notifications/cancelled) get no reply.
            return None

        params = message.get("params") or {}
        if not isinstance(params, Mapping):
            return _rpc_error(msg_id, -32602, "params must be an object")

        if method == "initialize":
            return _rpc_result(
                msg_id,
                {
                    "protocolVersion": MCP_PROTOCOL_VERSION,
                    "capabilities": {
                        "tools": {"listChanged": False},
                        "prompts": {"listChanged": False},
                        "resources": {"subscribe": False, "listChanged": False},
                    },
                    "serverInfo": {"name": SERVER_NAME, "version": __version__},
                    "instructions": SERVER_INSTRUCTIONS,
                },
            )
        if method == "ping":
            return _rpc_result(msg_id, {})
        if method == "tools/list":
            return _rpc_result(msg_id, {"tools": list(TOOLS)})
        if method == "tools/call":
            return self._handle_tool_call(msg_id, params)
        if method == "prompts/list":
            return _rpc_result(msg_id, {"prompts": list(PROMPTS)})
        if method == "prompts/get":
            return self._handle_prompt_get(msg_id, params)
        if method == "resources/list":
            return _rpc_result(
                msg_id,
                {"resources": [{k: v for k, v in r.items() if k != "rel_path"} for r in RESOURCES]},
            )
        if method == "resources/read":
            return self._handle_resource_read(msg_id, params)
        return _rpc_error(msg_id, -32601, f"Method not found: {method}")

    def _handle_tool_call(self, msg_id: Any, params: Mapping[str, Any]) -> dict[str, Any]:
        name = params.get("name")
        arguments = params.get("arguments") or {}
        if not isinstance(name, str) or name not in TOOL_TO_OPERATION:
            return _rpc_error(msg_id, -32602, f"Unknown tool: {name!r}")
        if not isinstance(arguments, Mapping):
            return _rpc_error(msg_id, -32602, "Tool arguments must be an object")
        envelope = execute_request(
            {
                "schema": CONTRACT_SCHEMA,
                "operation": TOOL_TO_OPERATION[name],
                "params": dict(arguments),
            },
            self.root,
        )
        return _rpc_result(
            msg_id,
            {
                "content": [
                    {
                        "type": "text",
                        "text": json.dumps(envelope, indent=2, ensure_ascii=False),
                    }
                ],
                "structuredContent": envelope,
                "isError": not envelope["ok"],
            },
        )

    def _handle_prompt_get(self, msg_id: Any, params: Mapping[str, Any]) -> dict[str, Any]:
        name = params.get("name")
        args = params.get("arguments") or {}
        if name == "translate_scenario":
            question = str(args.get("question", ""))
            text = (
                "Traduce la siguiente petición de League of Legends a una llamada de herramienta "
                "lol_* usando el contrato lol-knowledge-contract/1 (IA-02):\n"
                "- Nunca calcules cifras mentalmente ni inventes IDs de objetos/runas/casos.\n"
                "- Llama primero a lol_lookup si necesitas confirmar IDs o casos de habilidad.\n"
                "- Si faltan datos obligatorios (nivel, resistencias/vida del objetivo, rangos "
                "aprendidos, rotación o presupuesto), pregunta al usuario o decláralos como "
                "supuestos explícitos antes de llamar a la herramienta.\n\n"
                f"Petición del usuario: {question}"
            )
            return _rpc_result(
                msg_id,
                {
                    "description": (
                        "Translate natural language to lol-knowledge-contract/1 (IA-02)."
                    ),
                    "messages": [{"role": "user", "content": {"type": "text", "text": text}}],
                },
            )
        if name == "explain_result":
            envelope_json = str(args.get("envelope_json", ""))
            text = (
                "Explica al usuario en español el siguiente resultado del contrato "
                "lol-knowledge-contract/1 (IA-03):\n"
                "- Cita exactamente `patch`, `result_label` (`Calculado`) y `weakest_input_label` "
                "(`Oficial`, `Derivado` o `Pendiente de verificación`).\n"
                "- Lista todos los `assumptions` y `not_modelled` sin suavizar incertidumbres.\n"
                "- Si el resultado es de `optimize`, presenta `verified_builds` separado de "
                "`pending_builds`.\n"
                "- No inventes ni recalcules cifras fuera del JSON.\n\n"
                f"Resultado JSON:\n{envelope_json}"
            )
            return _rpc_result(
                msg_id,
                {
                    "description": "Explain lol-knowledge-contract/1 output honestly (IA-03).",
                    "messages": [{"role": "user", "content": {"type": "text", "text": text}}],
                },
            )
        return _rpc_error(msg_id, -32602, f"Unknown prompt: {name!r}")

    def _handle_resource_read(self, msg_id: Any, params: Mapping[str, Any]) -> dict[str, Any]:
        uri = params.get("uri")
        for resource in RESOURCES:
            if resource["uri"] == uri:
                path = self.root / resource["rel_path"]
                if not path.is_file():
                    return _rpc_error(
                        msg_id, -32002, f"Resource file missing: {resource['rel_path']}"
                    )
                text = path.read_text(encoding="utf-8")
                return _rpc_result(
                    msg_id,
                    {
                        "contents": [
                            {
                                "uri": uri,
                                "mimeType": resource["mimeType"],
                                "text": text,
                            }
                        ]
                    },
                )
        return _rpc_error(msg_id, -32002, f"Unknown resource URI: {uri!r}")

    def serve_stdio(
        self,
        in_stream: TextIO | None = None,
        out_stream: TextIO | None = None,
    ) -> int:
        """Read newline-delimited JSON-RPC 2.0 messages from stdin and write replies to stdout."""
        reader = in_stream if in_stream is not None else sys.stdin
        writer = out_stream if out_stream is not None else sys.stdout
        for raw_line in reader:
            line = raw_line.strip()
            if not line:
                continue
            try:
                message = json.loads(line)
            except json.JSONDecodeError as exc:
                response: dict[str, Any] | None = _rpc_error(None, -32700, f"Parse error: {exc}")
            else:
                response = self.handle_message(message)
            if response is not None:
                writer.write(json.dumps(response, ensure_ascii=False) + "\n")
                writer.flush()
        return 0
