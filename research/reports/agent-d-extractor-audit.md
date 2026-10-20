# Auditoría del extractor de cálculos — fase 5

- **Rama auditada:** `research/zaahen-formula-extraction` en `89e2dbe`.
- **Base de trabajo:** `feat/object-model`, creada desde `89e2dbe` porque el extractor todavía no está integrado en `dev`.
- **Fecha:** 2026-10-20.
- **Alcance:** garantías de la fase 4; no se audita el optimizador ni se refactoriza el extractor.

## 1. Método y línea base

Se inspeccionaron las ramas, los cinco commits de la rama (`c9d1647`…`89e2dbe`), el ODD `odd/tasks/zaahen-formula-extraction.md`, `research/README.md` y el código de `research/binmodel/`. Después se ejecutaron las puertas del proyecto y una batería de pruebas nuevas contra los nodos que el código trata como «valor por defecto».

| Comprobación | Resultado real |
|---|---|
| `git status` al empezar | árbol limpio, rama `research/zaahen-formula-extraction` |
| `pytest -q` | `105 passed` |
| `pytest research -q` | `82 passed` |
| `ruff check .` | `All checks passed!` |
| `ruff format --check .` | `76 files already formatted` |
| `lol_knowledge validate` | `valid: 181 files checked`, salida `0` |
| `python -m binmodel --input research/fixtures/zaahen_extract_min.json` | 5 habilidades, 10 cálculos, 55 valores, 0 nodos sin resolver |
| `python -m binmodel --input research/.cache/zaahen-16.20.bin.json` | 5 habilidades, 10 cálculos, 41 nodos BotData sin resolver |

No se encontró ningún fallo de entorno ni de instalación. Todos los defectos descritos abajo son de implementación.

## 2. Veredicto por garantía

### G1 — Un valor desconocido nunca se convierte en cero

**Veredicto inicial: incumplida.** Había tres caminos de sustitución silenciosa por `0.0`:

1. `ByCharLevelBreakpointsCalculationPart`: `_eval_breakpoints` leía `node.get("level1_value") or 0.0`, `initial_bonus_per_level or 0.0`, `additional_bonus_at_this_level or 0.0` y `bonus_per_level_at_and_after or 0.0`. Un campo ausente o `null` producía cero sin diagnóstico. Reproducción: un nodo con `level1_value: null` devolvía `0.0` con `complete=True`.
2. `GameCalculation` sin `mFormulaParts`: `parse_calculation` generaba `parts=[]` y el evaluador sumaba el vacío como `0.0`. Reproducción: dos `GameCalculation` reales del bin (`ZaahenE/BotData/{ec17e271}/0/EffectCalculation` y `ZaahenR/BotData/{ec17e271}/1/EffectCalculation`) no tienen `mFormulaParts` y se evaluaban como cero.
3. `SumOfSubPartsCalculationPart` sin `mSubparts`: mismo patrón, `operands=[]` y suma `0.0`.

**Corrección:** `_require_number` rechaza `null`, booleanos, `NaN` e infinitos con un código explícito. `_eval_breakpoints` solo aplica el cero cuando el extractor marcó la ausencia con `default_policy: lol-bin-omitted-float-defaults/v1` y el campo figura en `absent_fields`; si no, lanza `missing_breakpoint_field`. `GameCalculation`/`SumOfSubParts` distinguen lista vacía explícita de lista ausente: `parts`/`operands` quedan en `null` y el evaluador lanza `missing_formula_parts`/`missing_formula_operands`.

**Evidencia de corrección:** `research/tests/test_binmodel_audit.py::test_missing_breakpoint_fields_are_not_zero`, `::test_missing_breakpoint_bonus_is_not_zero`, `::test_number_node_without_value_is_malformed`, `::test_interpolation_without_bounds_is_malformed`, `::test_game_calculation_without_parts_is_not_zero`, `::test_sum_without_operands_is_not_zero` y `::test_breakpoint_extraction_preserves_absent_fields`.

