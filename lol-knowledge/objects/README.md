# Modelo mecánico de objetos — `lol-object-model/1`

- **Parche del snapshot:** `16.22.1` (`data/current/manifest.json`). El catálogo se creó sobre 16.20.1; en 16.22.1 las estadísticas, el oro, las descripciones y las recetas de los 15 objetos son idénticos en Data Dragon (comprobado el 2026-11-15). Las notas de parche 26.21 y 26.22 no tocan ninguno de los 15 objetos, y las cifras secundarias se han contrastado con los datos del cliente 16.22 ([informe](../../research/reports/item-data-values-16.22.md)). Las Botas de mercurio (3111) y las Flechas de los Yun Tal (3032) se añadieron el 2026-11-16 directamente desde 16.22.1.
- **Fuente:** Data Dragon (`https://ddragon.leagueoflegends.com`), locale `es_ES`.
- **Fecha de consulta:** 2026-10-20.
- **Estado:** estadísticas de los **218 objetos comprables de la Grieta del Invocador** (generadas); efectos curados en 42 objetos (64 efectos). Los efectos de los demás objetos **no** están modelados (`effect_review: pending`).
- **Versión del catálogo:** `catalog_version: 14` (esquema `1`; la 3 solo cambió el parche; la 4 añade `subject: target` explícito a la vida actual de Filo de la niebla, para que el motor de rotaciones la lea del objetivo sin depender de la convención implícita; la 5 añade los datos del cliente 16.22 como fuente `client_data` y corrige la ralentización a distancia de Zarpazo sombrío; la 6 añade `applies_life_steal` a los componentes de daño y lo declara en Filo de la niebla; la 7 añade las Botas de mercurio por su tenacidad; la 8 traslada las estadísticas de la descripción al archivo generado; la 9 añade las Flechas de los Yun Tal, el disparador `on_attack`, el escenario `max_stacks` y los ceros confirmados; la 10 añade el daño al impactar de cinco objetos, la evidencia `derived` y la aplicación en la hoja de los efectos `always` de estadísticas; la 11 añade Hoja encantada (disparador `spellblade`), el componente `repeat_on_hit` y las notas de parche como fuente; la 12 añade los contadores de ataques, el Vigor, las fórmulas `by_level` y la condición `target_is_structure`; la 13 añade la vida que le falta al objetivo, los umbrales de vida, `damage_types` y la ejecución; la 14 añade las quemaduras, el disparador `cast` para ellas, la condición `ultimate_ability` y los amplificadores de daño con el escenario `max_stacks`).
- **Código:** [`src/lol_knowledge/objects/`](../../src/lol_knowledge/objects/).
- **Catálogo curado (efectos y revisión):** [`catalog.json`](catalog.json).
- **Estadísticas generadas:** [`catalog-stats.json`](catalog-stats.json), con `src/lol_knowledge/objects/generate.py`. No se edita a mano: `validate` lo regenera y falla si no coincide.
- **Datos de efectos del cliente (`Derivado`):** [`../derived/item-effects.json`](../derived/item-effects.json): valores, cálculos, variantes cuerpo a cuerpo / distancia y textos es_ES de los 218 objetos ([informe](../../research/reports/item-effects-16.22.md)). Es la fuente de cifras para curar efectos; no los modela. `validate` comprueba su forma, que su versión coincida con el snapshot y que cubra los 218 objetos del archivo generado.
- **Auditoría previa del extractor:** [`research/reports/agent-d-extractor-audit.md`](../../research/reports/agent-d-extractor-audit.md).
- **Evidencia de esta fase:** [`research/reports/object-mechanics-2026-10-20.md`](../../research/reports/object-mechanics-2026-10-20.md).

Este documento explica el esquema, las decisiones, lo que está modelado y lo que no. El JSON es el contrato; este Markdown es la justificación y el inventario de límites.

## 1. Qué resuelve y qué no

Resuelve: representar de forma versionada y verificable la identidad, las estadísticas y los efectos de un objeto, distinguiendo lo que Data Dragon publica de forma estructurada, lo que solo aparece en prosa y lo que no se sabe.

Las rotaciones con sus efectos evaluables se calculan con `python -m lol_knowledge rotation` (ver el README del repositorio). No resuelve todavía: buscar builds, simular tiempo, modelar todos los objetos ni interpretar efectos que dependen de estado del juego no publicado. Tampoco convierte una fuente secundaria en oficial: cada cifra externa conserva su cita y su nivel de confianza.

## 2. Ejecutar

```powershell
# Validar el catálogo (también lo hace `lol_knowledge validate`)
.\.venv\Scripts\python.exe -m lol_knowledge.objects --validate

# Ver el resumen de la muestra
.\.venv\Scripts\python.exe -m lol_knowledge.objects

# Ver el modelo canónico completo y determinista
.\.venv\Scripts\python.exe -m lol_knowledge.objects --json
```

El modelo canónico no contiene timestamps ni rutas absolutas. Dos ejecuciones sobre el mismo snapshot y catálogo producen los mismos bytes.

```powershell
# Regenerar las estadísticas de la descripción tras actualizar el snapshot
.\.venv\Scripts\python.exe -m lol_knowledge.objects --generate-stats
```

### 2.1 Estadísticas generadas (`catalog-stats.json`, desde 2026-11-16)

