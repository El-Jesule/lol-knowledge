# Agente C — verificación independiente y refutación

- **Rol:** verificación independiente, sin modificar archivos ni confiar en las conclusiones del coordinador.
- **Fecha:** 2026-10-20.
- **Ámbito:** rama `research/zaahen-formula-extraction`, `research/binmodel/`, fixtures, documentación y mediciones.
- **Modo:** copia de trabajo en un directorio temporal; el repositorio no se modificó.

## 1. Veredicto de la primera pasada

**BLOCKED.** Las puertas de investigación estaban verdes y las afirmaciones centrales de datos de Zaahen se sostenían, pero la implementación y la documentación no cumplían varias specs (S3, S4, S10, S11, S12, S13) y había un defecto real de procedencia en la salida `--json`.

Comandos ejecutados en la copia temporal:

| Comando | Resultado |
|---|---|
| `pytest research -q` | 66 pasaron |
| `ruff check research` | limpio |
| `ruff format --check research` | limpio |
| `binmodel --input zaahen_extract_min.json --validate --level 18 --rank 1 --bonus-ad 100` | exit 0; AD 73.8/76.68/104.76/141.8 → 74/77/105/142; pasiva 1.5–2.8; una carga total 146; daño Q 35, W 90/60, E 90/135, R 450 |
| SHA-256 del cache | `76e32…a533ed0b`, 58 830 B |

## 2. Bloqueos encontrados

### B1 — Procedencia incorrecta de los overrides de modo

`extract_mode_overrides` pasaba las entradas a `extract_data_values`, pero esta seguía construyendo el puntero como `.../mSpell/DataValues/{index}`. En la salida real, el `PBonusADMin` de `cherry` citaba `DataValues/0` (el `PercentBonusAD` base) en lugar de `DataValuesModeOverride/cherry/SpellDataValues/0`.

**Estado:** resuelto. `extract_data_values` acepta `source_path_prefix` y `pointer_prefix`; el override usa su propia ruta y puntero. Test: `test_mode_override_provenance_points_at_the_override`.

### B2 — «unresolved nodes: 0» ocultaba datos no resueltos

El resumen contaba solo `extract.unresolved`; los 36 `{150d1b92}` de `BotData` y `BotsSpellData` quedaban en `bot_data.unresolved`, y cinco `GameCalculation` de `BotData` no se parseaban.

**Estado:** resuelto. El resumen muestra `unresolved formula nodes` y `unresolved BotData nodes` por separado; `summarize_bot_data` parsea los `GameCalculation` y expone `calculations`. Test: `test_all_24_game_calculations_have_a_typed_tree` (24/24 con puntero).

### B3 — `--validate` era exclusivo de Zaahen y fallaba en otros campeones

En un campeón sin `PercentBonusADCalc`, el CLI llamaba a `validate_passive_percent` y lanzaba `FormulaError` no capturado.

**Estado:** resuelto. `--validate` solo ejecuta la tabla de mediciones para Zaahen y avisa cuando se omite; `FormulaError` se captura. Probado con el fixture de Darius.

### B4 — Faltaba la regresión de no-sustitución por cero

Sustituir la rama de tipo desconocido por `{"kind":"number","value":0.0}` dejaba la suite verde. No había tests de entrada malformada, referencia rota ni las 24 cálculos.

**Estado:** resuelto. Tests nuevos: `test_unknown_part_is_preserved_not_zeroed`, `test_malformed_data_value_is_reported`, `test_all_24_game_calculations_have_a_typed_tree`, `test_conditional_and_effect_value_cannot_be_evaluated`.

### B5 — Documentación requerida ausente

No existían los informes A/B/C, la spec, el inventario ni el registro de incertidumbres; el README y el handoff no mencionaban `binmodel`.

**Estado:** resuelto. Documentos creados y enlazados desde `research/README.md` y `zaahen-research-handoff.md`.

## 3. Advisories y correcciones

| Advisory | Corrección |
|---|---|
| «base 64 + 10» no se excluye solo con la tabla | Documentado: la tabla no distingue; el bin/Data Dragon (`63`) y las runas (`+10.8`) sí. Texto ajustado en spec, informe A y handoff |
| `stat_ref` inflaba la confianza | `confidence` es la mínima de estadística/fórmula; se añaden `stat_confidence` y `formula_confidence` |
| `ranked_values` trataba `len == level_count` como alineado | Ahora emite `ambiguous_rank_alignment` y no selecciona; no afecta a Zaahen (arrays de 6/7) |
| Etiqueta `HealPercentOfDamageDealt` frente a «% vida máxima» | Documentado como discrepancia de etiqueta; la fórmula principal se apoya en el texto y `mStat=12` |
| El hash del bin local `7f1e…` no se había recomprobado | Verificado: el bin crudo CDragon y la entrada 618 del WAD local dan `7f1e9369…844078d1` |
| No había un segundo campeón real | Fixture recortado de Darius y test de extracción; Kha'Zix se ejecutó manualmente (18 cálculos, 4 `EffectValue` no evaluables) |
| S9 no tenía extracción RST durable | `tools/extract_rst.py` + `fixtures/zaahen_tooltips_es_es.json` (123 cadenas) + tests sintéticos |
| El ejemplo imprimía el hash del fixture como si fuera el original | `source` separa `input_sha256` y `artifact_sha256`; el CLI lee `_provenance` |
| `--rank 0` salía con 0 | El CLI valida `--level >= 1` y `--rank >= 1` |

## 4. Afirmaciones confirmadas

- SHA-256 del JSON y `content_version` del manifiesto.
- AD base `63.0`, crecimiento `4.0`; tabla de AD con `+10.8`.
- `PBonusADMin=0.014999999664723873`, `PBonusADMax=0.02800000086426735`; `{ee18a47b}` con `StartDataValue`/`EndDataValue`; `mPrecision=1`; ocho puntos de interpolación.
- `MaxStacks=12`, `MaxStacksMultiplier=2.0`; el `142→146` es compatible con AD total, no prueba la base.
- Índice 0 = rango 0, incluso con valor distinto de cero; contraste con la wiki y la KB.
- `Cooldown.values` como enfriamiento efectivo; W difiere del legado.
- `RevivePercentCalc` parcial (0.75 a nivel 18, `complete=False`, dos `missing`).
- Recorrido genérico y test sintético sin nombres de Zaahen.

## 5. Lo que sigue sin verificarse

- El hash `7f1e…` de la copia local ya se verificó; el WAD de strings se verificó por SHA-256.
- El texto «duplica» se conserva ahora en `fixtures/zaahen_tooltips_es_es.json`, con hash del WAD.
- Las mediciones de habilidades (Q/W/E/R) no existen; la validación es estructural y contra la wiki, no en partida.
- La base de la pasiva, el multiplicador máximo y el script Lua que los aplica siguen abiertos.
- `EffectValueCalculationPart`, `GameCalculationConditional`, `{150d1b92}`, `BotsSpellData` y `mStat=13` no se evalúan.

## 6. Conclusión

La fase es aceptable como **prototipo de extracción**: los datos centrales están verificados, las fórmulas se reconstruyen desde el árbol, lo desconocido se conserva y la generalización está probada con un campeón sintético y dos reales. No es aceptable presentar la pasiva como completamente resuelta ni afirmar que el modelo reproduce el juego sin mediciones de habilidades.

La verificación final debe repetirse después de los cambios de esta fase; el coordinador dejó los tests y las puertas en verde.
