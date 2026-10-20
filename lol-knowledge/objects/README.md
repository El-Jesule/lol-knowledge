# Modelo mecánico de objetos — `lol-object-model/1`

- **Parche del snapshot:** `16.20.1` (`data/current/manifest.json`).
- **Fuente:** Data Dragon (`https://ddragon.leagueoflegends.com`), locale `es_ES`.
- **Fecha de consulta:** 2026-10-20.
- **Estado:** muestra curada de 13 objetos; **no** es cobertura completa.
- **Código:** [`src/lol_knowledge/objects/`](../../src/lol_knowledge/objects/).
- **Catálogo curado:** [`catalog.json`](catalog.json).
- **Auditoría previa del extractor:** [`research/reports/agent-d-extractor-audit.md`](../../research/reports/agent-d-extractor-audit.md).

Este documento explica el esquema, las decisiones, lo que está modelado y lo que no. El JSON es el contrato; este Markdown es la justificación y el inventario de límites.

## 1. Qué resuelve y qué no

Resuelve: representar de forma versionada y verificable la identidad, las estadísticas y los efectos de un objeto, distinguiendo lo que Data Dragon publica de forma estructurada, lo que solo aparece en prosa y lo que no se sabe.

No resuelve todavía: evaluar daño de una rotación, buscar builds, simular tiempo, modelar todos los objetos ni interpretar efectos que dependen de estado del juego no publicado.

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

## 3. Esquema `lol-object-model/1`

### 3.1 Documento