- **Selección:** objetos con `maps['11']` verdadero, `gold.purchasable` verdadero e id numérico de hasta 4 cifras; los de más cifras son variantes de otros modos (ARAM, Arena…). En 16.22.1 son 218.
- **Lectura:** cada línea del bloque `<stats>` de la descripción («10 de letalidad», «30% de tenacidad») se traduce con una tabla de frases `es_ES` a una estadística canónica y se guarda con su cita literal. Una línea que no encaje es un error, no se omite.
- **Lo que Data Dragon ya trae en `stats`** no se duplica, pero el generador comprueba que el número de la descripción coincida (en 16.22.1 coinciden todos).
- **Un `0` no es un cero real por defecto:** Data Dragon usa `0` para cantidades no publicadas. La línea se guarda como `status: unknown` y la hoja la trata como aporte 0 `Pendiente de verificación`.
- **Cero confirmado (`confirmed_zero_stats`, desde la versión 9):** el objeto curado puede declarar que ese `0` es real, con `id`, `kind` y el motivo. La fusión lo convierte en valor `0` con la nota `confirmed zero: …`, que la hoja muestra como `Oficial`. `validate` falla si el archivo generado no tiene esa línea como `unknown` en ese objeto. Único caso en 16.22.1: Flechas de los Yun Tal, «0% de probabilidad de impacto crítico». El objeto no tiene estadística de crítico (el registro `Items/3032` del cliente 16.22 no tiene campo de crítico, `Derivado`); su crítico viene de la pasiva.
- **Líneas sin estadística del motor** (poder de curaciones y escudos, oro cada 10 s) se guardan en `unmodelled_stats` con el motivo, y el modelo las publica en `unmodelled_description_stats`.
- **Fusión con el catálogo curado:** un objeto curado conserva sus efectos y su `effect_review` y recibe las estadísticas generadas; no puede declararlas también a mano. Un objeto solo generado queda `effect_review: pending` si su descripción tiene `<passive>` o `<active>`, y `complete` si no tiene efectos.

## 3. Esquema `lol-object-model/1`

### 3.1 Documento

```json
{
  "schema_version": 1,
  "kind": "lol-object-model",
  "catalog_version": 2,
  "game_version": "16.20.1",
  "source": {
    "snapshot": "data/current",
    "items_sha256": "32ea85df...",
    "locale": "es_ES",
    "catalog": "lol-knowledge/objects/catalog.json"
  },
  "objects": []
}
```

`game_version` se contrasta con el `patch` del manifiesto. Si el catálogo se curó para otro parche, `validate` falla: no se aplica silenciosamente a una versión distinta.

### 3.2 Objeto

```json
{
  "id": "3153",
  "name": "Hoja del rey arruinado",
  "game_version": "16.20.1",
  "verification": "description_quote_verified",
  "tags": ["AttackSpeed", "Damage", "LifeSteal", "OnHit", "Slow"],
  "stats": [],
  "unmapped_source_stats": [],
  "effects": [],
  "gold": {"total": 3200, "base": 725, "sell": 2240},
  "availability": {
    "purchasable": true,
    "in_store": null,
    "hide_from_all": null,
    "consumed": null,
    "stacks": null,
    "maps": {"11": true, "12": true, "22": false, "30": false, "453": true},
    "map_ids": [11, 12, 453],
    "modes": {"status": "unknown", "reason": "Data Dragon does not encode game modes."},
    "required_champion": null,
    "required_ally": null
  },
  "recipe": {
    "builds_from": [{"id": "1037", "count": 1}, {"id": "1043", "count": 1}, {"id": "1053", "count": 1}],
    "builds_into": [],
    "depth": 3,
    "special_recipe": null
  }
}
```

`null` significa «el campo no está en Data Dragon», no `false` ni cero. `map_ids` deriva de `maps`; `modes` es explícitamente desconocido porque Data Dragon no codifica modos de juego.

### 3.3 Estadísticas

```json
{
  "id": "attack_speed",
  "kind": "percent",
  "value": 25.0,
  "raw_value": 0.25,
  "source": {"kind": "ddragon_stat", "key": "PercentAttackSpeedMod"},
  "verification": "official_field"
}
```

```json
{
  "id": "lethality",
  "kind": "flat",
  "value": 10.0,
  "source": {
    "kind": "ddragon_description",
    "item_id": "3134",
    "quote": "10 de letalidad"
  },
  "verification": "description_quote_verified"
}
```

Decisiones:

- `kind` es `flat` o `percent`. Los porcentajes se normalizan a **puntos porcentuales**: `0.25` de Data Dragon se publica como `25.0`. El valor bruto queda en `raw_value`.
- **Cambio de unidad (desde 2026-11-16):** `FlatHPRegenMod` va por segundo en Data Dragon y el modelo lo publica por cada 5 s (×5), como los campeones y las descripciones. La entrada lleva `unit_conversion` con el motivo, y la hoja de estadísticas trata ese valor como `Derivado`. Ver [Regeneración](../mechanics/regeneration.md).
- `health_regen` y `mana_regen` admiten `flat` (por cada 5 s) y `percent` (porcentaje de la regeneración base, «100% de regeneración de vida básica»).
- Solo se declaran en el catálogo las estadísticas que Data Dragon **no** estructura: letalidad, aceleración de habilidades, penetraciones (porcentuales y plana mágica) y daño crítico adicional. Las planas y porcentuales que sí están en `stats` se derivan y no se repiten.
- `magic_penetration_flat` es una estadística canónica nueva de esta fase (Botas de hechicero). No se confunde con `magic_penetration_percent` (Bastón del Vacío).
- `tenacity` (`kind: percent`) es canónica desde 2026-11-16, por el mismo motivo que `omnivamp`: Data Dragon solo la trae en la descripción. Ver [Tenacidad](../mechanics/tenacity.md).
- `omnivamp` (`kind: percent`) es canónica desde 2026-11-15. Data Dragon no la trae en `stats`, así que solo se declara con la cita de la descripción («omnisucción»). Ver [Robo de vida y omnivampirismo](../mechanics/life-steal-and-omnivamp.md).
- Un valor desconocido se declara con `"value": null`, `"status": "unknown"` y `"reason"`. Un cero real se declara con `"value": 0` y `"status": "declared"`.
- `source.kind` distingue `ddragon_stat` (campo estructurado) de `ddragon_description` (prosa). En el segundo caso la cita debe existir en la descripción normalizada y el número declarado debe aparecer en la cita; `validate` lo comprueba.
- `unmapped_source_stats` conserva cualquier clave de `stats` que el mapa canónico no reconozca. No se descarta en silencio.

### 3.4 Efectos

```json
{
  "id": "time-stop",
  "kind": "active",
  "name": "Tiempo detenido",
  "quote": "Entras en estasis durante 2.5 s.",
  "basis": "description_explicit",
  "trigger": {"event": "cast"},
  "target": {"kind": "self"},
  "conditions": [],
  "components": [
    {
      "kind": "stasis",
      "target": {"kind": "self"},
      "duration_seconds": 2.5
    }
  ],
  "cooldown_seconds": {"status": "unknown", "reason": "Data Dragon does not publish the active cooldown"},
  "stacks": null,
  "duration_seconds": 2.5,
  "limits": [],
  "model_status": "partially_evaluable",
  "derived_status": "partially_evaluable"
}
```

