# Fase 53 — Objetos prioritarios (`OBJ-02`, `OBJ-01` lote 1, `OBJ-08` y `MEC-31`)

- **Parche:** `16.23.1` (`data/current/manifest.json`)
- **Fuentes:** Data Dragon (`data/current/items.json`, `Oficial`), cliente `16.23.8399929` (`lol-knowledge/derived/item-effects.json`, `Derivado`) y `wiki.leagueoflegends.com` (`Module:ItemData/data` rev `4095269`, secundaria de corroboración).
- **Fecha de consulta:** 2026-11-21.
- **Estado:** completada.

## Qué se implementó

1. **Hoja de estadísticas (`src/lol_knowledge/stats/sheet.py`, `src/lol_knowledge/formula/schema.py`):**
   - Evaluación en dos pasadas de `build_stat_sheet`: los efectos `always` de conversión estadística-a-estadística (`stat_modifier`) leen `base_*`, `bonus_*` y totales resueltos tras las estadísticas planas de objetos y `extras`, y antes de amplificadores de total como Sombrero mortal de Rabadon (`3089`).
   - Protección para campeones sin maná (`mana = 0`, `bonus_mana = 0`, `base_mana = 0`) en fórmulas de conversión.
   - Nuevas estadísticas aceptadas en fórmulas de objetos: `omnivamp`, `basic_ability_haste` y `ultimate_haste`.
   - Los efectos `stat_modifier` con `model_status: excluded` (p. ej. `2501 retribution`) quedan registrados como aporte `0` con etiqueta `Pendiente de verificación` sin romper la construcción de la hoja.

2. **Motor de rotaciones y defensa (`src/lol_knowledge/rotation.py`, `src/lol_knowledge/rotation_report.py`, `src/lol_knowledge/defense.py`, `src/lol_knowledge/objects/schema.py`, `src/lol_knowledge/objects/validate.py`):**
   - Nuevo disparador `on_damage` y soporte de `cast` en efectos con duración (`TIMED_TRIGGERS`) y quemaduras (`BURN_TRIGGERS`).
   - Nuevos campos validados en componentes de catálogo: `secondary_only`, `max_targets`, `echo`, `repeats_on_hit`, `can_crit` y `shield_type`.
   - Procs de habilidad con distribución de ecos (`6655` Eco de Luden: `6` cargas, `20 %` por eco sobrante sobre el objetivo principal, `12 s` CD).
   - Procs `on_damage` con combo de N golpes en ventana y escudo simultáneo (`6692` Eclipse: `2` golpes en `2 s`, `6 s` CD, daño `%` vida máxima + escudo de `2 s`) y procs por enfriamiento (`3145` Alternador hextech, `3144` Honda de explorador con reducción de `1 s` por ataque en `--timeline`).
   - Ataques/impactos solo sobre objetivos secundarios (`hits_primary = False`): `3085` Huracán de Runaan (`60 %` DA hasta `2` secundarios, crítico, repite efectos al impactar y robo de vida) y `Hender` de `3748` Hidra titánica, `3074` Hidra voraz (con robo de vida), `6631` Cortasendas, `6698` Hidra profana y `3077` Tiamat.
   - Acumulaciones de daño de habilidad (`3161` Lanza de Shojin `Voluntad centrada`: `+3 %` por habilidad dañina hasta `4` cargas, ventana `6 s`, `source: ability`).
   - Quemaduras `on_damage` activables con ataques o habilidades y escalado por tipo de objetivo (`3068` Égida de fuego solar, `6660` Rescoldo de Bami, `6664` Fulgor vano).
   - `Lifeline` generalizado en `defense.py`: distingue `shield_type: magic` (`3156` Fauces de Malmortius, `3155` Sorbemaleficios) frente a `normal` (`6673` Arcoescudo inmortal, `3053` Calibrador de Sterak) y resuelve `by_holder_range` según `attackrange` del defensor.

3. **Catálogo curado (`lol-knowledge/objects/catalog.json`, `catalog_version: 23`):**
   - **32 objetos** añadidos/curados (de `43` a `75` entradas curadas en `catalog.json`; en el modelo combinado de `218` objetos, `119` pasan a `effect_review: complete` y `99` quedan `pending`):
     - `OBJ-02`: `6655` Eco de Luden, `6692` Eclipse.
     - Salpicadura secundaria: `3085`, `3748`, `3074`, `6631`, `6698`, `3077`.
     - Procs `on_damage`: `3145`, `3144`.
     - Auras / quemaduras (`OBJ-08`): `3068`, `6660`, `6664`, `4633`, `8020`.
     - Conversión estadística y aceleración (`MEC-31`): `2501`, `3003`, `3004`, `3119`, `3161`, `3073`, `2512`.
     - Utilidad / Heridas graves: `3046`, `3033`, `3165`, `6609`, `3123`, `3916`.
     - Supervivencia (`Lifeline` / `Thorns`): `6673`, `3156`, `3155`, `3076`.

## Limitaciones declaradas

- Las activas de objeto (`Creciente`, `Creciente voraz`, `Creciente titánico`, `Onda de choque`, `Cuchillada sacrílega`), `Desolación` al matar (`6664`), `Retribución` por vida faltante del atacante (`2501`) y `Andanada inicial` (`2512`) se declaran explícitamente como `excluded` y mantienen la etiqueta `Pendiente de verificación` cuando participan en daño.
- Quedan `99` objetos comprables de la Grieta con `effect_review: pending` en `catalog-stats.json` (principalmente objetos de soporte/enchanter, tanques reactivos y pasivas situacionales).
