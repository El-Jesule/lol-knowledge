# Efectos según la vida del objetivo — fase 27

- **Objetivo:** segunda mecánica nueva del motor: daño que crece con la vida que le falta al objetivo, umbrales de vida y ejecución.
- **Rama:** `feat/target-missing-health`, creada desde `dev` (`b08cef2`).
- **Entorno de ejecución:** shell Linux de Claude en el equipo del usuario, Python 3.14.8, `PYTHONPATH=src`. No se ha ejecutado con `.\.venv\Scripts\python.exe` en Windows.

## Decisiones

1. **Vida al inicio del paso:** igual que Filo de la niebla.
2. **Kraken lineal:** la wiki escribe «0% – 75% (based on target's missing health)»; el cliente solo da el máximo (×1,75). Fuentes `corroborated`. La base sigue siendo la del cliente (150 – 200): la página de la wiki dice 150 – 210, pero su historial de ARAM y el cliente dicen 150 – 200.
3. **Llamasombría:** `damage_modifier` con `damage_types` (mágico y verdadero) y la condición `target_health_below` 40.
4. **Recaudadora:** componente `execute`; tras un paso, un campeón vivo por debajo del 5 % recibe su vida restante como daño verdadero sin modificadores.
5. **Catálogo `catalog_version: 13`.** Pasan a `complete` Llamasombría y Recaudadora.

## Pruebas

- Nueva: `tests/test_rotation_target_health.py` (6). Casos nuevos en `tests/test_objects_validator.py`; ajustes en las pruebas de Kraken (`tests/test_rotation_attack_counters.py`) y de requisitos de fórmulas. Suite final: 847 pruebas, más 189 de `research/` (1 omitida, como antes).
- **Mutaciones deliberadas: 7, todas eliminadas.**

## Limitaciones

- La vida a mitad de un paso no se sigue.
- El aumento de Llamasombría al daño a lo largo del tiempo no aplica: no hay daño a lo largo del tiempo en las rotaciones.
