# Línea de tiempo — fase 29

- **Objetivo:** primera fase de la línea de tiempo de las rotaciones.
- **Rama:** `feat/rotation-timeline`, creada desde `dev` (`be15dca`).
- **Entorno de ejecución:** shell Linux de Claude en el equipo del usuario, Python 3.14.8, `PYTHONPATH=src`. No se ha ejecutado con `.\.venv\Scripts\python.exe` en Windows.
- **Push:** el usuario lo autorizó, pero este entorno lo bloquea (solo permite `clone` y `fetch` de GitHub). Queda pendiente de hacerlo desde su equipo.

## Decisiones del usuario (2026-11-16)

Tiempos mixtos (encadenado automático y `wait:<segundos>`); error al lanzar en enfriamiento; «al máximo» se mantendrá como opción; lo que no tenga datos se ignora.

## Decisiones técnicas

- La línea de tiempo es opcional (`--timeline`, `timeline=True`): sin ella, las rotaciones no cambian.
- Kit: `recast` en los casos y `recast_window_seconds` en la habilidad (Zaahen Q, 4 s).
- La recarga de Hoja encantada se respeta con la línea de tiempo.

## Pruebas

- Nueva: `tests/test_rotation_timeline.py` (16). Suite final: 868 pruebas, más 189 de `research/` (1 omitida, como antes).
- **Mutaciones deliberadas: 10; una sobrevivió** (abrir la reactivación también en habilidades sin caso `recast`): era equivalente, y el código se simplificó para quitar la condición.

## Siguientes fases

> **Nota (2026-11-19):** esta lista refleja el estado al cerrar la fase. Lo que sigue abierto, con su prioridad, está en la [hoja de ruta](../roadmap.md); lo resuelto después se marca abajo con la fase que lo resolvió.

Duraciones de efectos y quemaduras con tics; ventanas de acumulaciones; acumulaciones calculadas con «al máximo» como opción; tiempos de lanzamiento cuando haya datos; informes por ventana de tiempo.
