# Acumulaciones de combate desde 0 — fase 32

- **Objetivo:** que las acumulaciones temporales de combate empiecen en 0 y las calcule la rotación.
- **Rama:** `feat/combat-stacks`, creada desde `dev` (`1609e72`).
- **Entorno de ejecución:** shell Linux de Claude en el equipo del usuario, Python 3.14.8, `PYTHONPATH=src`. No se ha ejecutado con `.\.venv\Scripts\python.exe` en Windows.

## Decisiones del usuario (2026-11-16)

- «Los items cuyas cargas son temporales y solo están en combate no deben nunca empezar al máximo, sino a 0.»
- **El final:** empieza siempre con un golpe luminoso.
- **Guinsoo:** el ataque que completa las acumulaciones cuenta para el impacto fantasma.
- **Sin `--timeline`:** se cuenta por ataques.
- **Segundos en combate:** desde el inicio de la rotación, «dado que "en combate" empieza cuando recibes daño de un campeón».

## Decisiones técnicas

- **Catálogo, versión 17:**
  - Guinsoo y El final pierden el escenario `max_stacks` y declaran el valor por acumulación con `stacks.required: 1`.
  - El final declara `alternation`, el impacto fantasma `stacks_full`, y Liandry y Disfraz el disparador `in_combat` con un límite `maximum`.
  - `max_stacks` queda solo para el crítico de Yun Tal.
- **Hoja de estadísticas:** ya no incluye esas acumulaciones. `with_bonus` acepta cualquier estadística que no alimente a otras, incluidas las penetraciones porcentuales, y comprueba que las fracciones estén entre 0 y 1.
- **Rotación:** cuenta las acumulaciones ataque a ataque y las aplica desde el paso siguiente. Los tramos de las quemaduras se cortan también donde caducan acumulaciones y en cada segundo completo.

## Pruebas

- Nueva: `tests/test_rotation_combat_stacks.py` (17). Validador: 4 nuevas, entre ellas una para `cooldown_reduced_by_attacks`, que la fase 31 dejó sin prueba.
- Actualizadas:
  - Guinsoo, El final, Disfraz y la hoja en `test_rotation_attack_counters.py`, `test_rotation_burns.py`, `test_stats_real_items.py` y `test_rotation_timeline_windows.py`.
  - Las pruebas de quemaduras de `test_rotation_timed_effects.py` pasan de Liandry a Cenizas predestinadas, porque el Sufrimiento ahora parte los tramos en segundos.
- **Mutaciones deliberadas: 22; todas mueren.** Antes se quitaron dos comprobaciones equivalentes:
  - la caducidad dentro de `_full`, que ya resuelve `_stack`;
  - la línea de tiempo en el valor por segundo, porque sin ella el reloj vale 0.

## Siguientes fases

> **Nota (2026-11-19):** esta lista refleja el estado al cerrar la fase. Lo que sigue abierto, con su prioridad, está en la [hoja de ruta](../roadmap.md); lo resuelto después se marca abajo con la fase que lo resolvió.

Impactos fantasma como acumulación extra del Kraken; tiempos de lanzamiento cuando haya datos; informes por ventana de tiempo.
