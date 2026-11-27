# Fase `v1.2` — Modularización Arquitectónica y Pruebas de Mutación (`QA-03`, `QA-02`)

- **Versión objetivo:** `1.2.0`
- **Estado:** Planificada — pendiente de implementación
- **Prerrequisitos:** `v1.1.0` completada e integrada en `dev`
- **Rama sugerida:** `refactor/v1-2-modularize-engines`
- **Hoja de ruta:** [`../roadmap-v2.md`](../roadmap-v2.md) (`QA-03`, `QA-02`)
- **Modo de ejecución recomendado:** Orchestrator en 3 pistas disjuntas una vez fijadas las fachadas `__init__.py` (Pista A: paquete `rotation/`, Pista B: paquete `defense/`, Pista C: herramienta `mutation_check.py`).

---

## 1. Contexto y motivación (`Calculado`)

Tras completar la `v1.0.0`, cuatro módulos concentran un volumen excesivo de responsabilidades acopladas:

- [`src/lol_knowledge/rotation.py`](../../src/lol_knowledge/rotation.py): **`5.202` líneas** (parseo de pasos, modelo de partes, mitigación/modificadores, ataques y contadores, habilidades, activas de objeto, hechizos de invocador, quemaduras continuas, reloj y ventanas `--window`, y sesión incremental `RotationSession` para duelos).
- [`src/lol_knowledge/defense.py`](../../src/lol_knowledge/defense.py): **`4.095` líneas** (parseo `--incoming`, escudos tipados y reactivos, daño reciente almacenado, reducciones porcentuales/planas, negaciones, bloqueos de CC con tenacidad/purgas y sesión incremental `DefenseSession`).
- [`src/lol_knowledge/cli.py`](../../src/lol_knowledge/cli.py) (`1.938` líneas) y [`src/lol_knowledge/contract.py`](../../src/lol_knowledge/contract.py) (`1.429` líneas): duplican lógica de ensamblaje de `StatSheet` con legalidad, pasivas, runas, invocadores, elixires y Ornn.

Dividir estos módulos **antes** de añadir nuevas mecánicas de combate en `v1.3` y `v1.4` reduce errores de acoplamiento y permite trabajo paralelo limpio en las fases siguientes.

---

## 2. Invariantes y restricciones innegociables

- **Refactorización pura (`0` cambios semánticos):** las salidas de CLI, JSON, Contrato y MCP deben ser byte a byte idénticas a `v1.1.0` (verificado con `tests/test_performance_equivalence.py` y toda la suite actual).
- **Compatibilidad total de importaciones públicas:** `from lol_knowledge.rotation import ...` y `from lol_knowledge.defense import ...` deben seguir exponiendo exactamente los mismos símbolos públicos en sus `__init__.py` sin romper tests ni código consumidor.
- **Sin degradación de rendimiento:** `research/tools/benchmark_engine.py` no debe empeorar más de un `3 %` respecto a `v1.1.0`.

---

## 3. Plan de implementación paso a paso

### Paso 1 — Paquete `src/lol_knowledge/rotation/` (sustituyendo `rotation.py`)
Descomponer `rotation.py` en submódulos cohesivos de `< 1.200` líneas cada uno:
1. `rotation/models.py`: `Step`, `CritBase`, `Healing`, `NO_HEALING`, `Part`, `StepOutcome`, `Timeline`, `TimelineWindow`, `RotationOutcome`, constantes de dominio y `parse_steps`.
2. `rotation/effects.py`: representación interna `_Effect`, `_Window`, `_Burn`, extracción y filtrado de efectos del catálogo, evaluación de condiciones (`_conditions_hold`) y límites (`_limited`).
3. `rotation/timeline.py`: cálculo de enfriamientos efectivos, validación de lanzamientos y reactivaciones (`_cast`), devengo continuo de quemaduras y procs diferidos (`_accrue`) y cálculo de `TimelineWindow`.
4. `rotation/combat_steps.py`: resolución de ataques básicos, contadores cada N golpes, Impacto fantasma, Hoja encantada, habilidades (`_ability` y `active_effects`), activas de objeto (`_item_active`), hechizos de invocador y ejecuciones (`_execute`).
5. `rotation/session.py`: `_Runner`, `DuelStepResult`, `RotationSession`, `open_rotation_session` y punto de entrada `evaluate_rotation`.
6. `rotation/__init__.py`: reexportación explícita (`__all__`) de toda la API pública anterior.

