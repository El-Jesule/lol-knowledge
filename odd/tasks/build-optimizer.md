# Fase 54 — Optimizador de builds (`OPT-01`, `OPT-02`, `OPT-03`)

- **Parche:** `16.23.1` (`data/current/manifest.json`)
- **Código:** [`src/lol_knowledge/optimizer/`](../../src/lol_knowledge/optimizer/) y subcomando `python -m lol_knowledge optimize` en [`src/lol_knowledge/cli.py`](../../src/lol_knowledge/cli.py).
- **Pruebas:** [`tests/test_optimizer.py`](../../tests/test_optimizer.py).
- **Fecha:** 2026-11-21.
- **Estado:** completada.

## Qué se implementó

1. **Objetivos medibles y restricciones (`OPT-01`):**
   - `rotation_damage`, `dps` (activa `--timeline` automáticamente), `healing`, `effective_health_physical`, `effective_health_magic`, `effective_health_mixed` (media armónica exacta ponderada con `--damage-mix`) y `time_to_die` (con `--incoming` o rotación enemiga `--enemy-champion` evaluada dinámicamente contra cada build candidata).
   - Restricciones comprobadas: `--budget` (oro oficial de Data Dragon), `--slots` (`1..6`), `--require-item`, `--forbid-item`, `--require-boots`, `--tier completed|all`, `--only-verified`, `--top`, `--beam-width`, `--pool-limit`, más legalidad de página de runas (`RUN-04`) y grupos exclusivos de objetos (`OBJ-13`).

2. **Búsqueda determinista con poda y telemetría (`OPT-02`):**
   - Pre-filtrado por relevancia marginal de un objeto (manteniendo multiplicadores sinérgicos como Rabadon, Filo infinito y penetración porcentual), búsqueda en haz ranura a ranura (`beam search`) con poda incremental de legalidad/presupuesto y refinamiento local `1-swap` sobre los finalistas.
   - `SearchStats` informa en cada ejecución del tamaño del espacio, estados evaluados, podas (`pruned_illegal`, `pruned_budget`, `pruned_beam`), estrategia y milisegundos reales (`elapsed_ms`).
   - Mediciones de referencia (`16.23.1`, Windows, Python 3.14):
     - Garen nv. 11, `effective_health_mixed`, `3` huecos, `9500 g`, botas obligatorias (`beam=24, pool=22`): `1930` estados en `1056 ms`.
     - Ahri nv. 18, `rotation_damage`, `6` huecos, botas obligatorias (`beam=12, pool=16`): `2426` estados en `19,1 s` (frente a `C(125, 6) ≈ 4,8 × 10^9` combinaciones).

3. **Propagación de etiqueta más débil y separación (`OPT-03`):**
   - Cada build conserva la etiqueta más débil de sus entradas (`Oficial`/`Derivado` frente a `Pendiente de verificación`), incluyendo objetos con `effect_review: pending` en objetivos defensivos y notas de runas faltantes.
   - Dos pasadas independientes (subconjunto verificado + conjunto completo salvo `--only-verified`) garantizan que `verified_builds` (`Oficial`/`Derivado`) nunca quede desplazado por objetos `pending` durante la poda del haz, y devuelve `verified_builds` y `pending_builds` en listas separadas.

## Limitaciones declaradas

- La poda heurística (`beam + 1-swap`) reduce el espacio combinatorio de miles de millones de builds a miles de evaluaciones exactas; no garantiza optimalidad global exhaustiva sobre todo `C(N, k)` (se declara explícitamente en `notes` de cada resultado).
- `OPT-04` (curva de compra por oro parcial) y `OPT-05` (rotaciones tipo automáticas por campeón) siguen pendientes en P2.
