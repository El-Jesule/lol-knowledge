# ddragon-ingest — Fase 1

Objetivo: descargar el snapshot oficial de Data Dragon, normalizarlo de forma determinista y sustituirlo de manera reversible, con manifiesto verificable por checksums.

- Rama: `feat/ddragon-ingest` (base: `dev`)
- Runner: pytest sobre `.venv` (Python 3.14)
- Fuente: Data Dragon `https://ddragon.leagueoflegends.com`, locale `es_ES`, sin claves de API

## Specs

- **S1.** `python -m lol_knowledge update` descarga el parche más reciente (o el indicado con `--patch`) y escribe `data/current/`.
- **S2.** El snapshot contiene: `manifest.json`, `champion-index.json`, `champions/<Id>.json` por campeón, `items.json` y `runes.json`.
- **S3.** `manifest.json` registra `schema_version`, `patch`, `locale`, `source`, `fetched_at` en UTC y `sha256`/tamaño de cada archivo.
- **S4.** Serialización determinista: claves ordenadas, UTF-8 sin escapes ASCII, salto de línea final. Dos ejecuciones sobre el mismo parche producen los mismos bytes.
- **S5.** Segunda ejecución sobre el mismo parche informa «sin cambios» y no reescribe ningún archivo, incluido `manifest.json`.
- **S6.** Escritura en staging validado y sustitución por renombrado; si falla la descarga, la validación o el renombrado, el snapshot anterior queda intacto y no sobreviven restos de staging.
- **S7.** Datos externos tratados como entrada no confiable: se validan forma, tipos y rangos antes de publicarlos en `data/current/`.
- **S8.** Códigos de salida: `0` éxito (con o sin cambios), `1` datos inválidos, `2` entorno, red o fuente no disponible.
- **S9.** Los tests no acceden a la red: usan fixtures locales e inyección de cliente.
- **S10.** Sin dependencias nuevas de runtime.

## Tasks

- [x] T1 — Cliente HTTP y errores tipados (`errors.py`, `ddragon.py`). Spec: S1, S8, S9. Route: inline. Commit: `2fc1615`.
- [x] T2 — Sustitución de placeholders de tooltips (`textutil.py`). Spec: S4. Route: inline. Commit: `b7b9903`.
- [x] T3 — Construcción, validación y sustitución del snapshot (`snapshot.py`). Spec: S2, S3, S5, S6, S7. Route: inline. Commit: `500bfd2`.
- [x] T4 — Comando `update` en la CLI y documentación. Spec: S1, S8. Route: inline. Commit: `500bfd2`.
- [x] T5 — Snapshot real del parche vigente en `data/current/`. Spec: S2, S3. Route: inline. Commit: `0a04a0e`.

## Log

- **L1.** El usuario aprueba el plan y pide iniciar la Fase 1 tras la revisión de mantenimiento: «Adelante, inicia Fase 1». Condiciones vigentes: sin push desde el agente, validaciones obligatorias, Conventional Commits en inglés, etiquetas de fuente y nada de datos inventados.
- **L2.** Aprobado en la entrevista: Data Dragon como fuente oficial inicial, sin Riot API; actualización bajo demanda; snapshot del parche actual y changelog por parche; estadísticas comunitarias fuera de esta fase.
- **L3.** Decisión de diseño: se guarda el objeto crudo de cada campeón y el mapa `data` de objetos/runas sin reinterpretar, para no perder trazabilidad. El índice de campeones es una proyección compacta para consultas baratas.
- **L4.** Decisión de diseño: el renombrado de directorios (`current` → `.backup`, `.staging` → `current`) es el punto de confirmación. `manifest.json` se escribe al final del staging para que un snapshot a medias nunca se publique como válido.
- **L5.** Descubrimiento con datos reales: `items.json` de `es_ES` contiene 4 objetos heredados con `name` vacío (el primero, `2008`), no comprables y sin mapa. La validación se relajó de «nombre no vacío» a «nombre de tipo string»; se conservan por ser dato oficial y se emite un `WARNING` con el recuento. Un nombre de tipo distinto sigue siendo `PayloadError`.
- **L6.** Corrección de consistencia: `UpdateResult.file_count` excluye `manifest.json` en ambos caminos, para que «updated» y «unchanged» informen del mismo número. Cubierto por test.
- **L7.** Verificación ejecutada el 2026-10-18 sobre `feat/ddragon-ingest`: `pytest -q` → 38 passed; `ruff check .` → All checks passed; `ruff format --check .` → 18 files already formatted. Ejecución real: `update` → `updated: patch 16.20.1 (176 files)`, 177 archivos en disco, 4,61 MB. Segunda ejecución → `unchanged`, hash y `mtime` del manifiesto idénticos. `update --patch 0.0.1` → exit 2 con «patch 0.0.1 is not published by Data Dragon».
- **L8.** Sin acceso a notas de parche en esta fase: el snapshot solo contiene lo que Data Dragon publica. Las descripciones mecánicas y las builds se abordan en la fase 3 con la misma regla de no inventar.