### Paso 2 — Paquete `src/lol_knowledge/defense/` (sustituyendo `defense.py`)
Descomponer `defense.py` en submódulos cohesivos de `< 1.100` líneas cada uno:
1. `defense/models.py`: `IncomingHit`, `DefenseStep`, `DefenseOutcome`, `DefenseState`, `parse_incoming` y `hits_from_rotation`.
2. `defense/shields_heals.py`: `_ActiveShield`, `_StaggerBleed`, escudos reactivos (Salvavidas, *Protector*, *Rookern*), almacenamiento de daño reciente (`Sett W`, `Mordekaiser W`, `Tahm Kench E`, `Rengar W`, `Dr. Mundo W`), *Fuerzas renovadas* y *Revestimiento de huesos*.
3. `defense/cc_negations.py`: aplicación de `CCEffectSpec`, cálculo de duración con tenacidad y suelo `0,3 s`, purgas (*Limpiar*, QSS, campeones), inmunidades, escudos de hechizos, esquivas, bloqueo de primer impacto, invulnerabilidad/inmortalidad y estasis.
4. `defense/session.py`: `DefenseSession`, `open_defense_session` y `evaluate_defense`.
5. `defense/__init__.py`: reexportación explícita (`__all__`) de toda la API pública anterior.

### Paso 3 — Unificación de ensamblaje de escenarios (`src/lol_knowledge/loadout.py`)
- Extraer la construcción compartida de `StatSheet` validada (objetos + legalidad + pasivas de hoja + página de runas/fragmentos + hechizos de invocador + elixir + mejora de Ornn) usada tanto por `cli.py` como por `contract.py` a un módulo único `src/lol_knowledge/loadout.py`, eliminando duplicación y divergencias sutiles entre CLI y MCP.

### Paso 4 — Pruebas de mutación deterministas sobre el núcleo (`QA-02`)
- Crear `research/tools/mutation_check.py` (usando únicamente el módulo estándar `ast` y `subprocess`/`pytest` focalizado, sin añadir dependencias externas):
  - Aplica mutaciones atómicas controladas (operadores aritméticos `+`/`-`, `*`/`/`, comparadores `<`/`<=`/`>`/`>=` y constantes de borde `0`/`1`) sobre `damage/`, `stats/sheet.py`, `survival.py`, `tenacity` y los submódulos críticos de `rotation/` y `defense/`.
  - Ejecuta el subconjunto relevante de tests por mutante con *timeout* corto y reporta tasa de mutantes cazados (*mutation score*).
- Añadir tests unitarios en `tests/` para matar cualquier mutante superviviente legítimo (no equivalente) detectado en las fórmulas del motor.
- Documentar el uso de `mutation_check.py` en `odd/procedures/` y elevar `__version__` a `"1.2.0"`.

---

## 4. Validaciones obligatorias y criterios de salida (`Definición de terminado`)

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m pytest research/tests -q
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check .
.\.venv\Scripts\python.exe -m lol_knowledge validate
.\.venv\Scripts\python.exe research\tools\benchmark_engine.py
.\.venv\Scripts\python.exe research\tools\mutation_check.py --ci-sample
```

- [ ] Ningún archivo bajo `src/lol_knowledge/rotation/` ni `src/lol_knowledge/defense/` supera las `1.500` líneas.
- [ ] `100 %` de los tests existentes y `test_performance_equivalence.py` pasan sin cambios en valores esperados.
- [ ] `mutation_check.py` alcanza `>= 95 %` de mutantes no equivalentes cazados sobre `damage/` y `survival.py`, y `>= 90 %` sobre `stats/sheet.py`.
- [ ] Integrado en `integration`, validado y promovido con `--ff-only` a `dev` (sin `push`).
