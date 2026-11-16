# Probabilidad de crítico — fase 17

- **Objetivo:** resolver la probabilidad de crítico en la hoja de estadísticas.
- **Rama:** `feat/crit-chance`, creada desde `dev` (`91c27de`).
- **Entorno de ejecución:** shell Linux de Claude en el equipo del usuario, Python 3.14.8, `PYTHONPATH=src`. No se ha ejecutado con `.\.venv\Scripts\python.exe` en Windows.

## Reglas investigadas antes del código

[`critical-strike.md`](../../lol-knowledge/mechanics/critical-strike.md), sección «Probabilidad de crítico»: se suma, no crece por nivel y tiene tope de 100 % (wiki y un comentario de Riot de hacia 2020). Data Dragon 16.22.1 publica `crit` = `critperlevel` = 0 en los 173 campeones. Las notas de 26.x consultadas no cambian la regla general.

## Decisiones

1. **Reutilizar el `cap` del registro** (fase 16): el total se limita a 1 y `bonus` conserva el exceso, que aprovechan Senna, Yasuo o Yone.
2. **La base de Data Dragon entra como aporte `Oficial` 0.** Si algún campeón tuviera un valor distinto de 0, la estadística se bloquea: con todo a 0 no se puede saber si la unidad es fracción o porcentaje.
3. **Yasuo y Yone** duplican su probabilidad con la pasiva (wiki, 2026): quedan `Pendiente de verificación` con una nota.
4. **Rotaciones sin cambios:** cada paso sigue diciendo si critica; la probabilidad no se usa para valores esperados.

## Pruebas

- Nuevas: `tests/test_stats_crit_chance.py` (13). `tests/stats_helpers.py` añade `crit` y `critperlevel` al campeón sintético, como en Data Dragon. Suite final: 613 pruebas, más 173 de `research/` (1 omitida, como antes).
- **Mutaciones deliberadas: 14, todas eliminadas** (tope, apilamiento, base, bloqueo, campo ausente, etiquetas y pasivas).

## Limitaciones

- La pasiva de Yasuo y Yone (duplicar y convertir el exceso en daño de ataque) no está modelada.
- No hay confirmación del tope en notas de parche recientes; la fuente más directa es un comentario de Riot de hacia 2020.
- El cliente no se ha consultado: no hay campo de probabilidad base en los registros derivados.
