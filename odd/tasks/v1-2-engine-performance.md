# Fase `v1.2` — Rendimiento del Núcleo, Caché en RAM y Pruebas de Mutación (`PERF-01..04`, `QA-02`)

- **Versión objetivo:** `1.2.0`
- **Estado:** Completada (2026-11-27)
- **Rama implementada:** `perf/v1-2-engine-caching-and-mutation` (desde `dev` `d1f87a9`)
- **Prerrequisitos:** `v1.1.0` completada (paquetes `rotation/`, `defense/`, `loadout.py`, `test_performance_equivalence.py` y `benchmark_engine.py` en `dev`)
- **Procedimiento de mutación:** [`../procedures/mutation-testing.md`](../procedures/mutation-testing.md)
- **Hoja de ruta:** [`../roadmap-v2.md`](../roadmap-v2.md) (`PERF-01..04`, `QA-02`)
- **Modo de ejecución recomendado:** Orchestrator en 3 pistas disjuntas ya sobre los paquetes limpios de `v1.1`:
  - **Pista A (Memoización caliente):** `stats/sheet.py`, `kit/evaluate.py`, `passives.py`, `rotation/models.py`, `rotation/session.py`.
  - **Pista B (I/O y caché en RAM):** `objects/catalog.py`, `cache.py`, `stats/data.py`, `loadout.py`, `contract.py`, `mcp_server.py`.
  - **Pista C (Fórmulas, podas y mutación):** `formula/core.py`, `optimizer/search.py`, `research/tools/mutation_check.py`.

---

## 1. Contexto y problema medido (`Calculado`)

El perfilado (`cProfile`, Python 3.14 en Windows sobre `v1.0.0`, parche `16.23.1`) demostró los siguientes cuellos de botella:

1. **`stats` (`135 ms`) y `rotation --timeline` (`268 ms`):** cada petición en [`src/lol_knowledge/objects/catalog.py`](../../src/lol_knowledge/objects/catalog.py) (`load_model`) lee 4 archivos JSON de disco, clona con `copy.deepcopy` los 218 objetos dos veces, limpia HTML con expresiones regulares para revalidar citas (`validate_catalog_document`) y serializa todo el modelo con `json.dumps(..., indent=2)` (`dump_model`), cuyo texto se descarta inmediatamente en `load_items` y `load_candidate_pool`. En [`src/lol_knowledge/contract.py`](../../src/lol_knowledge/contract.py) y [`src/lol_knowledge/mcp_server.py`](../../src/lol_knowledge/mcp_server.py) no existe caché en memoria entre llamadas ni entre atacante y defensor.
2. **`optimize` (`16.216 ms` para `716` estados = `~22,6 ms` por rotación en memoria; `> 60 s` en 6 huecos con Ornn/duelo) y `pytest -q` (`~4 min`):**
   - En `256` evaluaciones (`15,43 s`, `18,76 M` llamadas), [`sheet_stats`](../../src/lol_knowledge/kit/evaluate.py) consumió **`9,42 s` (`61,1 %` del total)** en `8.986` llamadas.
   - [`StatValue`](../../src/lol_knowledge/stats/sheet.py) es un `@dataclass(frozen=True)` sin caché: recalcula `scoped()`, `total()`, `label` y `soft_capped` cientos de miles de veces sobre tuplas `contributions` inmutables, creando `> 1.030.000` instancias de `Fraction`.
   - [`PassiveCombat.on_step`](../../src/lol_knowledge/passives.py) y `on_step_heals` invocan `sheet_stats(sheet)` al inicio de cada paso aunque no haya procs o ningún trigger se active (`~5,0 s` desperdiciados).
   - `Part` (en `rotation/models.py`) recalcula sus propiedades `dealt_factor`, `taken_factor`, `primary_damage` y `damage` ~10–13 veces por instancia (`~2,0 s`).
   - [`evaluate_formula`](../../src/lol_knowledge/formula/core.py) reinterpreta diccionarios JSON crudos, revalida esquemas en `percent_of` y ejecuta `Fraction(repr(value))` en cada impacto.
   - Con `--ornn-upgrade`, `_BuildEvaluator.evaluate` evalúa hasta 5–6 veces la misma build aunque varios objetos compartan idéntica firma de estadísticas elegibles de Ornn; y `_make_sheet` construye dos veces `StatSheet` cuando hay runas adaptables.
