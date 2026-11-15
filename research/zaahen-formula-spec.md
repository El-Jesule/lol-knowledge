# Especificación del extractor de fórmulas de bin

- **Estado:** prototipo de investigación, aislado en `research/binmodel/`.
- **Objetivo:** transformar un `bin.json` de campeón en árboles de cálculo tipados, con procedencia y evaluación determinista, sin listas manuales de parámetros por campeón.
- **No objetivo:** optimizador de builds, motor de daño completo, scraping de la wiki, modificación de `data/current/` o de `src/lol_knowledge/`.

## 1. Pipeline

```
bin.json
  │
  ├─ 1. Descubrir CharacterRecord          (find_champion_root)
  ├─ 2. Descubrir pasiva y Q/W/E/R          (mCharacterPassiveSpell, spells, mAbilities, mRootSpell)
  ├─ 3. Descubrir rangos                    (mTooltipData.mLists.LevelUp.levelCount)
  ├─ 4. Extraer DataValues                  (base + DataValuesModeOverride)
  ├─ 5. Extraer árboles                     (mSpellCalculations → nodos tipados)
  ├─ 6. Extraer vectores                    (Cooldown, mana, castRange)
  ├─ 7. Extraer hechizos hijos              (mChildSpells → DataValues, cálculos, BotData)
  ├─ 8. Resumir BotData                     (efectos, cálculos, referencias, no resueltos)
  ├─ 9. Evaluar y validar                   (opcional, bajo demanda)
  └─ 10. Diagnosticar                       (errores, avisos, no resueltos)
```

El extractor no conoce el nombre del campeón, de la habilidad ni de los parámetros. El único punto con nombres de campeón es la capa de validación de mediciones (`validation.py`) y el CLI por defecto; el recorrido y el modelo son genéricos.

## 2. Descubrimiento

| Qué | De dónde | Regla |
|---|---|---|
| Campeón | `CharacterRecords/Root` | Único objeto con `__type == CharacterRecord` o `mCharacterName` |
| Pasiva | `Root.mCharacterPassiveSpell` | Ruta al objeto de hechizo |
| Q/W/E/R | `Root.spells[0..3]` | Orden convencional del root; se conserva el índice |
| Objetos de habilidad | `Root.mAbilities` | Mapa `mRootSpell -> {mChildSpells, mName}` |
| Hijos | `AbilityObject.mChildSpells` | Se extraen como `child_spells` |
| Rangos | `mSpell.mClientData.mTooltipData.mLists.LevelUp.levelCount` | Si falta y es pasiva, 1; si falta en otra, `None` + aviso |
| Cálculos | `mSpell.mSpellCalculations` | Mapa nombre → `IGameCalculation` |
| `DataValue` | `mSpell.DataValues` | Lista de `{name, values}` |
| Overrides | `mSpell.DataValuesModeOverride` | Se separan por `mode` (por ejemplo `cherry`) |
| Cooldown | `mSpell.Cooldown.values` | Efectivo; `cooldownTime` se conserva como legado |
| Maná | `mSpell.manaValues.values` o `mSpell.mana` | El primero si existe |
| Rango | `mSpell.castRangeValues.values` o `mSpell.castRange` | El primero si existe |

## 3. Alineación de rangos

Los arrays de hechizo reservan el índice 0 para el rango 0. El rango 1 es `raw[1]`, aunque `raw[0]` no sea cero. El extractor:

- usa `raw[1 : level_count + 1]` cuando `len(raw) > level_count`;
- acepta `raw` cuando `level_count == 1` y `len(raw) == 1` (escalar);
- emite `ambiguous_rank_alignment` y no selecciona si `len(raw) == level_count` (no puede saber si el índice 0 es rango 0 o rango 1);
- emite `rank_array_too_short` si `len(raw) < level_count`.

Esto evita el error de asumir que todos los arrays empiezan en 0 o que todos tienen un hueco.

## 4. Nodos tipados

Cada nodo es un objeto JSON con `kind`, `type` (nombre/hash/provisional), `provenance` y los campos del tipo.

