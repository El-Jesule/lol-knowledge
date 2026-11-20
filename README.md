# LoL-Knowledge

Base de conocimiento verificable de League of Legends: datos oficiales de Riot (Data Dragon), análisis con fuente declarada y una CLI en Python que ingesta, valida y calcula de forma reproducible.

Estado actual: **fase 45**. Existen la ingesta, el validador de integridad, dos campeones con kit y pasiva modelada (Zaahen y Ahri), el extractor de cálculos, el generador automático de borradores de kit (`binmodel.specdraft`) y el compilador (`binmodel.kitgen`) en `research/`, un modelo mecánico de objetos versionado (estadísticas de los 218 objetos comprables de la Grieta, efectos curados en 43, entre ellos daño al impactar, Hoja encantada de siete objetos incluida la devolución de maná de Segador de esencia y la curación de Amanecer y anochecer, efectos cada N ataques y de Vigor, efectos según la vida del objetivo, quemaduras, Calibrador de Sterak y el amplificador de Rabadon; valores, cálculos y textos del cliente de los 218 en `lol-knowledge/derived/item-effects.json`), el núcleo del motor de daño (mitigación por resistencias), la hoja de estadísticas de campeón (todas sus estadísticas resueltas, incluido el poder de curaciones y escudos, fragmentos, runas menores de estadísticas y pasivas de campeón) con sus métricas (vida efectiva, enfriamientos con aceleración general/básica/definitiva, reserva de recurso para maná/energía/secundarios y costes oficiales por rango) y una tabla de estadísticas base y por nivel extraída del cliente para los 173 campeones. `python -m lol_knowledge ability` evalúa una habilidad contra un objetivo; `python -m lol_knowledge rotation` encadena ataques básicos, críticos y habilidades con costes de habilidad, seguimiento de recursos (maná, energía y vida), regeneración continua en `--timeline`, pasivas de campeón, escudos, curación directa, Heridas graves, efectos evaluables de objetos, runas menores de combate y piedras angulares ofensivas; y `python -m lol_knowledge survive` realiza simulaciones defensivas inversas (`time_to_die`, escudos reactivos y reducción plana posmitigación).

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

La suite incluye pruebas de integración que ejecutan `python -m lol_knowledge` en un subproceso. La CLI escribe siempre en UTF-8, aunque la consola use otra codificación (en Windows, cp1252 cuando la salida va a una tubería); hay pruebas que fuerzan cp1252 para comprobarlo. Requieren el paquete instalado en modo editable (`pip install -e .`); si falta esa instalación, fallan de forma visible y no se saltan en silencio.

El flujo de GitHub Actions ([`.github/workflows/ci.yml`](.github/workflows/ci.yml)) ejecuta estas cuatro validaciones junto con `pytest research/tests -q` en Linux y Windows con Python 3.14.

## Estructura

| Ruta | Contenido |
|---|---|
| `lol-knowledge/` | Base de conocimiento: índices, campeones, objetos, reglas (`mechanics/`) y datos derivados del cliente (`derived/`) |
| `data/current/` | Snapshot oficial generado desde Data Dragon (no editar a mano) |
| `src/lol_knowledge/` | CLI, hoja de estadísticas y métricas (`stats/`), kits de campeón (`kit/`), fórmulas compartidas (`formula/`), motor de daño (`damage/`) y modelo de objetos (`objects/`) |
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
| `python -m lol_knowledge stats` | Disponible (hoja de estadísticas, vida efectiva, enfriamientos, reserva de recurso y costes oficiales) |
| `python -m lol_knowledge ability` | Disponible (daño de una habilidad contra un objetivo; campeones con kit) |
| `python -m lol_knowledge rotation` | Disponible (secuencia de ataques y habilidades con costes, recursos, supervivencia y efectos de objeto; campeones con kit) |
| `python -m lol_knowledge survive` | Disponible (simulación defensiva inversa: daño recibido, escudos reactivos, reducción plana y tiempo hasta morir) |

## Actualización de datos

Bajo demanda, sin tareas programadas:

```powershell
.\.venv\Scripts\python.exe -m lol_knowledge update
.\.venv\Scripts\python.exe -m lol_knowledge update --patch 16.23.1
```

