# LoL-Knowledge

Base de conocimiento verificable de League of Legends: datos oficiales de Riot (Data Dragon), análisis con fuente declarada y una CLI en Python que ingesta, valida y calcula de forma reproducible.

Estado actual: **fase 2**. Existe la ingesta del snapshot oficial de Data Dragon y el validador de integridad; el análisis de campeones llega en las fases siguientes.

## Requisitos

- Python 3.14
- Git

## Puesta en marcha

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\python.exe -m lol_knowledge version
```

## Validaciones

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check .
.\.venv\Scripts\python.exe -m lol_knowledge validate
```

La suite incluye pruebas de integración que ejecutan `python -m lol_knowledge` en un subproceso. Requieren el paquete instalado en modo editable (`pip install -e .`); si falta esa instalación, fallan de forma visible y no se saltan en silencio.

## Estructura

| Ruta | Contenido |
|---|---|
| `lol-knowledge/` | Base de conocimiento: índices, campeones, mecánicas, metodología |
| `data/current/` | Snapshot oficial generado desde Data Dragon (no editar a mano) |
| `src/lol_knowledge/` | CLI y biblioteca de cálculo |
| `tests/` | Pruebas sin acceso a red |
| `odd/tasks/` | Documentos de tarea por fase |
| `AGENTS.md` | Reglas persistentes del proyecto |

## Comandos disponibles

| Comando | Estado |
|---|---|
| `python -m lol_knowledge version` | Disponible |
| `python -m lol_knowledge update` | Disponible |
| `python -m lol_knowledge validate` | Disponible |
| `python -m lol_knowledge damage` | Fase 4 |

## Actualización de datos

Bajo demanda, sin tareas programadas:

```powershell
.\.venv\Scripts\python.exe -m lol_knowledge update
.\.venv\Scripts\python.exe -m lol_knowledge update --patch 16.20.1
```

Escribe `data/current/` con `manifest.json`, `champion-index.json`, `champions/<Id>.json` por campeón, `items.json` y `runes.json`. El manifiesto registra parche, locale, origen, fecha UTC y el `sha256` de cada archivo. Con el mismo parche ya aplicado informa «sin cambios» y no reescribe nada.

La descarga se valida antes de publicarse y se escribe primero en un directorio de staging; el snapshot anterior solo se sustituye cuando el nuevo está completo, y se restaura si el renombrado falla.

Códigos de salida: `0` éxito (con o sin cambios), `1` datos de origen inválidos, `2` problema de red, entorno o escritura. Sin claves de API y sin Riot API.

## Validación de integridad

```powershell
.\.venv\Scripts\python.exe -m lol_knowledge validate
```

Comprueba el snapshot y la estructura de la base de conocimiento:

- Forma del manifiesto, parche y fecha UTC válidos.
- Cada archivo listado existe, con el tamaño y el `sha256` registrados; ningún archivo sobrante.
- Índice de campeones coherente con los archivos: ids únicos y válidos, sin huérfanos, 4 habilidades y estadísticas numéricas.
- Objetos y runas con la forma esperada.
- Enlaces Markdown existentes y dentro del repositorio; directorios de campeón que correspondan a un id publicado.
- Referencias `data:item:<id>`, `data:rune:<id>` y `data:champion:<Id>` que existan en el snapshot.

Códigos de salida: `0` todo coherente, `1` violaciones (se listan con archivo y motivo), `2` problema de entorno. Si `lol-knowledge/` aún no existe, las comprobaciones de enlaces y referencias se informan como omitidas, no como superadas.

Los checksums dependen de los bytes exactos: `.gitattributes` fija `eol=lf` para que cualquier checkout use LF.

## Limitaciones conocidas

- No hay integración con la Riot API ni claves de API.
- No hay estadísticas comunitarias: solo datos oficiales.
- No hay CI ni publicación remota.
- La cobertura de campeones empieza por un caso representativo y crece de forma incremental.

## Flujo de trabajo

Las reglas de ramas, commits, pruebas y etiquetado de fuentes están en [`AGENTS.md`](AGENTS.md).