| `kind` | Campos principales | Evaluable |
|---|---|---|
| `game_calculation` | `parts`, `display_as_percent`, `precision`, `tooltip_only` | sí (suma de partes) |
| `number` | `value` | sí |
| `data_value` | `name` | sí |
| `stat_scaled` | `stat` (`mStat`, `mStatFormula`, nombre, confianza), `factor` | sí si el stat está resuelto |
| `product` | `operands` | sí |
| `sum` | `operands` | sí |
| `by_char_level_breakpoints` | `level1_value`, `initial_bonus_per_level`, `breakpoints` | sí |
| `by_char_level_formula` | `values` | sí (índice nivel-1) |
| `by_char_level_interpolation` | `start_value`, `end_value`, flags | sí (lineal 1..18) |
| `by_char_level_named_data_values_interpolation` | `start_data_value`, `end_data_value`, flags | sí (lineal 1..18) |
| `by_char_level_named_breakpoints` | `level1_data_value`, `bonus_per_level_data_value`, `breakpoints` | parcial; falla si falta un `DataValue` |
| `modified` | `base_calculation`, `multiplier` | sí |
| `calculation_reference` | `key` | sí, con detección de ciclos |
| `external_calculation_reference` | `source_object`, `key` | sí, con detección de ciclos |
| `external_data_value` | `source_object`, `name` | sí |
| `bot_effect` | `effect_tag`, `calculation` | sí, pero es auxiliar |
| `conditional` | `default_calculation`, `conditional_calculation`, `condition` | no; depende del estado de juego |
| `effect_value` | `effect_index`, `resolved=false` | no; requiere `SpellEffectAmount` |
| `unresolved` | `reason`, `raw`, `type` | no; se conserva el JSON original |

Un nodo desconocido **nunca** se convierte en `0` ni en una fórmula inventada.

## 5. Modelo de datos de salida

```json
{
  "schema_version": 1,
  "kind": "lol-bin-champion-extract",
  "game_version": "16.20",
  "content_version": "16.20.8248524+branch.releases-16-20.content.release",
  "source": {
    "url": "https://raw.communitydragon.org/16.20/game/data/characters/zaahen/zaahen.bin.json",
    "input": "research/fixtures/zaahen_extract_min.json",
    "input_sha256": "376b…",
    "artifact_sha256": "76e32…",
    "retrieved_at": "2026-10-20"
  },
  "champion": {
    "id": "Zaahen",
    "base_stats": {"values": {"attack_damage": 63.0, "attack_damage_per_level": 4.0}},
    "stats_by_level": {"1": {"attack_damage": 63.0, "...": "..."}},
    "spell_paths": ["..."],
    "ability_paths": ["..."],
    "passive_spell": "..."
  },
  "abilities": [
    {
      "id": "q",
      "slot": "Q",
      "path": ".../ZaahenQ",
      "level_count": 5,
      "level_count_source": "tooltip",
      "data_values": [
        {
          "name": "Q1BaseDamage",
          "raw_values": [0, 15, 30, 45, 60, 75, 90],
          "ranks": [15, 30, 45, 60, 75],
          "mode": "base",
          "status": "source_explicit",
          "provenance": {"json_pointer": "/.../DataValues/0", "source_sha256": "76e32…"}
        }
      ],
      "calculations": [
        {
          "name": "InitialDamage",
          "tree": {
            "kind": "game_calculation",
            "parts": [
              {"kind": "data_value", "name": "Q1BaseDamage"},
              {"kind": "stat_scaled", "stat": {"mStat": 2, "mStatFormula": 2, "stat": "attack_damage", "formula": "bonus"}, "factor": {"kind": "data_value", "name": "QCoeff"}}
            ],
            "provenance": {"json_pointer": "/.../mSpellCalculations/InitialDamage"}
          }
        }
      ],
      "cooldown": {"effective": true, "ranks": [10, 9, 8, 7, 6], "legacy": {"matches": true}},
      "mana": {"ranks": [25, 25, 25, 25, 25]},
      "cast_range": {"ranks": [25000, "..."]},
      "tooltip": {"loc_keys": {}, "lists": {"LevelUp": {"level_count": 5}}},
      "child_spells": [],
      "bot_data": {"type_counts": {}, "calculations": [], "unresolved": []}
    }
  ],
  "unresolved": [],
  "diagnostics": [],
  "registry": {"schema_version": 1, "provenance": {}}
}
```

### 5.1 Confianza

- `source_explicit`: valor tomado directamente del bin.
- `derived`: transformación determinista (por ejemplo, rango 1..N).
- `inferred`: interpretación semántica (por ejemplo, `mStat` o interpolación).
- `corroborated`: varias derivaciones o fuentes independientes coinciden.
- `verified`: coincide con Data Dragon y una fuente independiente.
- `unverified`: falta evidencia o no se pudo seleccionar.
- `conflict`: las fuentes discrepan.

La confianza del dato y la de su interpretación se registran por separado cuando aplica (`stat_confidence`, `formula_confidence`).

## 6. Evaluación

`evaluate.py` implementa:

