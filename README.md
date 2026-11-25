# LoL-Knowledge

Base de conocimiento verificable de League of Legends: datos oficiales de Riot (Data Dragon), análisis con fuente declarada y una CLI en Python que ingesta, valida y calcula de forma reproducible.

Estado actual: **Motor v1.0 (`1.0.0`, parche `16.23.1`)**. Existen la ingesta, el validador de integridad, **los 173 campeones del plantel con kit calculable** (`lol-knowledge/champions/<Id>/kit.json`, 100 % de `CH-01`), **134/173 pasivas automatizadas**, **135/173 campeones con habilidades defensivas, curaciones, purgas/inmunidades y esteroides activos (`309` efectos)**, **112/173 campeones con bloqueos por control de masas (`154` `cc_effects`)**, **218/218 objetos comprables de la Grieta** con revisión completa (`effect_review: complete`), **62/62 runas y 9/9 fragmentos**, **9/9 hechizos de invocador**, los **3 elixires de la Grieta** y la **mejora de obra maestra de Ornn** (`OrnnP.DataValues` `16.23`). El motor expone `stats`, `ability`, `rotation` (con `--timeline` y ventanas `--window`), `survive`, `duel` (simulador 1v1 acoplado determinista con CC, tenacidad, purgas y estasis), `optimize` (búsqueda determinista con `--purchase-curve`, `--gold-checkpoints`, rotación automática y `--ornn-upgrade`), contrato JSON `lol-knowledge-contract/1` (`contract`) y servidor MCP local sobre `stdio` (`mcp`).

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
| `src/lol_knowledge/` | CLI, hoja de estadísticas (`stats/`), kits (`kit/`), fórmulas (`formula/`), daño (`damage/`), objetos (`objects/`), rotaciones (`rotation.py`), supervivencia (`defense.py`), duelo 1v1 (`duel.py`), elixires/Ornn (`upgrades.py`), optimizador (`optimizer/`), contrato JSON (`contract.py`) y servidor MCP (`mcp_server.py`) |
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
| `python -m lol_knowledge rotation` | Disponible (secuencia de ataques, habilidades y hechizos con tiempo, ventanas `--window`, recursos, supervivencia y efectos de objeto) |
| `python -m lol_knowledge survive` | Disponible (simulación defensiva inversa: daño recibido, escudos reactivos, reducción plana y tiempo hasta morir) |
| `python -m lol_knowledge duel` | Disponible (simulador determinista de duelo 1v1 acoplado con CC, tenacidad, purgas, defensivos, hechizos y estasis) |
| `python -m lol_knowledge optimize` | Disponible (optimizador determinista de builds legales con curva de compra `--purchase-curve`, `--gold-checkpoints`, rotación automática y `--ornn-upgrade`) |
| `python -m lol_knowledge contract` | Disponible (contrato JSON único `lol-knowledge-contract/1` para capa de IA) |
| `python -m lol_knowledge mcp` | Disponible (servidor MCP local JSON-RPC 2.0 sobre `stdio`) |

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

`stats`, `ability`, `rotation`, `survive`, `duel` y `optimize` comprueban que los objetos del atacante y, si lo hay, del campeón objetivo quepan en un inventario: 6 huecos más el del abalorio, un objeto legendario de cada, un par de botas, los grupos exclusivos del cliente (Últimas palabras, Salvavidas, Lágrima, Hidras, Hoja encantada…), máximo 1 elixir activo (`--elixir`, 0 huecos) y máximo 1 objeto completado no-botas mejorado por Ornn (`--ornn-item` / `--ornn-upgrade`, `DEC-03`). Los límites salen del cliente ([`lol-knowledge/derived/item-groups.json`](lol-knowledge/derived/item-groups.json), `Derivado`) y la regla está en [`lol-knowledge/mechanics/build-legality.md`](lol-knowledge/mechanics/build-legality.md).

- Una build ilegal sale con código `2` y la lista de violaciones. `--allow-illegal-build` calcula igualmente y las escribe como aviso en la salida de errores.
- Las notas (un objeto sin `maxStack` en el bin, datos de otro parche, un objeto de campeón sin saber quién lo lleva) también van a la salida de errores.

## Runas y fragmentos