**Matiz importante:** CommunityDragon omite los `F32` que valen el valor por defecto de la clase. El extractor no convierte esa ausencia en cero: la conserva como `null`, anota el campo en `absent_fields`, marca `value_confidence: inferred` y deja que el evaluador aplique la política declarada. La política es una convención externa al bin, no un dato extraído; se documenta como `inferred`.

### G2 — Procedencia y confianza sobreviven

**Veredicto inicial: parcialmente incumplida.**

- Los nodos tipados conservaban `provenance` (ruta, puntero JSON, SHA-256, versión) y `confidence` (`source_explicit`, `inferred`, `unverified`). Los overrides `DataValuesModeOverride` conservaban su propio `mode` y su puntero.
- Los factores sintéticos de `StatByNamedDataValueCalculationPart` y `StatByCoefficientCalculationPart` eran la excepción: `{"kind": "data_value", "name": ...}` y `{"kind": "number", "value": ...}` se construían en línea sin `confidence` ni `provenance`. En el bin real había seis nodos así.
- Las entradas de `context.unresolved` conservaban puntero, ruta y motivo, pero no `source_sha256` ni `content_version`; el nodo del árbol sí los tenía.

**Corrección:** los dos factores sintéticos llevan ahora `confidence` y `provenance` apuntando al campo exacto (`/mDataValue`, `/mCoefficient`); un coeficiente malformado queda `unverified`. `TraversalContext.record_unresolved` centraliza las entradas y añade SHA-256 y versión de contenido. El test existente `test_typed_tree_nodes_have_confidence` se endureció para exigir procedencia y confianza en todo nodo con `kind`.

**Evidencia:** `test_binmodel_audit.py::test_inline_factor_nodes_keep_confidence_and_provenance`, `::test_malformed_factor_is_marked_unverified`, `::test_unresolved_entry_keeps_artifact_provenance` y `research/tests/test_binmodel_recheck.py::test_typed_tree_nodes_have_confidence`.

### G3 — Los tipos provisionales no se presentan como confirmados

**Veredicto: cumplida.** `registry.describe_type` devuelve `resolved: false` y `name: null` para tipos con hash; `_node_base` asigna `inferred` cuando hay `provisional_name` y `unverified` cuando no hay nombre. `PropertyDef.resolved` y `Registry.provisional` distinguen campos resueltos de hashes. Los nombres provisionales (`{ee18a47b}`, `{4ce08984}`, etc.) nunca se emiten como `name` confirmado. No se modificó nada en esta área.

### G4 — Rechazo explícito de lo no soportado, ciclos y datos malformados

**Veredicto inicial: parcialmente incumplida.** Los ciclos (`calculation_cycle`), los nodos condicionales (`conditional_requires_game_state`), los efectos (`effect_value_unresolved`) y los tipos desconocidos (`unresolved_node`, `unknown_node_kind`) ya se rechazaban. Sin embargo:

- un `NumberCalculationPart` sin `mNumber` producía `TypeError: float() argument must be ... NoneType`;
- una interpolación sin `mStartValue`/`mEndValue` producía el mismo `TypeError`;
- una estadística no soportada por `stat_value` escapaba como `KeyError`, no como `FormulaError`;
- un `by_char_level_formula` con valores no numéricos producía `TypeError`.

**Corrección:** todos esos caminos lanzan ahora `FormulaError` con códigos `malformed_number`, `malformed_interpolation`, `unsupported_stat` y `malformed_formula_values`. El CLI ya captura `FormulaError` y devuelve `2` sin traza.

**Evidencia:** `::test_number_node_without_value_is_malformed`, `::test_interpolation_without_bounds_is_malformed`, `::test_unsupported_stat_is_a_formula_error`; los tests preexistentes de ciclo y nodos condicionales siguen verdes.

### G5 — Fórmulas extraídas, inferidas y convenciones externas

**Veredicto: cumplida.** La distinción es explícita y se conserva en la salida:

- fórmulas/nodos del bin: `confidence: source_explicit` y `provenance` con puntero y SHA-256;
- tipos con hash: `inferred` + nombre provisional;
- estadísticas: `stat_ref` separa `stat_confidence` y `formula_confidence` (`corroborated` para `mStat=2`, `inferred` para `mStatFormula=1`);
- crecimiento de campeón: `stats.growth_model.status = "inferred"` con la nota de que el bin solo guarda base y crecimiento;
- validación de la pasiva: `status: "validated against display; internal implementation inferred"`.

