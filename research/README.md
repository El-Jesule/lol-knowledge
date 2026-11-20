# Investigación LoL-Knowledge — Zaahen

Índice del trabajo de investigación. Hay cuatro fases vivas:

- **Fase 6 (actual):** cierre de cinco mecánicas de objetos con evidencia citada, ampliación selectiva del catálogo y auditoría Git sin fusiones.
- **Fase 5:** auditoría de garantías del extractor y modelo mecánico de objetos (`lol-object-model/1`) preparado para el futuro motor de daño.
- **Fase 4:** extractor genérico de árboles de cálculo desde el bin 16.20, con evaluación determinista, procedencia y validación experimental.
- **Fase 3.5 (anterior):** prototipo CommunityDragon que extrae un subconjunto de valores y los compara con Data Dragon, RCP y la wiki.

Nada de `research/` modifica `data/current/`, `src/lol_knowledge/` ni `lol-knowledge/`. El prototipo se puede borrar sin afectar a la CLI ni al snapshot.

## Navegación

| Quiero… | Ir a |
|---|---|
| Continuar la investigación sin la conversación original | [`zaahen-research-handoff.md`](zaahen-research-handoff.md) |
| Entender el extractor y su modelo de datos | [`zaahen-formula-spec.md`](zaahen-formula-spec.md) |
| Ver todas las estructuras y cálculos encontrados | [`zaahen-structure-inventory.md`](zaahen-structure-inventory.md) |
| Ver qué falta y cómo cerrarlo | [`zaahen-uncertainties.md`](zaahen-uncertainties.md) |
| Leer el informe de fórmulas (Agente A) | [`reports/agent-a-formulas.md`](reports/agent-a-formulas.md) |
| Leer el informe de estructuras binarias (Agente B) | [`reports/agent-b-bin-structures.md`](reports/agent-b-bin-structures.md) |
| Leer la verificación independiente (Agente C) | [`reports/agent-c-verification.md`](reports/agent-c-verification.md) |
| Leer la auditoría de garantías del extractor (Agente D) | [`reports/agent-d-extractor-audit.md`](reports/agent-d-extractor-audit.md) |
| Leer la evidencia de las mecánicas de objetos y el plan Git | [`reports/object-mechanics-2026-10-20.md`](reports/object-mechanics-2026-10-20.md) |
| Ver qué cambió en el bin de Zaahen entre 16.20 y 16.22 | [`reports/zaahen-bin-diff-16.22.md`](reports/zaahen-bin-diff-16.22.md) |
| Ver la penetración de armadura de la R de Zaahen | [`reports/zaahen-r-armor-pen.md`](reports/zaahen-r-armor-pen.md) |
| Ver los registros de estadísticas extraídos del cliente 16.22 | [`reports/champion-records-16.22.md`](reports/champion-records-16.22.md) |
| Ver los datos de efectos de objetos extraídos del cliente 16.22 | [`reports/item-effects-16.22.md`](reports/item-effects-16.22.md) |
| Ver la especificación del kit de Zaahen | [`kits/Zaahen.spec.json`](kits/Zaahen.spec.json) |
| Ver cómo se hizo el kit de Ahri desde el bin del cliente | [`reports/ahri-kit-16.22.md`](reports/ahri-kit-16.22.md) |
| Entender el modelo mecánico de objetos | [`../lol-knowledge/objects/README.md`](../lol-knowledge/objects/README.md) |
| Saber qué fuentes se consultaron y qué límites tienen | [`evidence/usage-conditions.md`](evidence/usage-conditions.md) |
| Ver el estado del campeón en la base de conocimiento | [`../lol-knowledge/champions/Zaahen/overview.md`](../lol-knowledge/champions/Zaahen/overview.md) |
| Ver el seguimiento de la fase 4 | [`../odd/tasks/zaahen-formula-extraction.md`](../odd/tasks/zaahen-formula-extraction.md) |
| Ver el seguimiento de la fase 3.5 | [`../odd/tasks/zaahen-research-handoff.md`](../odd/tasks/zaahen-research-handoff.md) |

`zaahen-research-handoff.md` es el punto de entrada para otro agente. **Empezar por ahí.**

## Fase 4 — extractor genérico

### Ejecutar

```powershell
$env:PYTHONPATH="research"

# Resumen y validación de Zaahen (fixture recortado, sin red)
.\.venv\Scripts\python.exe -m binmodel `
  --input research\fixtures\zaahen_extract_min.json --validate

