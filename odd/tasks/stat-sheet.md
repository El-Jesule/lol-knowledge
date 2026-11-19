# Hoja de estadísticas y primeras métricas — fase 9

- **Objetivo:** que el motor sirva para cualquier aspecto del campeón, no solo para el daño. El núcleo es una hoja de estadísticas resuelta; cada métrica es una función pura que lee de ella.
- **Rama:** `feat/stat-sheet`, creada desde `dev` (`87a89bc`).
- **Entrega:** `src/lol_knowledge/stats/` (`registry`, `labels`, `growth`, `issues`, `data`, `sheet`, `metrics`, `report`), comando `python -m lol_knowledge stats`, comprobación del registro de defectos en `validate`, reglas nuevas en `lol-knowledge/mechanics/` y registro `lol-knowledge/data-issues.json`.
- **Entorno de ejecución:** shell Linux de Claude en el equipo del usuario, Python 3.14.10, `pytest==9.1.1`, `ruff==0.17.1`, `PYTHONPATH=src` en lugar de la instalación editable. No se ha ejecutado con `.\.venv\Scripts\python.exe` en Windows.

## Decisiones de diseño

1. **Aportes con procedencia.** Cada estadística guarda sus aportes por separado (campeón, crecimiento, objeto, supuesto), cada uno con fuente y etiqueta. Las penetraciones porcentuales no se agregan antes de tiempo: el motor de daño las necesita una por fuente.
2. **La etiqueta más débil manda.** A nivel 1 los valores de campeón son `Oficial`; desde el nivel 2 interviene la fórmula de crecimiento (fuente secundaria) y pasan a `Derivado`; un supuesto es `Pendiente de verificación`.
3. **Registro compartido.** `stats/registry.py` contiene todas las estadísticas canónicas del modelo de objetos (una prueba lo garantiza) y las nuevas que se pidieron: omnivampirismo, tenacidad, robo de vida, regeneración. Solo se totalizan las que tienen regla documentada.
4. **Los defectos de datos bloquean.** `lol-knowledge/data-issues.json` registra campos oficiales incorrectos. Una estadística afectada se bloquea con su motivo; solo esos campos admiten `--assume`.
5. **Carga separada del cálculo.** Solo las funciones `load_*` leen archivos; la hoja y las métricas son funciones puras sobre valores.
6. **Solo objetos curados.** Un objeto fuera del catálogo se rechaza: Data Dragon no publica en `stats` la letalidad, la aceleración ni varias penetraciones.

## Specs

### S1 — Reglas citadas antes del código

`mechanics/stat-growth.md` (fórmula de crecimiento, corroborada por dos wikis), `mechanics/ability-haste.md` (enfriamiento con aceleración, dos fuentes), `mechanics/effective-health.md` (vida efectiva a partir del multiplicador de mitigación) y `mechanics/known-data-issues.md`.

### S2 — Hallazgo durante la fase

Data Dragon 16.20.1 publica `attackdamageperlevel = 0` para los 173 campeones. La discrepancia E.1 de Zaahen era un caso de un defecto general. Queda registrado como `ddragon-attack-damage-growth`.

### S3 — Hoja y métricas

`stats --champion --level [--item …] [--assume FIELD=VALUE …] [--json]`. Métricas: vida efectiva frente a daño físico, mágico y verdadero; enfriamientos por rango de Q, W, E y R.

### S4 — Pruebas

90 pruebas nuevas, incluidas las de `validate`. Los ejemplos numéricos de las fuentes (crecimiento 685/120 → 771,4 a nivel 2; 72 %, 100 % y 128 % de ganancia por nivel; 100 y 200 de aceleración → enfriamiento al 50 % y al 33,3 %) están fijados. Diecisiete mutaciones deliberadas hacen fallar al menos una prueba cada una.

## Limitaciones

> **Nota (2026-11-19):** esta lista refleja el estado al cerrar la fase. Lo que sigue abierto, con su prioridad, está en la [hoja de ruta](../roadmap.md); lo resuelto después se marca abajo con la fase que lo resolvió.

- No hay runas, efectos de objeto, pasivas de campeón ni buffs.
- La velocidad de ataque, la de movimiento, la regeneración, los críticos, el robo de vida, el omnivampirismo y la tenacidad se listan sin total hasta tener regla documentada.
- Solo se modela el maná como recurso; otros recursos bloquean las estadísticas de maná.
- No se valida la legalidad de la build ni el nivel máximo de cada modo.
- Las reglas proceden de fuentes no oficiales y no se han medido en partida.