- suma de `GameCalculation.parts`;
- producto y suma de subpartes;
- `DataValue` por rango;
- `stat * factor` con `mStat`/`mStatFormula`;
- breakpoints por nivel;
- interpolación lineal `start + (end-start)*(level-1)/17`;
- `GameCalculationModified` y referencias;
- detección de ciclos con `ctx.stack`;
- errores explícitos: `missing_data_value`, `missing_calculation`, `unresolved_stat`, `calculation_cycle`, `conditional_requires_game_state`, `effect_value_unresolved`, `unresolved_node`.

`by_char_level_named_breakpoints` puede devolver un resultado parcial (`complete=False`) con la lista de `missing`; no rellena los huecos.

## 7. Generalización

Para añadir un campeón:

1. Obtener su `bin.json` con la versión fijada y calcular el SHA-256.
2. Ejecutar `python -m binmodel --input <bin.json> --output <salida.json>`.
3. Revisar `diagnostics` y `unresolved`; no interpretar los nodos no resueltos como cero.
4. Si aparece un tipo nuevo, añadirlo al registro `research/binmodel/schema/lol_classes.json` con su hash y estructura, y escribir un parser explícito.
5. Validar con mediciones propias; no copiar valores de la wiki como oficiales.

No hace falta añadir nombres de parámetros a una lista como `DATA_VALUE_SPECS`. El descubrimiento usa `Root.spells`, `mAbilities`, `mCharacterPassiveSpell`, `mRootSpell` y `mSpellCalculations`.

### 7.1 Prueba de generalización

- `research/fixtures/zaahen_extract_min.json`: Zaahen, 5 habilidades.
- `research/fixtures/darius_extract_min.json`: Darius, 5 habilidades, Q con `BladeDamage`/`HandleDamage`; el test evalúa `BladeDamage` y comprueba que no aparece «Zaahen» en la salida.
- `test_binmodel_generalization.py`: campeón sintético `TestChampion` con `TestBase`/`TestRatio`; demuestra que el código no depende de nombres de Zaahen.
- Kha'Zix (no versionado): el extractor descubre 18 cálculos y marca 4 `EffectValueCalculationPart` como no evaluables; los `GameCalculationConditional` se parsean estructuralmente.

## 8. CLI

```powershell
$env:PYTHONPATH="research"

# Resumen y validación de Zaahen
.\.venv\Scripts\python.exe -m binmodel `
  --input research\fixtures\zaahen_extract_min.json `
  --validate

# JSON completo
.\.venv\Scripts\python.exe -m binmodel `
  --input research\fixtures\zaahen_extract_min.json `
  --output research\reports\zaahen-extract.json --json

# Daño a nivel/rango concretos
.\.venv\Scripts\python.exe -m binmodel `
  --input research\fixtures\zaahen_extract_min.json `
  --level 18 --rank 1 --bonus-ad 100

# Otro campeón
.\.venv\Scripts\python.exe -m binmodel --input research\fixtures\darius_extract_min.json
```

`--validate` solo ejecuta la tabla de mediciones para Zaahen; para otros campeones informa que se omite. `--self-check` devuelve 1 si hay diagnósticos de severidad `error`.

## 9. Pruebas

| Archivo | Qué cubre |
|---|---|
| `test_binmodel_hashes.py` | FNV-1a, normalización de tipos/campos |
| `test_binmodel_registry.py` | clases resueltas, hashes provisionales, campos |
| `test_binmodel_extract.py` | descubrimiento, rangos, cooldowns, árboles, procedencia |
| `test_binmodel_evaluate.py` | daño Q/W/E/R, pasiva, breakpoints, ciclos, errores |
| `test_binmodel_validation.py` | tabla de AD, porcentajes, una carga, daño |
| `test_binmodel_generalization.py` | campeón sintético y Darius real |
| `test_binmodel_unsupported.py` | condicionales y valores de efecto |
| `test_binmodel_provenance.py` | overrides, 24 cálculos, no-sustitución por cero, entrada malformada |
| `test_rst.py` | parser RST v5 sintético |

## 10. Límites conocidos

- El tipo de daño no está en `mSpellCalculations`; aparece en el marcado de los tooltips.
- La aplicación de la pasiva (base del porcentaje, multiplicador máximo) está fuera del árbol, probablemente en Lua.
- `BotData` es auxiliar y contiene estructuras `{150d1b92}` sin semántica.
- `EffectValueCalculationPart` y `GameCalculationConditional` se conservan, pero no se evalúan.
- La fórmula de crecimiento de estadísticas es un modelo externo, no un dato del bin.
- El redondeo de pantalla se modela con `round_half_up` solo para validar; no se afirma que sea el del juego.