- `kind`: `passive` o `active`.
- `basis`: `description_explicit` (la prosa fija la operación), `description_partial` (faltan ratios o ventanas), `description_silent` (el efecto se reconoce pero la prosa no da fórmula) o `external_evidence_explicit` (la fórmula viene de una fuente declarada, no de la prosa de Data Dragon; exige `sources` y fórmulas evaluables).
- `trigger.event`: `always`, `on_attack` (al atacar, antes de impactar), `on_hit`, `spellblade` (el primer ataque tras una habilidad; [regla](../mechanics/spellblade.md)), `taking_attack`, `damaging_ability`, `on_heal_or_shield`, `cast`, `on_kill`, `periodic` o `unknown`.
- `target.kind`: `self`, `enemy_champion`, `enemy_unit`, `attacker`, `ally_champion`, `area` o `unknown`.
- `conditions`: lista de condiciones declarativas (`target_is_champion`, `damage_source_is_attack`, `critical_strike`, `stacks_at_least`, etc.). No son expresiones ejecutables.
- `cooldown_seconds`, `duration_seconds`, `stacks.window_seconds`: número no negativo, `null` (no aplica) o `{"status": "unknown", "reason": "..."}`.
- `stacks.required` y `stacks.max_stacks` son enteros; la ventana temporal puede ser desconocida. Desde la versión 12, en un efecto `on_hit` u `on_attack`, `stacks.required` = N ≥ 2 significa «cada N ataques» y las rotaciones lo cuentan ([regla](../mechanics/attack-counters.md)).
- Disparador `energized` y componente `trigger_energized` (desde la versión 12): el ataque con Vigor y el Galvanizado de la Espada ciclovoltaica.
- Fórmula `by_level` (desde la versión 12): un valor por nivel del campeón (1 a 18), para los saltos por nivel del cliente (Kraken, ataques luminosos de El final). Sus valores no pasan la comprobación de números en citas: salen de aplicar los saltos del cliente, que sí se citan.
- Desde la versión 13 ([regla](../mechanics/target-health.md)): `scope: missing_fraction` de `health` (con `subject: target`) es la fracción de vida que le falta al objetivo; la condición `target_health_below` lleva `value` (porcentaje de 0 a 100) y las rotaciones la evalúan; un `damage_modifier` puede limitarse con `damage_types`; el componente `execute` lleva como fórmula el umbral en porcentaje de la vida máxima.
- Desde la versión 14 ([regla](../mechanics/burns.md)): componente `burn` (`damage_type`, `duration_seconds` y una fórmula de daño por segundo), con disparador `damaging_ability` o `cast`; condición `ultimate_ability`; el escenario `max_stacks` admite también `damage_modifier` con `direction: dealt`, que aplican las rotaciones (la hoja solo aplica los efectos hechos solo de estadísticas). Las condiciones `target_is_minion` y `target_is_monster` cuentan para no debilitar rotaciones contra otro tipo de objetivo.
- En las citas, los ordinales en español («tercer», «quinto»…) cuentan como números.
- Condición `target_is_structure` (desde la versión 12). En las rotaciones, un efecto no aplicado cuya condición de tipo de objetivo no encaja con el objetivo (`target_is_champion` contra un súbdito, por ejemplo) ya no deja la rotación `Pendiente de verificación`.
- `limits`: topes o umbrales conocidos aunque la curva no lo esté. Ejemplo: el 15 % de Lord Dominik con 1500 de vida adicional.
- `scenario` (opcional, desde la versión 9): supuesto con el que un motor puede aplicar el efecto de forma permanente. Solo existe `max_stacks`: los componentes dan el valor con **todas las acumulaciones**, y la hoja de estadísticas los suma como estadísticas con la nota `scenario: maximum stacks`. Solo admite componentes `stat_modifier` con `mode: flat`, que suman su cantidad en la unidad del catálogo (puntos porcentuales para las estadísticas que son fracción: 25 → 0,25). `rotation` no los vuelve a aplicar: deja una nota `applied by the stat sheet`. Decisión del 2026-11-16: los escenarios se calculan con las acumulaciones al máximo, que es más sencillo aunque sobrestime los primeros compases de la partida.
- **Efectos de estadísticas siempre activos** (desde la versión 10): un efecto con `trigger.event: always`, sin `conditions` y hecho solo de componentes `stat_modifier` también lo aplica la hoja. `flat` suma como en `max_stacks`; `percent` con `scope: total` amplifica el total de una estadística de cantidad (Obra mágica de Rabadon: +30 % del poder de habilidad total) y se aplica al final, sobre el total sin amplificar, sin componerse con otros amplificadores. `rotation` deja la nota `applied by the stat sheet (always)`.
- `model_status` es la clasificación curada; `derived_status` se calcula desde las fórmulas. `validate` impide que `model_status` sea **más optimista** que `derived_status`.
- `sources`: lista opcional de fuentes externas con `kind`, `reference`, `quote`, `retrieved_at`, `confidence` y `note` opcional. Se usa solo para cifras que Data Dragon no publica. La wiki comunitaria se marca `community_wiki` y `secondary`; una fuente comunitaria **no puede** marcarse `official`. Los valores de datos del cliente se marcan `client_data` (`secondary` o `corroborated`, nunca `official`); como el cliente guarda los porcentajes como fracciones, en sus citas el validador acepta también el número multiplicado por 100. `corroborated` exige al menos dos fuentes declaradas.
- Componente `repeat_on_hit` (desde la versión 11): vuelve a aplicar una vez los efectos al impactar de los objetos en ese ataque (Amanecer y anochecer). No lleva fórmula.
- Fuente `patch_notes` (desde la versión 11): notas de parche oficiales, con confianza `official` o `corroborated`. Como las demás fuentes, no hace `official` al efecto (esa etiqueta queda para la descripción de Data Dragon); junto con los datos del cliente da `corroborated`.
- `evidence_confidence`: `official`, `corroborated`, `derived`, `secondary` o `unverified`. `derived` (desde la versión 10) es la cifra leída solo de los datos del cliente: exige una fuente `client_data` (que también puede marcarse `derived`) y da la etiqueta `Derivado`, como pide AGENTS.md para los datos del cliente; antes un único dato del cliente solo podía ser `secondary` (`Pendiente de verificación`). Es independiente de `model_status`: una fórmula puede ser evaluable y, aun así, descansar en una fuente secundaria. `official` solo se admite cuando no hay `sources` (la descripción de Data Dragon es la fuente).
- Regla de números: **cada constante, duración, límite, enfriamiento, contador o ventana de acumulaciones debe aparecer en la descripción de Data Dragon o en la cita de alguna fuente declarada**. El validador rechaza un número huérfano.
- Las fórmulas rechazan claves desconocidas: un `subjet` mal escrito no cae silenciosamente en la convención de campeón.
- `effect_review` del objeto: `complete` si el catálogo modela todos los efectos de la descripción; `partial` si falta alguno; `pending` si no se ha revisado ninguno. El modelo lo conserva y `rotation` deja el resultado `Pendiente de verificación`, con una nota, cuando un objeto del atacante o del objetivo no está en `complete`.
- `verification` del objeto: `official_field` (solo datos estructurados), `description_quote_verified` (prosa oficial) o `secondary_source_verified` (algún efecto usa fuentes externas).

### 3.5 Componentes y fórmulas

Componentes: `damage`, `healing`, `shield`, `stat_modifier`, `damage_modifier`, `crowd_control`, `status`, `stasis`.

Un componente `damage` puede declarar `applies_life_steal`: `{"value": true|false, "source": {…}}`, con una fuente propia del mismo formato que `sources`. Dice si ese daño cura con el robo de vida del portador ([regla](../mechanics/life-steal-and-omnivamp.md)). Si falta, no consta; el motor de rotaciones no lo adivina. Solo Filo de la niebla lo declara (`true`, LoL Wiki, `secondary`).

Los componentes `healing` y `shield` declaran `mode`: `absolute` (la fórmula devuelve la cantidad) o `percent_of_trigger` (la fórmula devuelve el porcentaje de la curación o escudo que disparó el efecto, que es una entrada del motor).

Fórmulas soportadas por el evaluador:

| Operación | Significado |
|---|---|
| `{"op": "constant", "value": 30}` | Constante finita. `0` es un cero real. |
| `{"op": "stat", "stat": "attack_damage", "scope": "bonus"}` | Estadística del campeón u objetivo. |
| `{"op": "percent_of", "percent": 10, "stat": "armor", "scope": "bonus"}` | `percent` por ciento de la estadística. `10` significa 10 %. |
| `{"op": "add", "operands": [...]}` | Suma. |
| `{"op": "mul", "operands": [...]}` | Producto. |
| `{"op": "min", "operands": [...]}` | Mínimo de varios operandos; se usa para topes. |
| `{"op": "by_holder_range", "melee": {...}, "ranged": {...}}` | Elige una rama según `holder_range`; sin valor explícito falla. |
| `{"op": "unknown", "reason": "..."}` | Dato ausente; nunca se sustituye por cero. |
| `{"op": "unsupported", "reason": "...", "needed": [...]}` | Mecánica no modelada. |

Scopes válidos: `base`, `bonus`, `total`, `current` y `max`. `subject` es opcional (`champion` o `target`): sirve para desambiguar estadísticas como `bonus_health` (objetivo) frente a `bonus_armor` (portador). Si se omite, `current`/`max` se interpretan como objetivo y el resto como campeón, que es la convención anterior. La resolución de claves es `total` → `attack_damage`, `bonus` → `bonus_attack_damage`, `current` sobre `health` → `current_health`.

El evaluador, compartido con los kits de campeón en [`src/lol_knowledge/formula/`](../../src/lol_knowledge/formula/) desde el 2026-11-15, evalúa para el catálogo `constant`, `stat`, `percent_of`, `add`, `mul`, `min` y `by_holder_range`, con aritmética exacta. Las operaciones de los kits (`by_rank`, `by_level`, `input`) no se admiten en el catálogo. El modelo generado no cambió con el traslado (comprobado byte a byte). Rechaza con códigos `unknown_input`, `unsupported_formula`, `missing_stat`, `missing_holder_range`, `malformed_formula`, `unsupported_operation` y `depth_exceeded`.

## 4. Decisiones del esquema

1. **El catálogo no duplica lo derivable.** Identidad, nombre, `stats`, `gold`, `maps`, `from`/`into`, `depth`, `in_store`, `hide_from_all`, `consumed`, `stacks`, `special_recipe`, `requiredChampion` y `requiredAlly` se leen de `data/current/items.json`. El catálogo solo aporta lo que Data Dragon no estructura. La excepción documentada es `game_version`: se declara para detectar que el catálogo se aplica a otro parche.
2. **Porcentajes en puntos.** Evita la ambigüedad entre `0.25` y `25`; el valor bruto se conserva.
3. **Recetas como multiconjunto.** Data Dragon repite ids (`from: ["1058", "1058"]`) para exigir dos copias. Por eso `builds_from` es una lista de `{id, count}` y no un conjunto.
4. **Ausente ≠ desconocido ≠ no modelado ≠ cero.** Se representan con `null`/campo ausente, `unknown`, `unsupported`/`excluded` y `constant: 0`, respectivamente.
5. **Procedencia por dato.** Cada estadística y efecto declara `source` y `verification`. Las citas se verifican contra la descripción normalizada del snapshot; los números declarados deben aparecer en la cita.
6. **Estado monotónico.** `model_status` no puede ser más optimista que `derived_status`. Ser más pesimista está permitido y documentado.
7. **Determinismo.** Objetos y estadísticas se ordenan por id canónico; el JSON se serializa con claves ordenadas. El orden de las claves del catálogo no altera el modelo.
8. **Sin red.** Todo se lee del snapshot versionado; las pruebas no descargan nada.
9. **Fuente externa explícita.** Una cifra que no está en Data Dragon solo se admite con `sources[]` citadas y `evidence_confidence` coherente. La wiki se marca `secondary`; nunca se etiqueta como `official_field`.
10. **Sujeto de la estadística.** `subject` desambigua `bonus_health` del objetivo frente a `bonus_armor` del portador. Sin `subject` se conserva la convención anterior.
11. **Rango del portador.** `ChampionState.attack_range` es obligatorio. Un efecto que depende de melee/ranged falla si falta; no se asume un valor.

## 5. Objetos con efectos curados (42)