# JSON completo
.\.venv\Scripts\python.exe -m binmodel `
  --input research\fixtures\zaahen_extract_min.json `
  --output research\reports\zaahen-extract.json --json

# Daño a nivel/rango concretos
.\.venv\Scripts\python.exe -m binmodel `
  --input research\fixtures\zaahen_extract_min.json `
  --level 18 --rank 1 --bonus-ad 100

# Otro campeón real (fixture Darius)
.\.venv\Scripts\python.exe -m binmodel `
  --input research\fixtures\darius_extract_min.json

# Suite offline (97 pruebas)
.\.venv\Scripts\python.exe -m pytest research -q
```

### Qué demuestra

- Descubrimiento genérico: campeón, pasiva, Q/W/E/R, hijos, rangos, `DataValue`, cálculos, cooldowns, maná y rango, sin `DATA_VALUE_SPECS`.
- 10 cálculos de nivel superior y las 24 `GameCalculation` del documento, incluidas las de `BotData` y `ZaahenQ2`.
- Árboles tipados con procedencia por nodo: ruta, puntero JSON, SHA-256, versión de contenido, tipo y nombre provisional.
- Evaluación determinista de Q/W/E/R y de la pasiva; errores explícitos para nodos no soportados, referencias rotas y ciclos.
- Validación con las mediciones del usuario: AD 74/77/105/142 y pasiva 1.5–2.8 %.
- Generalización: fixture sintético `TestChampion` y fixture real de Darius; Kha'Zix (no versionado) descubre 18 cálculos y marca 4 `EffectValueCalculationPart` como no evaluables.
- Separación de `Cooldown.values` (efectivo) y `cooldownTime` (legado); W se marca como discrepancia.
- `DataValuesModeOverride/cherry` se conserva separado y con su propio puntero.
- 97 pruebas offline; `ruff check` y `ruff format --check` limpios.

### Estructura nueva

| Ruta | Contenido |
|---|---|
| `binmodel/` | Extractor, registro de clases, evaluador, estadísticas, validación, generador de borradores (`specdraft`), compilador de kits (`kitgen`), compilador por lotes (`batch_kits`) y CLI |
| `binmodel/schema/lol_classes.json` | Registro compacto de clases y hashes usados por los cálculos |
| `fixtures/zaahen_extract_min.json` | Fixture recortado de Zaahen (43 KB) |
| `fixtures/darius_extract_min.json` | Fixture recortado de Darius (34 KB) |
| `fixtures/zaahen_tooltips_es_es.json` | 123 cadenas es_ES de Zaahen extraídas del WAD |
| `tools/make_extract_fixture.py` | Genera fixtures recortados y verifica el SHA-256 |
| `tools/extract_rst.py` | Extrae cadenas RST v5 de un WAD y las resuelve con XXH3 |
| `tests/test_binmodel_*.py` | Pruebas del extractor |
| `tests/test_rst.py` | Pruebas del parser RST |

### Límites de la fase 4

- La aplicación de la pasiva (base del porcentaje y multiplicador máximo) no está en el bin; probablemente vive en Lua. Ver `zaahen-uncertainties.md`.
- `RevivePercentCalc` es parcial: faltan `ReviveBonusPerLevel` y `ReviveBonusPerLevelAtAndAfter`.
- `BotData` contiene 36 `{150d1b92}` sin semántica y `BotsSpellData`; se preservan como no resueltos.
- `EffectValueCalculationPart` y `GameCalculationConditional` se tipan, pero no se evalúan.
- El tipo de daño no está en el árbol de cálculo; se infiere del marcado de los tooltips.
- La fórmula de crecimiento de estadísticas es un modelo externo, no un dato del bin.

## Fase 5 — auditoría y modelo de objetos

La auditoría de la fase 4 encontró y corrigió defectos reales de la garantía «desconocido nunca es cero»: breakpoints, cálculos vacíos, nodos malformados, dependencias filtradas, procedencia incompleta y factores sin confianza. El informe con evidencias y regresiones es [`reports/agent-d-extractor-audit.md`](reports/agent-d-extractor-audit.md).

El modelo de objetos vive fuera de `research/`, en la base de conocimiento y la biblioteca:

