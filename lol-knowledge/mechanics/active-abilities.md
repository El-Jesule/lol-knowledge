# Habilidades defensivas, curaciones y esteroides activos (`Q/W/E/R`)

- **Ámbito:** escudos activos, curaciones instantáneas y sobre el tiempo (*HoT*), curaciones por daño infligido, escudos/curaciones por daño recibido reciente, reducciones de daño porcentuales y planas, esquiva de ataques básicos, escudos de hechizos, bloqueo de primer impacto, invulnerabilidad/inmortalidad y esteroides temporales de estadísticas en `Q/W/E/R`, integrados en `rotation`, `survive`, `optimize`, `contract` y `mcp`.
- **Parche de referencia:** Data Dragon `16.23.1` y cliente `16.23` (`16.23.8406595+branch.releases-16-23.content.release`).
- **Fecha de consulta:** 2026-11-25
- **Especificaciones y kits:** `research/kits/<Id>.spec.json` y `lol-knowledge/champions/<Id>/kit.json`
- **Código:** [`src/lol_knowledge/kit/model.py`](../../src/lol_knowledge/kit/model.py), [`research/binmodel/kitgen.py`](../../research/binmodel/kitgen.py), [`src/lol_knowledge/rotation/`](../../src/lol_knowledge/rotation/), [`src/lol_knowledge/defense/`](../../src/lol_knowledge/defense/), [`src/lol_knowledge/optimizer/search.py`](../../src/lol_knowledge/optimizer/search.py)

## Fuentes

| Id | Fuente | Qué cubre | Naturaleza |
|---|---|---|---|
| S1 | Cliente `16.23` (`DATA/FINAL/Champions/<Id>.wad.client`, `mSpellCalculations` y `DataValues` de `Q/W/E/R`, build `16.23.8406595+branch.releases-16-23.content.release`) | Cálculos exactos, valores por rango, ventanas de almacenamiento y duraciones de escudos, curaciones, reducciones, esquivas, invulnerabilidades y bonificaciones temporales | `Derivado` (datos del cliente, no API oficial) |
| S2 | Cliente `16.23` (`DATA/FINAL/Localized/Global.es_ES.wad.client`) | Descripciones localizadas en español utilizadas para verificar tipo de escudo, duración, alcance propio/aliado y condiciones | `Derivado` |

## 1. Cobertura del plantel (`Derivado`, S1–S2)

Se han curado y compilado **301 efectos activos** repartidos en **220 habilidades** de **135 de los 173 campeones** del plantel:

| Categoría (`kind`) | Efectos compilados | Ejemplos representativos |
|---|---:|---|
| `shield` | 49 | Escudos normales (`Garen W`, `Lux W`, `Lulu E`, `Karma E`, `Volibear E`, `Taric W`, `Olaf W`, `Sion W`, `Ambessa W`, `Milio E`) y escudos mágicos (`Morgana E`, `Kassadin Q`, `Galio W`) |
| `heal` | 46 | Curaciones instantáneas (`Soraka W/R`, `Darius Q`, `Gangplank W`, `Sylas W`, `Vladimir Q/W/R`, `Zaahen Q`, `Volibear W`, `Yorick Q`, `Briar W`) y curaciones en el tiempo (`over_duration`: `DrMundo R`, `MasterYi W`, `Janna R`, `Milio W`, `Soraka Q`, `Fiora R`, `Swain R`, `Briar E`, `Yuumi R`) |
| `damage_dealt_heal` | 8 | Curación proporcional al daño post-mitigación infligido en ese mismo lanzamiento (`Warwick Q`, `Zaahen R`, `Fiddlesticks W`, `Hecarim W`, `Camille W` parte exterior, `Nilah R`, `Briar W` mordisco, `Viego Q` doble golpe) |
| `recent_damage_heal` | 2 | Curación reactiva basada en daño recibido en ventana reciente (`Rengar W`: `50 %` en `1,5 s`; `DrMundo W`: `25 %` vida gris base en `3 s`) |
| `recent_damage_shield` | 3 | Escudo reactivo basado en daño recibido con mínimo/máximo declarados (`Mordekaiser W`: `7,5 %` con suelo mínimo `5 %` y techo `30 %` vida máx.; `Sett W`: `100 %` en `4 s` hasta `50 %` vida máx.; `TahmKench E`: `15..47 %` vida gris) |
| `damage_taken_modifier` | 17 | Reducción porcentual global (`Alistar R`, `Garen W`, `Warwick E`, `Gragas W`, `MasterYi W`, `Belveth E`, `Briar E`, `Braum E`, `KSante W`, `Jax E`, `Zaahen R`), por tipo de daño (`Galio W`, `Irelia W`, `Nilah W`) y reducción plana con tope del `50 %` (`Leona W`) |
| `dodge_attacks` | 3 | Esquiva/bloqueo completo de ataques básicos y críticos (`Jax E` `2 s`, `Nilah W` `2,25 s`, `Shen W` `1,75 s`) |
| `spell_shield` | 2 | Bloqueo de la siguiente habilidad enemiga (`Sivir E` `1,5 s` con curación al bloquear, `Nocturne W` `1,5 s`) |
| `block_first_hit` | 1 | Anulación completa del primer impacto recibido (`Braum E` `3..4 s`, seguido de su reducción porcentual en golpes posteriores) |
| `invulnerable` | 5 | Invulnerabilidad total (`Kayle R` `2,5 s`, `Taric R` `2,5 s`, `Fiora W` `0,75 s`, `Pantheon E` `1,5 s` frontal) e inmortalidad con suelo de vida (`Tryndamere R` `30/50/70` vida mínima durante `5 s`) |
| `stat_bonus` | 165 | Vida máxima temporal (`Nasus R`, `Renekton R`, `Volibear R`, `Lulu R`, `Belveth R`, `DrMundo R`), armadura/RM (`Jax R`, `Rammus W`, `Leona W`, `Braum W`, `Kennen R`, `Hecarim W`, `Briar R`, `Singed R`), AD plano y porcentual (`Vayne R`, `Twitch R`, `Olaf R`, `Trundle Q`, `Aatrox R`, `Riven R`, `Naafiri W`), AP (`Singed R`), velocidad de ataque (`Tristana Q`, `Ashe Q`, `Jinx Q`, `Kled W`, `Trundle W`, `MasterYi R`, `Xayah W`), robo de vida/omnisucción (`LeeSin W`, `Belveth E`, `Briar R`) y velocidad de movimiento plana/porcentual (`Garen Q`, `Sivir R`, `Draven W`, `Lucian W`, `MissFortune W`, `Karma E`) |

Los **38 campeones restantes** no tienen efectos defensivos, de curación ni esteroides propios directos modelables en `Q/W/E/R` (kits de daño puro/CC o mecánicas ya modeladas en pasivas o daño de habilidades).

## 2. Esquema declarativo y convenciones de unidades (`Derivado` / `Calculado`)

Cada habilidad en `kit.json` puede declarar `active_effects: [...]` con los campos `id`, `name`, `kind`, `formula`, `label`, `source` y campos opcionales `duration_seconds` / `duration_formula`, `stat`, `mode`, `shield_type`, `damage_type`, `damage_reduction_cap`, `case_ids`, `over_duration`, `uses_hsp`, `window_seconds`, `min_formula`, `max_formula`, `part_index`, `input_name` y `condition`.

- **Escala de unidades:**
  - `attack_speed_bonus`, `life_steal`, `omnivamp` (`mode: "flat"`): puntos porcentuales (`0..200`, p. ej. `120` para `+120 %` VA de `Tristana Q` o `150` para `+150 %` de `Kled W`); el motor los convierte a fracción y soporta bonificaciones de VA superiores al `100 %`.
  - `move_speed` (`mode: "percent_ms"`): fracción decimal (`0,35` para `+35 %` VM); `mode: "flat"`: VM plana (`60..100`).
  - `attack_damage` / `armor` / `magic_resist` / `health` (`mode: "percent"`): puntos porcentuales (`20` para `+20 %` AD de `Riven R`, `40` para `+40 %` AD de `Aatrox R`).
  - `damage_taken_modifier`: `mode: "percent"` en puntos porcentuales (`55..75` en `Alistar R`); `mode: "flat"` en daño plano con `damage_reduction_cap` en fracción decimal (`0,5` en `Leona W`).
  - `damage_dealt_heal`, `recent_damage_heal` y `recent_damage_shield`: `formula` en puntos porcentuales (`25..150` % del daño infligido o recibido); cuando la habilidad declara `min_formula` (como `Mordekaiser W`, `5 %` vida máx.), se aplica siempre ese suelo mínimo aunque no haya daño previo almacenado.
  - `invulnerable`: `mode: "invulnerable"` anula el daño recibido durante la ventana; `mode: "undying"` impide que la vida baje del suelo calculado por `formula` (`Tryndamere R`: `30/50/70`).
