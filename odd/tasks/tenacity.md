# Tenacidad — fase 18

- **Objetivo:** resolver la tenacidad en la hoja de estadísticas y darle una fuente real en el catálogo (Botas de mercurio).
- **Rama:** `feat/tenacity`, creada desde `dev` (`1df8117`).
- **Entorno de ejecución:** shell Linux de Claude en el equipo del usuario, Python 3.14.8, `PYTHONPATH=src`. No se ha ejecutado con `.\.venv\Scripts\python.exe` en Windows.

## Reglas investigadas antes del código

[`tenacity.md`](../../lol-knowledge/mechanics/tenacity.md): las fuentes de un mismo grupo se multiplican y los grupos se suman (wiki). Todos los objetos con tenacidad están en el grupo A. No reduce el aire, la reducción de velocidad de ataque ni la supresión. Data Dragon 16.22.1 solo da la tenacidad en las descripciones: Botas de mercurio, «30% de tenacidad».

## Decisiones

1. **Multiplicativa como grupo A.** El registro ya sabía apilar así (penetración %). Con objetos como única fuente real, el resultado es correcto.
2. **Fuentes que no son objetos:** se multiplican igual, pero quedan `Pendiente de verificación` con una nota, porque su grupo no está documentado. El grupo B y la suma entre grupos no se modelan hasta tener una fuente que los use.
3. **Catálogo `catalog_version: 7`:** `tenacity` pasa a ser estadística canónica (`kind: percent`, desde la descripción) y entran las Botas de mercurio (3111). La muestra pasa de 15 a 16 objetos.
4. **Sin efecto en el daño:** la rotación no modela controles ni tiempo; la tenacidad se queda en la hoja.

## Pruebas

- Nuevas: `tests/test_stats_tenacity.py` (10), un caso en `tests/test_objects_model.py` y otro en `tests/test_objects_validator.py`. Dos pruebas usaban la tenacidad como ejemplo de estadística sin regla (`test_cli_stats.py`, `test_kit_model.py`); ahora usan la velocidad de movimiento, que sigue pendiente. Suite final: 636 pruebas, más 173 de `research/` (1 omitida, como antes).
- **Mutaciones deliberadas: 12, todas eliminadas** (apilamiento, unidad, estado, esquema del catálogo, aportes sin grupo y sus notas).

## Limitaciones

- La regla de grupos viene de un extracto de la wiki; la página completa no se pudo abrir y el grupo B no está identificado.
- Tenacidad condicional (Calibrador de Sterak, Final del ingenio), runas, elixires y resistencia a ralentizaciones: no modelados.