El procedimiento completo para pasar a un parche nuevo (snapshot, datos del cliente, catálogo, kits y pruebas) está en [`odd/procedures/patch-update.md`](odd/procedures/patch-update.md), con el guion `research/tools/refresh_patch.py`.

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
- **Registro compartido** (`src/lol_knowledge/stats/registry.py`): declara cada estadística, cómo se apilan sus fuentes y si tiene regla documentada. Hoy todas tienen regla; una estadística nueva sin regla se listaría con sus aportes, pero sin total. La velocidad de ataque se calcula como base + ratio del cliente × velocidad adicional (crecimiento y objetos), con tope de 3 ([regla](lol-knowledge/mechanics/attack-speed.md)). Robo de vida y omnivampirismo son fracciones que se suman entre sí ([regla](lol-knowledge/mechanics/life-steal-and-omnivamp.md)). La probabilidad de crítico se suma con tope de 100 % y conserva el exceso aparte ([regla](lol-knowledge/mechanics/critical-strike.md)). La tenacidad de los objetos se multiplica ([regla](lol-knowledge/mechanics/tenacity.md)). La regeneración va por cada 5 s: base del nivel × (1 + porcentajes) + aportes planos ([regla](lol-knowledge/mechanics/regeneration.md)); el `FlatHPRegenMod` de los objetos, que Data Dragon da por segundo, se multiplica por 5. La velocidad de movimiento es (base + planos) × (1 + porcentajes) con límites suaves por encima de 415 y 490 ([regla](lol-knowledge/mechanics/move-speed.md)).
- **Porcentajes:** el informe de texto muestra en porcentaje las estadísticas que son fracciones (`crit_chance: 25%`); el JSON conserva la fracción (`0.25`) y su valor exacto.
- **Defectos de datos** ([`lol-knowledge/data-issues.json`](lol-knowledge/data-issues.json)): un campo oficial que se sabe incorrecto no se usa. Se sustituye por el registro del cliente ([`lol-knowledge/derived/champion-records.json`](lol-knowledge/derived/champion-records.json)), `Derivado` si el parche coincide con el snapshot y `Pendiente de verificación` si no. Sin registro, la estadística queda bloqueada. `--assume` tiene prioridad y siempre es `Pendiente de verificación`.
- **Solo objetos curados:** Data Dragon no publica todas las estadísticas de los objetos (letalidad, aceleración, penetración van en la descripción), así que un objeto fuera del catálogo se rechaza.
- Reglas: [crecimiento](lol-knowledge/mechanics/stat-growth.md), [aceleración](lol-knowledge/mechanics/ability-haste.md), [vida efectiva](lol-knowledge/mechanics/effective-health.md), [defectos conocidos](lol-knowledge/mechanics/known-data-issues.md), [impacto crítico](lol-knowledge/mechanics/critical-strike.md).

Códigos de salida: `0` hoja calculada (aunque alguna estadística esté bloqueada; el informe lo dice), `2` petición inválida o datos ausentes.

## Legalidad de la build

`stats`, `ability` y `rotation` comprueban que los objetos del atacante y, si lo hay, del campeón objetivo quepan en un inventario: 6 huecos más el del abalorio, un objeto legendario de cada, un par de botas y los grupos exclusivos del cliente (Últimas palabras, Salvavidas, Lágrima, Hidras, Hoja encantada…). Los límites salen del cliente ([`lol-knowledge/derived/item-groups.json`](lol-knowledge/derived/item-groups.json), `Derivado`) y la regla está en [`lol-knowledge/mechanics/build-legality.md`](lol-knowledge/mechanics/build-legality.md).

- Una build ilegal sale con código `2` y la lista de violaciones. `--allow-illegal-build` calcula igualmente y las escribe como aviso en la salida de errores.
- Las notas (un objeto sin `maxStack` en el bin, datos de otro parche, un objeto de campeón sin saber quién lo lleva) también van a la salida de errores.

## Runas y fragmentos