```json
{
  "schema_version": 1,
  "kind": "lol-object-model",
  "catalog_version": 1,
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
- Solo se declaran en el catálogo las estadísticas que Data Dragon **no** estructura: letalidad, aceleración de habilidades, penetraciones y daño crítico adicional. Las planas y porcentuales que sí están en `stats` se derivan y no se repiten.
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
- `basis`: `description_explicit` (la prosa fija la operación), `description_partial` (faltan ratios o ventanas), `description_silent` (el efecto se reconoce pero la prosa no da fórmula).
- `trigger.event`: `always`, `on_hit`, `taking_attack`, `damaging_ability`, `on_heal_or_shield`, `cast`, `on_kill`, `periodic` o `unknown`.
- `target.kind`: `self`, `enemy_champion`, `enemy_unit`, `attacker`, `ally_champion`, `area` o `unknown`.
- `conditions`: lista de condiciones declarativas (`target_is_champion`, `damage_source_is_attack`, `critical_strike`, `stacks_at_least`, etc.). No son expresiones ejecutables.
- `cooldown_seconds`, `duration_seconds`, `stacks.window_seconds`: número no negativo, `null` (no aplica) o `{"status": "unknown", "reason": "..."}`.
- `stacks.required` y `stacks.max_stacks` son enteros; la ventana temporal puede ser desconocida.
- `limits`: topes o umbrales conocidos aunque la curva no lo esté. Ejemplo: el 15 % de Lord Dominik con 1500 de vida adicional.
- `model_status` es la clasificación curada; `derived_status` se calcula desde las fórmulas. `validate` impide que `model_status` sea **más optimista** que `derived_status`.

### 3.5 Componentes y fórmulas

Componentes: `damage`, `healing`, `shield`, `stat_modifier`, `damage_modifier`, `crowd_control`, `status`, `stasis`.

Los componentes `healing` y `shield` declaran `mode`: `absolute` (la fórmula devuelve la cantidad) o `percent_of_trigger` (la fórmula devuelve el porcentaje de la curación o escudo que disparó el efecto, que es una entrada del motor).

Fórmulas soportadas por el evaluador:

| Operación | Significado |
|---|---|
| `{"op": "constant", "value": 30}` | Constante finita. `0` es un cero real. |
| `{"op": "stat", "stat": "attack_damage", "scope": "bonus"}` | Estadística del campeón u objetivo. |
| `{"op": "add", "operands": [...]}` | Suma. |
| `{"op": "mul", "operands": [...]}` | Producto. |
| `{"op": "unknown", "reason": "..."}` | Dato ausente; nunca se sustituye por cero. |
| `{"op": "unsupported", "reason": "...", "needed": [...]}` | Mecánica no modelada. |

Scopes válidos: `base`, `bonus`, `total` para estadísticas de campeón; `current` y `max` para vida del objetivo. La resolución de claves es `total` → `attack_damage`, `bonus` → `bonus_attack_damage`, `current` sobre `health` → `current_health`.

El evaluador [`formula.py`](../../src/lol_knowledge/objects/formula.py) solo evalúa `constant`, `stat`, `add` y `mul`. Rechaza con códigos `unknown_input`, `unsupported_formula`, `missing_stat`, `malformed_formula`, `unsupported_operation` y `depth_exceeded`.

## 4. Decisiones del esquema

1. **El catálogo no duplica lo derivable.** Identidad, nombre, `stats`, `gold`, `maps`, `from`/`into`, `depth`, `in_store`, `hide_from_all`, `consumed`, `stacks`, `special_recipe`, `requiredChampion` y `requiredAlly` se leen de `data/current/items.json`. El catálogo solo aporta lo que Data Dragon no estructura. La excepción documentada es `game_version`: se declara para detectar que el catálogo se aplica a otro parche.
2. **Porcentajes en puntos.** Evita la ambigüedad entre `0.25` y `25`; el valor bruto se conserva.
3. **Recetas como multiconjunto.** Data Dragon repite ids (`from: ["1058", "1058"]`) para exigir dos copias. Por eso `builds_from` es una lista de `{id, count}` y no un conjunto.
4. **Ausente ≠ desconocido ≠ no modelado ≠ cero.** Se representan con `null`/campo ausente, `unknown`, `unsupported`/`excluded` y `constant: 0`, respectivamente.
5. **Procedencia por dato.** Cada estadística y efecto declara `source` y `verification`. Las citas se verifican contra la descripción normalizada del snapshot; los números declarados deben aparecer en la cita.
6. **Estado monotónico.** `model_status` no puede ser más optimista que `derived_status`. Ser más pesimista está permitido y documentado.
7. **Determinismo.** Objetos y estadísticas se ordenan por id canónico; el JSON se serializa con claves ordenadas. El orden de las claves del catálogo no altera el modelo.
8. **Sin red.** Todo se lee del snapshot versionado; las pruebas no descargan nada.

## 5. Objetos modelados (13)

| Id | Objeto | Demuestra |
|---|---|---|
| `data:item:1036` | Espada larga | Estadística plana derivada; objeto sin efectos. |
| `data:item:1031` | Chaleco de cadenas | Armadura plana; componente de receta. |
| `data:item:3067` | Gema avivadora | Aceleración de habilidades solo en prosa. |
| `data:item:3134` | Daga dentada | Letalidad solo en prosa; receta con dos Espadas largas. |
| `data:item:3135` | Bastón del Vacío | Penetración mágica porcentual. |
| `data:item:3089` | Sombrero mortal de Rabadon | Modificador porcentual de AP total (`evaluable`). |
| `data:item:3031` | Filo infinito | Crítico derivado + daño crítico adicional en prosa. |
| `data:item:3153` | Hoja del rey arruinado | Daño `on-hit` con ratio desconocido; slow con 3 acumulaciones y ventana desconocida. |
| `data:item:3036` | Recuerdos de lord Dominik | Penetración de armadura + efecto con tope conocido y curva no publicada (`excluded`). |
| `data:item:3047` | Botas blindadas | Reducción de daño entrante con condición (`evaluable`). |
| `data:item:3157` | Reloj de arena de Zhonya | Activo con duración conocida y enfriamiento desconocido (`partially_evaluable`). |
| `data:item:3075` | Malla de espinas | Reflejo con cantidad no publicada + heridas graves 40 % durante 3 s (`partially_evaluable`). |
| `data:item:6617` | Renovación de piedra lunar | Curación y escudo porcentuales de un efecto disparador (`evaluable`). |

Cobertura real: **13 objetos de los 600+ del snapshot**. No se afirma nada sobre el resto.

## 6. Efectos realmente modelados

| Objeto | Efecto | Estado | Qué falta |
|---|---|---|---|
| Rabadon | Obra mágica: +30 % de AP total | `evaluable` | Nada para el modificador; el redondeo de la hoja final es del motor. |
| BotRK | Filo de la niebla: daño físico `on-hit` según vida actual | `partially_evaluable` | Ratio numérico; Data Dragon solo dice «un porcentaje». |
| BotRK | Zarpazo sombrío: slow 30 % durante 1 s tras 3 ataques | `partially_evaluable` | Ventana temporal entre ataques. |
| Lord Dominik | Verdugo de gigantes: hasta 15 % de daño adicional | `excluded` | Curva entre 0 y 1500 de vida adicional. |
| Botas blindadas | Placas: −10 % de daño sufrido por ataques | `evaluable` | Nada para el modificador. |
| Zhonya | Tiempo detenido: estasis 2.5 s | `partially_evaluable` | Enfriamiento del activo. |
| Malla de espinas | Espinas: reflejo mágico + heridas graves 40 % / 3 s | `partially_evaluable` | Cantidad del daño reflejado. |
| Moonstone | Gracia estelar: 30 % de la curación / 35 % del escudo a otro aliado | `evaluable` | La cantidad original es una entrada del motor. |

## 7. Inventario no soportado

Dentro de la muestra:

- El ratio de daño `on-hit` de BotRK no está publicado con número.
- La ventana de 3 ataques del slow de BotRK no está publicada.
- La curva del pasivo de Lord Dominik no está publicada (solo el tope).
- El enfriamiento del activo de Zhonya no está en Data Dragon.
- La cantidad del daño reflejado de Malla de espinas no está publicada.

Fuera de la muestra: **no se modela ningún otro objeto**. Categorías deliberadamente fuera de alcance en esta fase: consumibles, centinelas y trinkets, generación de oro, efectos de muerte, acumulaciones permanentes, revives, auras, escudos con ratios, transformaciones, efectos de modo (Arena, URF) y cualquier pasivo cuya fórmula no esté publicada.

Data Dragon además renderiza placeholders que parecen números reales. Ejemplo: la descripción de `data:item:3076` (Chaleco de zarzas) contiene «0 de daño mágico», pero ese `0` es un placeholder de una cantidad no publicada. Por eso el modelo **no** parsea números de la prosa de forma automática: exige una cita y un valor declarado por el curador, y trata `0` como cero real solo si el árbol dice `constant: 0`.

## 8. Interfaz del motor de daño

El contrato está en [`interface.py`](../../src/lol_knowledge/objects/interface.py). No implementa daño, búsqueda de builds ni simulación temporal.

### 8.1 Entradas de una evaluación de daño explosivo

| Entrada | Contenido |
|---|---|
| `game_version` | Parche del modelo con el que se evalúa. |
| `champion` | `champion_id`, nivel, rangos por habilidad y hoja de estadísticas final (post-runas y post-objetos). |
| `items` | Lista de `{item_id, count, stacks}`; los stacks cubren efectos acumulables. |
| `runes` | Ids de runas y fragmentos. |
| `target` | Tipo, nivel, armadura, resistencia mágica, vida actual, vida máxima, vida adicional y reducción de daño. |
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
| Estadística de `items.json` | `Oficial` | `official_field` |
| Número copiado de la descripción y citado | `Oficial` | `description_quote_verified` |
| Mapeo del número a una estadística canónica o a un efecto | `Derivado` | `curated` en la documentación; el JSON conserva `source.quote` |
| Fórmula deducida de prosa explícita | `Derivado` | `basis: description_explicit` |
| Efecto con fórmula incompleta | `Pendiente de verificación` | `model_status: partially_evaluable` o `excluded` |
| Selección de la muestra y del esquema | `Recomendación` | Decisión de ingeniería, no un hecho del juego |

## 10. Límites declarados

- La muestra es pequeña y elegida por diversidad mecánica, no por frecuencia de compra.
- Data Dragon no publica modos de juego; `availability.modes` es desconocido.
- Data Dragon no publica el enfriamiento de los activos; se marca desconocido.
- Los ratios y curvas que solo aparecen como «un porcentaje» o «hasta» quedan desconocidos.
- El modelo no sustituye al extractor de campeones: los objetos describen efectos; el daño de habilidades sigue viniendo de `research/binmodel`.
- La conexión con el motor es conceptual y de contrato; no hay simulación todavía.