- **Vida que falta dinámica:** las fórmulas pueden referenciar `{"op": "stat", "stat": "health", "scope": "missing_fraction"}` junto a `scope: "max"`. En `survive`, las curaciones instantáneas se evalúan en el instante en que se disparan (proactiva si el defensor empieza herido o reactiva tras recibir el primer golpe no letal); en `rotation`, `missing_fraction_health` vale `0` por defecto y puede fijarse mediante `--input champion_missing_health_fraction=<0..1>`.

## 3. Integración en motor y herramientas (`Calculado`)

- **En `rotation`:**
  - Las habilidades puramente utilitarias sin casos de daño (`cases: []`, como `Garen W`, `Lux W`, `Tristana Q`, `Vayne R`, `Aatrox R`, `Mordekaiser W`) se pueden lanzar como pasos normales (`W`, `Q`, `R`), pagando su coste, respetando enfriamientos en `--timeline`, cargando Hoja encantada y disparando pasivas `after_ability`.
  - Los escudos emiten `ShieldEvent` y activan Golpe de escudo (`data:rune:8401`); las curaciones y `damage_dealt_heal` emiten `HealEvent`; los `recent_damage_shield` con suelo mínimo (`Mordekaiser W`) aplican su mínimo garantizado (y aceptan `--input <input_name>` si se desea simular daño almacenado previo); los `stat_bonus` temporales se inyectan en `_set_moment` con expiración exacta en `--timeline`.
  - En habilidades cuyo daño crece por ataques esquivados o daño sufrido (`Jax E`, `Sett W`), el caso base (`min`, `center_base`) aplica siempre la cantidad mínima (0 esquivas / 0 Coraje) junto al escalado del kit, manteniendo disponible el caso máximo (`max`, `center_max_grit`).
- **En `survive` y `optimize --objective time_to_die`:**
  - `--defender-cast <slot>[.<caso>][=<rango>]` (repetible; `defender_casts` en `contract` y `mcp`) y `--learned` activan las defensas del defensor.
  - Se evalúan en orden: negaciones (`invulnerable`, `dodge_attacks` sobre `attack`/`crit`, `spell_shield` sobre `ability`, `block_first_hit` en el primer golpe), mitigación con armadura/RM dinámicas, reducciones porcentuales (sin afectar al daño verdadero), reducciones planas con tope, absorción de escudos (`normal`/`magic`/`physical`), suelo de inmortalidad (`Tryndamere R`), registro de daño reciente para `recent_damage_shield` (`Sett W`, `TahmKench E`, `Mordekaiser W`) y `recent_damage_heal` (`Rengar W`, `DrMundo W`), y *HoT* continuos en `--timeline`.

## 4. Limitaciones

- **Sin decaimiento continuo ni interrupción de canalizaciones:** las velocidades de movimiento decrecientes (`Ahri W`, `Draven W`, `Blitzcrank W`) se modelan por su valor inicial durante su duración, y las canalizaciones (`MasterYi W`, `Janna R`, `Briar E`) asumen duración completa sin interrupción por CC.
- **Sin geometría 2D ni ángulos:** la dirección frontal de `Pantheon E` y `Braum E`, la distinción proyectil vs área no-proyectil (`Yasuo W`, `Braum E`), el retardo de caída de `Taric R` (`2,5 s`) y el número de enemigos cercanos (`Darius Q`, `JarvanIV W`, `Jax R`, `Shyvana W`, `Swain R`) se documentan en `condition` y se evalúan bajo el supuesto estándar de enfrentamiento directo (1 objetivo / golpe frontal).