- Esquema, decisiones, objetos modelados, inventario no soportado e interfaz del motor: [`../lol-knowledge/objects/README.md`](../lol-knowledge/objects/README.md).
- Catálogo curado: [`../lol-knowledge/objects/catalog.json`](../lol-knowledge/objects/catalog.json).
- Código y validador: [`../src/lol_knowledge/objects/`](../src/lol_knowledge/objects/).
- Seguimiento de la fase: [`../odd/tasks/object-model.md`](../odd/tasks/object-model.md).

```powershell
.\.venv\Scripts\python.exe -m lol_knowledge.objects --validate
.\.venv\Scripts\python.exe -m lol_knowledge.objects --json
```

Límites: la muestra es de 15 objetos tras la fase 6; no hay motor de daño ni búsqueda de builds. Los ratios y curvas no publicados se marcan como desconocidos o excluidos.

## Fase 12 — kits de campeón

`python -m binmodel.kitgen` compila `lol-knowledge/champions/<Id>/kit.json` a partir de:

1. la extracción del bin (`python -m binmodel --json`), de la que salen los números;
2. los tooltips del cliente, de los que sale el tipo de daño de cada parte;
3. una especificación curada (`kits/<Id>.spec.json`) que dice qué casos tiene cada habilidad y qué cálculo alimenta cada parte.

Un tipo de daño declarado que contradiga el tooltip, un nodo que no sabe traducir o un valor ausente detienen la compilación.

```powershell
$env:PYTHONPATH="research"
.\.venv\Scripts\python.exe -m binmodel --input research\.cache\zaahen-16.20.bin.json --json > zaahen-extract.json
.\.venv\Scripts\python.exe -m binmodel.kitgen --extract zaahen-extract.json `
  --tooltips research\fixtures\zaahen_tooltips_es_es.json `
  --spec research\kits\Zaahen.spec.json --output lol-knowledge\champions\Zaahen\kit.json
```

## Fase 33 — kits desde el bin del cliente (Ahri)

`python -m binmodel.bin2json` convierte el bin de un campeón del cliente instalado al formato de los exports de CommunityDragon, con las listas de hashes locales y los marcadores de los tooltips. Así el extractor y `kitgen` funcionan sin acceso a CommunityDragon. Se comprobó regenerando el kit de Zaahen desde su bin 16.22 (sale idéntico) y se usó para el kit de Ahri. Detalle, evidencia de `mStat` 0 = poder de habilidad y comandos en [`reports/ahri-kit-16.22.md`](reports/ahri-kit-16.22.md).

## Fase 10 — registros de estadísticas de todos los campeones

`python -m binmodel.records` lee `CharacterRecords/Root` del bin de cada campeón en el cliente instalado y publica una tabla `Derivado` en `lol-knowledge/derived/champion-records.json`. Sustituye el crecimiento de DA que Data Dragon publica a 0. Detalle, diferencias con Data Dragon y comando en [`reports/champion-records-16.22.md`](reports/champion-records-16.22.md).

`binmodel/wad.py` lee ahora solo el índice y la entrada pedida, no el archivo entero.

## Fase 23 — datos de efectos de todos los objetos

`python -m binmodel.item_effects` lee, para cada objeto de `lol-knowledge/objects/catalog-stats.json`, los valores, cálculos y variantes de su registro `Items/<id>` y sus textos es_ES, y publica una tabla `Derivado` en `lol-knowledge/derived/item-effects.json`. Detalle, resultados y límites en [`reports/item-effects-16.22.md`](reports/item-effects-16.22.md).

```powershell
$env:PYTHONPATH="research"
.\.venv\Scripts\python.exe -m binmodel.item_effects `
  --wad "<Game>\DATA\FINAL\Global.wad.client" `
  --strings "<Game>\DATA\FINAL\Localized\Global.es_ES.wad.client" `
  --rst-hashes <hashes.rst.xxh3.txt de CommunityDragon/Data> `
  --ids-from lol-knowledge\objects\catalog-stats.json `
  --content-version <version de Game\content-metadata.json> --retrieved-at <fecha> `
  --output lol-knowledge\derived\item-effects.json
```

## Fase 37 — runas y fragmentos del cliente

`python -m binmodel.perks` lee la entrada `perks` de `Global.wad.client`: árboles (`PerkStyle`), filas de fragmentos (`PerkSlot`) y cada runa (`Perk`) con sus valores, variantes por modo, cálculos y textos es_ES. Los valores se nombran con los marcadores `@…@` de los textos de runas y efectos. Publica `lol-knowledge/derived/runes.json` (`Derivado`); la regla está en [`../lol-knowledge/mechanics/runes.md`](../lol-knowledge/mechanics/runes.md). `research/tools/refresh_patch.py` lo regenera.

