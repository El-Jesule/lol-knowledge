# Tarea: Motor determinista v1.0 (`OPT-04`, `OPT-05`, `OBJ-12`, `MEC-21`, `OBJ-05`)

- **Parche:** `16.23.1`
- **Versión del paquete:** `1.0.0`
- **Fecha:** 2026-11-25
- **Estado:** Implementado y validado en local (sin `push`)

## Objetivo

Completar las mecánicas y capacidades de optimización pendientes para llevar el motor determinista de LoL-Knowledge a la **v1.0**, priorizando la curva de compra y puntos de control de oro (`OPT-04`), la rotación automática en el optimizador (`OPT-05`), los elixires y mejoras de obra maestra de Ornn (`OBJ-12`, `DEC-03`), los informes por ventana de tiempo (`MEC-21`) y la interacción Impacto fantasma de Guinsoo → Verdugo de krakens (`OBJ-05`), con paridad completa entre CLI, contrato JSON (`lol-knowledge-contract/1`) y servidor MCP (`mcp_server.py`).

## Alcance entregado

1. **Elixires de la Grieta y mejoras de obra maestra de Ornn (`OBJ-12`, `DEC-03`):**
   - Nuevo módulo puro [`src/lol_knowledge/upgrades.py`](../../src/lol_knowledge/upgrades.py):
     - Elixires oficiales (`2138` *Elixir de hierro*: `+300` vida, `+25 %` tenacidad; `2139` *Elixir de brujería*: `+50` PH, `+15 %` reg. maná base; `2140` *Elixir de cólera*: `+30` DA; `500 g`, `0` huecos de inventario, máximo `1` activo), con soporte de alias en español e inglés.
     - Mejora de obra maestra de Ornn (`Derivado`, valores exactos de `Ornn.wad.client` `OrnnP.DataValues` en `16.23`: `UpgradeTotalGoldValue = 1000`, `AD = 35`, `AP = 20`, `HP = 2,66`, `AR = 20`, `MR = 18`, `AH = 31,25`, `AS = 30` por `1 %`), aplicada con aritmética exacta `Fraction`, limitada a **un único objeto completado** (no botas) por build.
   - Expuesto como `--elixir` y `--ornn-item` en `stats`, `ability`, `rotation`, `survive` y `duel`, y como `--elixir` + `--ornn-upgrade` (selección automática del único objeto de cada build cuya mejora maximiza el objetivo) en `optimize`.
2. **Curva de compra y puntos de control de oro (`OPT-04`):**
   - Nuevos tipos `PurchaseStep` y `GoldCheckpointResult` en [`src/lol_knowledge/optimizer/models.py`](../../src/lol_knowledge/optimizer/models.py) y algoritmos en [`src/lol_knowledge/optimizer/search.py`](../../src/lol_knowledge/optimizer/search.py):
     - Orden de compra paso a paso (`1..k`) sobre la mejor build (`--purchase-curve`), respetando objetos obligatorios y eligiendo en cada paso el objeto que maximiza el objetivo con informe de `item_gold`, `cumulative_gold`, `score`, `delta_score` y `score_per_1000g`.
     - Puntos de control de oro opcionales (`--gold-checkpoints <oro,...>`) que resuelven la mejor build legal parcial en cada presupuesto.
3. **Rotación automática del optimizador (`OPT-05`):**
   - `default_champion_rotation(kit, ranks)` en [`src/lol_knowledge/optimizer/search.py`](../../src/lol_knowledge/optimizer/search.py) sintetiza una rotación determinista `attack` + casos de daño de `Q/W/E/R` (prefiriendo casos principales) cuando se omite `--steps` / `steps` en `optimize` para los objetivos `rotation_damage`, `dps` y `healing`, declarando `auto_steps` en el resultado.
4. **Informes por ventana de tiempo (`MEC-21`):**
   - `TimelineWindow` y `RotationOutcome.window(seconds)` en [`src/lol_knowledge/rotation.py`](../../src/lol_knowledge/rotation.py) y formato/JSON en [`src/lol_knowledge/rotation_report.py`](../../src/lol_knowledge/rotation_report.py), calculando daño acumulado exacto (`total`, `primary_total`, `secondary_total`), DPS, curación, pasos y vida restante del objetivo en `[0, W]` s (con prorrateo exacto de quemaduras continuas). Expuesto como `--window` / `windows`.
5. **Interacción Guinsoo (`3124`) → Kraken (`6672`) (`OBJ-05`):**
   - El Impacto fantasma de *Hoja de furia de Guinsoo* añade la acumulación extra documentada al contador de *Verdugo de krakens* en `rotation.py`.
6. **Paridad CLI, contrato JSON, servidor MCP y pruebas:**
   - Paridad completa en [`src/lol_knowledge/cli.py`](../../src/lol_knowledge/cli.py), [`src/lol_knowledge/contract.py`](../../src/lol_knowledge/contract.py) y [`src/lol_knowledge/mcp_server.py`](../../src/lol_knowledge/mcp_server.py).
   - Nueva suite [`tests/test_engine_v1.py`](../../tests/test_engine_v1.py) cubriendo elixires, Ornn Masterwork, optimizador con Ornn+elixir, curva de compra, puntos de control de oro, rotación automática, ventanas de tiempo e interacción Guinsoo→Kraken.
   - Versión del paquete elevada a `1.0.0` en [`src/lol_knowledge/__init__.py`](../../src/lol_knowledge/__init__.py).
