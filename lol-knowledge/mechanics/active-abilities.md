# Habilidades defensivas, curaciones y esteroides activos (`Q/W/E/R`)

- **Ámbito:** escudos activos, curaciones instantáneas y sobre el tiempo (*HoT*), reducciones de daño porcentuales y planas, y esteroides temporales de estadísticas en habilidades `Q/W/E/R` de campeones en rotación (`rotation`), supervivencia inversa (`survive`), optimizador (`optimize`), contrato JSON (`contract`) y servidor MCP (`mcp`).
- **Parche de referencia:** Data Dragon `16.23.1` y cliente `16.23` (`16.23.8406595+branch.releases-16-23.content.release`).
- **Fecha de consulta:** 2026-11-25
- **Especificaciones y kits:** `research/kits/<Id>.spec.json` y `lol-knowledge/champions/<Id>/kit.json`
- **Código:** [`src/lol_knowledge/kit/model.py`](../../src/lol_knowledge/kit/model.py), [`research/binmodel/kitgen.py`](../../research/binmodel/kitgen.py), [`src/lol_knowledge/rotation.py`](../../src/lol_knowledge/rotation.py), [`src/lol_knowledge/defense.py`](../../src/lol_knowledge/defense.py), [`src/lol_knowledge/optimizer/search.py`](../../src/lol_knowledge/optimizer/search.py)

## Fuentes

| Id | Fuente | Qué cubre | Naturaleza |
|---|---|---|---|
| S1 | Cliente `16.23` (`DATA/FINAL/Champions/<Id>.wad.client`, `mSpellCalculations` y `DataValues` de `Q/W/E/R`, build `16.23.8406595+branch.releases-16-23.content.release`) | Cálculos exactos, valores por rango y duraciones de escudos, curaciones, reducciones de daño y bonificaciones temporales de estadísticas | `Derivado` (datos del cliente, no API oficial) |
| S2 | Cliente `16.23` (`DATA/FINAL/Localized/Global.es_ES.wad.client`) | Descripciones localizadas en español utilizadas para verificar tipo de escudo, duración, alcance propio/aliado y condiciones | `Derivado` |

## 1. Cobertura del plantel (`Derivado`, S1–S2)

Se han curado y compilado **277 efectos activos** repartidos en **206 habilidades** de **134 de los 173 campeones** del plantel:

| Categoría (`kind`) | Efectos compilados | Ejemplos representativos |
|---|---:|---|
| `shield` | 50 | Escudos normales (`Garen W`, `Lux W`, `Lulu E`, `Karma E`, `Volibear E`, `Taric W`, `Olaf W`, `Sion W`, `Ambessa W`, `Milio E`) y escudos mágicos (`Morgana E`, `Kassadin Q`, `Galio W`) |
| `heal` | 45 | Curaciones instantáneas (`Soraka W/R`, `Darius Q`, `Gangplank W`, `Sylas W`, `Vladimir Q/W/R`, `Zaahen Q`, `Volibear W`, `Yorick Q`) y curaciones en el tiempo (`over_duration`: `DrMundo R`, `MasterYi W`, `Janna R`, `Milio W`, `Soraka Q`, `Fiora R`, `Swain R`, `Briar E`, `Yuumi R`) |
| `damage_taken_modifier` | 17 | Reducción porcentual global (`Alistar R`, `Garen W`, `Warwick E`, `Gragas W`, `MasterYi W`, `Belveth E`, `Briar E`, `Braum E`, `KSante W`, `Jax E`, `Zaahen R`), por tipo de daño (`Galio W`, `Irelia W`, `Nilah W`) y reducción plana con tope del `50 %` (`Leona W`) |
| `stat_bonus` | 165 | Vida máxima temporal (`Nasus R`, `Renekton R`, `Volibear R`, `Lulu R`, `Belveth R`, `DrMundo R`), armadura/RM (`Jax R`, `Rammus W`, `Leona W`, `Braum W`, `Kennen R`, `Hecarim W`, `Briar R`, `Singed R`), AD plano y porcentual (`Vayne R`, `Twitch R`, `Olaf R`, `Trundle Q`, `Aatrox R`, `Riven R`, `Naafiri W`), AP (`Singed R`), velocidad de ataque (`Tristana Q`, `Ashe Q`, `Jinx Q`, `Kled W`, `Trundle W`, `MasterYi R`, `Xayah W`), robo de vida/omnisucción (`LeeSin W`, `Belveth E`, `Briar R`) y velocidad de movimiento plana/porcentual (`Garen Q`, `Sivir R`, `Draven W`, `Lucian W`, `MissFortune W`, `Karma E`) |

Los **39 campeones restantes** no tienen efectos defensivos, de curación ni esteroides propios directos modelables en `Q/W/E/R` (p. ej. kits de daño puro/CC o mecánicas ya modeladas en pasivas o daño de habilidades).