No se encontró ningún caso donde una convención externa se marque como `source_explicit`.

### G6 — Determinismo

**Veredicto inicial: parcialmente incumplida.** La extracción y el orden de las colecciones eran deterministas, pero `EvaluationContext.dependencies` no se reiniciaba en `evaluate()`: evaluar A y después B con el mismo contexto hacía que B heredara las dependencias de A. El valor no cambiaba, pero el diagnóstico dependía del orden de llamadas.

**Corrección:** `evaluate()` reinicia `missing` y `dependencies` en cada llamada. Se añadió una prueba de repetición y otra de extracción determinista.

**Evidencia:** `::test_dependencies_do_not_leak_between_evaluations` y `::test_extraction_is_deterministic`.

## 3. Defectos corregidos (resumen)

| ID | Defecto | Archivo (post-corrección) | Regresión |
|---|---|---|---|
| D1 | Cero silencioso en breakpoints | `evaluate.py:365` (`_breakpoint_field`), `traverse.py:749` | `test_missing_breakpoint_*` |
| D2 | Cálculo vacío evaluado como cero | `evaluate.py:194`, `traverse.py:946` | `test_game_calculation_without_parts_*`, `test_sum_without_operands_*` |
| D3 | Datos malformados como `TypeError`/`KeyError` | `evaluate.py:19`, `:203`, `:273` | `test_*_malformed`, `test_unsupported_stat_*` |
| D4 | Dependencias filtradas entre evaluaciones | `evaluate.py:502` | `test_dependencies_do_not_leak_*` |
| D5 | `unresolved` sin SHA-256 ni versión | `traverse.py:48` | `test_unresolved_entry_keeps_artifact_provenance` |
| D6 | Factores sintéticos sin confianza ni procedencia | `traverse.py:687` | `test_inline_factor_nodes_*` |

Ningún defecto de los anteriores invalidaba los valores publicados de Zaahen: las mediciones de AD, la pasiva y Q/W/E/R siguen reproduciéndose. Lo que fallaba era la garantía de que un dato ausente no se pudiera confundir con cero.

## 4. Lo que sigue abierto

- **41 nodos BotData sin resolver:** 36 de tipo `{150d1b92}` y 5 `BotsSpellData`. Se conservan; no se interpretan.
- **Dos `GameCalculation` vacíos** en `ZaahenE`/`ZaahenR` (`BotData/{ec17e271}/…/EffectCalculation`). Ahora se marcan con `missing_formula_parts` y no se evalúan; su semántica sigue sin verificarse.
- **Una estadística sin resolver** (`unresolved_stat`) en el bin real.
- **Dos `DataValue` sin `values`**, conservadas como referencia con diagnóstico.
- **Discrepancia de enfriamiento de W** entre `Cooldown.values` y `cooldownTime`; se conserva como diagnóstico.
- **`RevivePercentCalc` incompleta**: faltan `ReviveBonusPerLevel` y `ReviveBonusPerLevelAtAndAfter`; el evaluador devuelve `complete=False`, nunca un valor completo inventado.
- **Política de defaults omitidos:** es una inferencia respaldada por la serialización de CommunityDragon y por las mediciones de `ReviveCooldownCalc` (300/240/180/120). No se ha verificado contra el esquema oficial del bin.
- **La base de aplicación de la pasiva** sigue sin demostrarse (AD total frente a variantes de redondeo).

## 5. Comandos de reproducibilidad

```powershell
$env:PYTHONPATH="research"
.\.venv\Scripts\python.exe -m pytest research -q
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check .
.\.venv\Scripts\python.exe -m lol_knowledge validate
.\.venv\Scripts\python.exe -m binmodel --input research\fixtures\zaahen_extract_min.json --validate
```

Resultados de la rama `feat/object-model` al cerrar la auditoría: `97 passed` en `research`, `105 passed` en la suite principal, Ruff limpio, validador `181 files checked` antes de añadir el catálogo de objetos.