| Id | Objeto | Demuestra |
|---|---|---|
| `data:item:1036` | Espada larga | Estadística plana derivada; objeto sin efectos. |
| `data:item:1031` | Chaleco de cadenas | Armadura plana; componente de receta. |
| `data:item:3020` | Botas de hechicero | Penetración mágica **plana** solo en prosa. |
| `data:item:3067` | Gema avivadora | Aceleración de habilidades solo en prosa. |
| `data:item:3134` | Daga dentada | Letalidad solo en prosa; receta con dos Espadas largas. |
| `data:item:3135` | Bastón del Vacío | Penetración mágica porcentual. |
| `data:item:3089` | Sombrero mortal de Rabadon | Modificador porcentual de AP total (`evaluable`). |
| `data:item:3031` | Filo infinito | Crítico derivado + daño crítico adicional en prosa. |
| `data:item:3153` | Hoja del rey arruinado | Daño `on-hit` 9 %/6 % de vida actual con cap 100; slow con 3 acumulaciones, ventana 6 s y enfriamiento 15 s. |
| `data:item:3036` | Recuerdos de lord Dominik | Penetración de armadura + rampa 1 %/100 de vida adicional con tope 15 % (`evaluable`). |
| `data:item:3047` | Botas blindadas | Reducción de daño entrante con condición (`evaluable`). |
| `data:item:3143` | Presagio de Randuin | −30 % de daño crítico + slow de área 70 %/2 s con enfriamiento 90 s. |
| `data:item:3157` | Reloj de arena de Zhonya | Estasis 2,5 s y enfriamiento de activa 120 s (`evaluable`). |
| `data:item:3075` | Malla de espinas | Reflejo 20 + 10 % de armadura adicional + heridas graves 40 %/3 s (`evaluable`). |
| `data:item:6617` | Renovación de piedra lunar | Curación y escudo porcentuales de un efecto disparador (`evaluable`). |
| `data:item:3111` | Botas de mercurio | Tenacidad (30 %) solo en prosa; resistencia mágica y velocidad de movimiento derivadas. |
| `data:item:3032` | Flechas de los Yun Tal | Cero confirmado de crítico; crítico por acumulaciones hasta 25 % con el escenario `max_stacks`; Ráfaga `excluded`. |
| `data:item:1043` | Arco curvo | Daño físico al impactar de la descripción (15). |
| `data:item:3091` | Final del ingenio | Daño mágico al impactar que Data Dragon omite (45, cliente, `derived`). |
| `data:item:3115` | Diente de Nashor | Daño mágico al impactar 15 + 15 % de AP (cliente, `derived`). |
| `data:item:3124` | Hoja de furia de Guinsoo | Daño mágico al impactar (30); velocidad de ataque por acumulaciones al máximo (4 × 8 %); impactos fantasma `excluded`. |
| `data:item:3057`, `3078`, `3100`, `3508`, `6662`, `2510`, `3877` | Brillo, Fuerza de trinidad, Perdición del liche, Segador de esencia, Guantelete de hielo, Amanecer y anochecer, Tonada sanguina | Hoja encantada con las cifras del cliente ([regla](../mechanics/spellblade.md)); sus efectos secundarios, declarados y sin aplicar salvo la repetición al impactar de Amanecer y anochecer. |
| `data:item:6672`, `3094`, `3087`, `6699`, `3181` | Verdugo de krakens, Cañón de fuego rápido, Puñal de Statikk, Espada ciclovoltaica, Rompecascos | Cada N ataques y Vigor ([regla](../mechanics/attack-counters.md)). |
| `data:item:4645`, `6676` | Llamasombría, Recaudadora | Umbral de vida del objetivo y ejecución ([regla](../mechanics/target-health.md)). |
| `data:item:6653`, `2503`, `2508`, `3118`, `3050`, `3147` | Tormento de Liandry, Antorcha de fuego negro, Cenizas predestinadas, Malignidad, Convergencia de Zeke, Disfraz encantado | Quemaduras y amplificadores por tiempo en combate ([regla](../mechanics/burns.md)). |
| `data:item:3302` | El final | Daño mágico al impactar 30 + 10 % de DA adicional + 10 % de AP (cliente, `derived`); 30 % de penetración al máximo; resistencias por nivel sin modelar. |

Cobertura de efectos: **42 objetos curados**; los otros 176 objetos comprables de la Grieta solo tienen estadísticas, y 132 de ellos tienen efectos en la descripción sin modelar (`pending`). No se afirma nada sobre las variantes de otros modos. Las fuentes secundarias de las cifras nuevas están en [`research/reports/object-mechanics-2026-10-20.md`](../../research/reports/object-mechanics-2026-10-20.md).

## 6. Efectos realmente modelados

