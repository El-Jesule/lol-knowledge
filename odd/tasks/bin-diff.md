# Lectura directa del bin del cliente y comparación entre parches — fase 7

- **Objetivo:** leer el bin binario de un campeón desde el cliente instalado y compararlo con un export `.bin.json` de CommunityDragon, para saber qué valores derivados siguen vigentes en cada parche sin depender de que CommunityDragon sea accesible.
- **Rama:** `feat/bin-diff`, creada desde `dev` (`f235a58`) después de integrar la fase 6 con aprobación expresa del usuario (2026-11-15).
- **Entrega:** `research/binmodel/{xxh64,propbin,wad,bindiff}.py`, pruebas sintéticas en `research/tests/`, sección «Fase 7» en `research/README.md` e informe `research/reports/zaahen-bin-diff-16.22.md`.
- **Entorno de ejecución:** shell Linux de Claude en el equipo del usuario, Python 3.14.10 (uv), `pytest==9.1.1`, `ruff==0.17.1`, `PYTHONPATH=src` en lugar de la instalación editable. No se ha ejecutado con `.\.venv\Scripts\python.exe` en Windows.

## Specs

### S1 — Integración previa de la fase 6

`feat/object-mechanics-coverage` (`c50e487`) → `integration` con `merge --no-ff` (`f235a58`) → `dev` con `merge --ff-only`. Validación integrada sobre `integration`: `pytest -q` `214 passed`, `pytest research -q` `97 passed`, `ruff check` y `ruff format --check` limpios, `lol_knowledge validate` `valid: 183 files checked`, salida `0`. `git diff dev..integration`: 61 archivos (53 añadidos, 8 modificados), sin archivos del cliente ni de `data/current/`.

### S2 — Lector estricto de PROP y WAD

- XXH64 en Python puro, fijado contra vectores publicados y contra cinco hashes de ruta observados en el cliente 16.22.
- Lector `PROP` v1–v3 que rechaza tipos desconocidos, tamaños declarados que no cuadran, campos o entradas duplicados, cadenas truncadas y bytes sobrantes.
- Lector de entradas de WAD v3 por ruta; tipos 2 y 4 se rechazan explícitamente.

### S3 — Comparador bin ↔ export

Recorrido paralelo guiado por los tipos del bin, nombres hasheados con FNV-1a (XXH64 para `file`), floats comparados en float32, claves de mapa normalizadas según su tipo. CLI `python -m binmodel.bindiff` con `--bin` o `--wad --entry`, `--json` y `--check`.

Las pruebas detectan dos mutaciones deliberadas: quitar el redondeo a float32 y quitar la comprobación del tamaño declarado.

### S4 — Aplicación a Zaahen 16.22

Ver `research/reports/zaahen-bin-diff-16.22.md`: tres cambios (enfriamiento de la Q, `PBonusADMax` solo en Arena, campo nuevo `{1632f6fc}` en la R). La base de conocimiento no se actualiza: sigue anclada al snapshot oficial 16.20.1.

## Limitaciones

- `skin0.bin` de Zaahen 16.22 se rechaza por un tipo `0xb5` sin documentar.
- `tools/extract_rst.py` sigue saltándose en silencio las entradas de tipo 4 del WAD.
- Data Dragon 16.22 no se ha descargado: CommunityDragon está bloqueado en este entorno y no se ha comprobado Data Dragon.
