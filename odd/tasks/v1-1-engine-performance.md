# Fase `v1.1` — Rendimiento del Núcleo, Caché en RAM e Higiene Post-v1.0

- **Versión objetivo:** `1.1.0`
- **Estado:** Planificada — pendiente de implementación
- **Prerrequisitos:** `v1.0.0` (`dev` en `bc431d0` o posterior)
- **Rama sugerida:** `perf/v1-1-engine-caching`
- **Hoja de ruta:** [`../roadmap-v2.md`](../roadmap-v2.md) (`PERF-01..04`, `FIX-01`, `DOC-08`)
- **Modo de ejecución recomendado:** Secuencial (1 agente principal; toca rutas calientes compartidas antes de la modularización de `v1.2`).

---

## 1. Contexto y problema medido (`Calculado`)

El perfilado (`cProfile`, Python 3.14 en Windows sobre `v1.0.0`, parche `16.23.1`) demostró los siguientes cuellos de botella:

1. **`stats` (`135 ms`) y `rotation --timeline` (`268 ms`):** cada petición en [`src/lol_knowledge/objects/catalog.py`](../../src/lol_knowledge/objects/catalog.py) (`load_model`) lee 4 archivos JSON de disco, clona con `copy.deepcopy` los 218 objetos dos veces, limpia HTML con expresiones regulares para revalidar citas (`validate_catalog_document`) y serializa todo el modelo con `json.dumps(..., indent=2)` (`dump_model`), cuyo texto se descarta inmediatamente en `load_items` y `load_candidate_pool`. En [`src/lol_knowledge/contract.py`](../../src/lol_knowledge/contract.py) y [`src/lol_knowledge/mcp_server.py`](../../src/lol_knowledge/mcp_server.py) no existe caché en memoria entre llamadas ni entre atacante y defensor.
2. **`optimize` (`16.216 ms` para `716` estados = `~22,6 ms` por rotación en memoria; `> 60 s` en 6 huecos con Ornn/duelo):**
   - En `256` evaluaciones (`15,43 s`, `18,76 M` llamadas), [`sheet_stats`](../../src/lol_knowledge/kit/evaluate.py) consumió **`9,42 s` (`61,1 %` del total)** en `8.986` llamadas.
   - [`StatValue`](../../src/lol_knowledge/stats/sheet.py) es un `@dataclass(frozen=True)` sin caché: recalcula `scoped()`, `total()`, `label` y `soft_capped` cientos de miles de veces sobre tuplas `contributions` inmutables, creando `> 1.030.000` instancias de `Fraction`.
   - [`PassiveCombat.on_step`](../../src/lol_knowledge/passives.py) y `on_step_heals` invocan `sheet_stats(sheet)` al inicio de cada paso aunque no haya procs o ningún trigger se active (`~5,0 s` desperdiciados).
   - [`Part`](../../src/lol_knowledge/rotation.py) recalcula sus propiedades `dealt_factor`, `taken_factor`, `primary_damage` y `damage` ~10–13 veces por instancia (`~2,0 s`).
   - [`evaluate_formula`](../../src/lol_knowledge/formula/core.py) reinterpreta diccionarios JSON crudos, revalida esquemas en `percent_of` y ejecuta `Fraction(repr(value))` en cada impacto.
   - Con `--ornn-upgrade`, `_BuildEvaluator.evaluate` evalúa hasta 5–6 veces la misma build aunque varios objetos compartan idéntica firma de estadísticas elegibles de Ornn; y `_make_sheet` construye dos veces `StatSheet` cuando hay runas adaptables.
3. **Bug detectado en auditoría (`FIX-01`):** lanzar en `rotation` o `duel` una habilidad aprendida que solo tiene `cc_effects` y carece de `cases` y `active_effects` (ej. `Darius E` en el ejemplo de [`README.md`](../../README.md)) falla con `step E: E has no modelled damage cases or active effects`.
4. **Deuda documental puntual (`DOC-08`):** secciones antiguas de [`lol-knowledge/objects/README.md`](../../lol-knowledge/objects/README.md) (§5–§6: «42 objetos curados») y [`lol-knowledge/mechanics/passives.md`](../../lol-knowledge/mechanics/passives.md) (§Fuera de alcance mencionando `CH-04` como pendiente).