`stats`, `ability`, `rotation`, `survive`, `duel` y `optimize` aceptan una página completa: `--rune` seis veces (piedra angular, tres runas del árbol principal y dos del secundario) y `--shard` tres veces (ataque, flexible, defensa), además de `--target-rune` / `--target-shard` para el campeón objetivo o defensor. Los datos salen del cliente ([`lol-knowledge/derived/runes.json`](lol-knowledge/derived/runes.json), `Derivado`, comprobado contra Data Dragon) y la regla está en [`lol-knowledge/mechanics/runes.md`](lol-knowledge/mechanics/runes.md).

```powershell
# Ahri con Electrocutar / Brujería y dos fragmentos adaptables
.\.venv\Scripts\python.exe -m lol_knowledge stats --champion Ahri --level 11 --item 3089 `
  --rune 8112 --rune 8143 --rune 8137 --rune 8106 --rune 8226 --rune 8210 `
  --shard 5008 --shard 5008 --shard 5001
```

- La página debe ser legal (código 2 si no; `--allow-illegal-build` la calcula con aviso).
- **62 de 62 runas y 9 de 9 fragmentos modelados:** los fragmentos y runas menores de estadísticas se aplican en la hoja (la fuerza adaptable elige DA o PH según los objetos; en un empate decide el campeón, `Pendiente de verificación`); las piedras angulares y runas menores de combate, supervivencia y recursos se evalúan en `rotation`, `survive` y `duel` (incluida *Inquebrantable* `8242` bajo CC en duelos); y las runas estrictamente de visión, oro, abalorios o utilidad fuera de combate se anotan sin debilitar el cálculo.

## Kits de campeón

