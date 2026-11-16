# Probabilidad de crítico — fase 17

- **Objetivo:** resolver la probabilidad de crítico en la hoja de estadísticas.
- **Rama:** `feat/crit-chance`, creada desde `dev` (`91c27de`).
- **Entorno de ejecución:** shell Linux de Claude en el equipo del usuario, Python 3.14.8, `PYTHONPATH=src`. No se ha ejecutado con `.\.venv\Scripts\python.exe` en Windows.

## Reglas investigadas antes del código

[`critical-strike.md`](../../lol-knowledge/mechanics/critical-strike.md), sección «Probabilidad de crítico»: se suma, no crece por nivel y tiene tope de 100 % (wiki y un comentario de Riot de hacia 2020). Data Dragon 16.22.1 publica `crit` = `critperlevel` = 0 en los 173 campeones. Las notas de 26.x consultadas no cambian la regla general.

## Decisiones

1. **Reutilizar el `cap` del registro** (fase 16): el total se limita a 1 y `bonus` conserva el exceso, que aprovechan Senna, Yasuo o Yone.
2. **La base de Data Dragon entra como aporte `Oficial` 0.** Si algún campeón tuviera un valor distinto de 0, la estadística se bloquea: con todo a 0 no se puede saber si la unidad es fracción o porcentaje.
3. **Yasuo y Yone** duplican su probabilidad con la pasiva (wiki, 2026): quedaron `Pendiente de verificación` con una nota. Desde la rama `feat/yasuo-yone-passive` la pasiva está modelada (ver «Pasivas de Yasuo y Yone»).
4. **Rotaciones sin cambios:** cada paso sigue diciendo si critica; la probabilidad no se usa para valores esperados.

## Pruebas

- Nuevas: `tests/test_stats_crit_chance.py` (13). `tests/stats_helpers.py` añade `crit` y `critperlevel` al campeón sintético, como en Data Dragon. Suite final: 613 pruebas, más 173 de `research/` (1 omitida, como antes).
- **Mutaciones deliberadas: 14, todas eliminadas** (tope, apilamiento, base, bloqueo, campo ausente, etiquetas y pasivas).

## Limitaciones

- No hay confirmación del tope en notas de parche recientes; la fuente más directa es un comentario de Riot de hacia 2020.
- El cliente no se ha consultado: no hay campo de probabilidad base en los registros derivados.

## Pasivas de Yasuo y Yone (rama `feat/yasuo-yone-passive`)

- **Objetivo:** modelar lo que el usuario confirmó el 2026-11-16 y las notas de 26.17 corroboran: duplicación de la probabilidad, 0,5 de daño de ataque por cada 1 % de exceso y −5 % de daño crítico total.
- **Decisiones:** la hoja añade la duplicación como aporte propio y el exceso como daño de ataque adicional, ambos `Derivado` (regla de la wiki), y nunca más fuertes que sus fuentes. Si la probabilidad está bloqueada, también se bloquea su daño de ataque. La reducción del daño crítico se aplica en `rotation` al multiplicador total, con una nota. Ambas pasivas viven como constantes en el motor, no en un kit, porque solo Zaahen tiene kit.
- **Pruebas:** 8 nuevas en `tests/test_stats_crit_chance.py`, que sustituyen a las 2 de «pendiente», y 4 en `tests/test_rotation.py`. 16 mutaciones, todas eliminadas; dos sobrevivieron al principio (un aporte de 0 al llegar exactamente al 100 % y la etiqueta de la reducción) y ahora tienen prueba.
- **Limitación:** la rotación de Yasuo o Yone sigue sin kit; la reducción solo se aplica a ataques básicos.