```powershell
$env:PYTHONPATH="research"
.\.venv\Scripts\python.exe -m binmodel.perks --wad "<Game>\DATA\FINAL\Global.wad.client" `
  --strings "<Game>\DATA\FINAL\Localized\Global.es_ES.wad.client" --rst-hashes <hashes.rst.xxh3.txt> `
  --content-version <version de Game\content-metadata.json> --retrieved-at <fecha> `
  --output lol-knowledge\derived\runes.json
```

`binmodel.records` publica además `adaptiveforceapweight` (`mAdaptiveForceToAbilityPowerWeight`), que decide la fuerza adaptable en un empate.

## Fase 36 — grupos de objetos para la legalidad de la build

`python -m binmodel.item_groups` lee, para cada objeto de `lol-knowledge/objects/catalog-stats.json`, sus grupos (`mItemGroups`), su `maxStack` y su `mRequiredChampion`, y de cada grupo su máximo (`mMaxGroupOwnable`) y su hueco fijo (`mInventorySlotMin`/`Max`). Publica una tabla `Derivado` en `lol-knowledge/derived/item-groups.json`; la regla está en [`../lol-knowledge/mechanics/build-legality.md`](../lol-knowledge/mechanics/build-legality.md). `research/tools/refresh_patch.py` la regenera con los demás datos del cliente.

```powershell
$env:PYTHONPATH="research"
.\.venv\Scripts\python.exe -m binmodel.item_groups --wad "<Game>\DATA\FINAL\Global.wad.client" `
  --ids-from lol-knowledge\objects\catalog-stats.json --entry-names <hashes.binentries.txt> `
  --content-version <version de Game\content-metadata.json> --retrieved-at <fecha> `
  --output lol-knowledge\derived\item-groups.json
```

## Fase 7 — lectura directa del bin del cliente

Lee el bin binario (`PROP`) desde el `*.wad.client` instalado y lo compara campo a campo con un export `.bin.json` de CommunityDragon. Sirve para saber, en cada parche, qué valores derivados siguen vigentes sin depender de que CommunityDragon sea accesible.

```powershell
$env:PYTHONPATH="research"

# Comparar el bin instalado con la caché 16.20
.\.venv\Scripts\python.exe -m binmodel.bindiff `
  --wad "D:\Games\Riot Games\League of Legends\Game\DATA\FINAL\Champions\Zaahen.wad.client" `
  --entry data/characters/zaahen/zaahen.bin `
  --against research\.cache\zaahen-16.20.bin.json

# Informe JSON; --check sale con 1 si hay diferencias
.\.venv\Scripts\python.exe -m binmodel.bindiff --bin zaahen.bin `
  --against research\.cache\zaahen-16.20.bin.json --json --check
```

Códigos de salida: `0` comparación hecha, `1` diferencias con `--check`, `2` entrada ilegible o mal formada.

| Ruta | Contenido |
|---|---|
| `binmodel/propbin.py` | Lector estricto de bins `PROP` v1–v3 (y envoltorio `PTCH`) |
| `binmodel/wad.py` | Lectura de una entrada de un WAD v3 por su ruta |
| `binmodel/xxh64.py` | XXH64 en Python puro para rutas de WAD y campos `file` |
| `binmodel/bindiff.py` | Comparador bin binario ↔ export JSON y CLI |
| `tests/propbuild.py` | Codificadores mínimos de PROP y WAD para generar entradas sintéticas |
| `tests/test_binmodel_{propbin,wad,xxh64,bindiff}.py` | Pruebas sin red ni archivos del cliente |

### Límites de la fase 7

- El lector es estricto: un tipo desconocido, un tamaño declarado que no cuadra o bytes sobrantes detienen la lectura. `skin0.bin` de Zaahen en 16.22 se rechaza por un tipo `0xb5` sin documentar; no se ha investigado.
- `wad.py` decodifica entradas de tipo 0, 1 y 3. Las de tipo 2 (satélite) y 4 (zstd por subchunks) se rechazan en lugar de adivinar su formato. `tools/extract_rst.py` sigue saltándose las de tipo 4 en silencio.
- La comparación es estructural: compara valores por hash de nombre, no interpreta semántica. Un campo nuevo aparece con su hash sin resolver.
- Los campos `file` se comparan por XXH64 de la ruta en minúsculas; si un export usara otra normalización, aparecería como cambio.

