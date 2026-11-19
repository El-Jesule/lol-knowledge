# Motor de daño: núcleo de mitigación — fase 8

- **Objetivo:** construir el núcleo determinista del motor de daño: dado un daño bruto, su tipo y la resistencia del objetivo con sus modificadores, devolver el daño mitigado y la traza de la resistencia.
- **Rama:** `feat/damage-engine`, creada desde `dev` (`7b5d018`).
- **Entrega:** `src/lol_knowledge/damage/` (`mitigation.py`, `report.py`), comando `python -m lol_knowledge damage`, pruebas en `tests/test_damage_mitigation.py`, `tests/test_cli_damage.py` y `tests/test_cli_integration.py`, y documentación en `README.md` y `lol-knowledge/mechanics/damage-mitigation.md`.
- **Entorno de ejecución:** shell Linux de Claude en el equipo del usuario, Python 3.14.10, `pytest==9.1.1`, `ruff==0.17.1`, `PYTHONPATH=src` en lugar de la instalación editable. No se ha ejecutado con `.\.venv\Scripts\python.exe` en Windows.

## Decisiones de diseño

1. **Independencia de los datos.** El motor recibe números; no importa `objects`, `snapshot` ni `ddragon`. Una prueba recorre los `import` del paquete y falla si aparece una dependencia de datos del juego. La traducción de campeones y objetos a entradas será una capa aparte.
2. **Aritmética exacta.** Se calcula con `fractions.Fraction` (biblioteca estándar). El resultado no depende del orden de las fuentes ni del redondeo binario. Un `float` de entrada se lee por su representación decimal más corta (`0.3` es 3/10).
3. **Sin redondeo.** El redondeo del daño mostrado en el juego no está documentado; el motor devuelve el valor exacto y lo declara como supuesto.
4. **Entradas incoherentes se rechazan.** Daño verdadero con resistencia o modificadores, porcentajes fuera de 0–1, valores negativos o no finitos: `DamageInputError`, salida `2`, sin resultado parcial.
5. **Rama de resistencia negativa.** Se implementa porque ya tiene dos fuentes secundarias (S4 y S5 del documento de reglas).

## Specs

### S1 — Resistencia efectiva

Cuatro pasos en orden: reducción plana (puede bajar de 0), reducción porcentual (multiplicativa, se omite con resistencia ≤ 0), penetración porcentual (ídem) y penetración plana (aditiva, suelo en 0, se omite con resistencia ≤ 0). La traza conserva el valor tras cada paso.

### S2 — Multiplicador y mitigación

`100 / (100 + R)` con `R ≥ 0`; `2 − 100 / (100 − R)` con `R < 0`. El daño verdadero no se mitiga.

### S3 — CLI

`damage --raw --type {physical,magic,true} [--resistance] [--flat-reduction …] [--percent-reduction …] [--percent-penetration …] [--flat-penetration …] [--json]`. Las opciones de modificador se repiten, una vez por fuente.

### S4 — Pruebas

76 pruebas nuevas. Once mutaciones deliberadas del motor (orden de penetraciones invertido, sin suelo en 0, porcentajes aplicados a resistencia negativa, rama negativa sustituida, apilamiento aditivo, lectura binaria de `float`, sin tope de porcentaje, daño verdadero con resistencia, daño bruto negativo) hacen fallar al menos una prueba cada una.

## Limitaciones

> **Nota (2026-11-19):** esta lista refleja el estado al cerrar la fase. Lo que sigue abierto, con su prioridad, está en la [hoja de ruta](../roadmap.md); lo resuelto después se marca abajo con la fase que lo resolvió.

- Una instancia de daño por llamada; no hay rotaciones, tiempo ni DPS.
- No modela amplificaciones o reducciones de daño, escudos, críticos ni efectos al impacto.
- No modela la penetración porcentual de armadura *adicional*.
- No lee campeones ni objetos: los números de entrada los pone quien llama.
- Las reglas proceden de fuentes no oficiales (confirmación del responsable del proyecto y wikis comunitarias) y no se han medido en partida.
