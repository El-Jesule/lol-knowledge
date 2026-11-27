# Fase `v1.1` — Modularización Arquitectónica e Higiene Post-v1.0 (`QA-03`, `FIX-01`, `DOC-08`)

- **Versión objetivo:** `1.1.0`
- **Estado:** Completada (`2026-11-27`)
- **Prerrequisitos:** `v1.0.0` (`dev` en `bc431d0` o posterior)
- **Rama sugerida:** `refactor/v1-1-modularize-engines`
- **Hoja de ruta:** [`../roadmap-v2.md`](../roadmap-v2.md) (`QA-03`, `FIX-01`, `DOC-08`)
- **Modo de ejecución recomendado:** Orchestrator en 2 pistas disjuntas tras crear el arnés de equivalencia y fijar las fachadas `__init__.py` (Pista A: paquete `rotation/` + `FIX-01`; Pista B: paquete `defense/` + `DOC-08`), seguido de un paso único para `loadout.py` y validación final.

---

## 1. Contexto y motivación (`Calculado`)

Tras completar la `v1.0.0`, cuatro módulos concentran un volumen excesivo de responsabilidades acopladas:

- [`src/lol_knowledge/rotation.py`](../../src/lol_knowledge/rotation.py): **`5.202` líneas** (parseo de pasos, modelo de partes, mitigación/modificadores, ataques y contadores, habilidades, activas de objeto, hechizos de invocador, quemaduras continuas, reloj y ventanas `--window`, y sesión incremental `RotationSession` para duelos).
- [`src/lol_knowledge/defense.py`](../../src/lol_knowledge/defense.py): **`4.095` líneas** (parseo `--incoming`, escudos tipados y reactivos, daño reciente almacenado, reducciones porcentuales/planas, negaciones, bloqueos de CC con tenacidad/purgas y sesión incremental `DefenseSession`).
- [`src/lol_knowledge/cli.py`](../../src/lol_knowledge/cli.py) (`1.938` líneas) y [`src/lol_knowledge/contract.py`](../../src/lol_knowledge/contract.py) (`1.429` líneas): duplican lógica de ensamblaje de `StatSheet` con legalidad, pasivas, runas, invocadores, elixires y Ornn.
- **Bug detectado en auditoría (`FIX-01`):** lanzar en `rotation` o `duel` una habilidad aprendida que solo tiene `cc_effects` y carece de `cases` y `active_effects` (ej. `Darius E` en el ejemplo de [`README.md`](../../README.md)) falla con `step E: E has no modelled damage cases or active effects`.
- **Deuda documental puntual (`DOC-08`):** secciones antiguas de [`lol-knowledge/objects/README.md`](../../lol-knowledge/objects/README.md) (§5–§6: «42 objetos curados») y [`lol-knowledge/mechanics/passives.md`](../../lol-knowledge/mechanics/passives.md) (§Fuera de alcance mencionando `CH-04` como pendiente).

Ordenar la casa primero en `v1.1` deja paquetes pequeños (`< 1.500` líneas) que permiten ejecutar en paralelo tanto la optimización de rendimiento (`v1.2`) como todas las fases posteriores (`v1.3`–`v2.0`).

---

## 2. Invariantes y restricciones innegociables

- **Refactorización pura (`0` cambios semánticos salvo `FIX-01`):** para cualquier escenario válido previo, las salidas de CLI, JSON, Contrato y MCP deben ser **100 % idénticas** en `Fraction`, etiquetas, notas y rankings.
- **Compatibilidad total de importaciones públicas:** `from lol_knowledge.rotation import ...` y `from lol_knowledge.defense import ...` deben seguir exponiendo exactamente los mismos símbolos públicos en sus `__init__.py` sin romper tests ni consumidores.
- **Biblioteca estándar pura en runtime** ([`AGENTS.md`](../../AGENTS.md) §9) y **cero red en `tests/`** (§8).

---

## 3. Plan de implementación paso a paso

