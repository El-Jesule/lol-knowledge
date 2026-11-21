# Tarea: Resolución de mecánicas surgidas en las oleadas de campeones (CH-01 / CH-04)

- **Fase:** 50
- **Fecha:** 2026-11-21
- **Parche y fuentes:** Data Dragon `16.23.1` (`data/current/manifest.json`), cliente instalado `16.23.8406595+branch.releases-16-23.content.release` (`<Game>/DATA/FINAL/Champions/<Id>.wad.client` + `Localized/Global.es_ES.wad.client`) y `wiki.leagueoflegends.com` (consultado el 2026-11-21).
- **Rama de tarea:** `feat/champion-wave-mechanics`

## 1. Objetivo

Resolver en el extractor (`research/binmodel/`), el compilador de kits (`research/binmodel/kitgen.py`), el evaluador de fórmulas (`src/lol_knowledge/formula/`) y las especificaciones curadas (`research/kits/<Id>.spec.json`) las 7 familias de mecánicas de cálculo que surgieron durante las 4 oleadas de kits de campeones (`CH-01`), actualizando y recompilando los **43 kits afectados** sobre el cliente `16.23`:

1. **`EffectValueCalculationPart` (`mSpell.mEffectAmount`):**
   - `extract_effect_amounts` en [`research/binmodel/traverse.py`](../../research/binmodel/traverse.py) e integrado en [`research/binmodel/extract.py`](../../research/binmodel/extract.py) extrae las tablas indexadas `mSpell.mEffectAmount` como `DataValue` con `mode="effect_amount"` y nombre `Effect{i}Amount` (1-indexado).
   - [`research/binmodel/kitgen.py`](../../research/binmodel/kitgen.py) traduce `kind == "effect_value"` (y `{"op": "effect_amount", "index": i}` en fórmulas curadas) a `constant` o `by_rank`.
   - Campeones actualizados (6): `Chogath` (W), `Fizz` (Q), `JarvanIV` (E), `Kaisa` (W), `Khazix` (Q normal + aislado, W, E) y `Velkoz` (R).
2. **`ByCharLevelBreakpointsCalculationPart` con `mLevel1Value` omitido (`0.0` por defecto en `.bin`):**
   - [`research/binmodel/traverse.py`](../../research/binmodel/traverse.py) registra `"level1_value"` en `absent_fields` cuando `mLevel1Value` se omite en el `.bin`, activando `default_policy = "lol-bin-omitted-float-defaults/v1"`.
   - [`research/binmodel/kitgen.py`](../../research/binmodel/kitgen.py) (`_breakpoints_formula`) toma `level1 = 0.0` cuando `default_policy == "lol-bin-omitted-float-defaults/v1"` y existen tramos numéricos.
   - Campeones actualizados (3): `Azir` (W), `Mordekaiser` (Q normal + aislado) y `Heimerdinger` (Q disparo + láser).
3. **`AbilityResourceByCoefficientCalculationPart` (escalado por maná):**
   - [`research/binmodel/traverse.py`](../../research/binmodel/traverse.py) traduce `AbilityResourceByCoefficientCalculationPart` (`mAbilityResource` omitido o `0` = maná) a `stat_scaled` con `stat = "mana"` y `formula` (`total`, `base`, `bonus`).
   - Campeones actualizados (3): `Ryze` (Q, W, E con `+2 % / +3 % / +2 %` maná adicional), `Kassadin` (R base `+2 %` maná máximo y por carga `+1 %` maná máximo) y `Blitzcrank` (R rayo pasivo `+2 %` maná máximo).
4. **Tipo `{b22609db}` (progresión lineal por nivel nombrada sin tramos):**
   - [`research/binmodel/traverse.py`](../../research/binmodel/traverse.py) traduce `{b22609db}` (`{91d404a5}` valor a nivel 1 + `{b2cd0eb0}` incremento por nivel) a `by_char_level_named_breakpoints` sin tramos intermedios.
   - Campeón actualizado (1): `Irelia` (P `OnHitBonus`: `10 + 3 × (nivel - 1) + 20 % DA adicional` y `SingleStackAS` por acumulación en `passive_effects`).
