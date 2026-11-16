# Ahri — fase 33

- **Objetivo:** segundo campeón con kit, distinto de Zaahen (maga a distancia), para comprobar que el generador de kits generaliza.
- **Rama:** `feat/champion-ahri`, creada desde `dev` (`6ae0f36`).
- **Entorno de ejecución:** shell Linux de Claude en el equipo del usuario, Python 3.14.8, `PYTHONPATH=src` (y `research`). No se ha ejecutado con `.\.venv\Scripts\python.exe` en Windows.

## Petición del usuario (2026-11-16)

«Haz a Ahri», tras recomendar un segundo campeón muy distinto de Zaahen.

## Qué faltaba para generalizar

- **CommunityDragon bloqueado:** se añade `binmodel/bin2json.py`, que lee el bin del cliente y lo convierte al formato de los exports. Comprobado: el kit de Zaahen regenerado desde su bin 16.22 sale idéntico.
- **`mStat` ausente:** se mapea al 0 por defecto, poder de habilidad (`corroborated`). La evidencia está en el informe.
- **Un valor bajo dos etiquetas** (Q de Ahri): `kitgen` lo admite si la parte declara el tipo.
- **Varias reactivaciones con intervalo** (R de Ahri): `max_recasts` y `recast_interval_seconds` en el kit, que la línea de tiempo aplica. Ventana e intervalo se leen del bin.

## Entregables

- Kit: `lol-knowledge/champions/Ahri/kit.json`.
- Fichas del campeón: `overview.md`, `abilities.md` y `sources.md`.
- Especificación: `research/kits/Ahri.spec.json`.
- Fixtures: `research/fixtures/ahri_extract_min.json` y `research/fixtures/ahri_tooltips_es_es.json` (122 cadenas).
- Informe: `research/reports/ahri-kit-16.22.md`.

## Pruebas

- **Nuevas:**
  - `research/tests/test_binmodel_bin2json.py` (8);
  - `research/tests/test_binmodel_kitgen.py`: 4 más (dos etiquetas, kit de Ahri reproducible, AP sin `mStat`, ajustes de reactivación);
  - `research/tests/test_binmodel_recheck.py`: 1 más (`mStat` ausente);
  - `tests/test_champion_ahri.py` (12).
- **Actualizadas:**
  - `tests/test_rotation_timeline.py`, con el nuevo mensaje al agotar las reactivaciones;
  - `tests/test_cli_ability.py` y `tests/test_kit_model.py`, que usaban a Ahri como campeón sin kit y ahora usan a Lux.
- **Suite final:** 951 pruebas, más 202 de `research/` (1 omitida).
- **Mutaciones deliberadas: 14.** Una sobrevivió: medir el intervalo de la R desde el primer impulso en vez del último. Murió con una prueba nueva.
