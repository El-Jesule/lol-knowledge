# Zaahen formula extraction — fase de investigación

- **Objetivo:** reconstruir de forma reproducible y generalizable las fórmulas, parámetros y estructuras de cálculo de Zaahen desde el bin 16.20, con árboles tipados, procedencia y validación experimental.
- **Rama:** `research/zaahen-formula-extraction` (base: `dev`).
- **Entrega:** solo investigación y prototipo aislado en `research/`. Sin push, sin merge a `dev` ni `integration`, sin tocar `data/current/` ni `src/lol_knowledge/`.
- **Runner:** `.\.venv\Scripts\python.exe -m pytest research -q`; puertas completas del repo al cerrar.

## Specs

### S1 — Artefactos, hashes y versiones

Identificar y verificar los artefactos de entrada antes de usarlos. El bin cacheado debe conservar:

- URL: `https://raw.communitydragon.org/16.20/game/data/characters/zaahen/zaahen.bin.json`
- `content_version`: `16.20.8248524+branch.releases-16-20.content.release`
- SHA-256: `76e32de67667917769cc6022a818b13e5024ea521a23c70436dc48eea533ed0b`

El SHA-256 registrado de la copia local del bin era `7f1e936990c527d1cf457eea9d9327efaa743d6619436f0ccfc15e7e844078d1`. No se asume que siga siendo válido: se comprueba o se declara como no verificado.

La instalación local es `D:\Games\Riot Games\League of Legends`. Es de solo lectura. Si no está disponible, las comprobaciones que dependan de ella se declaran no ejecutadas.

### S2 — Descubrimiento genérico, sin `DATA_VALUE_SPECS`

El extractor no debe contener una lista manual de nombres de Zaahen. Debe descubrir:

- el campeón y su bloque de estadísticas desde `CharacterRecords/Root`;
- las habilidades desde `Root.spells`, `Root.mAbilities`, `Root.mCharacterPassiveSpell` y `mRootSpell`;
- los cálculos desde `mSpell.mSpellCalculations`;
- los `DataValues` desde `mSpell.DataValues`;
- el número de rangos desde `mSpell.mClientData.mTooltipData.mLists.LevelUp.levelCount`;
- las etiquetas semánticas desde `mLists.LevelUp.Elements[].type` y `nameOverride`.

Debe funcionar con nombres de campeón, habilidades y parámetros distintos sin cambios de código.

### S3 — Árboles de cálculo tipados

Recorrer recursivamente las 24 `GameCalculation` de Zaahen y representar cada nodo con un tipo explícito. Como mínimo:

- `NumberCalculationPart`, `NamedDataValueCalculationPart`;
- `StatByNamedDataValueCalculationPart`, `StatByCoefficientCalculationPart`, `StatBySubPartCalculationPart`;
- `ProductOfSubPartsCalculationPart`, `SumOfSubPartsCalculationPart`;
- `ByCharLevelBreakpointsCalculationPart`, `ByCharLevelFormulaCalculationPart`, `ByCharLevelInterpolationCalculationPart`;
- `GameCalculationModified`;
- `{ee18a47b}` (interpolación entre dos `DataValue` por nivel; nombre provisional por FNV-1a);
- `{4ce08984}` (breakpoints con nombres de `DataValue`; nombre provisional);
- `{f3cbe7b2}`, `{ba007871}`, `{9e9e2e5c}` (referencias a cálculos o `DataValue`);
- `{b09016f6}` (envoltorio de efecto de `BotData`).

Un tipo desconocido se conserva como nodo `unresolved` con el JSON original, el hash y la ruta. Nunca se sustituye por cero ni se inventa una fórmula.

### S4 — Procedencia y confianza

Cada valor y cada nodo debe conservar:

- ruta del objeto de origen y puntero JSON;
- SHA-256 y versión del artefacto;
- nombre o hash de la clase, y nombre provisional si no está resuelto;
- transformación aplicada (índice de rango, interpolación, breakpoint, etc.);
- estado de confianza: `source_explicit`, `derived`, `inferred`, `corroborated`, `verified`, `unverified`, `conflict`.

