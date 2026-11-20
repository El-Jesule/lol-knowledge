# Runas menores de estadísticas — fase 38

- **Objetivo:** primera entrega del resto de `RUN-04` ([hoja de ruta](../roadmap.md), prioridad decidida en `DEC-01`): modelar en la hoja de estadísticas las runas menores que otorgan estadísticas y separar las estrictamente no-combate.
- **Rama:** `feat/minor-rune-stats`, desde `dev`.
- **Entorno de validación:** Windows con `.\.venv\Scripts\python.exe` (Python 3.14).

## Decisiones

1. **Permanentes con tope fijo al máximo por defecto:** siguiendo [`combat-stacks.md`](../../lol-knowledge/mechanics/combat-stacks.md), las runas con acumulaciones permanentes y tope fijo (`LegendAlacrity`, `LegendHaste`, `LegendBloodline`, `ManaflowBand`, `UltimateHunter`, `BiscuitDelivery`) usan por defecto el escenario `maximum stacks`, con sobrescritura opcional mediante `--input` (`legend_stacks`, `bounty_stacks`, `game_minutes`).
2. **Condicionales, por minuto o sin tope sin adivinar:** `GatheringStorm`, `Conditioning`, `Overgrowth`, `AbsoluteFocus` y `Waterwalking` requieren `--input` explícito (`game_minutes`, `overgrowth_units`, `attacker_health_percent`, `in_river`). Si falta, la runa permanece en `pending_effects` indicando la clave necesaria.
3. **Aceleración básica y de definitiva separadas (`MEC-29` parcial):** se añaden `basic_ability_haste` (Q, W, E) y `ultimate_haste` (R) al registro y a `ability_cooldowns` para que `LegendHaste` y `UltimateHunter` ajusten solo sus ranuras y funcionen también en `rotation --timeline`.
4. **Celeridad prudente:** el +1 % de velocidad de movimiento es `Derivado`; el +7 % de eficacia sobre otras bonificaciones planas y porcentuales se marca `Pendiente de verificación` porque no se ha medido en partida el orden exacto ni si amplifica su propio 1 %.
5. **No-combate fuera de `pending_effects`:** las 7 runas menores estrictamente de visión, oro, abalorios (`DEC-03`), velocidad fuera de combate o sustitución de Destello pasan a notas informativas y no degradan la etiqueta de daño.

## Cambios

- `src/lol_knowledge/stats/registry.py`, `metrics.py`, `report.py`: `basic_ability_haste` y `ultimate_haste` aplicados a Q/W/E y R en enfriamientos e informes.
- `src/lol_knowledge/stats/data.py`: `ItemData.unmodelled_stats` para que `JackOfAllTrades` cuente `heal_shield_power` e ignore oro cada 10 s.
- `src/lol_knowledge/stats/sheet.py`, `__init__.py`: `StatAmplifier`, `extra_amplifiers`, `extra_notes` y `move_speed_bonus_amp`.
- `src/lol_knowledge/objects/legality.py`: `ItemGroups.has_boots` para `MagicalFootwear`.
- `src/lol_knowledge/runes.py`: `RuneEffects`, `needs_adaptive_stat` y `minor_rune_effects` (15 runas menores de estadísticas + 7 no-combate).
- `src/lol_knowledge/cli.py`: `--input NAME=VALUE` en `stats` y cableado común de runas menores en `stats`, `ability` y `rotation`.
- Reglas y docs: [`lol-knowledge/mechanics/runes.md`](../../lol-knowledge/mechanics/runes.md), [`lol-knowledge/mechanics/ability-haste.md`](../../lol-knowledge/mechanics/ability-haste.md), [`README.md`](../../README.md), [`odd/roadmap.md`](../roadmap.md).
- Pruebas: `tests/test_runes.py` y `tests/test_stats_metrics.py`.

## Limitaciones

- Las 23 runas menores de combate/curación/defensa/recursos/consumibles quedan para la fase 39 (o sus `MEC-*`) y las 17 piedras angulares para la fase 40.
- Sin runas para el campeón objetivo.
- Celeridad (+7 % de eficacia) y el límite exacto `0,7` de Concentración absoluta quedan `Pendiente de verificación` hasta medición en partida.