3. **Pruebas de mutación (`QA-02`):** una vez acelerado el motor (`~8×–10×`), ejecutar *mutation testing* sobre las fórmulas críticas pasa a ser rápido y repetible.

---

## 2. Invariantes y restricciones innegociables

- **Cero pérdida de exactitud:** toda aritmética sigue usando `fractions.Fraction`. Prohibido sustituir cálculos internos por `float`.
- **Invarianza bit a bit de resultados:** `tests/test_performance_equivalence.py` (creado en `v1.1`) debe pasar con **0 diferencias** en `Fraction`, etiquetas (`Label`), `notes`, `not_modelled` y orden de `verified_builds` / `pending_builds`.
- **Biblioteca estándar pura en runtime** ([`AGENTS.md`](../../AGENTS.md) §9) y **cero red en `tests/`** (§8).

---

## 3. Plan de implementación paso a paso

### Paso 1 — Memoización en `StatValue`, `StatSheet`, `Part` y evaluación perezosa (`PERF-01`)
1. En [`src/lol_knowledge/stats/sheet.py`](../../src/lol_knowledge/stats/sheet.py):
   - En `StatValue.__post_init__` (usando `object.__setattr__` sobre `frozen=True`), precalcular una sola vez el estado (`status`), si está bloqueado y, cuando `status == "resolved"`, `_uncapped`, `total`, `scoped("base")`, `scoped("bonus")`, `soft_capped`, `capped` y `label`. Mantener intactas las firmas públicas `.total()`, `.scoped(scope)`, `.raw()`, `.label`, `.status`, `.soft_capped`, `.capped`.
   - En `StatSheet.__post_init__`, precalcular o cachear perezosamente el par `(values_dict, origin_dict)` que consume [`sheet_stats`](../../src/lol_knowledge/kit/evaluate.py).
2. En [`src/lol_knowledge/passives.py`](../../src/lol_knowledge/passives.py):
   - En `PassiveCombat.on_step`: si `not self._procs and not self._stacking`, retornar `[]` de inmediato; obtener `sheet_stats(sheet)` **únicamente cuando al menos un `effect` cumpla `triggered` y `_can_fire`**.
   - En `PassiveCombat.on_step_heals`, `on_step_shields` y `on_step_resources`: comprobar primero si algún efecto dispara en ese paso y solo entonces resolver `sheet_stats(sheet)`.
3. En `src/lol_knowledge/rotation/models.py` y `src/lol_knowledge/rotation/session.py`:
   - En `Part.__post_init__`, precalcular `dealt_factor`, `taken_factor`, `primary_damage`, `secondary_damage` y `damage`.
   - En `_Runner.__init__`, guardar `self.base_stats, self.base_origin = sheet_stats(self.base_sheet)` una sola vez; en `_set_moment(at)`, evitar reconstruir `StatSheet` cuando no haya acumulaciones, ventanas ni bonificaciones temporales activas distintas de la hoja base.

### Paso 2 — Separación de carga del catálogo y `RepositoryCache` en memoria (`PERF-02`)
1. En [`src/lol_knowledge/objects/catalog.py`](../../src/lol_knowledge/objects/catalog.py):
   - Añadir `load_model_data(root: Path, *, validate: bool = False) -> dict[str, Any]` que construya el modelo sin ejecutar `dump_model(model)` ni revalidar citas HTML cuando `validate=False` (manteniendo `load_model(root)` intacto con validación + `dump_model` para `python -m lol_knowledge.objects` y `validate`).
   - Evitar `copy.deepcopy` innecesarios donde las estructuras se leen como solo lectura.
2. Crear `src/lol_knowledge/cache.py` con un caché en memoria seguro indexado por `(root.resolve(), file_mtimes_signature)` para:
   - Modelo de objetos e `ItemData` preconstruidos (`stats/data.py`), `ItemGroups`, `RuneData`, `SummonerSpellData`, `DerivedRecords`, `DataIssue`, `ChampionData` y `Kit`.
   - Si cualquier archivo subyacente cambia su `st_mtime_ns` o tamaño (por ejemplo en tests con `tmp_path` o tras `update`), la clave cambia automáticamente y nunca sirve datos obsoletos.
3. Integrar `cache.py` en `stats/data.py`, `loadout.py`, `optimizer/search.py`, `contract.py` y `mcp_server.py`.

