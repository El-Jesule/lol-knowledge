# Capa de IA, contrato JSON y servidor MCP local (`IA-01`–`IA-04`)

- **Parche:** `16.23.1` (`data/current/manifest.json`)
- **Esquema de contrato:** `lol-knowledge-contract/1` (`Oficial` / `Derivado` según entradas; resultados `Calculado`)
- **Código:** [`src/lol_knowledge/contract.py`](../src/lol_knowledge/contract.py) y [`src/lol_knowledge/mcp_server.py`](../src/lol_knowledge/mcp_server.py)
- **Fecha de actualización:** 2026-11-21
- **Limitación:** el servidor MCP es estrictamente local sobre `stdio` (sin exposición en red, sin estado compartido y sin dependencias externas en runtime; aprobado en `DEC-02`).

## 1. Contrato versionado `lol-knowledge-contract/1` (`IA-01`)

Toda petición estructurada al motor sigue una única forma JSON:

```json
{
  "schema": "lol-knowledge-contract/1",
  "operation": "lookup | stats | ability | rotation | survive | optimize",
  "params": {}
}
```

Toda respuesta (tanto correcta como de error) devuelve un sobre uniforme:

```json
{
  "schema": "lol-knowledge-contract/1",
  "ok": true,
  "operation": "rotation",
  "patch": "16.23.1",
  "result_label": "Calculado",
  "weakest_input_label": "Derivado",
  "inputs": {},
  "assumptions": [],
  "not_modelled": [],
  "result": {},
  "explanation_contract": {
    "must_cite_labels": true,
    "must_report_not_modelled": true,
    "never_invent_or_round_away_uncertainty": true
  }
}
```

Cuando faltan parámetros obligatorios o una build/página de runas es ilegal, `ok` es `false` y `error` indica `code` (`missing_input`, `invalid_input`, `not_found` o `illegal_build`), `message` y, si aplica, `missing_fields`.

### Uso desde CLI

```powershell
.\.venv\Scripts\python.exe -m lol_knowledge contract --input-file request.json
```

## 2. Traducción de escenarios y explicación (`IA-02`, `IA-03`)

1. **Cero cálculo mental (`IA-02`):** la IA nunca estima daño, estadísticas, vida efectiva, supervivencia ni comparativas de builds por su cuenta; toda cifra debe salir de una invocación al motor (`lol_*`).
2. **Resolución sin adivinanzas (`IA-02`):** ante dudas sobre nombres de casos de habilidad (p. ej. `Q.both` frente a `Q.out`), IDs de objetos o IDs de runas, la IA consulta primero `lol_lookup`.
3. **Huecos explícitos (`IA-02`):** si la petición en lenguaje natural omite datos necesarios (nivel, resistencias/vida del objetivo, rangos aprendidos, pasos de la rotación o presupuesto), la IA pregunta al usuario o los declara explícitamente como supuestos antes de invocar la herramienta.
4. **Explicación trazable (`IA-03`):** la explicación al usuario debe citar `patch`, `result_label` (`Calculado`), `weakest_input_label` (`Oficial`, `Derivado` o `Pendiente de verificación`), los `assumptions` y todo `not_modelled`. En `optimize`, debe presentar `verified_builds` estrictamente separado de `pending_builds`, sin suavizar ni ocultar incertidumbres.

## 3. Servidor MCP local (`IA-04`, `DEC-02`)

El servidor implementa **Model Context Protocol (JSON-RPC 2.0 sobre `stdio`)** usando solo la biblioteca estándar de Python (`python -m lol_knowledge mcp --root <RUTA>`):

- **Herramientas (`tools/list`):** `lol_lookup`, `lol_stats`, `lol_ability`, `lol_rotation`, `lol_survive`, `lol_optimize`.
- **Prompts (`prompts/list`):** `translate_scenario` (`IA-02`) y `explain_result` (`IA-03`).
- **Recursos (`resources/list`):** `lol-knowledge://index` y `lol-knowledge://ai-layer`.

### Ejemplo de configuración en cliente MCP (OpenCode / Antigravity / Claude Desktop)

```json
{
  "mcpServers": {
    "lol-knowledge": {
      "command": "C:\\Users\\Yisus\\Documents\\LoL-Knowledge\\.venv\\Scripts\\python.exe",
      "args": [
        "-m",
        "lol_knowledge",
        "mcp",
        "--root",
        "C:\\Users\\Yisus\\Documents\\LoL-Knowledge"
      ]
    }
  }
}
```
