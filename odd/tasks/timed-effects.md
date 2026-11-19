# Quemaduras en el tiempo y efectos con duración — fase 30

- **Objetivo:** segunda fase de la línea de tiempo: repartir las quemaduras en el tiempo y aplicar los efectos con duración.
- **Rama:** `feat/rotation-timed-effects`, creada desde `dev` (`19a6b1f`).
- **Entorno de ejecución:** shell Linux de Claude en el equipo del usuario, Python 3.14.8, `PYTHONPATH=src`. No se ha ejecutado con `.\.venv\Scripts\python.exe` en Windows.

## Decisiones del usuario (2026-11-16)

- **Quemaduras continuas:** sin tics. El cliente da `TickFrequency` 0,5 s para Liandry, Antorcha y Cenizas, pero no para Malignidad ni Zeke, ni dice cuándo cae el primer tic.
- **El daño posterior cuenta:** la rotación acaba cuando se apaga la última quemadura.
- **Efectos de esta fase:** marca de Tonada sanguina, −10 de RM de Malignidad, letalidad de la Ciclovoltaica y Fuego negro de la Antorcha. La Ráfaga de Yun Tal queda para otra fase.

## Decisiones técnicas

- Catálogo, versión 15: los cuatro efectos pasan a `evaluable`. Fuego negro y la reducción de Malignidad toman su duración del cliente (`BurnDuration` y `GroundDuration`, 3 s) con una fuente `client_data`; Fuego negro pasa a evidencia `derived`.
- Un efecto con `duration_seconds`, un `damage_modifier` o `stat_modifier` y disparador `spellblade`, `energized` o `damaging_ability` solo lo aplica la línea de tiempo. Sin ella se lista y deja la rotación `Pendiente de verificación` si puede afectar al objetivo.
- Hoja de estadísticas: `with_bonus` y `with_amplifier` añaden una contribución temporal a una hoja ya hecha. Las contribuciones de amplificadores llevan `amplifier=True`, para calcular otro sobre el total sin ellas.
- Rotaciones: el daño de las fórmulas de objeto (al impactar, quemaduras, aumentos de daño) lleva también las etiquetas de las estadísticas del atacante que lee.
- Supuestos marcados como `Pendiente de verificación`: si el golpe que dispara Tonada o la letalidad se beneficia del efecto; que el daño por segundo de una quemadura se fije al aplicarla, cuando las estadísticas cambian después; Fuego negro junto al Rabadon.

## Pruebas

- Nueva: `tests/test_rotation_timed_effects.py` (31). Actualizadas: `test_objects_model.py` (versión 15) y `test_rotation_spellblade.py` (nota de Tonada).
- Suite final: 899 pruebas, más 189 de `research/` (1 omitida, como antes).
- **Mutaciones deliberadas: 18.** Sobrevivieron 8 en la primera tanda:
  - 7 murieron con pruebas nuevas.
  - La octava era el filtro por tipo de objetivo añadido a `_skip`, que sobraba (ningún efecto evaluable con esa condición llega ahí); se quitó del código.
  - Otra, con el ancla mal escrita, se repitió y murió.

## Siguientes fases

> **Nota (2026-11-19):** esta lista refleja el estado al cerrar la fase. Lo que sigue abierto, con su prioridad, está en la [hoja de ruta](../roadmap.md); lo resuelto después se marca abajo con la fase que lo resolvió.

Ráfaga de Yun Tal; ventanas de acumulaciones (Kraken, Rompecascos, los 10 s de Hoja encantada); acumulaciones calculadas con «al máximo» como opción; tiempos de lanzamiento cuando haya datos; informes por ventana de tiempo.