Los **173 campeones** del snapshot `16.23.1` tienen kit calculable (`lol-knowledge/champions/<Id>/kit.json`, esquema `lol-champion-kit/1`). Cada kit describe el daño de cada habilidad como *casos* alternativos con *partes* de daño (fórmula, tipo, etiqueta y fuente), estadísticas pasivas, efectos activos defensivos/esteroides (`active_effects`) y controles de masas (`cc_effects`). Las fórmulas usan el evaluador compartido con `by_rank` (valor por rango), `by_level` e `input` (dato del escenario, nunca 0 por defecto salvo que el campo declare `default: 0`).

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
- Hay **173 kits publicados** (100 % del plantel del snapshot `16.23.1`, completados en `CH-01` y `CH-04` con `EffectValue`, tramos `level1=0`, escalados por maná/crítico/letalidad/velocidad de movimiento/velocidad de ataque, acumuladores `--input` con `default: 0`, casos multiforma y las reglas especiales de hoja y rotación de Bel'Veth, Zeri, Jhin, Graves, Sion, Ashe y Cassiopeia).

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

- **Pasos:** `attack`, `attack:crit`, `attack:nospellblade` (también `attack:crit:nospellblade`), `SLOT`, `SLOT.caso` o `SLOT.caso@<N>` (número de objetivos para ese paso), separados por comas o espacios. Con `--target-count <N>`, cada caso de habilidad golpea hasta `max_targets` objetivos (o todos los `N` si declara `aoe: true` sin tope, con `secondary_damage_ratio` sobre los `targets_hit - 1` secundarios), mientras la vida, el escudo y las ejecuciones siguen el daño recibido por el objetivo principal (`primary_total`). Con un objeto de Hoja encantada, el primer ataque tras una habilidad se potencia solo ([regla](lol-knowledge/mechanics/spellblade.md)); `nospellblade` lo evita.
- **Línea de tiempo (`--timeline`):** cada paso recibe un momento; los ataques se separan por 1 / velocidad de ataque, las habilidades son instantáneas, lanzar una en enfriamiento es un error y `wait:<segundos>` avanza el reloj. Las quemaduras hacen su daño a lo largo del tiempo y se reinician al volver a aplicarlas; los efectos con duración (marca de Tonada sanguina, letalidad de la Ciclovoltaica, Fuego negro, reducción de resistencia mágica de Malignidad) solo se aplican aquí, igual que la Ráfaga de Yun Tal, la caducidad de las acumulaciones de Kraken y Rompecascos y la ventana de 10 s de Hoja encantada. El informe añade la duración y el daño por segundo ([regla](lol-knowledge/mechanics/timeline.md)). Una habilidad con varios casos exige elegir uno, y su rango sale de `--learned`.
- **Acumulaciones de combate:** las temporales (Guinsoo, El final, Liandry, Disfraz encantado) empiezan en 0 y se calculan paso a paso; con `--timeline` caducan y crecen por segundos. Solo las permanentes (crítico de Yun Tal) se toman al máximo ([regla](lol-knowledge/mechanics/combat-stacks.md)).
- **Crítico:** multiplicador base del registro del cliente (`critdamagemultiplier`, 2,0 desde el parche 26.1) más el daño crítico adicional de los objetos. No hay valor esperado: cada paso dice si critica.
- **Datos que no se adivinan:** cuerpo a cuerpo o a distancia (`--attacker-range`, lo pide Filo de la niebla), el tipo de un objetivo manual (`--target-kind`) y su vida adicional (`--target-bonus-health`, lo pide Verdugo de gigantes). La rotación exige la vida del objetivo.
- **Lo no aplicado se lista:** cualquier efecto `excluded` o `partially_evaluable` de un objeto o mecánica no modelada del kit se reporta explícitamente; si puede afectar al daño, el resultado queda marcado como `Pendiente de verificación`.
- **Curación:** con robo de vida u omnivampirismo, cada parte informa la curación que da su daño final (`heal:`), y cada paso y el total la suman (`step heal`, `total heal`; en JSON, `healing` con su etiqueta). El robo de vida cura con los ataques y con el daño al impactar que el catálogo declara (`applies_life_steal`); el omnivampirismo, con todo. Es la curación que genera el daño: no se limita a la vida que le falta al atacante. Una habilidad con omnivampirismo pide `--target-kind`.
- **Recursos y costes:** cada habilidad descuenta su coste oficial de Data Dragon (maná o energía) o el declarado en `kit.json` (incluido coste de vida con suelo en 1 de vida); las reactivaciones no vuelven a pagar coste. Lanzar sin recurso suficiente es un error (`--allow-insufficient-resource` calcula con tope en 0 y etiqueta `Pendiente de verificación`). La reserva inicial se ajusta con `--attacker-resource` o `--input attacker_resource_percent`; en `--timeline` se acumula la regeneración pasiva y los tics de 5 s de Banda de maná, y en cualquier rotación se aplican Segador de esencia (`3508`) y Claridad mental (`8009`) ([regla](lol-knowledge/mechanics/resources.md)).
- **Elixires y mejoras de Ornn (`OBJ-12`):** `stats`, `ability`, `rotation`, `survive` y `duel` aceptan `--elixir <2138|2139|2140>` (0 huecos, máximo 1) y `--ornn-item <id>` (mejora exacta de obra maestra de `1000 g` sobre un único objeto completado no-botas, `OrnnP.DataValues` `16.23`). En `optimize`, `--ornn-upgrade` selecciona automáticamente el único objeto de cada build cuya mejora maximiza el objetivo.
- **Ventanas de tiempo (`--window`):** en `rotation --timeline`, `--window <segundos>` (repetible) informa el daño exacto acumulado (`primary`/`secondary`), DPS, curación y vida restante en `[0, W]` s, prorrateando quemaduras continuas.
- **Duelo 1v1 (`duel`) y optimizador (`optimize`):** `duel` ejecuta un combate 1v1 acoplado sobre reloj exacto `Fraction` con bloqueos de CC, tenacidad (suelo `0,3 s`), purgas, inmunidades, defensivos y estasis ([`duel.md`](lol-knowledge/mechanics/duel.md)); `optimize` busca builds legales deterministas por daño, DPS, vida efectiva, supervivencia, curación o duelo 1v1, con rotación automática si se omite `--steps`, curva de compra paso a paso (`--purchase-curve`) y puntos de control de oro (`--gold-checkpoints`) ([`engine-v1.md`](odd/tasks/engine-v1.md)).
- Reglas: [ataques y daño al impactar](lol-knowledge/mechanics/basic-attacks-and-on-hit.md), [impacto crítico](lol-knowledge/mechanics/critical-strike.md), [modificadores de daño](lol-knowledge/mechanics/damage-modifiers.md), [robo de vida y omnivampirismo](lol-knowledge/mechanics/life-steal-and-omnivamp.md), [supervivencia](lol-knowledge/mechanics/survival.md), [recursos y costes](lol-knowledge/mechanics/resources.md), [duelo 1v1](lol-knowledge/mechanics/duel.md).

Códigos de salida: `0` cálculo hecho, `2` petición inválida, dato ausente o campeón sin kit.

## Supervivencia (`survive`)

`survive` realiza simulaciones defensivas inversas contra golpes manuales (`--incoming`) o contra una rotación enemiga (`--enemy-champion` + `--steps`), calculando supervivencia, paso letal, `time_to_die`, `damage_taken_per_second`, habilidades defensivas activas (`--defender-cast`), escudos reactivos (Sterak, Fauces, Rookern), reducción plana posmitigación (`8473` Revestimiento de huesos) y reflejo de *Malla de espinas* (`3075`) ([regla](lol-knowledge/mechanics/survival.md)).

```powershell
# Darius nivel 11 con Calibrador de Sterak frente a una rotación de Ahri
.\.venv\Scripts\python.exe -m lol_knowledge survive --champion Darius --level 11 `
  --item 3053 --enemy-champion Ahri --enemy-level 11 --enemy-item 3089 `
  --enemy-learned Q=5 --enemy-learned W=3 --enemy-learned E=1 --enemy-learned R=2 `
  --steps "E, Q.both, W, R.dash" --timeline
```

## Simulador de duelo 1v1 (`duel`)

`duel` ejecuta un combate 1v1 acoplado y determinista sobre reloj exacto `Fraction`, reutilizando `rotation.py` y `defense.py` sin doble conteo ([regla](lol-knowledge/mechanics/duel.md)). Modela ataques, habilidades ofensivas y defensivas (`135/173` campeones), bloqueos por control de masas (`112/173` campeones, `154` `cc_effects`), tenacidad con suelo de `0,3 s` (`airborne`/`suppression` inmunes), purgas (*Limpiar*, QSS, campeones), inmunidades a CC, escudo de hechizos, hechizos de invocador, quemaduras, reflejo de *Malla de espinas* y estasis de *Ángel de la guarda*.

```powershell
# Duelo 1v1 Darius vs Garen a nivel 11
.\.venv\Scripts\python.exe -m lol_knowledge duel `
  --a-champion Darius --a-level 11 --a-item 3078 --a-range melee `
  --a-learned Q=5 --a-learned W=1 --a-learned E=3 --a-learned R=2 --a-steps "E, attack, W, Q.blade, R" `
  --b-champion Garen --b-level 11 --b-item 3078 --b-range melee `
  --b-learned Q=5 --b-learned W=1 --b-learned E=3 --b-learned R=2 --b-steps "Q, E, R"
```

## Optimizador de builds (`optimize`)

`optimize` busca builds legales deterministas (relevancia marginal + *beam search* + refinamiento *1-swap*) separando estrictamente `verified_builds` (`Oficial`/`Derivado`) de `pending_builds` (`Pendiente de verificación`). Admite 8 objetivos (`rotation_damage`, `dps`, `effective_health_physical`, `effective_health_magic`, `effective_health_mixed`, `time_to_die`, `healing` y `duel`), rotación automática si se omite `--steps` (`OPT-05`), curva de compra paso a paso (`--purchase-curve`), puntos de control de oro (`--gold-checkpoints`), elixires (`--elixir`) y selección automática del mejor objeto para la mejora de obra maestra de Ornn (`--ornn-upgrade`, `DEC-03`) ([`engine-v1.md`](odd/tasks/engine-v1.md)).

```powershell
# Mejor build de 3 objetos para Ahri con curva de compra, checkpoints de oro y mejora de Ornn
.\.venv\Scripts\python.exe -m lol_knowledge optimize --champion Ahri --level 11 `
  --objective rotation_damage --slots 3 --attacker-range ranged `
  --learned Q=5 --learned W=3 --learned E=1 --learned R=2 `
  --target-armor 60 --target-mr 45 --target-max-health 1800 --target-kind champion `
  --ornn-upgrade --purchase-curve --gold-checkpoints 3500,7000
```

## Contrato JSON y servidor MCP local (`contract` / `mcp`)

Para conectar asistentes de IA sin cálculo mental, el proyecto expone un contrato JSON único versionado (`lol-knowledge-contract/1` vía `python -m lol_knowledge contract`) y un servidor **MCP local JSON-RPC 2.0 sobre `stdio`** sin dependencias externas (`python -m lol_knowledge mcp`) con 7 herramientas (`lol_lookup`, `lol_stats`, `lol_ability`, `lol_rotation`, `lol_survive`, `lol_duel`, `lol_optimize`), 2 prompts y 2 recursos ([`lol-knowledge/ai-layer.md`](lol-knowledge/ai-layer.md)).

```json
{
  "mcpServers": {
    "lol-knowledge": {
      "command": "C:\\Users\\Yisus\\Documents\\LoL-Knowledge\\.venv\\Scripts\\python.exe",
      "args": ["-m", "lol_knowledge", "mcp", "--root", "C:\\Users\\Yisus\\Documents\\LoL-Knowledge"]
    }
  }
}
```

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

Este proyecto es una base de conocimiento no comercial. Incluye datos oficiales de Data Dragon y valores derivados de los datos del cliente, marcados `Derivado`: los de Zaahen, de los archivos del cliente 16.20 publicados por CommunityDragon; los de Ahri, los 171 kits de las oleadas 1 a 4 (`CH-01`), los registros de estadísticas de los 173 campeones ([`champion-records.json`](lol-knowledge/derived/champion-records.json)) y los efectos de los objetos ([`item-effects.json`](lol-knowledge/derived/item-effects.json)), del cliente instalado (16.22 para Ahri, 16.23 para las oleadas 1–4, los registros y los objetos), leído con `research/binmodel`. No se redistribuyen archivos originales del cliente.

> LoL-Knowledge isn't endorsed by Riot Games and doesn't reflect the views or opinions of Riot Games or anyone officially involved in producing or managing Riot Games properties. Riot Games, and all associated properties are trademarks or registered trademarks of Riot Games, Inc.

Condiciones de uso y cuestiones pendientes: [`research/evidence/usage-conditions.md`](research/evidence/usage-conditions.md).

## Limitaciones conocidas

- No hay integración con la Riot API ni claves de API.
- No hay estadísticas comunitarias (tasa de victorias, builds populares); están excluidas bajo cualquier condición (DEC-05). Los valores derivados del cliente se marcan `Derivado` y llevan atribución.
- Data Dragon (16.20.1, 16.22.1 y 16.23.1) publica `attackdamageperlevel = 0` para todos los campeones. Se sustituye por el crecimiento del cliente 16.23, `Derivado` porque cliente y snapshot coinciden. Senna no tiene el campo en el bin y su DA queda bloqueado por encima del nivel 1.
- La hoja de estadísticas (`stats`) aplica los fragmentos, las runas menores de estadísticas, las pasivas de campeón de tipo estadística/acumulación (`--input`), los elixires (`--elixir`), la mejora de Ornn (`--ornn-item`) y los efectos de objeto permanentes (`always`) o con acumulaciones permanentes al máximo; las piedras angulares y efectos de combate se evalúan en `rotation`, `survive` y `duel`. Antes de calcular comprueba la legalidad de la build (ver «Legalidad de la build»).
- `ability` calcula un lanzamiento sin efectos de objeto ni tiempo; para críticos, efectos de objeto, costes, recursos, escudos, curación, ventanas `--window` y tiempo está `rotation`, y para combates acoplados con CC, tenacidad, purgas y defensivos está `duel`. No hay tiempos de lanzamiento, animaciones, geometría espacial ni viaje de proyectiles. Los 173 campeones tienen kit calculable (`CH-01` completo); sus huecos declarados figuran en cada `not_modelled`.
- El núcleo `damage` trata una instancia aislada; `rotation`, `survive` y `duel` añaden críticos, escudos, reducciones planas y modificadores porcentuales de daño. No se modelan la penetración de armadura adicional ni el redondeo visual del juego.
- Data Dragon no publica valores numéricos de las habilidades de Zaahen; los valores derivados están documentados y las discrepancias abiertas siguen como pendientes.
- El modelo de objetos cubre los **218 objetos comprables de la Grieta** con revisión completa (`effect_review: complete`), además de los 3 elixires y la mejora de obra maestra de Ornn. Las cifras que Data Dragon no publica solo se incorporan con una fuente citada: la wiki (`secondary`) y, cuando coinciden, los datos del cliente 16.23 (`corroborated`). Lo no verificado se marca como desconocido o parcial, no se inventa.

## Flujo de trabajo

Las reglas de ramas, commits, pruebas y etiquetado de fuentes están en [`AGENTS.md`](AGENTS.md).

Lo que falta para terminar el proyecto, con prioridades y el orden propuesto, está en [`odd/roadmap.md`](odd/roadmap.md).