## 2. Esquema declarativo y convenciones de unidades (`Derivado` / `Calculado`)

Cada habilidad en `kit.json` puede declarar `active_effects: [...]` con los campos `id`, `name`, `kind`, `formula`, `label`, `source` y campos opcionales `duration_seconds` / `duration_formula`, `stat`, `mode`, `shield_type`, `damage_type`, `damage_reduction_cap`, `case_ids`, `over_duration`, `uses_hsp` y `condition`.

- **Escala de unidades:**
  - `attack_speed_bonus`, `life_steal`, `omnivamp` (`mode: "flat"`): puntos porcentuales (`0..200`, p. ej. `120` para `+120 %` VA de `Tristana Q` o `150` para `+150 %` de `Kled W`); el motor los convierte a fracción y soporta bonificaciones de VA superiores al `100 %`.
  - `move_speed` (`mode: "percent_ms"`): fracción decimal (`0,35` para `+35 %` VM); `mode: "flat"`: VM plana (`60..100`).
  - `attack_damage` / `armor` / `magic_resist` / `health` (`mode: "percent"`): puntos porcentuales (`20` para `+20 %` AD de `Riven R`, `40` para `+40 %` AD de `Aatrox R`).
  - `damage_taken_modifier`: `mode: "percent"` en puntos porcentuales (`55..75` en `Alistar R`); `mode: "flat"` en daño plano con `damage_reduction_cap` en fracción decimal (`0,5` en `Leona W`).
- **Vida que falta dinámica:** las fórmulas pueden referenciar `{"op": "stat", "stat": "health", "scope": "missing_fraction"}` junto a `scope: "max"`. En `survive`, las curaciones instantáneas se evalúan en el instante en que se disparan (proactiva si el defensor empieza herido o reactiva tras recibir el primer golpe no letal); en `rotation`, `missing_fraction_health` vale `0` por defecto y puede fijarse mediante `--input champion_missing_health_fraction=<0..1>`.

## 3. Integración en motor y herramientas (`Calculado`)

- **En `rotation`:**
  - Las habilidades puramente utilitarias sin casos de daño (`cases: []`, como `Garen W`, `Lux W`, `Tristana Q`, `Vayne R`, `Aatrox R`) se pueden lanzar como pasos normales (`W`, `Q`, `R`), pagando su coste, respetando enfriamientos en `--timeline`, cargando Hoja encantada y disparando pasivas `after_ability`.
  - Los escudos emiten `ShieldEvent` y activan Golpe de escudo (`data:rune:8401`); las curaciones emiten `HealEvent`; los `stat_bonus` temporales se inyectan en `_set_moment` con expiración exacta en `--timeline` (recalculando la cadencia de ataque cuando modifican `attack_speed_bonus`).
- **En `survive` y `optimize --objective time_to_die`:**
  - `--defender-cast <slot>[.<caso>][=<rango>]` (repetible; `defender_casts` en `contract` y `mcp`) y `--learned` activan las habilidades defensivas, curaciones, *HoT* y esteroides de vida/armadura/RM del defensor.
  - Los escudos respetan `shield_type` (`normal`, `magic`, `physical`), escala con HSP/Revitalizar y caducidad en `--timeline`.
  - Las reducciones de daño porcentuales se multiplican tras Extenuación (sin afectar jamás al daño verdadero) y las reducciones planas se aplican con su tope (`50 %` en `Leona W`) antes de `damage_after_flat`.
  - Las curaciones marcadas con `over_duration: true` se integran de forma continua en `accrue_continuous` cuando `--timeline` está activo.

## 4. Limitaciones

- **Sin decaimiento continuo ni interrupción de canalizaciones:** las velocidades de movimiento decrecientes (p. ej. `Ahri W`, `Draven W`, `Blitzcrank W`) se modelan por su valor inicial durante su duración, y las canalizaciones (`MasterYi W`, `Janna R`, `Briar E`) asumen duración completa sin interrupción por CC.
- **Condiciones posicionales o de múltiples objetivos:** habilidades con escalado por número de enemigos golpeados o cercanos (`Darius Q`, `JarvanIV W`, `Jax R`, `Shyvana W`, `Swain R`) se modelan en su caso base (1 campeón / escudo base) con `condition` declarada; las mecánicas basadas en daño almacenado previo (`TahmKench E`, `Sett W` coraje, `Rengar W` daño reciente) o curaciones porcentuales del daño infligido (`Warwick Q`, `Fiddlesticks W`, `Hecarim W`) no se aproximan sin datos de combate acumulados.
- **Invulnerabilidad y esquiva direccional:** la esquiva de ataques básicos (`Jax E`, `Nilah W`), el bloqueo completo del primer proyectil (`Braum E`), la invulnerabilidad frontal (`Pantheon E`) y el bloqueo de hechizos (`Sivir E`, `Nocturne W`) se registran en las condiciones del efecto o quedan fuera de la reducción numérica continua.
