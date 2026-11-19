# Registros de estadísticas del cliente para todos los campeones — fase 10

- **Objetivo:** desbloquear el daño de ataque por nivel de todos los campeones, que Data Dragon 16.20.1 publica a 0, con el valor real del cliente.
- **Rama:** `feat/client-champion-records`, creada desde `dev` (`d057b62`).
- **Entrega:** `research/binmodel/records.py` y sus pruebas; `lol-knowledge/derived/champion-records.json` (173 campeones, `Derivado`); `src/lol_knowledge/stats/derived.py`; la hoja de estadísticas usa la tabla para los campos con defecto abierto; `validate` revisa la tabla; informe `research/reports/champion-records-16.22.md`.
- **Entorno de ejecución:** shell Linux de Claude en el equipo del usuario, Python 3.14.10, `pytest==9.1.1`, `ruff==0.17.1`, `PYTHONPATH=src` en lugar de la instalación editable. No se ha ejecutado con `.\.venv\Scripts\python.exe` en Windows.

## Decisiones

1. **No se actualiza el snapshot.** Data Dragon no es accesible desde el entorno de Claude (ni desde la shell del equipo del usuario ni desde la nube). El snapshot sigue en 16.20.1.
2. **La diferencia de parche se declara, no se oculta.** Un valor del cliente 16.22 usado con el snapshot 16.20.1 es `Pendiente de verificación`. Al alinear los parches pasa a `Derivado` sin cambiar código.
3. **Los registros derivados solo sustituyen campos con defecto abierto.** Nunca pisan un dato oficial correcto, aunque difiera (Jinx, Mel, Sion, Thresh y Viktor cambiaron entre parches; la hoja sigue usando Data Dragon para esos campos).
4. **Lo ausente no se rellena.** Senna no tiene crecimiento de DA en el bin; su DA sigue bloqueado.
5. **Orden de prioridad:** supuesto explícito > registro derivado > bloqueo.

## Pruebas

42 pruebas nuevas entre `tests/` y `research/tests/`. Diez mutaciones deliberadas; la única que sobrevivió al principio (WAD truncado) destapó un hueco y ahora tiene su prueba. Las pruebas encontraron además un fallo real: un índice de campeones inválido producía en silencio una tabla vacía.

## Limitaciones

> **Nota (2026-11-19):** esta lista refleja el estado al cerrar la fase. Lo que sigue abierto, con su prioridad, está en la [hoja de ruta](../roadmap.md); lo resuelto después se marca abajo con la fase que lo resolvió.

- Cliente 16.22 frente a snapshot 16.20.1 hasta que se ejecute `update` con red.
- La tabla solo cubre estadísticas base y por nivel; el maná y la regeneración no se extraen todavía.
- Las regeneraciones del bin están en otra unidad (Zaahen: 1,5 por segundo frente a 7,5 cada 5 s en Data Dragon) y no se publican.
