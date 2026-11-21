# Tarea: Cierre de CH-04 — Reglas especiales de hoja y rotación por campeón

- **Fase:** 51
- **Fecha:** 2026-11-21
- **Parche y fuentes:** Data Dragon `16.23.1` (`data/current/manifest.json`), cliente instalado `16.23.8406595+branch.releases-16-23.content.release` (`<Game>/DATA/FINAL/Champions/<Id>.wad.client` + `Localized/Global.es_ES.wad.client`) y `wiki.leagueoflegends.com` (consultado el 2026-11-21).
- **Rama de tarea:** `feat/ch04-champion-mechanics`

## 1. Objetivo

Completar las reglas globales de hoja (`src/lol_knowledge/stats/sheet.py`), rotación (`src/lol_knowledge/rotation.py`) y kits (`research/kits/*.spec.json`) pendientes en `CH-04`:

1. **Velocidad de ataque especial por campeón ([`attack-speed.md`](../../lol-knowledge/mechanics/attack-speed.md)):**
   - **Bel'Veth (`BelvethPassive`):** elimina el tope de `3,0` ataques/s (`cap = None` en la hoja) y modela las acumulaciones permanentes de *Muerte en lavanda* (`AttackSpeedPerStack`: `0,1 %..1,8 %` VA adicional por carga mediante `--input lavender_stacks`).
   - **Zeri (`ZeriQ`):** fija el tope de `attack_speed` en `1,5` ataques/s (`AttackSpeedCap = 1.5`) y convierte el exceso de velocidad de ataque adicional sobre ese tope (`> 134,72 %` VA adicional) en daño de ataque adicional a razón de `0,6` DA por cada `1 %` de exceso (`ExcessAttackSpeedToADMult = 0.6`). Añade además el caso `uncharged_zap` (`10..25 + 3 % PH`) en `Zeri/kit.json`.
   - **Jhin (`JhinPassive`):** velocidad de ataque fija por nivel (`0,625 × (1 + 0,03 × growth_multiplier(nivel))`, `0,625` a nivel 1 hasta `0,94375` a nivel 18, inmune a la velocidad de ataque adicional externa porque `attackspeedratio = 0`), amplificador de DA total *Susurro* (`TotalADPercent = [4..44] % por nivel + 35 % de crit_chance + 30 % de attack_speed_bonus`), reducción del `25 %` al daño crítico total en `rotation.py` (`CritReductionPercent = 0.25`) y caso `fourth_shot_total` en `Jhin/kit.json`.
   - **Sion (`SionPassive` / `SionW`):** usa el tope normal de `3,0` ataques/s mientras está vivo (sin degradar la hoja a `Pendiente de verificación`) y modela las acumulaciones permanentes de vida máxima de *Horno del alma* (`+4` vida por `--input soul_furnace_small_kills` y `+15` vida por `--input soul_furnace_large_kills`).
   - **Graves (`GravesPassive`):** resuelve su velocidad de ataque entre disparos (`0,475 + 0,490 × attack_speed_bonus`) con nota informativa de recarga cada 2 cartuchos y modela los casos de escopeta de 1 perdigón, 4 perdigones (`SingleBulletDamage + 3 × MultiBulletDamage`) y 6 perdigones críticos (`(SingleBulletDamage + 5 × MultiBulletDamage) × (1 + CritDamageMult)`).
2. **Conversión de críticos de Ashe ([`critical-strike.md`](../../lol-knowledge/mechanics/critical-strike.md)):**
   - **Ashe (`AshePassive.mSpellCalculations.DamageBonus`):** sus ataques básicos (`attack` y `attack:crit`) en `rotation.py` multiplican el DA total por `1 + crit_chance × (1 + crit_damage_bonus)`, y sus impactos críticos (`critdamagemultiplier = 1.0`) duplican la ralentización sin añadir un segundo multiplicador de daño ni degradar la etiqueta a `Pendiente de verificación`.
3. **Amplificación de velocidad de movimiento de Cassiopeia ([`move-speed.md`](../../lol-knowledge/mechanics/move-speed.md)):**
   - **Cassiopeia (`CassiopeiaPassive.mSpellCalculations.PercentHasteMod`):** amplifica todas las bonificaciones planas y porcentuales de velocidad de movimiento en `5 % + 1,8 % × (nivel - 1)` (`5 %` a nivel 1 hasta `35,6 %` a nivel 18) directamente en la hoja (`Derivado` cuando hay bonificaciones, `Oficial` sin bonificaciones).
4. **Evoluciones y conversiones adicionales en kits (`Kai'Sa`, `Corki`):**
   - **Kai'Sa (`KaisaQ`):** casos de objetivo aislado con 6 misiles (`2,25 × TotalIndividualMissileDamage`) y evolucionado con 12 misiles (`3,75 × TotalIndividualMissileDamage`).
   - **Corki (`CorkiPassive`):** caso `true_bonus_crit` (`CriticalStrikeTOOLTIP`: `20 % DA × (2 + crit_damage_bonus)` de daño verdadero en ataques críticos).

## 2. Verificación ejecutada

- `.\.venv\Scripts\python.exe -m pytest -q`
- `.\.venv\Scripts\python.exe -m pytest research/tests -q`
- `.\.venv\Scripts\python.exe -m ruff check .`
- `.\.venv\Scripts\python.exe -m ruff format --check .`
- `.\.venv\Scripts\python.exe -m lol_knowledge validate`
- `.\.venv\Scripts\python.exe research\tools\refresh_patch.py --game "D:\Games\Riot Games\League of Legends\Game" --hashes "research\.cache\hashes" --retrieved-at 2026-11-19` (`0` diferencias en los 173 kits).