| Objeto | Efecto | Estado | Qué falta |
|---|---|---|---|
| Rabadon | Obra mágica: +30 % de AP total | `evaluable` | La hoja lo aplica desde la versión 10 (antes la rotación lo omitía y quedaba `Pendiente de verificación`). |
| BotRK | Filo de la niebla: 9 %/6 % de vida actual como daño físico `on-hit`, cap 100 vs súbditos/monstruos | `evaluable` | Ratio y tope corroborados por el cliente 16.22; el cap es un límite declarado que el motor debe aplicar. |
| BotRK | Zarpazo sombrío: slow 30 % (15 % a distancia)/1 s tras 3 ataques, ventana 6 s, enfriamiento 15 s | `partially_evaluable` | Persistencia de acumulaciones entre objetivos no publicada; las 3 acumulaciones solo vienen de la wiki. |
| Lord Dominik | Verdugo de gigantes: 1 %/100 de vida adicional, tope 15 % a 1500 | `evaluable` | Tope y umbral corroborados por el cliente; la pendiente lineal sigue siendo de fuente secundaria. |
| Botas blindadas | Placas: −10 % de daño sufrido por ataques | `evaluable` | Nada para el modificador. |
| Randuin | Adaptabilidad: −30 % de daño crítico | `evaluable` | La reducción es multiplicativa y afecta al total de la instancia; el motor debe aplicarlo. |
| Randuin | Humildad: slow 70 %/2 s en área, enfriamiento 90 s | `evaluable` | El radio exacto no se modela. |
| Zhonya | Tiempo detenido: estasis 2,5 s, enfriamiento 120 s | `evaluable` | La interacción con item haste se documenta, no se formula. |
| Malla de espinas | Espinas: 20 + 10 % de armadura adicional, mágico; heridas graves 40 %/3 s | `evaluable` | La mitigación por RM del atacante la aplica el motor. |
| Moonstone | Gracia estelar: 30 % de la curación / 35 % del escudo a otro aliado | `evaluable` | La cantidad original es una entrada del motor. |
| Yun Tal | La práctica hace al asesino: +25 % de crítico con todas las acumulaciones | `evaluable` (`max_stacks`) | El valor por ataque (0,4 cuerpo a cuerpo; ×0,5 a distancia) y los 63/125 ataques hasta el tope son datos del cliente 16.22 (`Derivado`), en la nota del efecto; no se modelan acumulaciones parciales. |
| Yun Tal | Ráfaga: +30 % de velocidad de ataque 6 s, enfriamiento 30 s que reducen los ataques | `excluded` | Es una ventana temporal y las rotaciones no tienen línea de tiempo; con este objeto la rotación queda `Pendiente de verificación`. |
| Arco curvo | Picadura: 15 de daño físico al impactar | `evaluable` | Nada. |
| Final del ingenio | Refriega: 45 de daño mágico al impactar | `evaluable` (`derived`) | Data Dragon no da la cifra; el cálculo del cliente es fijo, sin escalado por nivel. |
| Diente de Nashor | Mordisco de Icathia: 15 + 15 % de AP mágico al impactar | `evaluable` (`derived`) | La parte del AP no lleva `mStat`; que sea AP lo confirma el nombre `NashorsAPValue`. |
| Guinsoo | Ira: 30 de daño mágico al impactar | `evaluable` | Nada. |
| Guinsoo | Golpe furioso: +8 % de velocidad de ataque por acumulación, hasta 4 | `evaluable` (`max_stacks`) | Se aplica con las 4 acumulaciones (+32 %). |
| Guinsoo | Impacto fantasma: cada tercer ataque aplica dos veces los efectos al impactar | `evaluable` | Desde la versión 12, cada tercer ataque de la rotación (contando desde cero) repite los efectos al impactar. |
| El final | Sombra: 30 + 10 % de DA adicional + 10 % de AP mágico al impactar | `evaluable` (`corroborated`) | Data Dragon muestra 0. El cliente y las notas oficiales de 26.15 («30 Magic Damage On-Hit ⇒ 30 (+10% bonus Attack Damage) (+10% Ability Power)») coinciden. La wiki antigua de Fandom aún da 30 fijo, de antes de 26.15. |
| Hoja encantada (7 objetos) | Golpe del primer ataque tras una habilidad | `evaluable` (`derived`) | Ver [`spellblade.md`](../mechanics/spellblade.md). |
| El final | Yuxtaposición, ataques sombríos: 10 % de penetración de armadura y mágica por ataque, hasta 30 % | `evaluable` (`max_stacks`, `derived`) | Se aplica al máximo (30 %, `PenMax` del cliente). |
| El final | Yuxtaposición, ataques luminosos: armadura y resistencia mágica | `evaluable` (`max_stacks`, `derived`) | Desde la versión 12: 3 × (6/7/8 según el nivel: 1, 11, 14) con `by_level`. |
| Kraken, Rompecascos, Cañón, Ciclovoltaica, Statikk | Cada N ataques y Vigor | Ver [`attack-counters.md`](../mechanics/attack-counters.md) | La letalidad de la Ciclovoltaica y el rayo de Statikk no se aplican; el aumento de Kraken por la vida que falta, sí (versión 13). |
| Llamasombría | Florascua: +20 % al daño mágico y verdadero contra objetivos por debajo del 40 % | `evaluable` | Ver [`target-health.md`](../mechanics/target-health.md). |
| Recaudadora | Muerte: ejecuta a campeones por debajo del 5 % | `evaluable` | Ver [`target-health.md`](../mechanics/target-health.md). |
| Liandry, Antorcha, Cenizas, Malignidad, Zeke | Quemaduras | `evaluable` (salvo Liandry contra monstruos) | Ver [`burns.md`](../mechanics/burns.md); Fuego negro y la reducción de RM de Malignidad no se aplican. |
| Liandry, Disfraz encantado | +6 % de daño a campeones al máximo | `evaluable` (`max_stacks`) | Ver [`burns.md`](../mechanics/burns.md). |

## 7. Inventario no soportado

Dentro de la muestra:

- La persistencia de las acumulaciones de BotRK entre objetivos distintos no está publicada; se marca como no verificada.
- Los modificadores de BotRK por modo (ARAM/Arena) están documentados pero no modelados.
- La interacción de la aceleración de objetos con los activos de Zhonya y Randuin se documenta, pero no se formula.
- El radio exacto de Humildad (Randuin) no se modela.
- El orden de aplicación de penetraciones, mitigaciones, escudos y modificadores es responsabilidad del motor; el catálogo expone fórmulas y condiciones, no el pipeline.

Fuera de la muestra: **no se modela ningún otro objeto**. Categorías deliberadamente fuera de alcance en esta fase: consumibles, centinelas y trinkets, generación de oro, efectos de muerte, acumulaciones permanentes, revives, auras, escudos con ratios, transformaciones, efectos de modo (Arena, URF) y cualquier pasivo cuya fórmula no esté publicada. Kraken Slayer, Luden's Companion, Eclipse y Sterak's Gage se evaluaron y se dejaron fuera por falta de una fórmula completa y verificable; no se declaran cubiertos.

Data Dragon además renderiza placeholders que parecen números reales. Ejemplo: la descripción de `data:item:3076` (Chaleco de zarzas) contiene «0 de daño mágico», pero ese `0` es un placeholder de una cantidad no publicada. Por eso el modelo **no** parsea números de la prosa de forma automática: exige una cita y un valor declarado por el curador, y trata `0` como cero real solo si el árbol dice `constant: 0`.

