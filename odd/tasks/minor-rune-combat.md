# Runas menores de combate en rotaciones — fase 39

- **Objetivo:** segunda entrega del resto de `RUN-04` ([hoja de ruta](../roadmap.md), prioridad `DEC-01`): modelar las runas menores de combate evaluables en `rotation` sin inflar `rotation.py`.
- **Rama:** `feat/minor-rune-combat`, desde `dev`.
- **Entorno de validación:** Windows con `.\.venv\Scripts\python.exe` (Python 3.14).

## Decisiones

1. **Módulo dedicado `src/lol_knowledge/rune_combat.py`:** encapsula el estado y las reglas de las 8 runas menores de combate (`CoupDeGrace`, `CutDown`, `LastStand`, `NullifyingOrb`/Arcanólogo axiomático, `Scorch`, `CheapShot`, `SuddenImpact`, `Demolish`) con 4 puntos de enganche mínimos en `rotation.py`, preparando el mismo patrón para las piedras angulares de la fase 40.
2. **Separación entre `stats`, `ability` y `rotation`:** en `stats` las 8 runas de combate son notas informativas; en `ability` siguen en `pending_effects` (porque `ability` no evalúa efectos de combate y debe mantener `Pendiente de verificación`); en `rotation` salen de `pending_effects` y se evalúan activamente.
3. **Sin adivinar el estado de combate:** `LastStand` (`attacker_health_percent`), `NullifyingOrb` (`ultimate_aoe`, solo si hay un paso `R`), `CheapShot` (`target_impaired`) y `SuddenImpact` (`sudden_impact`) exigen `--input` explícito; si falta, pasan a `not_applied` y debilitan la etiqueta. Las runas específicas de campeón o estructura exigen `--target-kind` cuando pueden aplicarse y no debilitan si el objetivo es de otro tipo.
4. **Procs retardados en `--timeline`:** `Scorch` programa su impacto de daño mágico a `clock + 1 s` (`dotduration`) con enfriamiento de 10 s (`BurnlockoutDuration`), integrado en `_accrue` y en el vaciado final de la línea de tiempo (mecanismo reutilizable para Cometa arcano y otras piedras angulares).
5. **Curación en procs de runas (`kind: "rune"`):** no aplican robo de vida y sí aplican omnivampirismo contra campeones (wiki, R7 en `runes.md`).

## Cambios

- Nuevo `src/lol_knowledge/rune_combat.py`: `RuneModifier`, `RuneProc`, `DelayedRuneProc`, `RuneCombat`.
- `src/lol_knowledge/runes.py`: `COMBAT_MINOR_RUNE_KEYS`, `RuneEffects.combat_runes`, `combat_rune_notes` y utilidades compartidas de validación de `--input`.
- `src/lol_knowledge/rotation.py`: paso de `slot` a `_modifiers`, soporte `kind="rune"` en `_healing`, cola de procs retardados en `_accrue` y vaciado final, e integración de `RuneCombat` en `_Rotation` y `evaluate_rotation`.
- `src/lol_knowledge/cli.py`: `combat_context` en `_build_sheet` (`stats`, `ability`, `rotation`) y paso de runas a `evaluate_rotation`.
- Reglas y docs: [`lol-knowledge/mechanics/runes.md`](../../lol-knowledge/mechanics/runes.md), [`README.md`](../../README.md), [`odd/roadmap.md`](../roadmap.md).
- Pruebas: nuevo `tests/test_rune_combat.py` y ajuste de `--target-kind champion` en el test de timeline de `tests/test_runes.py`.

## Limitaciones

- Quedan 15 runas menores dependientes de mecánicas aún no construidas (`MEC-01` recursos, `MEC-04` escudos, `MEC-05` curación de efectos, `MEC-07` poder de curaciones/escudos, `MEC-08` reducción plana, `MEC-26` CC, `MEC-29` aceleración de objetos/invocador, `OBJ-12` consumibles) y las 17 piedras angulares (fase 40).
- El límite exacto `0,6` de Último esfuerzo (`<` frente a `<=`) queda `Pendiente de verificación` hasta medición en partida.
