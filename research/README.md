# Prototipo CommunityDragon — Zaahen (Fase 3.5)

Extrae un subconjunto pequeño de valores de Zaahen desde el bin de CommunityDragon, conserva la procedencia por campo y compara con Data Dragon, los datos RCP del cliente y la wiki. **El prototipo no modifica `data/current`, no escribe en `lol-knowledge/` y no publica valores conflictivos como verificados.**

## Navegación

| Quiero… | Ir a |
|---|---|
| Continuar la investigación sin la conversación original | [`zaahen-research-handoff.md`](zaahen-research-handoff.md) |
| Saber qué fuentes se consultaron y qué límites tienen | [`evidence/usage-conditions.md`](evidence/usage-conditions.md) |
| Ejecutar el prototipo | Sección «Ejecutar», más abajo |
| Ver el estado del campeón en la base de conocimiento | [`../lol-knowledge/champions/Zaahen/overview.md`](../lol-knowledge/champions/Zaahen/overview.md) |
| Ver el seguimiento de esta fase | [`../odd/tasks/zaahen-research-handoff.md`](../odd/tasks/zaahen-research-handoff.md) |

`zaahen-research-handoff.md` es el punto de entrada para otro agente: resume hallazgos verificados, inferencias, líneas abiertas, licencias y reproducibilidad. **Empezar por ahí.**

## Ejecutar

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

La suite del prototipo es offline:

```powershell
.\.venv\Scripts\python.exe -m pytest research -q
```

## Qué demuestra

- Extracción de 41 parámetros con ruta exacta, SHA-256 del origen y versión de contenido.
- Enfriamientos efectivos desde `mSpell.Cooldown.values`; `cooldownTime` se conserva solo como diagnóstico y no se compara.
- Estadísticas del campeón desde `CharacterRecords/Root`; el crecimiento de AD es `4.0`.
- Cálculo de la R en rango 1 con 100 de bonus AD: `250 + 2 × 100 = 450`, marcado `derived` porque `mStat`/`mStatFormula` es una interpretación, no un enum documentado.
- Detección de tres conflictos sin resolverlos: crecimiento de AD (Data Dragon `0` frente a bin y wiki `4`), AD por acumulación de la pasiva (`2,8 %` frente a `2,95 %`) y multiplicador de Q contra monstruos (`1,0` frente a `200 %`).
- El conflicto del enfriamiento de W queda resuelto: el campo efectivo coincide con Data Dragon, RCP y wiki.
- Propagación de bloqueos solo a los parámetros afectados.
- Rechazo de partes de cálculo con tipos desconocidos (`unverified`), en lugar de adivinar.
- Fallos de red o JSON inválido no tocan la caché ni los datos publicados.

## Estructura

| Ruta | Contenido |
|---|---|
| `zaahen-research-handoff.md` | Documento de continuidad: hallazgos, líneas abiertas, licencias y reproducibilidad |
| `cdragon_zaahen/client.py` | Cliente fijado a 16.20, sin credenciales, con caché y hash |
| `cdragon_zaahen/extract.py` | Extracción y procedencia por campo |
| `cdragon_zaahen/compare.py` | Reglas de comparación y conflictos |
| `cdragon_zaahen/wiki_evidence.py` | Trascripción manual de la wiki, con URL y fecha |
| `fixtures/` | Recortes pequeños de los datos usados (no se versiona el archivo original) |
| `evidence/usage-conditions.md` | Políticas consultadas y dudas pendientes |
| `.cache/` | Archivo original descargado; ignorado por Git |

## Estados

`source_explicit`, `derived`, `inferred`, `corroborated`, `verified`, `unverified`, `conflict`. Precedencia: conflicto > no verificado > verificado > corroborado > inferido > derivado > explícito.

`corroborated` se usa cuando coinciden derivaciones del mismo origen (Data Dragon y CommunityDragon) o una fuente secundaria; `verified` exige además que el valor coincida con Data Dragon del parche objetivo y con una fuente independiente.

## Condiciones de uso

El archivo original se guarda solo en `.cache/` (ignorado). Los fixtures son recortes derivados. **No hay conclusión legal firme**: ver `evidence/usage-conditions.md`. No se versiona el bin completo.

## Eliminar el prototipo

```powershell
Remove-Item -Recurse -Force research
```

No hay cambios en `src/`, `tests/` ni `data/` que dependan de este directorio.