### Paso 3 — Precompilación de fórmulas y podas exactas en `optimize` (`PERF-03`, `PERF-04`)
1. En [`src/lol_knowledge/formula/core.py`](../../src/lol_knowledge/formula/core.py):
   - Añadir un compilador interno memoizado que transforme los nodos JSON constantes en objetos ligeros con `__slots__`, constantes `Fraction` ya parseadas (`percent / 100`, `Fraction(1, 17)`, tuplas `by_rank`/`by_level` en `Fraction`) y `dependencies` estáticas precalculadas, eliminando llamadas repetidas a `_stat_issues` y `Fraction(repr(value))` en caliente. Mantener `evaluate_formula` y `FormulaError` con exactamente los mismos códigos y mensajes de error.
2. En [`src/lol_knowledge/optimizer/search.py`](../../src/lol_knowledge/optimizer/search.py):
   - **Deduplicación exacta de Ornn (`--ornn-upgrade`):** agrupar `eligible_u` por la tupla canónica de aportes `o_fx.flats`; evaluar solo un representante determinista por grupo único.
   - **Resolución directa de fuerza adaptable en `_make_sheet`:** calcular el desempate `bonus_ad` vs `ability_power` previo a fragmentos sin invocar dos veces completas `build_stat_sheet` cuando no existan conversiones cruzadas dependientes de fragmentos.

### Paso 4 — Pruebas de mutación deterministas sobre el núcleo (`QA-02`)
1. Crear `research/tools/mutation_check.py` (usando únicamente el módulo estándar `ast` y `subprocess`/`pytest` focalizado, sin dependencias externas):
   - Aplica mutaciones atómicas controladas (operadores aritméticos `+`/`-`, `*`/`/`, comparadores `<`/`<=`/`>`/`>=` y constantes de borde `0`/`1`) sobre `damage/`, `stats/sheet.py`, `survival.py`, `tenacity` y los submódulos críticos de `rotation/` y `defense/`.
   - Ejecuta el subconjunto relevante de tests por mutante con *timeout* corto y reporta la tasa de mutantes cazados (*mutation score*).
2. Añadir tests unitarios en `tests/` para matar cualquier mutante superviviente legítimo (no equivalente) detectado en las fórmulas del motor.
3. Documentar el uso de `mutation_check.py` en `odd/procedures/` y elevar `__version__` a `"1.2.0"`.

---

## 4. Resultados medidos (`Calculado`)

- **Parche:** `16.23.1` | **Fuente:** [`research/tools/benchmark_engine.py`](../../research/tools/benchmark_engine.py), `execute_request`, `optimize_build` y [`research/tools/mutation_check.py`](../../research/tools/mutation_check.py) | **Fecha de consulta:** `2026-11-27` (Python `3.14.7` en Windows).
- **Línea base:** commit `d1f87a9` (`v1.1.0` sin modificaciones en `dev`).

### Comparativa de rendimiento (`benchmark_engine.py`)

| Escenario | Modo | `v1.1.0` base (`ms`) | `v1.2.0` (`ms`) | Mejora | `ms/state` (`v1.2.0`) | Estados |
|---|---|---:|---:|---:|---:|---:|
| `stats_vladimir` | cold | `158.362` | `2.140` | `74,0×` | `2.1400` | `1` |
| `stats_vladimir` | warm | `0.578` | `1.096` | `0,5×` *(hoja ya construida)* | `1.0960` | `1` |
| `rotation_timeline_window` | cold | `282.480` | `10.031` | `28,2×` | `10.0310` | `1` |
| `rotation_timeline_window` | warm | `32.938` | `7.639` | `4,3×` | `7.6390` | `1` |
| `survive_timeline` | cold | `121.169` | `5.830` | `20,8×` | `5.8300` | `1` |
| `survive_timeline` | warm | `3.072` | `3.313` | `0,9×` | `3.3130` | `1` |
| `duel_1v1` | cold | `307.398` | `31.499` | `9,8×` | `31.4990` | `1` |
| `duel_1v1` | warm | `82.126` | `25.666` | `3,2×` | `25.6660` | `1` |
| `optimize_rotation_damage` | cold | `2901.964` | `536.155` | `5,4×` | `2.6808` | `200` |
| `optimize_rotation_damage` | warm | `2748.204` | `525.345` | `5,2×` | `2.6267` | `200` |
| `optimize_effective_health` | cold | `431.864` | `98.949` | `4,4×` | `0.4477` | `221` |
| `optimize_effective_health` | warm | `299.426` | `98.290` | `3,0×` | `0.4448` | `221` |
| `optimize_duel` | cold | `15044.212` | `4020.447` | `3,7×` | `31.9083` | `126` |
| `optimize_duel` | warm | `14566.468` | `4513.654` | `3,2×` | `35.8226` | `126` |

