# LoL-Knowledge

Base de conocimiento verificable de League of Legends: datos oficiales de Riot (Data Dragon), análisis con fuente declarada y una CLI en Python que ingesta, valida y calcula de forma reproducible.

Estado actual: **fase 8**. Existen la ingesta, el validador de integridad, el primer campeón analizado (Zaahen), el extractor de cálculos y el lector del bin del cliente en `research/`, un modelo mecánico de objetos versionado para 15 objetos y el núcleo del motor determinista de daño (mitigación por resistencias). Todavía no existe la capa que traduce campeones y objetos a entradas del motor.

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
| `lol-knowledge/` | Base de conocimiento: índices, campeones, objetos, metodología |
| `data/current/` | Snapshot oficial generado desde Data Dragon (no editar a mano) |
| `src/lol_knowledge/` | CLI, motor de daño (`damage/`) y modelo de objetos (`objects/`) |
| `research/` | Extractor de cálculos, auditoría y prototipos aislados |
| `tests/` | Pruebas sin acceso a red |
| `odd/tasks/` | Documentos de tarea por fase |
| `AGENTS.md` | Reglas persistentes del proyecto |

## Comandos disponibles

| Comando | Estado |
|---|---|
| `python -m lol_knowledge version` | Disponible |
| `python -m lol_knowledge update` | Disponible |
| `python -m lol_knowledge validate` | Disponible |
| `python -m lol_knowledge.objects` | Disponible (modelo de objetos) |
| `python -m lol_knowledge damage` | Disponible (mitigación de una instancia de daño) |

## Actualización de datos

Bajo demanda, sin tareas programadas:

```powershell
.\.venv\Scripts\python.exe -m lol_knowledge update
.\.venv\Scripts\python.exe -m lol_knowledge update --patch 16.20.1
```

Escribe `data/current/` con `manifest.json`, `champion-index.json`, `champions/<Id>.json` por campeón, `items.json` y `runes.json`. El manifiesto registra parche, locale, origen, fecha UTC y el `sha256` de cada archivo. Con el mismo parche ya aplicado informa «sin cambios» y no reescribe nada.

La descarga se valida antes de publicarse y se escribe primero en un directorio de staging; el snapshot anterior solo se sustituye cuando el nuevo está completo, y se restaura si el renombrado falla.

Códigos de salida: `0` éxito (con o sin cambios), `1` datos de origen inválidos, `2` problema de red, entorno o escritura. Sin claves de API y sin Riot API.

## Motor de daño

Calcula el daño de una instancia tras la resistencia del objetivo. Es independiente de los datos del juego: recibe números y aplica las reglas de [`lol-knowledge/mechanics/damage-mitigation.md`](lol-knowledge/mechanics/damage-mitigation.md); no sabe nada de campeones, objetos ni parches.

```powershell
# 450 de daño físico contra 100 de armadura, con 30 % de penetración y 18 de letalidad
.\.venv\Scripts\python.exe -m lol_knowledge damage --raw 450 --type physical `
  --resistance 100 --percent-penetration 0.3 --flat-penetration 18

# Varias fuentes: se repite la opción. Informe en JSON
.\.venv\Scripts\python.exe -m lol_knowledge damage --raw 300 --type magic --resistance 80 `
  --flat-reduction 15 --percent-penetration 0.4 --percent-penetration 0.1 --json

# Daño verdadero: no admite resistencia
.\.venv\Scripts\python.exe -m lol_knowledge damage --raw 275 --type true
```

- Los porcentajes se escriben como fracción (`0.3` = 30 %). Cada repetición de una opción es una fuente independiente.
- Orden aplicado: reducción plana → reducción porcentual → penetración porcentual → penetración plana. El informe muestra la resistencia tras cada paso.
- La aritmética es exacta (fracciones), sin redondeo; el JSON incluye además el resultado como fracción en `exact`.
- Todo resultado es `Calculado` y declara sus supuestos.

Códigos de salida: `0` cálculo hecho, `2` entrada inválida o incoherente (por ejemplo, daño verdadero con resistencia, o un porcentaje fuera de 0–1).

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
- Catálogo de objetos: esquema y parche, ids y estadísticas canónicas, citas literales de la descripción, fórmulas, estados de modelo, procedencia y referencias de receta.

Códigos de salida: `0` todo coherente, `1` violaciones (se listan con archivo y motivo), `2` problema de entorno. Si `lol-knowledge/` aún no existe, las comprobaciones de enlaces y referencias se informan como omitidas, no como superadas.

Los checksums dependen de los bytes exactos: `.gitattributes` fija `eol=lf` para que cualquier checkout use LF.

## Aviso legal

Este proyecto es una base de conocimiento no comercial. Incluye datos oficiales de Data Dragon y, para Zaahen, valores derivados de los datos del cliente publicados por CommunityDragon, marcados como `Derivado`. No se redistribuyen archivos originales del cliente.

> LoL-Knowledge isn't endorsed by Riot Games and doesn't reflect the views or opinions of Riot Games or anyone officially involved in producing or managing Riot Games properties. Riot Games, and all associated properties are trademarks or registered trademarks of Riot Games, Inc.

Condiciones de uso y cuestiones pendientes: [`research/evidence/usage-conditions.md`](research/evidence/usage-conditions.md).

## Limitaciones conocidas

- No hay integración con la Riot API ni claves de API.
- No hay estadísticas comunitarias; para Zaahen se publican valores derivados de datos del cliente, marcados `Derivado` y con atribución.
- No hay CI ni publicación remota.
- El motor de daño solo modela la mitigación por armadura y resistencia mágica de una instancia. No modela amplificaciones ni reducciones de daño, escudos, críticos, la penetración de armadura adicional ni el redondeo del juego, y todavía no lee campeones ni objetos.
- Data Dragon 16.20.1 no publica valores numéricos de las habilidades de Zaahen; los valores derivados están documentados y las discrepancias abiertas siguen como pendientes.
- La cobertura de campeones empieza por un caso representativo y crece de forma incremental.
- El modelo de objetos cubre una muestra de 15 objetos por diversidad mecánica. Las cifras que Data Dragon no publica solo se incorporan con una fuente citada y `evidence_confidence: secondary`; lo no verificado se marca como desconocido o parcial, no se inventa.

## Flujo de trabajo

Las reglas de ramas, commits, pruebas y etiquetado de fuentes están en [`AGENTS.md`](AGENTS.md).