`stats`, `ability` y `rotation` aceptan una página: `--rune` seis veces (piedra angular, tres runas del árbol principal y dos del secundario) y `--shard` tres veces (ataque, flexible, defensa). Los datos salen del cliente ([`lol-knowledge/derived/runes.json`](lol-knowledge/derived/runes.json), `Derivado`, comprobado contra Data Dragon) y la regla está en [`lol-knowledge/mechanics/runes.md`](lol-knowledge/mechanics/runes.md).

```powershell
# Ahri con Electrocutar / Brujería y dos fragmentos adaptables
.\.venv\Scripts\python.exe -m lol_knowledge stats --champion Ahri --level 11 --item 3089 `
  --rune 8112 --rune 8143 --rune 8137 --rune 8106 --rune 8226 --rune 8210 `
  --shard 5008 --shard 5008 --shard 5001
```

- La página debe ser legal (código 2 si no; `--allow-illegal-build` la calcula con aviso).
- Los fragmentos y las 16 runas menores de estadísticas (Trascendencia, Celeridad, Manitas, Calzado mágico, Banda de maná, Entrega de galletas, las tres de Leyenda, Cazador definitivo, Revitalizar y, con `--input`, Se avecina tormenta, Condicionamiento, Sobrecrecimiento, Concentración absoluta y Caminar sobre agua) se aplican en la hoja. La fuerza adaptable elige DA o PH según los objetos; en un empate decide el campeón, `Pendiente de verificación`.
- Las 14 runas menores de combate, supervivencia y recursos (Golpe de gracia, Derribado, Último esfuerzo, Arcanólogo axiomático, Piroláser, Golpe bajo, Impacto repentino, Demoler, Revitalizar < 40 % de vida, Golpe de escudo, Sabor a sangre, Absorber vida, Triunfo, Fuente de vida y Claridad mental) y las 11 piedras angulares ofensivas (Electrocutar, Cosecha oscura, Ataque intensificado, Conquistador, Compás letal, Lluvia de cuchillas, Invocar a Aery, Cometa arcano, Toque de muerte ígnea, Primer golpe y Garras del inmortal, incluida su curación) se evalúan en `rotation`; las 3 runas defensivas (`8473` Revestimiento de huesos, `8444` Fuerzas renovadas y `8465` Protector) se evalúan en `survive` (**51/62** runas de árbol cubiertas). Las 7 runas menores estrictamente de visión, oro, abalorios, Destello o velocidad fuera de combate se anotan sin debilitar el daño. Las 5 piedras angulares y 6 runas menores dependientes de mecánicas aún no construidas (CC, Vigor, hechizos de invocador, consumibles) siguen en `pending_effects` y dejan el daño en `Pendiente de verificación`.

## Kits de campeón

Hay kits de Zaahen y de Ahri. Un kit (`lol-knowledge/champions/<Id>/kit.json`, esquema `lol-champion-kit/1`) describe el daño de cada habilidad como *casos* alternativos con *partes* de daño (fórmula, tipo, etiqueta y fuente), y las estadísticas que una habilidad concede pasivamente. Las fórmulas usan el evaluador compartido con `by_rank` (valor por rango), `by_level` e `input` (dato del escenario, nunca 0 por defecto).

```python
from lol_knowledge.kit import ability_damage, load_kit, passive_contributions

kit = load_kit(root, "Zaahen")
extras = passive_contributions(kit, {"R": 3})  # penetración de la R en la hoja
sheet = build_stat_sheet(..., extras=extras)
parts = ability_damage(kit, "E", 5, sheet, case="edge", target={"max_health": 2500})
```

- El borrador de la especificación se genera automáticamente con `python -m binmodel.specdraft` (detecta tipos de daño dobles, reactivaciones, escalados sin `mStat`, curaciones y costes de vida) y se compila con `python -m binmodel.kitgen` desde los árboles del bin y el marcado de los tooltips; la estructura final de casos se cura en `research/kits/<Id>.spec.json`.
- Las pasivas de campeón (`abilities.P.passive_effects` en `kit.json`) se aplican automáticamente en `stats`, `ability` y `rotation` ([regla](lol-knowledge/mechanics/passives.md)): por ejemplo, Determinación de Zaahen (`--input determination_stacks` en hoja o acumulación paso a paso en rotación) y Robo de esencias de Ahri.
- `validate` comprueba el esquema, el campeón y que el número de rangos coincida con Data Dragon.
- Hay kit de Zaahen y de Ahri; los demás campeones no tienen kit todavía ([hoja de ruta](odd/roadmap.md), CH-01).

