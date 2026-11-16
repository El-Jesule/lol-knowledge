# Ráfaga de Yun Tal y ventanas de tiempo — fase 31

- **Objetivo:** tercera fase de la línea de tiempo: la Ráfaga de Yun Tal, la caducidad de las acumulaciones de Kraken y la ventana de 10 s de Hoja encantada.
- **Rama:** `feat/rotation-timeline-windows`, creada desde `dev` (`4eb7f22`).
- **Entorno de ejecución:** shell Linux de Claude en el equipo del usuario, Python 3.14.8, `PYTHONPATH=src`. No se ha ejecutado con `.\.venv\Scripts\python.exe` en Windows.

## Petición del usuario (2026-11-16)

«Haz el Yun Tal, el Kraken y las 10 Hojas Encantadas»: la Ráfaga, la ventana de acumulaciones de Kraken y la ventana de 10 s de Hoja encantada.

## Decisiones técnicas

- **Catálogo, versión 16:**
  - La Ráfaga pasa a `evaluable` (evidencia `derived`) con el campo nuevo `cooldown_reduced_by_attacks` (1 s, 2 s con crítico; `AACDR` y `CritCDR` del cliente).
  - Los siete efectos de Hoja encantada declaran `duration_seconds: 10`, con la wiki como fuente secundaria.
- **Hoja de estadísticas:** guarda el ratio de velocidad de ataque (`attack_speed_ratio`), y `with_bonus` acepta velocidad de ataque adicional y recalcula la velocidad de ataque.
- **Ventanas:** la caducidad de las acumulaciones usa `stacks.window_seconds`, así que vale también para Rompecascos (10 s).
- **Supuestos sin fuente directa**, que dejan el resultado `Pendiente de verificación` cuando deciden algo:
  - el tiempo hasta el siguiente ataque usa la velocidad justo después de cada ataque;
  - las acumulaciones se renuevan con cada ataque (la wiki solo lo dice de las estructuras);
  - la ventana de 10 s viene de la wiki.

## Pruebas

- Nueva: `tests/test_rotation_timeline_windows.py` (19). Actualizadas: `test_objects_model.py` (versión 16), `test_stats_real_items.py` (nota de la Ráfaga) y `test_rotation_timed_effects.py` (la velocidad de ataque ya admite una bonificación temporal).
- **Mutaciones deliberadas: 20.** Una sobrevivió (restar la reducción antes de comprobar el enfriamiento, que solo se distingue con un ataque crítico que activa la Ráfaga) y murió con una prueba nueva.

## Siguientes fases

Acumulaciones calculadas con «al máximo» como opción; impactos fantasma de Guinsoo en el Kraken; tiempos de lanzamiento cuando haya datos; informes por ventana de tiempo.