### Paso 1 — Arnés de equivalencia exacta y línea base de tiempos
1. Crear `tests/test_performance_equivalence.py` que capture instantáneas doradas en memoria (daño exacto `Fraction`, vida restante, curación, escudos, etiquetas, notas y top builds) cubriendo:
   - `stats` (con conversiones globales: Zeri, Jhin, Vladimir, Pyke, Ryze, Ornn, Cassiopeia, Hecarim).
   - `rotation --timeline --window` (con quemaduras, Guinsoo+Kraken, Hoja encantada, pasivas acumulables y runas).
   - `survive` y `duel` (con CC, tenacidad, purgas y estasis).
   - `optimize` (`rotation_damage`, `dps`, `effective_health_mixed`, `time_to_die`, `duel`, `--ornn-upgrade`, `--purchase-curve`, `--gold-checkpoints`).
2. Crear `research/tools/benchmark_engine.py` que mida e imprima `wall_ms`, `states_evaluated` y `ms/state` en frío y en caliente para dejar registrada la línea base antes de `v1.2`.

### Paso 2 — Paquete `src/lol_knowledge/rotation/` (sustituyendo `rotation.py`)
Descomponer `rotation.py` en submódulos cohesivos de `< 1.200` líneas cada uno:
1. `rotation/models.py`: `Step`, `CritBase`, `Healing`, `NO_HEALING`, `Part`, `StepOutcome`, `Timeline`, `TimelineWindow`, `RotationOutcome`, constantes de dominio y `parse_steps`.
2. `rotation/effects.py`: representación interna `_Effect`, `_Window`, `_Burn`, extracción y filtrado de efectos del catálogo, evaluación de condiciones (`_conditions_hold`) y límites (`_limited`).
3. `rotation/timeline.py`: cálculo de enfriamientos efectivos, validación de lanzamientos y reactivaciones (`_cast`), devengo continuo de quemaduras y procs diferidos (`_accrue`) y cálculo de `TimelineWindow`.
4. `rotation/combat_steps.py`: resolución de ataques básicos, contadores cada N golpes, Impacto fantasma, Hoja encantada, habilidades (`_ability` y `active_effects`), activas de objeto (`_item_active`), hechizos de invocador y ejecuciones (`_execute`).
5. `rotation/session.py`: `_Runner`, `DuelStepResult`, `RotationSession`, `open_rotation_session` y punto de entrada `evaluate_rotation`.
6. `rotation/__init__.py`: reexportación explícita (`__all__`) de toda la API pública anterior.

### Paso 3 — Paquete `src/lol_knowledge/defense/` (sustituyendo `defense.py`)
Descomponer `defense.py` en submódulos cohesivos de `< 1.100` líneas cada uno:
1. `defense/models.py`: `IncomingHit`, `DefenseStep`, `DefenseOutcome`, `DefenseState`, `parse_incoming` y `hits_from_rotation`.
2. `defense/shields_heals.py`: `_ActiveShield`, `_StaggerBleed`, escudos reactivos (Salvavidas, *Protector*, *Rookern*), almacenamiento de daño reciente (`Sett W`, `Mordekaiser W`, `Tahm Kench E`, `Rengar W`, `Dr. Mundo W`), *Fuerzas renovadas* y *Revestimiento de huesos*.
3. `defense/cc_negations.py`: aplicación de `CCEffectSpec`, cálculo de duración con tenacidad y suelo `0,3 s`, purgas (*Limpiar*, QSS, campeones), inmunidades, escudos de hechizos, esquivas, bloqueo de primer impacto, invulnerabilidad/inmortalidad y estasis.
4. `defense/session.py`: `DefenseSession`, `open_defense_session` y `evaluate_defense`.
5. `defense/__init__.py`: reexportación explícita (`__all__`) de toda la API pública anterior.

### Paso 4 — Unificación de ensamblaje de escenarios (`src/lol_knowledge/loadout.py`)
- Extraer la construcción compartida de `StatSheet` validada (objetos + legalidad + pasivas de hoja + página de runas/fragmentos + hechizos de invocador + elixir + mejora de Ornn) usada tanto por `cli.py` como por `contract.py` a un módulo único `src/lol_knowledge/loadout.py`, eliminando duplicación y divergencias sutiles entre CLI y MCP.