---

## 2. Invariantes y restricciones innegociables

- **Cero pérdida de exactitud:** toda aritmética sigue usando `fractions.Fraction`. Prohibido sustituir cálculos internos por `float`.
- **Invarianza bit a bit de resultados:** para cualquier escenario válido (salvo `FIX-01` donde antes lanzaba error en habilidades de CC puro), el resultado numérico (`exact`), las etiquetas (`Label`), las `notes`, `not_modelled` y el orden de `verified_builds` / `pending_builds` deben ser **100 % idénticos** antes y después de optimizar.
- **Biblioteca estándar pura en runtime** ([`AGENTS.md`](../../AGENTS.md) §9) y **cero red en `tests/`** (§8).

---

## 3. Plan de implementación paso a paso

### Paso 1 — Arnés de equivalencia y benchmark antes de tocar el motor (`PERF-00`)
1. Crear `tests/test_performance_equivalence.py` que capture instantáneas doradas en memoria (daño exacto `Fraction`, vida restante, curación, escudos, etiquetas, notas y top builds) cubriendo:
   - `stats` (con conversiones globales: Zeri, Jhin, Vladimir, Pyke, Ryze, Ornn, Cassiopeia, Hecarim).
   - `rotation --timeline --window` (con quemaduras, Guinsoo+Kraken, Hoja encantada, pasivas acumulables y runas).
   - `survive` y `duel` (con CC, tenacidad, purgas y estasis).
   - `optimize` (`rotation_damage`, `dps`, `effective_health_mixed`, `time_to_die`, `duel`, `--ornn-upgrade`, `--purchase-curve`, `--gold-checkpoints`).
2. Crear `research/tools/benchmark_engine.py` que mida e imprima `wall_ms`, `states_evaluated` y `ms/state` en frío y en caliente para estos escenarios.

### Paso 2 — Memoización en `StatValue`, `StatSheet`, `Part` y evaluación perezosa (`PERF-01`)
1. En [`src/lol_knowledge/stats/sheet.py`](../../src/lol_knowledge/stats/sheet.py):
   - En `StatValue.__post_init__` (usando `object.__setattr__` sobre `frozen=True`), precalcular una sola vez el estado (`status`), si está bloqueado y, cuando `status == "resolved"`, `_uncapped`, `total`, `scoped("base")`, `scoped("bonus")`, `soft_capped`, `capped` y `label`. Mantener intactas las firmas públicas `.total()`, `.scoped(scope)`, `.raw()`, `.label`, `.status`, `.soft_capped`, `.capped`.
   - En `StatSheet.__post_init__`, precalcular o cachear perezosamente el par `(values_dict, origin_dict)` que consume [`sheet_stats`](../../src/lol_knowledge/kit/evaluate.py) (devolviendo vistas inmutables o copias superficiales rápidas si un llamador muta el `dict`).
2. En [`src/lol_knowledge/passives.py`](../../src/lol_knowledge/passives.py):
   - En `PassiveCombat.on_step`: si `not self._procs and not self._stacking`, retornar `[]` de inmediato; obtener `sheet_stats(sheet)` **únicamente cuando al menos un `effect` cumpla `triggered` y `_can_fire`**.
   - En `PassiveCombat.on_step_heals`, `on_step_shields` y `on_step_resources`: comprobar primero si algún efecto dispara en ese paso y solo entonces resolver `sheet_stats(sheet)`.
3. En [`src/lol_knowledge/rotation.py`](../../src/lol_knowledge/rotation.py):
   - En `Part.__post_init__`, precalcular `dealt_factor`, `taken_factor`, `primary_damage`, `secondary_damage` y `damage`.
   - En `_Runner.__init__`, guardar `self.base_stats, self.base_origin = sheet_stats(self.base_sheet)` una sola vez; en `_set_moment(at)`, evitar reconstruir `StatSheet` cuando no haya acumulaciones, ventanas ni bonificaciones temporales activas distintas de la hoja base.