## 8. Interfaz del motor de daño

El contrato está en [`interface.py`](../../src/lol_knowledge/objects/interface.py). No implementa daño, búsqueda de builds ni simulación temporal.

### 8.1 Entradas de una evaluación de daño explosivo

| Entrada | Contenido |
|---|---|
| `game_version` | Parche del modelo con el que se evalúa. |
| `champion` | `champion_id`, nivel, rangos por habilidad, hoja de estadísticas final (post-runas y post-objetos) y `attack_range` (`melee`/`ranged`), obligatorio para efectos como BotRK. |
| `items` | Lista de `{item_id, count, stacks}`; los stacks cubren efectos acumulables. |
| `runes` | Ids de runas y fragmentos. |
| `target` | Tipo, nivel, armadura, resistencia mágica, vida actual, vida máxima, vida adicional (`bonus_health`, obligatoria) y reducción de daño. |
| `conditions` | Crítico, `on-hit`, impacto de habilidad, distancia, ratio de vida del objetivo y stacks. |
| `rotation` | Pasos ordenados con habilidad, rango, número de impactos, condiciones y tiempo de casteo. |

La hoja de estadísticas debe incluir **todas** las claves canónicas, incluso con valor `0.0`: así un cero explícito nunca se confunde con un dato ausente. `required_stat_sheet()` devuelve la lista.

```python
from lol_knowledge.objects import (
    ChampionState,
    DamageRequest,
    ImpactConditions,
    ItemSlot,
    RotationStep,
    RuneState,
    TargetProfile,
    validate_request,
)

request = DamageRequest(
    game_version="16.20.1",
    champion=ChampionState(
        champion_id="Zaahen",
        level=18,
        ability_ranks={"q": 5, "w": 5, "e": 5, "r": 3},
        stats={...},  # hoja canónica completa
        attack_range="melee",
    ),
    items=(ItemSlot("3153"), ItemSlot("3047")),
    runes=RuneState(),
    target=TargetProfile(
        kind="champion",
        level=18,
        armor=100,
        magic_resist=60,
        health=2500,
        max_health=2500,
        bonus_health=500,
    ),
    conditions=ImpactConditions(critical_strike=False, on_hit=True),
    rotation=(RotationStep("q", rank=5, hits=1),),
)
assert not validate_request(request)
```

### 8.2 Salidas

`DamageOutcome.status` usa exactamente cuatro estados:

| Estado | Significado |
|---|---|
| `evaluable` | Todos los componentes tienen fórmulas evaluables y entradas presentes. |
| `partially_evaluable` | La estructura se entiende, pero falta al menos un dato; se devuelven componentes conocidos y motivos. |
| `excluded` | El efecto se excluye por falta de información; no se inventa un número. |
| `unreliable` | El cálculo se sale del dominio validado (por ejemplo, parche distinto o nivel fuera de rango). |

`total` es `None` salvo que el resultado sea fiable. Los componentes y los motivos siempre se conservan.

## 9. Etiquetas y confianza

| Dato | Etiqueta AGENTS | Verificación en JSON |
|---|---|---|
| Estadística de `items.json` | `Oficial` (`Derivado` si lleva `unit_conversion`) | `official_field` |
| Número copiado de la descripción y citado | `Oficial` | `description_quote_verified` |
| Mapeo del número a una estadística canónica o a un efecto | `Derivado` | `curated` en la documentación; el JSON conserva `source.quote` |
| Fórmula deducida de prosa explícita | `Derivado` | `basis: description_explicit` |
| Fórmula o cifra de una fuente externa citada (wiki comunitaria) | `Derivado` / `Pendiente de verificación` | `basis: external_evidence_explicit`, `sources[]` y `evidence_confidence: secondary` |
| Efecto con fórmula incompleta | `Pendiente de verificación` | `model_status: partially_evaluable` o `excluded` |
| Selección de la muestra y del esquema | `Recomendación` | Decisión de ingeniería, no un hecho del juego |

## 10. Límites declarados

- Los efectos curados son una muestra pequeña (16 objetos) elegida por diversidad mecánica, no por frecuencia de compra. Las estadísticas sí cubren los 218 objetos comprables de la Grieta.
- Data Dragon no publica modos de juego; `availability.modes` es desconocido.
- Data Dragon no publica el enfriamiento de los activos. Cuando se conoce por una fuente citada, se registra con su confianza (Zhonya y Randuin: wiki y cliente, `corroborated`); si no, se marca desconocido.
- Los ratios y curvas que solo aparecen como «un porcentaje» o «hasta» se resuelven únicamente si existe una fuente citada y verificable; en caso contrario quedan desconocidos. No se interpolan extremos sin evidencia.
- La evidencia secundaria no es oficial de Riot. La coincidencia de estadísticas/oro con Data Dragon corrobora el estado de balance, no la exactitud de cada cifra.
- El modelo no sustituye al extractor de campeones: los objetos describen efectos; el daño de habilidades sigue viniendo de `research/binmodel`.
- La conexión con el motor es conceptual y de contrato; no hay simulación todavía. El orden de mitigaciones y el pipeline de daño quedan para la siguiente fase.
