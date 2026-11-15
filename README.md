# LoL-Knowledge

Base de conocimiento verificable de League of Legends: datos oficiales de Riot (Data Dragon), análisis con fuente declarada y una CLI en Python que ingesta, valida y calcula de forma reproducible.

Estado actual: **fase 10**. Existen la ingesta, el validador de integridad, el primer campeón analizado (Zaahen), el extractor de cálculos y el lector del bin del cliente en `research/`, un modelo mecánico de objetos versionado para 15 objetos, el núcleo del motor de daño (mitigación por resistencias) la hoja de estadísticas de campeón con sus primeras métricas (vida efectiva y enfriamientos) y una tabla de estadísticas base y por nivel extraída del cliente para los 173 campeones. Todavía no se evalúan las habilidades de los campeones.

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
| `lol-knowledge/` | Base de conocimiento: índices, campeones, objetos, reglas (`mechanics/`) y datos derivados del cliente (`derived/`) |
| `data/current/` | Snapshot oficial generado desde Data Dragon (no editar a mano) |
| `src/lol_knowledge/` | CLI, hoja de estadísticas y métricas (`stats/`), motor de daño (`damage/`) y modelo de objetos (`objects/`) |
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
| `python -m lol_knowledge stats` | Disponible (hoja de estadísticas, vida efectiva y enfriamientos) |

## Actualización de datos

Bajo demanda, sin tareas programadas:

```powershell
.\.venv\Scripts\python.exe -m lol_knowledge update
.\.venv\Scripts\python.exe -m lol_knowledge update --patch 16.22.1
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

## Hoja de estadísticas

Resuelve las estadísticas de un campeón a un nivel, con objetos del catálogo curado, y calcula métricas a partir de ellas: vida efectiva frente a cada tipo de daño y enfriamientos de Q, W, E y R tras la aceleración de habilidades.

```powershell
# Zaahen a nivel 11 con Gema avivadora y Botas blindadas
.\.venv\Scripts\python.exe -m lol_knowledge stats --champion Zaahen --level 11 --item 3067 --item 3047

# El DA queda bloqueado por un defecto de Data Dragon; se puede suponer el crecimiento
.\.venv\Scripts\python.exe -m lol_knowledge stats --champion Zaahen --level 11 `
  --assume attackdamageperlevel=4 --json
```

- **Cada estadística es una lista de aportes** (campeón, crecimiento por nivel, objetos, supuestos), cada uno con su fuente y su etiqueta. La etiqueta de un total es la más débil de sus aportes.
- **Registro compartido** (`src/lol_knowledge/stats/registry.py`): declara cada estadística, cómo se apilan sus fuentes y si tiene regla documentada. Las que no la tienen (velocidad de ataque y de movimiento, regeneración, críticos, robo de vida, omnivampirismo, tenacidad) se listan con sus aportes, pero sin total.
- **Defectos de datos** ([`lol-knowledge/data-issues.json`](lol-knowledge/data-issues.json)): un campo oficial que se sabe incorrecto no se usa. Se sustituye por el registro del cliente ([`lol-knowledge/derived/champion-records.json`](lol-knowledge/derived/champion-records.json)), `Derivado` si el parche coincide con el snapshot y `Pendiente de verificación` si no. Sin registro, la estadística queda bloqueada. `--assume` tiene prioridad y siempre es `Pendiente de verificación`.
- **Solo objetos curados:** Data Dragon no publica todas las estadísticas de los objetos (letalidad, aceleración, penetración van en la descripción), así que un objeto fuera del catálogo se rechaza.
- Reglas: [crecimiento](lol-knowledge/mechanics/stat-growth.md), [aceleración](lol-knowledge/mechanics/ability-haste.md), [vida efectiva](lol-knowledge/mechanics/effective-health.md), [defectos conocidos](lol-knowledge/mechanics/known-data-issues.md).

Códigos de salida: `0` hoja calculada (aunque alguna estadística esté bloqueada; el informe lo dice), `2` petición inválida o datos ausentes.

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
- Registro de defectos de datos (`lol-knowledge/data-issues.json`): esquema, campos de Data Dragon conocidos, ids de campeón y documentación existente.
- Registros derivados del cliente (`lol-knowledge/derived/champion-records.json`): esquema, etiqueta, versiones coherentes, campos conocidos con valores no negativos e ids de campeón del snapshot.

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
- Data Dragon (16.20.1 y 16.22.1) publica `attackdamageperlevel = 0` para todos los campeones. Se sustituye por el crecimiento del cliente 16.22, `Derivado` porque cliente y snapshot coinciden. Senna no tiene el campo en el bin y su DA queda bloqueado por encima del nivel 1.
- La hoja de estadísticas no incluye runas, efectos de objeto ni pasivas de campeón, y no valida la legalidad de una build (objetos únicos, botas).
- El motor de daño solo modela la mitigación por armadura y resistencia mágica de una instancia. No modela amplificaciones ni reducciones de daño, escudos, críticos, la penetración de armadura adicional ni el redondeo del juego, y todavía no lee campeones ni objetos.
- Data Dragon no publica valores numéricos de las habilidades de Zaahen; los valores derivados están documentados y las discrepancias abiertas siguen como pendientes.
- La cobertura de campeones empieza por un caso representativo y crece de forma incremental.
- El modelo de objetos cubre una muestra de 15 objetos por diversidad mecánica. Las cifras que Data Dragon no publica solo se incorporan con una fuente citada y `evidence_confidence: secondary`; lo no verificado se marca como desconocido o parcial, no se inventa.

## Flujo de trabajo

Las reglas de ramas, commits, pruebas y etiquetado de fuentes están en [`AGENTS.md`](AGENTS.md).
