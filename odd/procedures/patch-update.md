# Procedimiento: actualizar el proyecto a un parche nuevo (DAT-02)

Pasos repetibles para llevar snapshot, catálogo, datos del cliente y kits a un parche nuevo. La primera vez se aplicó a 16.23.1 ([revisión](../../research/reports/client-16.23.md)).

## Requisitos

- El cliente de League of Legends ya actualizado al parche nuevo (`Game/content-metadata.json`).
- Las listas de hashes de CommunityDragon/Data (en GitHub, `hashes/lol/`): `hashes.binentries.txt`, `hashes.binfields.txt`, `hashes.bintypes.txt` y `hashes.rst.xxh3.txt`. No se versionan.
- Una rama de tarea desde `dev` (`chore/snapshot-<parche>`).

## Pasos

1. **Snapshot oficial** (necesita acceso a Data Dragon, normalmente en Windows):

   ```powershell
   cd "C:\Users\Yisus\Documents\LoL-Knowledge"
   .\.venv\Scripts\python.exe -m lol_knowledge update --patch <parche>
   ```

   Desde aquí `validate` falla hasta el paso 5: el catálogo sigue en el parche anterior.

2. **Qué cambió en Data Dragon:** `git diff --stat data/current` y, por campeón y objeto, las diferencias de estadísticas, costes, enfriamientos y descripciones. Anota los cambios en el informe del parche (`research/reports/client-<parche>.md`).

3. **Datos del cliente, primero sin escribir:**

   ```powershell
   $env:PYTHONPATH="research"
   .\.venv\Scripts\python.exe research\tools\refresh_patch.py --game "D:\Games\Riot Games\League of Legends\Game" `
     --hashes <carpeta de hashes> --retrieved-at <fecha>
   ```

   El guion regenera `catalog-stats.json`, `champion-records.json` e `item-effects.json` en un directorio temporal y lista cada cambio que no sea de procedencia; recompila cada kit desde el bin nuevo y lo compara con el publicado. Si el cliente y el snapshot son de parches distintos, se detiene (código 2).

4. **Escribir** los tres archivos con `--write`. Los kits nunca se escriben solos: si un kit cambia, se cura su especificación (`research/kits/<Id>.spec.json`) y se regenera como en [`research/README.md`](../../research/README.md). Si no cambia, se actualiza `verified_against` en la especificación (versión, `sha256` del bin e informe) y se recompila desde el fixture.

5. **Catálogo y defectos:**
   - `lol-knowledge/objects/catalog.json`: `game_version` al parche nuevo, `catalog_version` + 1 y una nota que diga qué se revisó. Cada efecto curado cuyo valor del cliente cambie se actualiza con dos fuentes cuando existan (cliente y notas del parche).
   - `lol-knowledge/data-issues.json`: comprobar cada defecto abierto en el snapshot nuevo y añadir el parche a `patches`, o marcarlo resuelto.

6. **Notas del parche:** buscar cambios de objetos curados, runas y campeones con kit. Un cambio en las notas que no aparezca en el cliente es una discrepancia que se documenta y se marca `Pendiente de verificación`.

7. **Pruebas y documentación:** las pruebas que nombran el parche o una cifra cambiada se actualizan (las pruebas con objetos sintéticos usan el parche del snapshot, no uno escrito a mano). Se actualizan las cabeceras de parche de las fichas de campeón, `INDEX.md`, el modelo de objetos y el README.

8. **Validar e integrar:** las cuatro validaciones de [`AGENTS.md`](../../AGENTS.md) §5, más `python -m pytest research -q`, y el flujo de integración habitual.