## Fase 6 — mecánicas de objetos y plan de integración

Cierra BotRK (daño de impacto y acumulaciones), Lord Dominik (curva completa), Zhonya (enfriamiento de la activa) y Malla de espinas (daño reflejado), y añade Botas de hechicero y Randuin. Separa la evidencia oficial de Data Dragon de la evidencia secundaria citada, con `sources`, `evidence_confidence` y validación de que ningún número quede huérfano.

- Informe completo con fuentes, citas, confianza, límites y grafo Git: [`reports/object-mechanics-2026-10-20.md`](reports/object-mechanics-2026-10-20.md).
- Seguimiento de la fase: [`../odd/tasks/object-mechanics-coverage.md`](../odd/tasks/object-mechanics-coverage.md).

## Fase 3.5 — prototipo CommunityDragon

Extrae un subconjunto de valores de Zaahen desde el bin de CommunityDragon, conserva la procedencia por campo y compara con Data Dragon, RCP y la wiki. **No modifica `data/current`, no escribe en `lol-knowledge/` y no publica valores conflictivos como verificados.**

### Ejecutar

```powershell
$env:PYTHONPATH="research"

# Descarga fijada a 16.20, verifica el JSON y rellena research/.cache
.\.venv\Scripts\python.exe -m cdragon_zaahen

# Solo caché, sin red
.\.venv\Scripts\python.exe -m cdragon_zaahen --offline

# Informe completo en JSON
.\.venv\Scripts\python.exe -m cdragon_zaahen --json

# Falla (exit 1) si hay conflictos
.\.venv\Scripts\python.exe -m cdragon_zaahen --offline --check
```

### Qué demuestra

- Extracción de 41 parámetros con ruta exacta, SHA-256 del origen y versión de contenido.
- Enfriamientos efectivos desde `mSpell.Cooldown.values`; `cooldownTime` se conserva solo como diagnóstico.
- Estadísticas del campeón desde `CharacterRecords/Root`; el crecimiento de AD es `4.0`.
- Cálculo de la R en rango 1 con 100 de bonus AD: `250 + 2 × 100 = 450`, marcado `derived`.
- Detección de conflictos sin resolverlos: crecimiento de AD, AD por acumulación de la pasiva y multiplicador de Q contra monstruos.
- Rechazo de partes de cálculo con tipos desconocidos (`unverified`), en lugar de adivinar.
- Fallos de red o JSON inválido no tocan la caché ni los datos publicados.

### Estructura de la fase 3.5

| Ruta | Contenido |
|---|---|
| `cdragon_zaahen/client.py` | Cliente fijado a 16.20, sin credenciales, con caché y hash |
| `cdragon_zaahen/extract.py` | Extracción y procedencia por campo |
| `cdragon_zaahen/compare.py` | Reglas de comparación y conflictos |
| `cdragon_zaahen/wiki_evidence.py` | Transcripción manual de la wiki, con URL y fecha |
| `fixtures/zaahen_spells_min.json` | Recorte usado por el prototipo anterior |
| `fixtures/zaahen_rcp_min.json` | Recorte del RCP |
| `evidence/usage-conditions.md` | Políticas consultadas y dudas pendientes |
| `.cache/` | Archivo original descargado; ignorado por Git |

## Estados de confianza

`source_explicit`, `derived`, `inferred`, `corroborated`, `verified`, `unverified`, `conflict`. Precedencia: conflicto > no verificado > verificado > corroborado > inferido > derivado > explícito.

`corroborated` se usa cuando coinciden derivaciones del mismo origen o una fuente secundaria; `verified` exige además que el valor coincida con Data Dragon del parche objetivo y con una fuente independiente.

## Condiciones de uso

El archivo original se guarda solo en `.cache/` (ignorado). Los fixtures son recortes derivados. **No hay conclusión legal firme**: ver `evidence/usage-conditions.md`. No se versiona el bin completo, ni el WAD, ni la tabla de hashes de 8 MB.

## Eliminar los prototipos

```powershell
Remove-Item -Recurse -Force research
```

No hay cambios en `src/`, `tests/` ni `data/` que dependan de este directorio.