### S5 — `DataValues`, rangos y overrides

Extraer los `DataValues` con su array bruto y los rangos 1..`levelCount`. Conservar `DataValuesModeOverride` (por ejemplo `cherry`) sin mezclarlo con el modo base. Un `DataValue` sin `values` se conserva como referencia no resuelta y produce un diagnóstico; no se rellena con cero.

### S6 — Estadísticas y crecimiento de AD

Extraer del `Root`:

- AD base: `63.0`; crecimiento: `4.0`;
- HP `640` / `114`, armadura `36` / `5`, RM `32` / `2.05`, velocidad `345`, rango `175`, velocidad de ataque `0.625` / `2.5`.

Implementar la fórmula de crecimiento de campeón:

```
nivel <= 18: base + crecimiento * (nivel-1) * (0.7025 + 0.0175 * (nivel-1))
nivel > 18:  base + crecimiento * 17 + crecimiento * (nivel-18)
```

La fórmula es un modelo externo al bin; se marca `inferred` y se valida con las mediciones. El bin solo almacena base y crecimiento.

Mediciones del usuario (prácticas, sin objetos, dos runas pequeñas de daño):

| Nivel | AD mostrado | AD descontando las runas |
|---:|---:|---:|
| 1 | 74 | 64 |
| 2 | 77 | 67 |
| 10 | 105 | 95 |
| 18 | 142 | 132 |

Hipótesis a contrastar: las runas adaptativas aportan `+5.4` AD cada una (`+10.8` total), no `+10`. Con base `63` y crecimiento `4`, la fórmula debe reproducir `74, 77, 105, 142` exactamente al redondear el AD mostrado.

### S7 — Pasiva

Investigar y documentar:

- `PBonusADMin = 0.015` y `PBonusADMax = 0.028` (float32 con ruido de representación).
- `PercentBonusADCalc` usa `{ee18a47b}` con `StartDataValue=PBonusADMin`, `EndDataValue=PBonusADMax`.
- `mPrecision = 1`.
- `MaxStacks = 12`, `MaxStacksMultiplier = 2.0`.
- El tooltip oficial dice: «Obtiene un <physicalDamage>@PercentBonusADCalc@ de daño de ataque</physicalDamage> adicional por acumulación» y «Con el máximo de Determinación, Zaahen duplica la cantidad de daño de ataque otorgado».

Validar la progresión observada:

| Nivel | Porcentaje observado |
|---:|---:|
| 1 | 1,5 % |
| 5 | 1,8 % |
| 6 | 1,9 % |
| 10 | 2,2 % |
| 11 | 2,3 % |
| 15 | 2,6 % |
| 16 | 2,6 % |
| 18 | 2,8 % |

Hipótesis candidata: interpolación lineal `min + (max-min) * (nivel-1)/17`. Debe reproducir los ocho valores al mostrarse con una décima. No se afirma que sea la implementación interna hasta comprobar el árbol y documentar la limitación.

La base sobre la que se aplica el porcentaje (AD base, AD adicional o AD total) no está en el bin. La observación `142 -> 146` con una carga a nivel 18 es compatible con AD total y con variantes de redondeo; se registra como cuestión abierta y se propone un experimento controlado.

### S8 — Q, W, E y R

Recuperar y documentar, como mínimo:

- Q: daño inicial y de reactivación, ratio de DA adicional, curación % vida máxima, derribo, enfriamiento, maná, coste, daño a monstruos.
- W: daño inicial y secundario, ratios, enfriamiento, maná, rango.
- E: daño base, ratio, multiplicador de borde, daño % vida máxima, enfriamiento, maná.
- R: daño final, ratio de DA adicional, penetración de armadura, reducción de daño, curación, enfriamiento, maná.

Cada fórmula debe indicar tipo de daño (físico/mágico/verdadero), unidad, condición (por ejemplo, borde de E, monstruos de Q) y fuente.

### S9 — Localización y tooltips