## Daño de una habilidad contra un objetivo

`ability` resuelve la hoja del atacante (nivel, objetos y estadísticas pasivas de las habilidades aprendidas), evalúa la habilidad con el kit del campeón y mitiga cada parte del daño con la resistencia que le corresponde y las penetraciones del atacante.

```powershell
# R de Zaahen rango 3 contra un objetivo con 150 de armadura y 50 de RM
.\.venv\Scripts\python.exe -m lol_knowledge ability --champion Zaahen --level 16 `
  --ability R --rank 3 --item 3036 --target-armor 150 --target-mr 50

# Borde de la E contra Ahri nivel 16 con Botas blindadas; la R aprendida aporta su penetración
.\.venv\Scripts\python.exe -m lol_knowledge ability --champion Zaahen --level 16 `
  --ability E --rank 5 --case edge --learned R=3 --item 3036 `
  --target-champion Ahri --target-level 16 --target-item 3047 --json
```

- **Objetivo:** a mano (`--target-armor`, `--target-mr` y, si una fórmula lo pide, `--target-max-health`) o como campeón (`--target-champion`, `--target-level`, `--target-item`), resuelto con la misma hoja de estadísticas. No se pueden mezclar.
- **Penetración:** el daño físico usa la penetración de armadura y la letalidad del atacante; el mágico, la penetración mágica porcentual y plana; el verdadero no se mitiga.
- **Pasivas de habilidad:** `--learned SLOT=RANK` declara otras habilidades aprendidas (la R de Zaahen da penetración aunque se lance la E). La habilidad lanzada cuenta como aprendida a su rango.
- **Casos:** sin `--case` se muestran todos (por ejemplo, tajo y borde de la E); el total es por caso.
- La etiqueta final es la más débil de las entradas; el informe lista lo que el kit no modela.

Códigos de salida: `0` cálculo hecho, `2` petición inválida, dato ausente o campeón sin kit.

## Rotaciones

`rotation` evalúa pasos en orden contra un objetivo: ataques básicos (`attack`, `attack:crit`) con el daño al impactar de los objetos del atacante, y casos de habilidad (`Q`, `E.edge`…). Cada parte se mitiga y después se multiplica por los aumentos de daño del atacante (Verdugo de gigantes) y las reducciones de los objetos del objetivo (Placas, Adaptabilidad). La vida actual del objetivo baja paso a paso, así que Filo de la niebla lee la vida que dejaron los pasos anteriores.

```powershell
# Zaahen nivel 16 con Hoja del rey arruinado, lord Dominik y Filo infinito contra Ahri
.\.venv\Scripts\python.exe -m lol_knowledge rotation --champion Zaahen --level 16 `
  --learned Q=5 --learned W=3 --learned E=5 --learned R=3 `
  --item 3153 --item 3036 --item 3031 --attacker-range melee `
  --steps "attack, Q.first_hit, attack:crit, E.edge, R" `
  --target-champion Ahri --target-level 16 --target-item 3047 --target-item 3143