### Paso 5 — Corrección `FIX-01` (habilidades de CC puro en `rotation`/`duel`) e higiene `DOC-08`
1. En `rotation/combat_steps.py` (`_ability`) y [`src/lol_knowledge/duel.py`](../../src/lol_knowledge/duel.py) (`_parse_priority_slots`):
   - Permitir lanzar una habilidad aprendida cuando `ability.cc_effects` no esté vacío aunque `ability.cases` y `ability.active_effects` estén vacíos (descontando su coste oficial, aplicando su enfriamiento en `--timeline`, cargando *Hoja encantada*, disparando pasivas `after_ability` y entregando el CC en `duel.py`).
   - Añadir test de regresión con el duelo exacto de [`README.md`](../../README.md) (`Darius` con `E, attack, W, Q.blade, R` contra `Garen`).
2. Actualizar [`lol-knowledge/objects/README.md`](../../lol-knowledge/objects/README.md) (§5–§6) y [`lol-knowledge/mechanics/passives.md`](../../lol-knowledge/mechanics/passives.md) (§Fuera de alcance) al estado real de `catalog_version: 28` y `CH-04`, y elevar `__version__` a `"1.1.0"`.

---

## 4. Validaciones obligatorias y criterios de salida (`Definición de terminado`)

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m pytest research/tests -q
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check .
.\.venv\Scripts\python.exe -m lol_knowledge validate
.\.venv\Scripts\python.exe research\tools\benchmark_engine.py
```

- [x] Ningún archivo bajo `src/lol_knowledge/rotation/` ni `src/lol_knowledge/defense/` supera las `1.500` líneas:
  - `rotation/`: `__init__.py` (`71`), `models.py` (`436`), `timeline.py` (`673`), `runner.py` (`706`), `effects.py` (`972`), `session.py` (`1.066`), `combat_steps.py` (`1.203`).
  - `defense/`: `__init__.py` (`27`), `models.py` (`294`), `cc_negations.py` (`1.049`), `session.py` (`1.271`), `shields_heals.py` (`1.335`).
- [x] `100 %` de los tests existentes y `test_performance_equivalence.py` pasan con `0` discrepancias en `Fraction`, etiquetas, notas y rankings.
- [x] El duelo `Darius vs Garen` actualizado de `README.md` y las habilidades de CC puro (`Elise E`, `Renata R`, `Veigar E`, `Viktor W`) pasan en CLI, Contrato JSON y MCP (`FIX-01`). Nota de verificación (`AGENTS.md` §2.1): `Darius E` (*Atrapar*) en `lol-knowledge/champions/Darius/kit.json` no declara `cc_effects` porque el `.bin` del cliente (`DariusAxeGrabCone`) no publica duración numérica de levantamiento/atracción; se mantiene `not_modelled` sin inventar cifras, y se actualizó el ejemplo de `README.md` con casos válidos (`attack, W, Q.blade, R.base` vs `Q, E.tick, R`).
- [x] `loadout.py` unifica el ensamblaje de `StatSheet` entre `cli.py` y `contract.py`, `DOC-08` actualizado en `lol-knowledge/objects/README.md` y `lol-knowledge/mechanics/passives.md`, y `__version__ = "1.1.0"`.
- [x] Línea base de rendimiento registrada (`research/tools/benchmark_engine.py`, pre-`v1.2`): `stats_vladimir` `135.509 ms` frío / `0.609 ms` caliente; `rotation_timeline_window` `330.033 ms` / `30.746 ms`; `survive_timeline` `130.550 ms` / `3.108 ms`; `duel_1v1` `332.003 ms` / `86.440 ms`; `optimize_rotation_damage` `2737.753 ms` (`13.6888 ms/state`, 200 estados); `optimize_effective_health` `355.454 ms` (`1.6084 ms/state`, 221 estados); `optimize_duel` `13711.402 ms` (`108.8207 ms/state`, 126 estados).
- [x] Integrado en `integration`, validado con la suite completa y promovido con `--ff-only` a `dev` (sin `push`).
