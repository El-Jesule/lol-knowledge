# Investigación LoL-Knowledge — Zaahen

Índice del trabajo de investigación. Hay dos fases vivas:

- **Fase 4 (actual):** extractor genérico de árboles de cálculo desde el bin 16.20, con evaluación determinista, procedencia y validación experimental.
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

# Suite offline (82 pruebas)
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
- 82 pruebas offline; `ruff check` y `ruff format --check` limpios.

### Estructura nueva

| Ruta | Contenido |
|---|---|
| `binmodel/` | Extractor, registro de clases, evaluador, estadísticas, validación y CLI |
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