### Paso 3 — Separación de carga del catálogo y `RepositoryCache` en memoria (`PERF-02`)
1. En [`src/lol_knowledge/objects/catalog.py`](../../src/lol_knowledge/objects/catalog.py):
   - Añadir `load_model_data(root: Path, *, validate: bool = False) -> dict[str, Any]` que construya el modelo sin ejecutar `dump_model(model)` ni revalidar citas HTML cuando `validate=False` (manteniendo `load_model(root)` intacto con validación + `dump_model` para `python -m lol_knowledge.objects` y `validate`).
   - Evitar `copy.deepcopy` innecesarios donde las estructuras se leen como solo lectura.
2. Crear `src/lol_knowledge/cache.py` con un caché en memoria seguro indexado por `(root.resolve(), file_mtimes_signature)` para:
   - Modelo de objetos e `ItemData` preconstruidos (`stats/data.py`), `ItemGroups`, `RuneData`, `SummonerSpellData`, `DerivedRecords`, `DataIssue`, `ChampionData` y `Kit`.
   - Si cualquier archivo subyacente cambia su `st_mtime_ns` o tamaño (por ejemplo en tests con `tmp_path` o tras `update`), la clave cambia automáticamente y nunca sirve datos obsoletos.
3. Integrar `cache.py` en `stats/data.py`, `optimizer/search.py`, `contract.py` y `mcp_server.py`.

### Paso 4 — Precompilación de fórmulas y podas exactas en `optimize` (`PERF-03`, `PERF-04`)
1. En [`src/lol_knowledge/formula/core.py`](../../src/lol_knowledge/formula/core.py):
   - Añadir un compilador interno memoizado (o campo precompilado al cargar kits/catálogo) que transforme los nodos JSON constantes en objetos ligeros con `__slots__`, constantes `Fraction` ya parseadas (`percent / 100`, `Fraction(1, 17)`, tuplas `by_rank`/`by_level` en `Fraction`) y `dependencies` estáticas precalculadas, eliminando llamadas repetidas a `_stat_issues` y `Fraction(repr(value))` en caliente. Mantener `evaluate_formula` y `FormulaError` con exactamente los mismos códigos y mensajes de error.
2. En [`src/lol_knowledge/optimizer/search.py`](../../src/lol_knowledge/optimizer/search.py):
   - **Deduplicación exacta de Ornn (`--ornn-upgrade`):** agrupar `eligible_u` por la tupla canónica de aportes `o_fx.flats` (dos objetos con las mismas estadísticas elegibles de Ornn producen idéntica hoja y puntuación); evaluar solo un representante determinista (menor ID o mayor oro según `_rank_key`) por grupo único.
   - **Resolución directa de fuerza adaptable en `_make_sheet`:** calcular el desempate `bonus_ad` vs `ability_power` previo a fragmentos sin invocar dos veces completas `build_stat_sheet` cuando no existan conversiones cruzadas dependientes de fragmentos.

### Paso 5 — Corrección `FIX-01` (habilidades de CC puro en `rotation`/`duel`) e higiene `DOC-08`
1. En [`src/lol_knowledge/rotation.py`](../../src/lol_knowledge/rotation.py) (`_ability`, línea ~3267) y [`src/lol_knowledge/duel.py`](../../src/lol_knowledge/duel.py) (`_parse_priority_slots`, línea ~186):
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

- [ ] `test_performance_equivalence.py` pasa con `0` discrepancias en `Fraction`, etiquetas, notas y rankings.
- [ ] El duelo `Darius vs Garen` con `E` del `README.md` pasa en CLI, Contrato JSON y MCP (`FIX-01`).
- [ ] Consulta `stats` / `rotation` en caliente (vía `execute_request` / MCP) baja de `135–268 ms` a **`< 5 ms`**.
- [ ] `optimize` (`rotation_damage`, 3 huecos, `716` estados) baja de `~16,2 s` a **`<= 2,0 s`** (`>= 8×` de mejora real medida).
- [ ] Integrado en `integration`, validado con la suite completa y promovido con `--ff-only` a `dev` (sin `push`).