```

- **Pasos:** `attack`, `attack:crit`, `attack:nospellblade` (también `attack:crit:nospellblade`), `SLOT` o `SLOT.caso`, separados por comas o espacios. Con un objeto de Hoja encantada, el primer ataque tras una habilidad se potencia solo ([regla](lol-knowledge/mechanics/spellblade.md)); `nospellblade` lo evita.
- **Línea de tiempo (`--timeline`):** cada paso recibe un momento; los ataques se separan por 1 / velocidad de ataque, las habilidades son instantáneas, lanzar una en enfriamiento es un error y `wait:<segundos>` avanza el reloj. Las quemaduras hacen su daño a lo largo del tiempo y se reinician al volver a aplicarlas; los efectos con duración (marca de Tonada sanguina, letalidad de la Ciclovoltaica, Fuego negro, reducción de resistencia mágica de Malignidad) solo se aplican aquí, igual que la Ráfaga de Yun Tal, la caducidad de las acumulaciones de Kraken y Rompecascos y la ventana de 10 s de Hoja encantada. El informe añade la duración y el daño por segundo ([regla](lol-knowledge/mechanics/timeline.md)). Una habilidad con varios casos exige elegir uno, y su rango sale de `--learned`.
- **Acumulaciones de combate:** las temporales (Guinsoo, El final, Liandry, Disfraz encantado) empiezan en 0 y se calculan paso a paso; con `--timeline` caducan y crecen por segundos. Solo las permanentes (crítico de Yun Tal) se toman al máximo ([regla](lol-knowledge/mechanics/combat-stacks.md)).
- **Crítico:** multiplicador base del registro del cliente (`critdamagemultiplier`, 2,0 desde el parche 26.1) más el daño crítico adicional de los objetos. No hay valor esperado: cada paso dice si critica.
- **Datos que no se adivinan:** cuerpo a cuerpo o a distancia (`--attacker-range`, lo pide Filo de la niebla), el tipo de un objetivo manual (`--target-kind`) y su vida adicional (`--target-bonus-health`, lo pide Verdugo de gigantes). La rotación exige la vida del objetivo.
- **Lo no aplicado se lista:** efectos no evaluables, de otro tipo o de estadística porcentual (Rabadon). Si pueden cambiar el daño, el resultado queda `Pendiente de verificación`. También queda pendiente si un objeto usado no tiene todos sus efectos revisados (`effect_review` distinto de `complete`).
- **Curación:** con robo de vida u omnivampirismo, cada parte informa la curación que da su daño final (`heal:`), y cada paso y el total la suman (`step heal`, `total heal`; en JSON, `healing` con su etiqueta). El robo de vida cura con los ataques y con el daño al impactar que el catálogo declara (`applies_life_steal`); el omnivampirismo, con todo. Es la curación que genera el daño: no se limita a la vida que le falta al atacante. Una habilidad con omnivampirismo pide `--target-kind`.
- **Recursos y costes:** cada habilidad descuenta su coste oficial de Data Dragon (maná o energía) o el declarado en `kit.json` (incluido coste de vida con suelo en 1 de vida); las reactivaciones no vuelven a pagar coste. Lanzar sin recurso suficiente es un error (`--allow-insufficient-resource` calcula con tope en 0 y etiqueta `Pendiente de verificación`). La reserva inicial se ajusta con `--attacker-resource` o `--input attacker_resource_percent`; en `--timeline` se acumula la regeneración pasiva y los tics de 5 s de Banda de maná, y en cualquier rotación se aplican Segador de esencia (`3508`) y Claridad mental (`8009`) ([regla](lol-knowledge/mechanics/resources.md)).
- Reglas: [ataques y daño al impactar](lol-knowledge/mechanics/basic-attacks-and-on-hit.md), [impacto crítico](lol-knowledge/mechanics/critical-strike.md), [modificadores de daño](lol-knowledge/mechanics/damage-modifiers.md), [robo de vida y omnivampirismo](lol-knowledge/mechanics/life-steal-and-omnivamp.md), [supervivencia](lol-knowledge/mechanics/survival.md), [recursos y costes](lol-knowledge/mechanics/resources.md).

Códigos de salida: `0` cálculo hecho, `2` petición inválida, dato ausente o campeón sin kit.

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
- Kits de campeón (`lol-knowledge/champions/<Id>/kit.json`): esquema, fórmulas, campeón del directorio y rangos máximos frente a Data Dragon.
- Runas del cliente (`lol-knowledge/derived/runes.json`): esquema, parche, referencias entre árboles, filas y runas, y árboles, filas e ids iguales a los de Data Dragon.
- Grupos de objetos del cliente (`lol-knowledge/derived/item-groups.json`): esquema, enlaces a grupos existentes, parche igual al del snapshot y cobertura de los objetos del catálogo.

Códigos de salida: `0` todo coherente, `1` violaciones (se listan con archivo y motivo), `2` problema de entorno. Si `lol-knowledge/` aún no existe, las comprobaciones de enlaces y referencias se informan como omitidas, no como superadas.

Los checksums dependen de los bytes exactos: `.gitattributes` fija `eol=lf` para que cualquier checkout use LF.

## Aviso legal

Este proyecto es una base de conocimiento no comercial. Incluye datos oficiales de Data Dragon y valores derivados de los datos del cliente, marcados `Derivado`: los de Zaahen, de los archivos del cliente 16.20 publicados por CommunityDragon; los de Ahri, los registros de estadísticas de los 173 campeones ([`champion-records.json`](lol-knowledge/derived/champion-records.json)) y los efectos de los objetos ([`item-effects.json`](lol-knowledge/derived/item-effects.json)), del cliente instalado (16.22 para los kits, 16.23 para los registros y los objetos), leído con `research/binmodel`. No se redistribuyen archivos originales del cliente.

> LoL-Knowledge isn't endorsed by Riot Games and doesn't reflect the views or opinions of Riot Games or anyone officially involved in producing or managing Riot Games properties. Riot Games, and all associated properties are trademarks or registered trademarks of Riot Games, Inc.

Condiciones de uso y cuestiones pendientes: [`research/evidence/usage-conditions.md`](research/evidence/usage-conditions.md).

## Limitaciones conocidas

- No hay integración con la Riot API ni claves de API.
- No hay estadísticas comunitarias (tasa de victorias, builds populares); están excluidas bajo cualquier condición (DEC-05). Los valores derivados del cliente se marcan `Derivado` y llevan atribución.
- Data Dragon (16.20.1, 16.22.1 y 16.23.1) publica `attackdamageperlevel = 0` para todos los campeones. Se sustituye por el crecimiento del cliente 16.23, `Derivado` porque cliente y snapshot coinciden. Senna no tiene el campo en el bin y su DA queda bloqueado por encima del nivel 1.
- La hoja de estadísticas aplica los fragmentos y las runas menores de estadísticas, pero no las piedras angulares, las runas menores de combate ni las pasivas de campeón; de los efectos de objeto solo aplica los de estadística permanentes (`always`) y las acumulaciones permanentes al máximo. Antes de calcular comprueba que los objetos puedan llevarse a la vez (ver «Legalidad de la build»).
- `ability` calcula un lanzamiento sin efectos de objeto ni tiempo; para críticos, efectos de objeto y tiempo está `rotation`, cuya línea de tiempo (`--timeline`) separa los ataques por la velocidad de ataque, respeta los enfriamientos y aplica los efectos con duración. No hay tiempos de lanzamiento, animaciones ni viaje de proyectiles. Ninguno de los dos admite reducciones de resistencia de habilidades ni escudos; `rotation` informa la curación por robo de vida y omnivampirismo, pero no la vida del atacante ni los costes de maná. Solo Zaahen y Ahri tienen kit.
- El núcleo de mitigación trata una instancia; `rotation` añade críticos y modificadores porcentuales de daño. No se modelan escudos, reducciones planas de daño, la penetración de armadura adicional ni el redondeo del juego.
- Data Dragon no publica valores numéricos de las habilidades de Zaahen; los valores derivados están documentados y las discrepancias abiertas siguen como pendientes.
- La cobertura de campeones empieza por un caso representativo y crece de forma incremental.
- El modelo de objetos tiene las estadísticas de los 218 objetos comprables de la Grieta, generadas desde la descripción con `python -m lol_knowledge.objects --generate-stats`; los efectos solo están curados en 42 objetos, y una rotación con un objeto sin efectos revisados queda `Pendiente de verificación`. Las cifras que Data Dragon no publica solo se incorporan con una fuente citada: la wiki (`secondary`) y, cuando coinciden, los datos del cliente 16.23 (`corroborated`). Lo no verificado se marca como desconocido o parcial, no se inventa.

## Flujo de trabajo

Las reglas de ramas, commits, pruebas y etiquetado de fuentes están en [`AGENTS.md`](AGENTS.md).

Lo que falta para terminar el proyecto, con prioridades y el orden propuesto, está en [`odd/roadmap.md`](odd/roadmap.md).
