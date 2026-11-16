# Regeneración de vida y maná — fase 19

- **Objetivo:** resolver la regeneración de vida y de maná en la hoja de estadísticas.
- **Rama:** `feat/regeneration`, creada desde `dev` (`c98b27c`).
- **Entorno de ejecución:** shell Linux de Claude en el equipo del usuario, Python 3.14.8, `PYTHONPATH=src`. No se ha ejecutado con `.\.venv\Scripts\python.exe` en Windows.

## Reglas investigadas antes del código

[`regeneration.md`](../../lol-knowledge/mechanics/regeneration.md): por cada 5 s; base y crecimiento con la fórmula general; los porcentajes de «regeneración básica» multiplican la base del nivel; las fuentes se suman, planas y porcentuales (wiki).

## Hallazgo de datos

`FlatHPRegenMod` de los objetos va **por segundo** en Data Dragon 16.22.1, mientras que el `hpregen` de los campeones va por cada 5 s. Los 18 objetos con el campo lo confirman: su descripción da siempre 5 veces el valor «cada 5 s» (Escudo de Doran: `0.8` y «4 de vida cada 5 s»). Antes de esta fase el modelo de objetos copiaba el valor tal cual; como ningún objeto del catálogo lo tenía y la regeneración estaba pendiente, no afectaba a ningún cálculo.

## Decisiones

1. **Unidad canónica: por cada 5 s.** El modelo multiplica `FlatHPRegenMod` por 5 y anota `unit_conversion`; la hoja trata ese aporte como `Derivado`, con una nota.
2. **Porcentaje de la base como cantidad.** `percent_of_base` en el registro: un `kind: percent` se convierte en porcentaje × base del nivel, de modo que el total sigue siendo una suma de aportes con su etiqueta.
3. **El catálogo admite ambos tipos** para `health_regen` y `mana_regen` (`flat` y `percent`).
4. **Maná solo para campeones de maná**, como ya hacía la hoja.

## Pruebas

- Nuevas: `tests/test_stats_regeneration.py` (14) y 4 casos en `tests/test_objects_validator.py`. Suite final: 654 pruebas, más 173 de `research/` (1 omitida, como antes).
- **Mutaciones deliberadas: 17, todas eliminadas.** Sobrevivió una al principio (quitar el `percent` de `health_regen` en el catálogo) y ahora tiene prueba.

## Limitaciones

- Multiplicadores de regeneración (poder de curación y escudos, Rostro espiritual), regeneración por vida o maná máximos, y regeneración de otros recursos: no modelados.
- La unidad de `FlatHPRegenMod` es una deducción de los datos (`Derivado`); ninguna fuente de Riot la documenta.
