# Escenario de acumulaciones al máximo — fase 22

- **Objetivo:** que las Flechas de los Yun Tal den su crítico real. El objeto da 0 % al comprarlo y su pasiva suma crítico permanente con cada ataque hasta 25 % (corrección del usuario, 2026-11-16).
- **Rama:** `feat/item-stack-scenario`, creada desde `dev` (`afcc717`).
- **Entorno de ejecución:** shell Linux de Claude en el equipo del usuario, Python 3.14.8, `PYTHONPATH=src`. No se ha ejecutado con `.\.venv\Scripts\python.exe` en Windows.

## Fuentes

- **Data Dragon 16.22.1** (`Oficial`): «0% de probabilidad de impacto crítico» y «Al atacar, obtienes probabilidad de impacto crítico de forma permanente, hasta un 25%.»
- **Cliente 16.22** (`Derivado`): `Items/3032.mDataValues` (`CritPerStackMelee` 0,4, `StackRangedMultiplier` 0,5, `CritMax` 25) y la plantilla `item_3032_tooltip` en es_ES. Detalle y cobertura de los demás tooltips en [`research/reports/item-data-values-16.22.md`](../../research/reports/item-data-values-16.22.md).
- **Internet:** secundario y contradictorio; solo sirve de contraste.

## Decisiones

1. **Acumulaciones al máximo** (elegido por el usuario frente a tres escenarios cero/intermedio/máximo): es más sencillo y directo, aunque sobrestime el daño antes de completar las acumulaciones.
2. **El escenario va en el catálogo, no en la hoja:** un efecto declara `scenario: max_stacks` y sus componentes `stat_modifier` planos dan el valor con todas las acumulaciones. La hoja los suma como estadísticas con la nota `scenario: maximum stacks` y la etiqueta según su evidencia (`official` → `Derivado`, como en las rotaciones). Las rotaciones no los repiten.
3. **Cero confirmado** (`confirmed_zero_stats`): la regla general de que un 0 de la descripción es desconocido se mantiene; el catálogo curado puede confirmar un 0 concreto con motivo, y `validate` comprueba que siga existiendo en el archivo generado.
4. **Nuevo disparador `on_attack`** («al atacar»), distinto de `on_hit`.
5. **Ráfaga queda `excluded`:** es una ventana temporal y las rotaciones no tienen línea de tiempo. Con Yun Tal la rotación queda `Pendiente de verificación`.
6. **Valores por acumulación en la nota del efecto**, no en el modelo: no se usan con el escenario al máximo.
7. **Catálogo `catalog_version: 9`.**

## Pruebas

- Nuevas: `tests/test_stats_item_scenarios.py` (14: unidad, etiqueta, efecto no evaluable, sin escenario, duplicación de Yasuo, errores, fusión del cero confirmado, nota del modelo) y casos en `tests/test_stats_real_items.py`, `tests/test_objects_validator.py` y `tests/test_objects_generate.py`. Suite final: 751 pruebas, más 173 de `research/` (1 omitida, como antes).
- **Mutaciones deliberadas: 13, todas eliminadas.** Cuatro sobrevivieron al principio (modo del componente en la hoja, estado `unknown` en la fusión y en la validación, y el filtro de notas del informe) y ahora tienen prueba.

## Limitaciones

- No hay acumulaciones parciales ni otros escenarios; `SCENARIOS` solo admite `max_stacks`.
- Solo componentes `stat_modifier` planos. El +30 % de AP de Rabadon (`always`, porcentual) sigue sin aplicarse en la hoja.
- Siguiente paso propuesto: generar un archivo de efectos con los valores del cliente para los 218 objetos y curar efectos sobre él.