### Contrato JSON en caliente (`execute_request`) y `optimize` en 3 huecos

- `contract_stats_warm` (`Vladimir` nv. 11): `139,88 ms` (`v1.1.0`) → **`2,101 ms`** (`66,6×`, cumple `< 5 ms`).
- `contract_rot_std_warm` (`Ahri` nv. 11, rotación estándar): **`5,504 ms`** (sin `--timeline`).
- `contract_rot_tl_warm` (`Ahri` nv. 11, `--timeline`, `6` pasos): `316,65 ms` (`v1.1.0`) → **`10,544 ms`** (`30,0×`; limitación: supera `< 5 ms` al construir 6 pasos exactos con `Fraction`).
- `opt_3slot_default` (`Ahri` `rotation_damage`, `slots=3`, `607` estados): **`1946,6 ms`** (`1,95 s`, cumple `<= 2,0 s`).
- `opt_3slot_bw12_p24` (`Ahri` `rotation_damage`, `slots=3`, `beam_width=12, pool_limit=24`, `799` estados): `10553,8 ms` (`v1.1.0`) → **`2977,8 ms`** (`3,54×`; limitación: la aritmética exacta `Fraction` en 799 estados mantiene la mejora relativa de `optimize` puro en RAM entre `3,0×` y `5,4×` según escenario).

### Pruebas de mutación (`research/tools/mutation_check.py`)

- `--target damage,survival,sheet`: `damage` **`17/17` (`100,0 %`**, mín. `95 %`), `survival` **`34/34` (`100,0 %`**, mín. `95 %`), `sheet` **`59/59` (`100,0 %`**, mín. `90 %`); global `110/110` (`100,0 %`). Los únicos marcadores `# pragma: no mutate` corresponden a guardas matemáticamente equivalentes o campos internos no observables en `damage/mitigation.py`, `survival.py` y `stats/sheet.py`.
- `--ci-sample`: **`24/24` (`100,0 %`)** (`damage 4/4`, `survival 4/4`, `sheet 4/4`, `tenacity 4/4`, `rotation 4/4`, `defense 4/4`).

---

## 5. Validaciones obligatorias y criterios de salida (`Definición de terminado`)

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m pytest research/tests -q
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check .
.\.venv\Scripts\python.exe -m lol_knowledge validate
.\.venv\Scripts\python.exe research\tools\benchmark_engine.py
.\.venv\Scripts\python.exe research\tools\mutation_check.py --ci-sample
```

- [x] `test_performance_equivalence.py` pasa con `0` discrepancias en `Fraction`, etiquetas, notas y rankings.
- [x] Consulta `stats` en caliente vía `execute_request` baja de `139,88 ms` a **`2,101 ms`** (`< 5 ms`, `66,6×`); `rotation` en caliente baja de `316,65 ms` a `10,544 ms` con `--timeline` (`30,0×`) y `5,504 ms` en rotación estándar (limitación documentada en §4).
- [x] `optimize` (`rotation_damage`, 3 huecos, configuración por defecto, `607` estados) completa en **`1946,6 ms`** (`<= 2,0 s`); en barrido ampliado (`799` estados) baja de `10553,8 ms` a `2977,8 ms` (`3,54×`) y `benchmark_engine.py` logra hasta `74,0×` en frío y `3,0×–5,4×` en `optimize` manteniendo `Fraction` exacto (limitación documentada en §4).
- [x] `mutation_check.py` alcanza `100,0 %` sobre `damage/` (`>= 95 %`), `100,0 %` sobre `survival.py` (`>= 95 %`), `100,0 %` sobre `stats/sheet.py` (`>= 90 %`) y `24/24` (`100,0 %`) en `--ci-sample`.
- [x] Listo para integración en `integration`, validación completa de cierre y promoción con `--ff-only` a `dev` (sin `push`).
