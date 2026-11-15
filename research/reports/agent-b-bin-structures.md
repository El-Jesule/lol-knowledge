# Agente B — estructuras binarias, hashes y herramientas

- **Alcance:** entender cómo se representan las clases de cálculo en el bin 16.20 de Zaahen, qué hashes están resueltos, cómo se alinean los rangos y qué estructuras quedan fuera del modelo.
- **Fuente principal:** `research/.cache/zaahen-16.20.bin.json`, SHA-256 `76e32de67667917769cc6022a818b13e5024ea521a23c70436dc48eea533ed0b`.
- **Metadatos de clases:** `database.py` de [LeagueToolkit/lol-meta-classes](https://github.com/LeagueToolkit/lol-meta-classes), consultado el 2026-10-20, y su wiki pública.
- **Estado:** los tipos usados por los cálculos de Zaahen están identificados; los tipos de `BotData` y algunos campos siguen sin nombre público.

## 1. Artefactos y verificación

| Artefacto | Valor | Cómo se comprobó |
|---|---|---|
| Export CDragon | `https://raw.communitydragon.org/16.20/game/data/characters/zaahen/zaahen.bin.json` | URL del manifiesto de la fase anterior |
| SHA-256 del JSON | `76e32de67667917769cc6022a818b13e5024ea521a23c70436dc48eea533ed0b` | `Get-FileHash` el 2026-10-20; coincide con el manifiesto |
| `content_version` | `16.20.8248524+branch.releases-16-20.content.release` | `research/.cache/manifest.json`; el bin no contiene la cadena |
| Bin crudo CDragon | `7f1e936990c527d1cf457eea9d9327efaa743d6619436f0ccfc15e7e844078d1`, 28 038 B | `GET .../zaahen.bin` y SHA-256 |
| Bin local | mismo SHA-256 `7f1e…`, entrada 618 de `Zaahen.wad.client` | Descompresión zstd de la entrada 618; 28 038 B |
| WAD de strings es_ES | `Global.es_ES.wad.client`, SHA-256 `284604a42cb66761f2ae1e987a3b2dc2553f3de3703da3f9594fd14d093cee93` | `research/fixtures/zaahen_tooltips_es_es.json` |

La instalación local existe en `D:\Games\Riot Games\League of Legends`. La comprobación del bin local se hizo en solo lectura.

## 2. Formato del bin y del WAD

- El export `.bin.json` es un objeto plano `ruta -> objeto`; las clases se marcan con `__type` y los tipos no resueltos aparecen como `{hash}`.
- El bin crudo usa el contenedor `PROP` de Riot; el export de CommunityDragon ya lo decodifica. No se reimplementó el lector `PROP` porque el JSON es determinista y verificable por hash.
- El WAD v3 se parseó con el formato documentado por CommunityDragon: cabecera de 272 bytes, `count` en el offset 268, entradas de 32 bytes, tipos 0/1/3 (sin comprimir, gzip, zstd). El WAD local de Zaahen no contiene scripts Lua; solo bin, animaciones y PROP.
- Las stringtables `RST v5` del WAD es_ES se parsean con `research/tools/extract_rst.py`: `N` ranuras de 8 bytes, `blob` en `8+8N`, `hash = v & (2^38 - 1)`, `offset = v >> 38`. El diccionario `hashes.rst.xxh3.txt` se trunca a 38 bits para resolver claves. La herramienta generó `research/fixtures/zaahen_tooltips_es_es.json` (123 cadenas).

## 3. Clases de cálculo de Zaahen

### 3.1 Tipos resueltos

| Tipo | Uso en Zaahen | Campos relevantes |
|---|---|---|
| `GameCalculation` | 10 cálculos de nivel superior | `mFormulaParts`, `mDisplayAsPercent`, `mPrecision`, `tooltipOnly` |
| `GameCalculationModified` | `E.BonusDamageCalc` | `mModifiedGameCalculation`, `mMultiplier` |
| `NamedDataValueCalculationPart` | hojas de `DataValue` | `mDataValue` |
| `NumberCalculationPart` | constantes | `mNumber` |
| `StatByNamedDataValueCalculationPart` | ratio por `DataValue` | `mStat`, `mStatFormula`, `mDataValue` |
| `StatByCoefficientCalculationPart` | ratio constante | `mStat`, `mStatFormula`, `mCoefficient` |
| `StatBySubPartCalculationPart` | `BotData` (cura de Q) | `mStat`, `mSubpart` |
| `ProductOfSubPartsCalculationPart` | `BotData` | `mPart1`, `mPart2` |
| `SumOfSubPartsCalculationPart` | `BotData` | `mSubparts` |
| `ByCharLevelBreakpointsCalculationPart` | `ReviveCooldownCalc` | `mLevel1Value`, `mInitialBonusPerLevel`, `mBreakpoints` |
| `ByCharLevelFormulaCalculationPart` | valores por nivel | `values` / `mValues` |
| `ByCharLevelInterpolationCalculationPart` | interpolación lineal | `mStartValue`, `mEndValue`, flags |
| `Breakpoint` | breakpoints de cooldown | `mLevel`, `mAdditionalBonusAtThisLevel`, `mBonusPerLevelAtAndAfter` |

### 3.2 Tipos con hash sin nombre público

La tabla pública `hashes.bintypes.txt` no contiene estos hashes. Se identificaron por estructura y, cuando fue posible, por FNV-1a de un nombre candidato. Los nombres son **provisionales**.

| Hash | Nombre provisional | Estructura observada | Evidencia |
|---|---|---|---|
| `0xee18a47b` | `ByCharLevelNamedDataValuesInterpolationCalculationPart` | `StartDataValue`, `EndDataValue`, dos bool | `fnv1a32(nombre) = ee18a47b`; herencia `IGameCalculationPartByCharLevel` en la wiki |
| `0x4ce08984` | `ByCharLevelNamedDataValuesBreakpointsCalculationPart` | `{91d404a5}` (hash), `{bbd778a2}` (hash), `{9823b29a}` (lista de `0x0333530c`) | Estructura análoga a `ByCharLevelBreakpointsCalculationPart`, pero con nombres de `DataValue` |
| `0x0333530c` | `NamedBreakpoint` | `level`, `{ae9b464d}` (hash), `{b0d8b2ac}` (hash) | Análogo a `Breakpoint`, con nombres en lugar de floats |
| `0xf3cbe7b2` | `SpellCalculationKeyReference` | `mSpellCalculationKey` | Referencia interna a otro cálculo |
| `0xba007871` | `ExternalCalculationReference` | `SourceObject`, `CalculationKey` | Referencia a un cálculo de otro objeto |
| `0x9e9e2e5c` | `ExternalDataValueReference` | `SourceObject`, `DataValue` | Referencia a un `DataValue` de otro objeto |
| `0xb09016f6` | `BotDataEffect` | `EffectTag`, `EffectCalculation` | Envoltorio de `BotData` |
| `0x0a0eddc9` | `UnnamedSpellDataValueVector7` | `values` (7 floats) | `Cooldown` y `castRangeValues` |
| `0x630af303` | `UnnamedSpellDataValueVector6` | `values` (6 floats) | `manaValues` |
| `0x150d1b92` | `UnnamedBotDataEntry` | `{e38f54f7}` (U32), `{717e686}` (bool) | 36 apariciones en `BotData`; semántica desconocida |
| `0x6c87d653` | `UnnamedEmptyStruct` | sin propiedades | Una aparición; sin semántica |

El campo `{0a3e0478}` de `Cooldown` no aparece en la clase pública `0xa0eddc9` de `database.py`; se conserva como `UnresolvedScalar0a3e0478`. No se usa para ningún cálculo.

### 3.3 Campos con hash dentro de tipos conocidos

- `{0a3e0478}`: escalar de `Cooldown`/`castRangeValues`; sin nombre público.
- `{3de6ce2d}`: `CalculationKey`, resuelto por la tabla pública de campos.
- `{91d404a5}`, `{bbd778a2}`, `{9823b29a}`, `{ae9b464d}`, `{b0d8b2ac}`: campos de los tipos provisionales de breakpoints.
- `{e38f54f7}`, `{717e686}`: campos de `{150d1b92}`.

## 4. Alineación de rangos: índice 0 es rango 0

Todos los arrays de hechizo reservan el índice 0 para el rango 0. El rango 1 es `raw[1]`, **aunque `raw[0]` no sea cero**. Ejemplos verificados:

| `DataValue` | Array bruto | Rango 1..N | Fuente de contraste |
|---|---|---|---|
| `Q1BaseDamage` | `[0, 15, 30, 45, 60, 75, 90]` | 15/30/45/60/75 | KB y wiki |
| `QCoeff` | `[0.15, 0.20, 0.25, 0.30, 0.35, 0.40, 0.45]` | 0.20/0.25/0.30/0.35/0.40 | Tooltip «Relación de DA adicional» y wiki |
| `HealPercent` | `[0.04, 0.05, 0.06, 0.07, 0.08, 0.09, 0.10]` | 0.05/0.06/0.07/0.08/0.09 | Tooltip y wiki |
| `W.InitialBaseDamage` | `[20, 40, 60, 80, 100, 120, 140]` | 40/60/80/100/120 | Wiki |
| `E.Damage_Base` | `[20, 40, 60, 80, 100, 120, 140]` | 40/60/80/100/120 | Wiki |
| `R.EndDamage` | `[100, 250, 400, 550, 700, 850, 1000]` | 250/400/550 | Wiki |
| `R.ArmorPen` | `[0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6]` | 0.10/0.20/0.30 | Tooltip y wiki |
| `E.PercentHPDamage` | `[0.035, 0.04, 0.045, 0.05, 0.055, 0.06, 0.065]` | 0.04/0.045/0.05/0.055/0.06 | Wiki |

El número de rangos no se hardcodea: se lee de `mClientData.mTooltipData.mLists.LevelUp.levelCount` (Q/W/E=5, R=3; la pasiva no declara lista y se trata como rango único).

**Límite:** si un array tiene exactamente `level_count` elementos, el extractor no puede saber si el índice 0 es rango 0 o rango 1. Emite `ambiguous_rank_alignment` y no inventa la selección. Los arrays de Zaahen tienen 7 elementos (o 6 para `mana`), así que no se activa.

## 5. Enums `mStat` y `mStatFormula`

La evidencia cruzada con otros campeones permite mapear los valores usados por Zaahen. No es un enum publicado por Riot.

| `mStat` | Estadística | Evidencia | Confianza |
|---:|---|---|---|
| 1 | armadura | Malphite W, Rammus W, Poppy W | corroborado |
| 2 | daño de ataque | Kha'Zix Q `BonusADRatio`, Garen Q `tADRatio` | corroborado |
| 4 | velocidad de ataque | Jhin pasiva | inferido |
| 6 | resistencia mágica | Rammus W, Poppy W | corroborado |
| 8 | probabilidad de crítico | Caitlyn pasiva, Jhin pasiva | inferido |
| 9 | daño crítico | Nasus Q, Yasuo pasiva, Caitlyn, Senna | corroborado |
| 12 | vida | Sett W `StoredHealth`, Sion W, Poppy pasiva | corroborado |
| 13 | desconocido | `R.BotData` | desconocido |

| `mStatFormula` | Fórmula | Evidencia | Confianza |
|---:|---|---|---|
| 0 (o ausente) | total | Garen Q `tADRatio`, Darius Q | corroborado |
| 1 | base | vecino natural del enum; sin muestra decisiva | inferido |
| 2 | adicional | Kha'Zix Q `BonusADRatio`, tooltip de Zaahen | corroborado |

Zaahen usa `2/2` en Q, W, E y R: los ratios son de **DA adicional**. La pasiva usa `12/0` en la cura de Q de `BotData` (vida máxima) y el porcentaje de la pasiva no lleva `mStat` porque es una concesión de estadística, no un daño.

## 6. Enfriamientos: `Cooldown.values` frente a `cooldownTime`

- `mSpell.Cooldown.values` es el vector efectivo: coincide con Data Dragon y con la wiki en Q, W, E y R.
- `mSpell.cooldownTime` es un espejo legado. En Q, E y R coincide; en W no:

| Habilidad | `Cooldown.values` (efectivo) | `cooldownTime` (legado) |
|---|---|---|
| Q | 10/9/8/7/6 | 10/9/8/7/6 |
| W | 14/13.5/13/12.5/12 | 16/16/15/14/13/12/11 |
| E | 10/9.5/9/8.5/8 | 10/9.5/9/8.5/8 |
| R | 110/95/80 | 110/95/80 |

El extractor usa `Cooldown.values`, conserva `cooldownTime` como `legacy` y emite `cooldown_mismatch` cuando difieren.

## 7. Estructuras no modeladas o no evaluables

| Estructura | Dónde aparece | Estado | Por qué |
|---|---|---|---|
| `{150d1b92}` (`UnnamedBotDataEntry`) | 36 veces en `BotData` de Q/W/E/R | preservada como `unresolved` | Se desconocen sus dos campos y su consumo |
| `BotsSpellData` | raíz de cada `BotData` | preservada como `unresolved` | Clase de IA; no se modela |
| `EffectValueCalculationPart` | Kha'Zix Q/W/E; no en Zaahen | tipada como `effect_value`, no evaluable | Requiere `SpellEffectAmount`, fuera del árbol |
| `GameCalculationConditional` | Kha'Zix Q/W/E/R; no en Zaahen | tipada como `conditional`, no evaluable | Depende de un buff/condición de juego |
| `ReviveBonusPerLevel` | pasiva de Zaahen | sin `values` | El bin no trae el valor; no se sustituye por cero |
| `ReviveBonusPerLevelAtAndAfter` | pasiva de Zaahen | sin `values` | Igual |
| `mStat=13` | `R.BotData` | `unresolved_stat` | Sin muestra que permita mapearlo |

## 8. Herramientas y reproducibilidad

| Herramienta | Qué hace | Requisitos |
|---|---|---|
| `python -m binmodel` | Extrae árboles tipados, `DataValue`, estadísticas, diagnósticos y validación | Python 3.14, sin red |
| `python -m tools.make_extract_fixture` | Genera un fixture recortado y verifica el SHA-256 | JSON de entrada |
| `python -m tools.extract_rst` | Extrae cadenas RST v5 de un WAD y las resuelve con la tabla XXH3 | WAD local, tabla de hashes |
| `python -m pytest research -q` | Suite offline (75 pruebas) | Python 3.14 |
| `ruff check` / `ruff format --check` | Calidad del código nuevo | ruff 0.17.1 |

La tabla `hashes.rst.xxh3.txt` se descarga de `https://raw.communitydragon.org/data/hashes/lol/hashes.rst.xxh3.txt` y no se versiona. El WAD y el bin originales tampoco se versionan.
