# Fase `v1.2` — Rendimiento del Núcleo, Caché en RAM y Pruebas de Mutación (`PERF-01..04`, `QA-02`)

- **Versión objetivo:** `1.2.0`
- **Estado:** Planificada — pendiente de implementación
- **Prerrequisitos:** `v1.1.0` completada (paquetes `rotation/`, `defense/`, `loadout.py`, `test_performance_equivalence.py` y `benchmark_engine.py` en `dev`)
- **Rama sugerida:** `perf/v1-2-engine-caching-and-mutation`
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

- [ ] `test_performance_equivalence.py` pasa con `0` discrepancias en `Fraction`, etiquetas, notas y rankings.
- [ ] Consulta `stats` / `rotation` en caliente (vía `execute_request` / MCP) baja de `135–268 ms` a **`< 5 ms`**.
- [ ] `optimize` (`rotation_damage`, 3 huecos, `716` estados) baja de `~16,2 s` a **`<= 2,0 s`** (`>= 8×` de mejora real medida).
- [ ] `mutation_check.py` alcanza `>= 95 %` de mutantes no equivalentes cazados sobre `damage/` y `survival.py`, y `>= 90 %` sobre `stats/sheet.py`.
- [ ] Integrado en `integration`, validado con la suite completa y promovido con `--ff-only` a `dev` (sin `push`).
