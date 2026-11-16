# Quemaduras — fase 28

- **Objetivo:** tercera mecánica nueva del motor: daño a lo largo del tiempo de objetos y aumentos de daño por tiempo en combate.
- **Rama:** `feat/burns`, creada desde `dev` (`21a3db1`).
- **Entorno de ejecución:** shell Linux de Claude en el equipo del usuario, Python 3.14.8, `PYTHONPATH=src`. No se ha ejecutado con `.\.venv\Scripts\python.exe` en Windows.

## Decisiones del usuario (2026-11-16)

1. Quemadura completa como una parte, suponiendo que dura toda su duración.
2. **Una quemadura por efecto y rotación**, aunque se lancen varias habilidades.

## Decisiones técnicas

- Componente `burn`; disparadores `damaging_ability` y `cast`; condición `ultimate_ability` (catálogo versión 14).
- Un efecto por tipo de objetivo cuando las cifras cambian (súbditos, monstruos); Liandry contra monstruos no se aplica (unidad del tope sin verificar).
- Las quemaduras no aplican robo de vida; el omnivampirismo cura un 33 % contra súbditos y monstruos.
- Los aumentos por tiempo en combate (Liandry, Disfraz encantado) se aplican al máximo, como decidió el usuario para las acumulaciones; el escenario `max_stacks` admite ahora aumentos de daño, que aplican las rotaciones.
- `burn`, `execute` y `repeat_on_hit` cuentan como efectos que cambian el daño: si no se aplican, debilitan la rotación.

## Pruebas

- Nueva: `tests/test_rotation_burns.py` (7). Casos nuevos en `tests/test_objects_validator.py` y `tests/test_stats_item_scenarios.py`. Suite final: 855 pruebas, más 189 de `research/` (1 omitida, como antes).
- **Mutaciones deliberadas: 8; dos sobrevivieron al principio** (la quemadura de `damaging_ability` sin daño en el paso y el robo de vida de las quemaduras) y ahora tienen prueba.

## Limitaciones

- Sin tiempo: Fuego negro de la Antorcha y la reducción de resistencia mágica de Malignidad no se aplican.
- Auras que queman alrededor (Égida de fuego solar, Rescoldo de Bami, Fulgor vano) y Creagrietas: pendientes.
