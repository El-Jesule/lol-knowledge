# Automatización de kits y pasivas de campeón — fase 45

- **Objetivo:** completar `CH-02` (automatización de borradores de especificación y compilación de kits desde el bin) y `CH-03` (pasivas de campeón declarativas en la hoja de estadísticas y en las rotaciones), cerrando además `CH-Z-01` (Determinación de Zaahen) y `CH-A-01` (curaciones de Robo de esencias de Ahri).
- **Rama:** `feat/kit-automation-and-passives`, creada desde `dev` (`de3d9a8`).
- **Entrega:**
  - `src/lol_knowledge/formula/schema.py` y `core.py`: operador exacto `linear_by_level` en `ABILITY_OPS` (`min + (max - min) × (nivel - 1) / 17` en `Fraction`).
  - `src/lol_knowledge/kit/model.py`: `PassiveEffectSpec` (`stat_bonus`, `stacking_stat`, `heal`, `damage_proc`) en `lol-champion-kit/1`.
  - `research/binmodel/kitgen.py`: traducción de `by_char_level_interpolation`, `{ee18a47b}` (`by_char_level_named_data_values_interpolation`), `by_char_level_breakpoints`, `by_char_level_formula`, `sum`, `product`, multiplicadores de `GameCalculation`, `passive_effects` (con `scale` y ajustes desde `DataValues`) y `cost`, escribiendo en LF.
  - `research/binmodel/specdraft.py`: generador automático de borradores `spec.json` + informe de curación (`dual_damage_type`, `tooltip_data_value_damage`, `recast_detected`, `omitted_mstat_default`, `uncorroborated_stat`, `untranslatable_node`, `healing_or_shield_calc`, `passive_stat_candidate`, `health_cost_needed`).
  - `src/lol_knowledge/passives.py`: `sheet_passive_effects` y `PassiveCombat`, integrados en `cli.py` (`stats`, `ability`, `rotation`) y `rotation.py`.
  - Recompilación desde los fixtures de `lol-knowledge/champions/Zaahen/kit.json` (Determinación) y `lol-knowledge/champions/Ahri/kit.json` (Robo de esencias).
  - Documentación en `lol-knowledge/mechanics/passives.md` y pruebas en `tests/test_passives.py` y `research/tests/test_binmodel_specdraft.py`.

## Decisiones de diseño

1. **Motor 100 % dirigido por datos (`kit.json`):** `src/lol_knowledge/passives.py` no contiene nombres de campeón; cualquier campeón futuro de `CH-01` declara sus pasivas en su `spec.json` y se compila con `kitgen`.
2. **Aritmética exacta para curvas lineales 1–18:** `linear_by_level` evita el redondeo de guardar 18 floats en `by_level` cuando el paso no es decimal exacto (`90/17` en Ahri P, `0,013/17` en Zaahen P).
3. **Borradores compilables a la primera:** `specdraft` genera un `spec.json` válido que ya compila en `kitgen` y separa las decisiones de curación en `review.findings`.
4. **Coherencia con acumulaciones de combate:** `stacking_stat` empieza en `0` en `rotation` (o en `--input <input_name>` si se pasa) y solo se incluye en `stats`/`ability` cuando el usuario proporciona `--input <input_name>`.

## Limitaciones

Ver [`lol-knowledge/mechanics/passives.md`](../../lol-knowledge/mechanics/passives.md) §Fuera de alcance y la [hoja de ruta](../roadmap.md).
