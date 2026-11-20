# Tarea — Fase 41: Verificación documental de runas, `{ee18a47b}` y mecánicas (`MEC-13`, `OBJ-06`)

- **Fecha:** 2026-11-20
- **Parche de referencia:** cliente `16.23` (`16.23.8399929+branch.releases-16-23.content.release`) y Data Dragon `16.23.1`.
- **Fuente contrastada:** API MediaWiki oficial de `wiki.leagueoflegends.com` (comprobando `V26.23` rev `4096203`: sin cambios en runas y solo `Voltaic Cyclosword` en objetos de la Grieta).

## Hallazgos resueltos en código y documentación

1. **Decodificación exacta de `{ee18a47b}` (hash FNV-1a 32 bits):**
   - `{ee18a47b}` = `ByCharLevelNamedDataValuesInterpolationCalculationPart`.
   - `{0589a59c}` = `StartDataValue`, `{0b65bc23}` = `EndDataValue`, `{f4e470e6}` = `ScaleByStatProgressionMultiplier` (ausente = `False`, interpolación lineal 1–18), `{032a393a}` = `ScalePastDefaultMaxLevel`.
   - Corroborado en `Template:Rune_data_Hail_of_Blades` (rev `4060661`) y `Template:Data_Zaahen/Cultivation_of_War` (rev `4060321`, que además coincide con el `2,8 %` del cliente 16.23 para `CH-Z-01`).
2. **Corrección de `LethalTempo` (`8008`) a distancia:**
   - El cliente `16.23` declara en `calculations`: `ASPerStack` = `0,06 × 0,8 = 0,048` (`4,8 %`/acumulación, `28,8 %` al máximo) y `NoteDamage` = `(9..30) × 0,667` (`6,003..20,01`).
   - `Lethal_Tempo` (rev `4060427`) y `Template:Rune_data_Lethal_Tempo` (rev `4065934`) corroboran que esos valores son los reales en partida y que `TTASPerStackRanged` (`4 %`, sin actualizar desde V14.19/V14.21) y `TTMaxNoteDamageRanged` (`24`, multiplicado por `0,8` por error) son errores conocidos del texto de lobby.
   - `Rune` ahora expone `ranged_multipliers` leídos directamente de `lol-knowledge/derived/runes.json`, y `LethalTempo` a distancia pasa a `Derivado`.
3. **Corrección de `ArcaneComet` (`8229`):**
   - `V26.09` (rev `4050133`), `Arcane_Comet` (rev `4024412`) y el tooltip real del cliente `16.23` confirman que el reembolso de enfriamiento al golpear con habilidades se **eliminó** en V26.09 (`PercentRefund = 0,2` en `effect_amounts` es legado).
   - `Template:Rune_data_Arcane_Comet` (rev `4060639`) corrobora la rampa lineal `0–100 %` en `0–750` unidades; todas las distancias pasan a `Derivado`.
4. **Curvas lineales 1–18 corroboradas (`Derivado`):**
   - `PressTheAttack` (`8005`, rev `4015574`), `Conqueror` (`8010`, rev `4060685`), `HailOfBlades` (`9923`, rev `4060661` + `{ee18a47b}`) y fragmento `HealthScaling` (`5001`, `Rune` rev `4094440`: `10 × nivel`).
5. **`SummonAery` (`8214`):**
   - Se mantiene el comportamiento conservador de 1 impacto sin geometría (corroborado por rev `4062237`) y se añade `--input aery_return_seconds=<s > 0>` opcional para modelar repeticiones en `--timeline`.
6. **`MEC-13` (Placas vs daño al impactar) cerrado:**
   - `Plated_Steelcaps` (rev `4022248`) confirma que Placas no reduce efectos al impactar (`on-hit`). `rotation.py` deja de degradar esas partes a `Pendiente de verificación`.
7. **`OBJ-06` (Tope de Liandry contra monstruos) cerrado:**
   - `Module:ItemData/data` (`Liandry's Torment`, rev `4095269`) corrobora que `MonsterDamageCap = 40` del cliente `16.23` es `40/s` (20 por tic de 0,5 s, 120 en 3 s). `6653 torment-monsters` pasa a `evaluable` en `catalog.json` (versión 19) y `_burns` aplica `self._limited` en `rotation.py`.
8. **Evidencia anotada en [`odd/roadmap.md`](../roadmap.md) para próximas fases:**
   - `OBJ-02` (Luden 1 + 5×20 % cada 0,25 s; Sterak `mStat 2 = 50 % DA base` y `mStat 12 = 60 % vida adicional`), `OBJ-03` (Statikk alcanza al objetivo y rebota, ahora Vigor), `OBJ-05` (Guinsoo interactúa con Kraken, duración 4 s), `MEC-22` (suelo exacto `0,2` ataques/s) y `CH-Z-01` (Zaahen `1,5–2,8 %` AD lineal 1–18).
