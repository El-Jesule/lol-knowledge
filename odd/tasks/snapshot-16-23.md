# Parche 16.23 y procedimiento repetible — fase 35

- **Objetivo:** llevar snapshot, catálogo, datos del cliente y kits a 16.23 (DAT-01) y dejar el proceso escrito y automatizado (DAT-02).
- **Rama:** `chore/snapshot-16-23`, desde `dev`. El snapshot lo descargó el usuario en Windows (`lol_knowledge update --patch 16.23.1`); Data Dragon no es accesible desde el entorno de Claude.
- **Entorno de validación:** shell Linux de Claude en el equipo del usuario, Python 3.14.10 (venv propio). No se ha ejecutado la suite con `.\.venv\Scripts\python.exe` en Windows sobre este estado.

## Cambios

- `data/current/` → Data Dragon 16.23.1. Detalle de lo que cambia en [`research/reports/client-16.23.md`](../../research/reports/client-16.23.md).
- `catalog-stats.json`, `champion-records.json` e `item-effects.json` regenerados con el cliente 16.23. Solo cambian Azir (alcance 550) y la Espada ciclovoltaica (Firmamento 8 % / 6 %).
- Catálogo `catalog_version: 18`, `game_version: 16.23.1`; Firmamento actualizado con el cliente y las notas del parche 26.23.
- Defecto `ddragon-attack-damage-growth` comprobado en 16.23.1.
- Kits: `verified_against` → bin 16.23; las cifras siguen citando su bin de origen.
- Nuevo `research/tools/refresh_patch.py`, con pruebas en `research/tests/test_refresh_patch.py`, y el procedimiento [`odd/procedures/patch-update.md`](../procedures/patch-update.md).
- Pruebas: las que nombraban 16.22.1 pasan a 16.23.1; las de objetos sintéticos usan el parche del snapshot.

## Limitaciones

- La evidencia secundaria del catálogo no se ha vuelto a leer en la wiki; ni el cliente ni las notas del parche indican cambios.
- `refresh_patch.py` no actualiza el catálogo, los defectos ni las pruebas: los lista como siguientes pasos, porque exigen criterio.
