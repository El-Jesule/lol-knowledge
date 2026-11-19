# Contadores de ataques y Vigor — fase 26

- **Objetivo:** primera mecánica nueva del motor para los objetos pendientes (decisión del usuario: ampliar el motor antes de declarar los 140 objetos restantes).
- **Rama:** `feat/attack-counter`, creada desde `dev` (`a1208cd`).
- **Entorno de ejecución:** shell Linux de Claude en el equipo del usuario, Python 3.14.8, `PYTHONPATH=src`. No se ha ejecutado con `.\.venv\Scripts\python.exe` en Windows.

## Decisiones del usuario (2026-11-16)

1. Empezar por «cada N ataques».
2. El contador empieza **desde cero**; los ataques con Vigor empiezan listos.
3. Los consumibles, guardianes y compañeros se declararán más adelante sin aplicar.

## Decisiones técnicas

- `stacks.required` en efectos `on_hit` / `on_attack` = «cada N ataques»; disparador `energized`, componente `trigger_energized` y condición `target_is_structure` nuevos (catálogo versión 12).
- `by_level` pasa a estar permitido en las fórmulas de objeto, para los saltos por nivel del cliente. Con ello, los ataques luminosos de El final se aplican.
- El Vigor no se recarga en la rotación (depende del movimiento); varios objetos de Vigor dejan la rotación `Pendiente de verificación`.
- Un efecto no aplicado cuya condición de tipo de objetivo no encaja con el objetivo ya no debilita la rotación.
- Los ordinales en español de las citas («tercer», «quinto») cuentan como números en la validación.

## Pruebas

- Nueva: `tests/test_rotation_attack_counters.py` (13). Casos nuevos en `tests/test_objects_validator.py`; ajustes en `tests/test_stats_real_items.py`, `tests/test_objects_model.py` y `tests/test_objects_interface.py`. Suite final: 839 pruebas, más 189 de `research/` (1 omitida, como antes).
- **Mutaciones deliberadas: 11; tres sobrevivieron al principio.** Dos tienen ya prueba (Galvanizado sin la Espada, disparadores que cuentan ataques); la tercera (N ≥ 2 frente a N ≥ 1) es equivalente: contar cada ataque da el mismo resultado que aplicarlo en cada ataque.

## Limitaciones

> **Nota (2026-11-19):** esta lista refleja el estado al cerrar la fase. Lo que sigue abierto, con su prioridad, está en la [hoja de ruta](../roadmap.md); lo resuelto después se marca abajo con la fase que lo resolvió.

- Kraken: falta el aumento por la vida que le falta al objetivo (siguiente mecánica). *Resuelto en la fase 27.*
- Statikk: el rayo no se aplica (no consta si alcanza al objetivo atacado).
- Ventanas de tiempo y recarga del Vigor, sin modelar. *Ventanas resueltas en las fases 29 a 31; la recarga del Vigor sigue abierta (OBJ-04).*