5. **Nuevos `mStat` corroborados (`4` `attack_speed`, `7` `move_speed`, `8` `critical_strike_chance`, `9` `critical_strike_damage`, `18` `life_steal`, `29` `lethality`):**
   - Corroborados en [`research/binmodel/stats.py`](../../research/binmodel/stats.py), habilitados en [`src/lol_knowledge/formula/schema.py`](../../src/lol_knowledge/formula/schema.py) (`attack_speed_bonus/total` y `move_speed` `base`/`bonus`/`total`) y traducidos en [`research/binmodel/kitgen.py`](../../research/binmodel/kitgen.py) (`critical_strike_chance/total` → `crit_chance/total`, `critical_strike_damage/bonus` → `crit_damage_bonus/total`, `critical_strike_damage/total` → `2 + crit_damage_bonus/total`, `attack_speed/bonus` → `attack_speed_bonus/total`, `lethality/bonus` → `lethality/total`).
   - Campeones actualizados (16): `TwistedFate` (W cartas azul/roja/dorada), `Pyke` (R daño físico con letalidad), `Hecarim` (P), `Janna` (P y W con velocidad de movimiento adicional), `Katarina` (R dagas físicas con DA y velocidad de ataque), `Zeri` (P descarga máxima y W láser crítico por muro), `Gangplank` (Q crítica), `Yasuo` (Q crítica), `Yone` (Q crítica), `Talon` (Q crítica cuerpo a cuerpo), `MasterYi` (Q crítica 4 impactos), `Caitlyn` (P Disparo a la cabeza y R con crítico), `MissFortune` (Q rebote crítico y R oleada crítica), `Samira` (Q crítica), `Lucian` (R total escalada con crítico) y `Rell` (W aterrizaje y volteo).
6. **`BuffCounterByCoefficientCalculationPart` y `BuffCounterByNamedDataValueCalculationPart` (escalado por cargas `--input`):**
   - [`src/lol_knowledge/formula/core.py`](../../src/lol_knowledge/formula/core.py) admite la clave opcional `"default"` en `{"op": "input", "name": ..., "default": 0}` para que los contadores de cargas evalúen a `0` cargas por defecto y escalen de forma exacta al pasar `--input <nombre>=N`.
   - [`research/binmodel/traverse.py`](../../research/binmodel/traverse.py) y [`research/binmodel/kitgen.py`](../../research/binmodel/kitgen.py) traducen ambos tipos de `BuffCounter` a `input` con `default: 0`.
   - Campeones actualizados (9): `Nasus` (Q normal y crítica con `--input siphoning_strike_stacks`), `Chogath` (E con `--input feast_stacks`), `Draven` (R ida y vuelta), `Thresh` (E pasiva con `--input souls`), `AurelionSol` (Q estallido con `--input stardust_stacks`), `Kindred` (W y E con `--input kindred_marks`), `Smolder` (Q `tier3_burn` con `--input dragon_practice_stacks`), `Swain` (P `+15` vida por `--input soul_fragments`), `Sona` (P `+0,5` velocidad de habilidades por `--input accelerando_stacks`) y `Garen` (P/W `+0,2` armadura y RM por `--input courage_stacks`).
7. **Casos multiforma y referencias cruzadas entre ranuras/tooltips en `kitgen.py`:**
   - [`research/binmodel/kitgen.py`](../../research/binmodel/kitgen.py) expande inclusiones `{{tooltip_key}}`, acepta `"tooltip"` y `"ability"` por caso/parte/efecto pasivo y resuelve referencias de etiqueta de daño sin sensibilidad a mayúsculas.
   - Campeones actualizados (5): `Gnar` (Mega Gnar Q/W/E), `RekSai` (Q enterrada), `Nidalee` (Puma Q/W/E en R), `Elise` (forma de araña al impactar y arañita en R) y `Yunara` (P amplificación crítica y R+W `transcendent_w`).

## 2. Verificación ejecutada

- `.\.venv\Scripts\python.exe -m pytest -q`
- `.\.venv\Scripts\python.exe -m pytest research/tests -q`
- `.\.venv\Scripts\python.exe -m ruff check .`
- `.\.venv\Scripts\python.exe -m ruff format --check .`
- `.\.venv\Scripts\python.exe -m lol_knowledge validate`
- `.\.venv\Scripts\python.exe research\tools\refresh_patch.py --game "D:\Games\Riot Games\League of Legends\Game" --hashes "research\.cache\hashes"` (`0` diferencias en los 173 kits).
