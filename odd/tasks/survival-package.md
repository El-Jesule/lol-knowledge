# Tarea — Fase 42: Paquete de supervivencia (`MEC-04` a `MEC-07`)

- **Fecha:** 2026-11-20
- **Parche de referencia:** cliente `16.23` y Data Dragon `16.23.1`.
- **Regla publicada:** [`lol-knowledge/mechanics/survival.md`](../../lol-knowledge/mechanics/survival.md).

## Alcance implementado

1. **Poder de curaciones y escudos (`MEC-07`):**
   - Nueva estadística aditiva `heal_and_shield_power` en `stats/registry.py`, `formula/schema.py` y `objects/schema.py`.
   - `objects/generate.py` extrae «poder de curaciones y escudos» como estadística del motor y `catalog-stats.json` se regenera con los 7 objetos de enchanter en `stats` (`218 items, 141 stats`).
   - `Revitalize` (`8453`) suma `+5 %` permanente en la hoja y `+10 %` multiplicativo en `rotation` por debajo del 40 % de vida del atacante.
2. **Escudos (`MEC-04`):**
   - `Target` y CLI admiten `--target-shield` y `--target-shield-type normal|physical|magic`.
   - Absorción posmitigación en `survival.py` / `rotation.py` sin alterar fórmulas de vida ni ejecuciones (`execute` atraviesa escudos).
   - `ShieldEvent` para escudos del atacante (escalados con `heal_and_shield_power` y `Revitalize`, inmunes a Heridas graves), alimentando automáticamente a `ShieldBash` (`8401`).
3. **Heridas graves (`MEC-06`):**
   - Reducción `-40 %` no acumulable sobre toda curación (robo de vida, omnivampirismo, drenaje y curaciones directas de efectos; nunca sobre escudos).
   - Activable por escenario (`--input grievous_wounds=1`) o automáticamente al atacar a un objetivo campeón con `3075` Malla de espinas (antes de la curación del ataque disparador, duración `3 s` en `--timeline`).
4. **Curaciones de efectos y vida del atacante (`MEC-05`):**
   - `HealEvent` para curaciones directas de objetos (`2510` `dusk-heal` pasa a `evaluable` en `catalog.json` v20) y runas (`8437` Garras del inmortal, `8139` Sabor a sangre, `9101` Absorber vida, `9111` Triunfo, `8463` Fuente de vida).
   - Seguimiento de la vida del atacante y `effective_healing` acotada por vida perdida cuando se pasa `--input attacker_health_percent=<0..1>`.

## Pendiente para la fase siguiente (`MEC-09`)

- Simulación inversa (el objetivo ataca al campeón analizado: daño recibido, tiempo hasta morir y disparadores defensivos al recibir daño como `3053` Sterak, `8465` Protector, `8444` Fuerzas renovadas y `8473` Revestimiento de huesos).
