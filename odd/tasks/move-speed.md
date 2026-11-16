# Velocidad de movimiento — fase 20

- **Objetivo:** resolver la velocidad de movimiento, la última estadística que la hoja dejaba sin total.
- **Rama:** `feat/move-speed`, creada desde `dev` (`6a917c4`).
- **Entorno de ejecución:** shell Linux de Claude en el equipo del usuario, Python 3.14.8, `PYTHONPATH=src`. No se ha ejecutado con `.\.venv\Scripts\python.exe` en Windows.

## Reglas investigadas antes del código

[`move-speed.md`](../../lol-knowledge/mechanics/move-speed.md): `(base + planos) × (1 + Σ porcentajes aditivos)`, y límites suaves: el 80 % entre 415 y 490, el 50 % por encima de 490 y la mitad de lo que falta por debajo de 220 (wiki y una guía de septiembre de 2026). Data Dragon 16.22.1 da bases entre 315 y 355; las tres botas del catálogo dan 45 planos.

## Decisiones

1. **Porcentajes al final.** `percent_of` en el registro (`base` para la regeneración, `flat` para la velocidad) y conversión cuando ya están todos los aportes planos, así que el orden de los objetos no importa. La regeneración usa el mismo camino; sus resultados no cambian.
2. **Límite suave como transformación del total** (`soft_cap`). `base` y `bonus` se quedan en bruto; el informe muestra el bruto y la etiqueta baja como mucho a `Derivado` cuando el límite actúa.
3. **Cassiopeia** (pasiva de 26.1 que aumenta la eficacia de los aumentos de velocidad): `Pendiente de verificación` con nota.
4. **Ya no queda ninguna estadística pendiente.** Tres pruebas usaban una estadística real como ejemplo de «pendiente»; ahora registran una de prueba con `monkeypatch` para no perder la cobertura de ese camino. El informe de texto dice `not modelled yet: none`.

## Pruebas

- Nuevas: `tests/test_stats_move_speed.py` (20) y la prueba con `monkeypatch` de `tests/test_kit_model.py`. Suite final: 675 pruebas, más 173 de `research/` (1 omitida, como antes).
- **Mutaciones deliberadas: 22; 21 eliminadas.** La superviviente (`> 490` frente a `>= 490`) es equivalente: las dos fórmulas dan 475 en 490. Otra sobrevivió al principio (el límite de 415) y ahora tiene un caso entre 415 y 416.

## Limitaciones

- Aportes multiplicativos, ralentizaciones y resistencia a ralentizaciones: no modelados; no hay ninguno en el catálogo.
- Ningún objeto del catálogo da velocidad porcentual; ese camino solo está probado con objetos sintéticos.
