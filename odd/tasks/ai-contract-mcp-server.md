# Fase 55 — Contrato JSON versionado y servidor MCP local (`IA-01`–`IA-04`)

- **Parche:** `16.23.1` (`data/current/manifest.json`)
- **Código:** [`src/lol_knowledge/contract.py`](../../src/lol_knowledge/contract.py), [`src/lol_knowledge/mcp_server.py`](../../src/lol_knowledge/mcp_server.py) y subcomandos `contract` y `mcp` en [`src/lol_knowledge/cli.py`](../../src/lol_knowledge/cli.py).
- **Documentación:** [`lol-knowledge/ai-layer.md`](../../lol-knowledge/ai-layer.md) y enlace en [`lol-knowledge/INDEX.md`](../../lol-knowledge/INDEX.md).
- **Pruebas:** [`tests/test_contract_and_mcp.py`](../../tests/test_contract_and_mcp.py).
- **Fecha:** 2026-11-21.
- **Estado:** completada.

## Qué se implementó

1. **Contrato JSON único y versionado (`IA-01`):**
   - Esquema `lol-knowledge-contract/1` (`execute_request` y subcomando `python -m lol_knowledge contract`) que unifica `lookup`, `stats`, `ability`, `rotation`, `survive` y `optimize`.
   - Sobre uniforme con `schema`, `ok`, `operation`, `patch`, `result_label`, `weakest_input_label`, `inputs`, `assumptions`, `not_modelled`, `result` y `explanation_contract`.
   - Errores estructurados con `code` (`missing_input`, `invalid_input`, `not_found`, `illegal_build`), `message` y `missing_fields` sin ocultar parámetros ausentes.
2. **Traducción y explicación (`IA-02`, `IA-03`):**
   - Operación `lookup` (`entity: champion | items | runes`) para consultar casos de habilidad exactos, entradas requeridas, IDs de objetos/runas y estado `effect_review` sin adivinar.
   - Reglas explícitas en [`lol-knowledge/ai-layer.md`](../../lol-knowledge/ai-layer.md), `SERVER_INSTRUCTIONS` del `initialize` MCP y prompts `translate_scenario` (`IA-02`) y `explain_result` (`IA-03`).
3. **Servidor MCP local sin dependencias externas (`IA-04`, `DEC-02`):**
   - Servidor JSON-RPC 2.0 sobre `stdio` en biblioteca estándar (`python -m lol_knowledge mcp --root <RUTA>`).
   - Implementa `initialize`, notificaciones (`notifications/initialized`), `ping`, `tools/list`, `tools/call` (6 herramientas `lol_*` con `inputSchema` JSON Schema y `structuredContent`), `prompts/list`, `prompts/get`, `resources/list` y `resources/read` (`lol-knowledge://index` y `lol-knowledge://ai-layer`).
   - Toda salida de diagnóstico va a `stderr` para no corromper las tramas JSON-RPC de `stdout`, con UTF-8 explícito en `stdin`/`stdout`/`stderr`.

## Limitaciones declaradas

- Transporte MCP limitado a `stdio` local (acorde a `DEC-02` y `AGENTS.md` §1); no hay servidor HTTP ni streaming SSE.
- La traducción de lenguaje natural a JSON la realiza el cliente LLM conectado siguiendo `SERVER_INSTRUCTIONS`, `lol_lookup` y los prompts `translate_scenario`/`explain_result`; el servidor nunca ejecuta heurísticas de lenguaje natural sin validación estricta del contrato.
