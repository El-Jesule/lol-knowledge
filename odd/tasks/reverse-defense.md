# Tarea — Fase 43: Simulación inversa (`MEC-09`), reducción plana (`MEC-08`) y Calibrador de Sterak (`3053`)

- **Fecha:** 2026-11-20
- **Parche de referencia:** cliente `16.23` y Data Dragon `16.23.1`.
- **Regla publicada:** [`lol-knowledge/mechanics/survival.md`](../../lol-knowledge/mechanics/survival.md).

## Alcance implementado

1. **Escalado desde estadísticas base (`MEC-31` parcial) y `3053` Calibrador de Sterak:**
   - `stats/sheet.py` resuelve `base_*` en efectos `always` `stat_modifier` del catálogo, con propagación de etiquetas.
   - `objects/schema.py` añade el evento disparador `taking_damage`.
   - `catalog.json` (versión 21) cura `3053` Calibrador de Sterak (`the-claws-that-catch`: `+50 %` DA base en la hoja; `lifeline`: escudo del `60 %` de vida adicional al bajar del `30 %` de vida máxima, 4,5 s, 90 s de enfriamiento).
2. **Reducción plana de daño (`MEC-08`) y simulación inversa (`MEC-09`):**
   - Nuevos módulos `src/lol_knowledge/defense.py` y `src/lol_knowledge/defense_report.py`, y subcomando CLI `python -m lol_knowledge survive`.
   - Dos modos de entrada: secuencia manual (`--incoming "attack:400, attack:crit:600, magic:300, true:150, wait:1"`) o rotación completa de un campeón enemigo (`--enemy-champion` + `--steps`).
   - Evalúa reducción plana (`8473` Revestimiento de huesos y `--input flat_damage_reduction`), escudos previos al daño (`3053` Salvavidas y `8465` Protector con `--input guardian_ally=0|1`), regeneración defensiva (`8444` Fuerzas renovadas, con Heridas graves e inmune a HSP/Revitalizar), reflejo reactivo (`3075` Malla de espinas), supervivencia, paso letal, tiempo hasta morir (`time_to_die`) y daño recibido por segundo (`damage_taken_per_second`).
   - Cierra por completo la sección 4.2 (**Defensa y supervivencia**) de `odd/roadmap.md` y eleva la cobertura de runas a **50/62 runas de árbol**.