Reutilizar el hallazgo RST v5 de la fase anterior. Extraer las cadenas `Spell_Zaahen*` de `Global.es_ES.wad.client` y usarlas para:

- confirmar la semántica de cada nodo (ratio de DA adicional, cura % vida máxima, penetración, etc.);
- mapear `mLists.LevelUp.Elements[].type` con las etiquetas `nameOverride`;
- conservar las claves y los textos citados con procedencia.

Si la asociación de slots vuelve a fallar, documentar la limitación y no bloquear la extracción de fórmulas.

### S10 — Generalización

Demostrar que el extractor no depende de Zaahen:

- ejecutarlo sobre al menos otro campeón real (por ejemplo Darius y Kha'Zix) sin cambios de código;
- añadir un fixture sintético con nombres de campeón, habilidades y `DataValue` distintos;
- comprobar que descubre los mismos tipos de nodo y produce árboles válidos.

No se procesan todos los campeones en esta fase.

### S11 — Modelo de datos JSON

El JSON de salida debe incluir:

- `schema_version`, `game_version`, `content_version`, `source` (URL, SHA-256, fecha);
- `champion` con id, nombre, estadísticas y crecimiento;
- `abilities` con id estable, nombre, slots, enfriamientos, maná, rango, `level_count`;
- `data_values` con nombre, array bruto, rangos, overrides y estado;
- `calculations` con árboles tipados y referencias resueltas;
- `unresolved` con tipos, campos y referencias no resueltas;
- `diagnostics` con severidad, código, ruta y mensaje;
- `confidence` y `provenance` por nodo.

Markdown sigue siendo el formato para explicaciones, fuentes y limitaciones.

### S12 — Pruebas y criterios de aceptación

Pruebas automatizadas, sin red, que cubran:

- FNV-1a y hashes conocidos;
- carga del registro de esquemas;
- recorrido de las 24 cálculos de Zaahen;
- evaluación de Q/W/E/R en rango 1 con estadísticas conocidas;
- interpolación de la pasiva en los ocho niveles medidos;
- crecimiento de AD en los cuatro niveles medidos;
- `DataValue` ausente, referencia rota, ciclo, tipo desconocido y entrada malformada;
- fixture sintético de otro campeón;
- regresión: el extractor no debe sustituir datos desconocidos por cero.

Criterios de aceptación: los 12 puntos de la sección 6 de la solicitud, con evidencia y limitaciones declaradas.

### S13 — Documentación

Crear o actualizar:

- `research/README.md` (índice);
- `research/zaahen-research-handoff.md` (continuidad);
- `research/reports/agent-a-formulas.md`;
- `research/reports/agent-b-bin-structures.md`;
- `research/reports/agent-c-verification.md`;
- `research/zaahen-formula-spec.md`;
- `research/zaahen-structure-inventory.md`;
- `research/zaahen-uncertainties.md`.

Cada afirmación importante debe llevar fuente, ruta, valor bruto, transformación, evidencia experimental y nivel de confianza.

### S14 — Límites

- Solo lectura sobre la instalación del juego.
- No versionar bins completos ni datos voluminosos de terceros.
- No push, no merge a `dev`/`integration`.
- No implementar el optimizador de builds.
- No introducir dependencias nuevas en runtime.
- No usar `DATA_VALUE_SPECS` ni listas manuales equivalentes.
- No ocultar fallos: una comprobación no ejecutada se informa como no ejecutada.

## Tasks

| ID | Tarea | Specs | Ruta | Estado |
|---|---|---|---|---|
| T1 | Verificar artefactos, hashes y entorno | S1 | inline | hecho: SHA-256 del JSON, bin crudo y bin local `7f1e?`; WAD es_ES `2846?` |
| T2 | Registro compacto de esquemas y hashes | S2, S4 | inline | hecho: `binmodel/schema/lol_classes.json` |
| T3 | Traversor gen?rico y modelo de datos | S2, S3, S5, S11 | inline | hecho: `binmodel/traverse.py`, `model.py`, 24/24 c?lculos |
| T4 | Evaluador, crecimiento y validaci?n | S6, S7, S8 | inline | hecho: `evaluate.py`, `stats.py`, `validation.py` |
| T5 | CLI y salida JSON | S11 | inline | hecho: `python -m binmodel` |
| T6 | Pruebas y fixtures | S12 | inline | hecho: 82 pruebas, fixtures Zaahen/Darius/tooltips |
| T7 | Generalizaci?n (Darius/Kha'Zix + sint?tico) | S10 | inline | hecho: fixture Darius, sint?tico y ejecuci?n Kha'Zix |
| T8 | Documentaci?n e informes | S13 | inline | hecho: README, handoff, spec, inventario, incertidumbres, informes A/B/C |
| T9 | Verificaci?n independiente (Agente C) | S12, S13 | delegated | hecho: bloqueos corregidos; ver informe C |
| T10 | Puertas de calidad y commits | S14 | inline | pendiente: commits de la rama |

## Log

### L1 — Solicitud original (resumen fiel)

Investigar los archivos locales de League of Legends para reconstruir de forma reproducible las fórmulas, parámetros y mecánicas de Zaahen. Prioridad absoluta: descubrir cómo recuperar los datos y las fórmulas de manera generalizable, no introducir manualmente los valores ya conocidos. No implementar el optimizador completo. No ampliar el alcance a todos los campeones. Trabajar en rama de tarea, sin push, sin fusionar a `dev` ni `integration`. Documentar todo con evidencias, hashes, rutas, comandos, incertidumbres y niveles de confianza.

### L2 — Evidencia recogida al inicio

- `dev` e `integration` están sincronizadas; el árbol está limpio. Rama creada: `research/zaahen-formula-extraction`.
- SHA-256 de `research/.cache/zaahen-16.20.bin.json` recalculado: `76e32de67667917769cc6022a818b13e5024ea521a23c70436dc48eea533ed0b`; coincide con el registrado. Tamaño: 58 830 bytes.
- El bin contiene 45 objetos, 24 `GameCalculation`, 12 `NamedDataValueCalculationPart`, 7 `NumberCalculationPart`, 5 `ProductOfSubPartsCalculationPart`, 3 `StatByNamedDataValueCalculationPart`, 3 `StatBySubPartCalculationPart`, 3 `StatByCoefficientCalculationPart`, 2 `SumOfSubPartsCalculationPart`, 1 `ByCharLevelBreakpointsCalculationPart`, 1 `{ee18a47b}`.
- `CharacterRecords/Root`: `baseDamageModifiable.baseValue = 63.0`, `damagePerLevelModifiable.baseValue = 4.0`.
- `mTooltipData.mLists.LevelUp.levelCount`: Q=5, W=5, E=5, R=3; la pasiva no declara lista.
- Los ratios de Q/W/E/R usan `mStat=2`, `mStatFormula=2`; la evidencia cruzada (Kha'Zix `BonusADRatio`, tooltip de Zaahen «Relación de DA adicional») identifica `2/2` como DA adicional. `mStatFormula=0` es DA total (Darius/Garen) y `mStat=1` es armadura (Malphite/Rammus), `mStat=6` RM (Rammus/Poppy), `mStat=12` vida (Sett/Sion/Poppy).
- Tooltip oficial de la pasiva: `@PercentBonusADCalc@` de daño de ataque adicional por acumulación; al máximo «duplica la cantidad de daño de ataque otorgado».
- Tooltip de Q: cura `@HealPercent*100@%` de vida máxima; lista «Relación de DA adicional».
- `PercentBonusADCalc`: `{ee18a47b}` con `StartDataValue=PBonusADMin`, `EndDataValue=PBonusADMax`; `mPrecision=1`. La interpolación lineal `0.015 + 0.013*(nivel-1)/17` reproduce los ocho porcentajes observados con una décima.
- Las mediciones de AD se reproducen con base `63`, crecimiento `4` y runas adaptativas `+10.8`: `73.8 -> 74`, `76.68 -> 77`, `104.76 -> 105`, `141.8 -> 142`. La lectura «base 64 + 10» es un artefacto de redondear las runas; el bin y Data Dragon dicen `63`.
- El WAD local `Zaahen.wad.client` no contiene scripts Lua; solo bin, animaciones y PROP. El script que aplica el porcentaje de la pasiva no está localizado. La base de aplicación queda abierta.


### L3 - Implementaci?n y verificaci?n (2026-10-20)

- Se cre? `research/binmodel/` con registro de clases, traversor gen?rico, evaluador, estad?sticas, validaci?n y CLI.
- Se generaron fixtures recortados con `tools/make_extract_fixture.py`: `zaahen_extract_min.json` (43 KB) y `darius_extract_min.json` (34 KB). El generador verifica el SHA-256 del original y registra la procedencia.
- Se implement? `tools/extract_rst.py` y se gener? `fixtures/zaahen_tooltips_es_es.json` con 123 cadenas es_ES; el WAD es_ES tiene SHA-256 `284604a42cb66761f2ae1e987a3b2dc2553f3de3703da3f9594fd14d093cee93`.
- Se verific? el bin local: la entrada 618 de `Zaahen.wad.client` descomprime a 28 038 B con SHA-256 `7f1e936990c527d1cf457eea9d9327efaa743d6619436f0ccfc15e7e844078d1`, igual al bin crudo de CommunityDragon.
- La suite `pytest research -q` pas? de 63 a 82 pruebas. `ruff check` y `ruff format --check` limpios. La suite completa del repo y `lol_knowledge validate` se ejecutaron antes de la fase de documentaci?n.
- El Agente C hizo una verificaci?n independiente en copia temporal. Encontr? 5 bloqueos: procedencia de overrides, resumen que ocultaba no resueltos, `--validate` exclusivo de Zaahen, ausencia de regresi?n de no-sustituci?n por cero y documentaci?n faltante. Todos se corrigieron; los detalles est?n en `research/reports/agent-c-verification.md`.
- Se a?adieron tests de las 24 `GameCalculation`, de procedencia de `cherry`, de referencia rota/entrada malformada, de nodos condicionales y de valores de efecto.
- Se separ? `input_sha256` de `artifact_sha256` en la salida; el fixture ya no hace pasar su propio hash por el del bin original.
- Se corrigi? `stat_ref` para no inflar la confianza y `ranked_values` para no adivinar cuando `len(raw) == level_count`.

### L4 - L?mites y siguiente paso

- La base de aplicaci?n del porcentaje de la pasiva, el multiplicador m?ximo y el script Lua que los aplica siguen abiertos. `142?146` favorece AD total, pero no lo demuestra.
- `RevivePercentCalc` es parcial: faltan `ReviveBonusPerLevel` y `ReviveBonusPerLevelAtAndAfter`.
- `BotData` contiene 36 `{150d1b92}` sin sem?ntica; `EffectValueCalculationPart` y `GameCalculationConditional` se tipan pero no se eval?an.
- No se hizo push ni merge a `dev`/`integration`. La rama `research/zaahen-formula-extraction` queda local.
- Siguiente paso imprescindible: cerrar P1/P2 con mediciones controladas. Siguiente paso opcional: localizar el Lua de la pasiva y ampliar el evaluador a condicionales/efectos.

### L5 — Auditoría de garantías (fase 5, 2026-10-20)

- Auditoría independiente sobre `89e2dbe`; informe completo en `research/reports/agent-d-extractor-audit.md`.
- Defectos reales corregidos con regresión: cero silencioso en breakpoints y en cálculos vacíos; `TypeError`/`KeyError` en nodos malformados; dependencias filtradas entre evaluaciones; `unresolved` sin SHA-256/versión; factores sintéticos sin confianza ni procedencia.
- La política de defaults omitidos (`lol-bin-omitted-float-defaults/v1`) queda marcada como `inferred`: el bin no la documenta, se apoya en la serialización de CommunityDragon y en las mediciones de `ReviveCooldownCalc`.
- Siguen abiertos: 41 nodos BotData, dos `GameCalculation` vacíos, `RevivePercentCalc` incompleta y la base de aplicación de la pasiva.
