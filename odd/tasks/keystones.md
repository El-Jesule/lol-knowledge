# Piedras angulares ofensivas en rotaciones — fase 40

- **Objetivo:** completar `RUN-04` ([hoja de ruta](../roadmap.md), prioridad `DEC-01`) modelando en `rotation` las 11 piedras angulares ofensivas del cliente 16.23 y clasificando las 6 restantes según las mecánicas pendientes de las que dependen.
- **Rama:** `feat/keystones`, desde `dev`.
- **Entorno de validación:** Windows con `.\.venv\Scripts\python.exe` (Python 3.14).

## Decisiones

1. **Módulo dedicado `src/lol_knowledge/rune_keystones.py`:** separado de `rune_combat.py` y coordinado a través de `RuneCombat` para mantener `rotation.py` acotado.
2. **Cifras del cliente 16.23 y discrepancias declaradas:**
   - `LethalTempo` a distancia: el bin 16.23 publica 4 % (`TTASPerStackRanged`) frente a 4,8 % (`ASPerStack`) y 24 (`TTMaxNoteDamageRanged`) frente a 20 (`NoteDamage`); se usan los valores del tooltip y se marcan `Pendiente de verificación`.
   - `PressTheAttack` y `Conqueror`: sin curva por nivel en el bin; niveles 1 y 18 son `Derivado`, niveles 2–17 se interpolan linealmente como `Pendiente de verificación`.
   - `HailOfBlades`: usa la curva `{ee18a47b}` sin descifrar; niveles 1 y 18 son `Derivado`, niveles 2–17 quedan `Pendiente de verificación`.
   - `ArcaneComet`: amplificación por distancia (`comet_distance`) `Derivado` en los extremos (`0` y `≥ 750`) y `Pendiente de verificación` en distancias intermedias.
   - `SummonAery`: dispara una vez; si hay un segundo golpe dañino advierte que el retorno depende de la distancia y marca `Pendiente de verificación`.
3. **Sin doble amplificación en `FirstStrike`:** el +7 % de daño verdadero sobre el daño posmitigación del paso se emite con `apply_modifiers=False` para no volver a multiplicar por modificadores ya aplicados al paso.
4. **Quemadura continua de `DeathfireTouch`:** integrada en `_accrue`, dividiendo automáticamente el tramo en `started_at + 3 s` (`TimeToAmp`) para aplicar +75 % a partir del segundo 3 continuo.
5. **Curación de `Conqueror` al máximo (12 acumulaciones):** se integra en `_healing` (8 % cuerpo a cuerpo, 5 % a distancia sobre daño posmitigación a campeones) y se muestra en `rotation_report.py` aunque no haya robo de vida ni omnivampirismo en los objetos.

## Cambios

- Nuevo `src/lol_knowledge/rune_keystones.py`: `RuneModifier`, `RuneProc`, `DelayedRuneProc`, `RuneStatBonus`, `KeystoneCombat`.
- `src/lol_knowledge/runes.py`: `COMBAT_KEYSTONE_KEYS` y `COMBAT_RUNE_KEYS`.
- `src/lol_knowledge/rune_combat.py`: delegación de piedras angulares a `KeystoneCombat`.
- `src/lol_knowledge/rotation.py`: `ap_weight`, `apply_modifiers`, bonificaciones temporales de runas en `_set_moment`, curación de Conquistador en `_healing`, quemadura continua de Toque de muerte ígnea en `_accrue` y `on_step_complete` para Cosecha oscura y Primer golpe.
- `src/lol_knowledge/rotation_report.py`: mostrar sección de curación cuando `outcome.healing > 0`.
- `src/lol_knowledge/cli.py`: paso de `ap_weight` a `evaluate_rotation` y ayuda actualizada de `--rune`.
- Reglas y docs: [`lol-knowledge/mechanics/runes.md`](../../lol-knowledge/mechanics/runes.md), [`README.md`](../../README.md), [`odd/roadmap.md`](../roadmap.md).
- Pruebas: nuevo `tests/test_rune_keystones.py` y actualización de fixtures de runas no modeladas en `tests/test_runes.py` y `tests/test_rune_combat.py`.

## Limitaciones

- Las 6 piedras angulares restantes (`FleetFootwork`, `PhaseRush`, `GlacialAugment`, `UnsealedSpellbook`, `Aftershock`, `Guardian`) y 15 runas menores dependen de mecánicas pendientes (`MEC-01/04/05/07/08/26/27/29`, `DAT-06`, `OBJ-04/12`) y siguen marcando `Pendiente de verificación`.
- `HailOfBlades` sobrepasa el límite de 3,0 de velocidad de ataque en partida; la hoja mantiene hoy el tope de 3,0.
- Sin runas para el campeón objetivo.
