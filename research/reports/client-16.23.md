# Revisión del parche 16.23 (Data Dragon 16.23.1 y cliente 16.23)

- **Fecha:** 2026-11-19
- **Snapshot:** Data Dragon 16.23.1, descargado por el usuario en Windows (`lol_knowledge update --patch 16.23.1`).
- **Cliente:** `16.23.8399929+branch.releases-16-23.content.release` (`Game/content-metadata.json`).
- **Método:** `research/tools/refresh_patch.py` y comparación campo a campo con los archivos de 16.22.1, sin contar los campos de procedencia (versiones, fechas, `sha256`). Procedimiento en [`../../odd/procedures/patch-update.md`](../../odd/procedures/patch-update.md).
- **Notas del parche:** <https://www.leagueoflegends.com/en-us/news/game-updates/league-of-legends-patch-26-23-notes/> (consultadas el 2026-11-19).

## Data Dragon 16.22.1 → 16.23.1 (`Oficial`)

| Archivo | Cambio |
|---|---|
| `champions/Azir.json` | Alcance de ataque 525 → 550 |
| `champions/KSante.json` | Coste de la W 45/50/55/60/65 → 45 |
| `champions/Syndra.json` | E: enfriamiento 15 → 17/16,5/16/15,5/15; coste 50 → 60 |
| `champions/Velkoz.json` | R: tercer valor del efecto 2 925 → 950 |
| `champions/Mel.json`, `Neeko.json`, `Sona.json`, `Zoe.json` | Solo aspectos o textos |
| `items.json` | Solo las descripciones de 4015 (Perplejidad) y 443079 (Arena); ninguno es comprable en la Grieta |

Zaahen y Ahri no cambian. `attackdamageperlevel` sigue a 0 en los 173 campeones, así que el defecto `ddragon-attack-damage-growth` se amplía a 16.23.1.

## Cliente 16.22 → 16.23 (`Derivado`)

| Archivo | Resultado |
|---|---|
| `lol-knowledge/derived/champion-records.json` | Cambian los 173 `sha256` de los bins; el único valor distinto es Azir `attackrange` 525 → 550 (coincide con Data Dragon) |
| `lol-knowledge/derived/item-effects.json` | Igual en los 218 objetos salvo 6699 (Espada ciclovoltaica): `PercentCurrentHPMelee` 9 → 8 y `PercentCurrentHPRanged` 7 → 6 |
| `lol-knowledge/objects/catalog-stats.json` | Sin cambios de estadísticas; solo el parche y el `sha256` de `items.json` |
| Kits de Zaahen y Ahri | El bin 16.23 (convertido con `binmodel.bin2json`) produce el mismo kit, salvo la versión que citan las fuentes. Bins: Zaahen `2cc61b27…`, Ahri `63bbd039…` |
| Tooltips es_ES de Zaahen y Ahri | Idénticos a los fixtures (123 y 122 cadenas) |

Las notas del parche 26.23 solo listan un cambio de objeto de la Grieta, el mismo que muestra el cliente: Espada ciclovoltaica, Firmamento, «[9% || 7%] ⇒ [8% || 6%]» de la vida actual. No hay cambios de runas.

## Decisiones

- **Catálogo de objetos (versión 18):** Firmamento pasa a 8 % / 6 % con dos fuentes, el cliente 16.23 y las notas del parche. Las fuentes `client_data` de los demás efectos citan ahora el cliente 16.23, porque sus valores se han vuelto a leer y coinciden.
- **Kits:** siguen citando el bin del que se extrajeron sus cifras (CommunityDragon 16.20 para Zaahen, cliente 16.22 para Ahri). El campo `verified_against` registra el bin 16.23 y su `sha256`. Así los fixtures de las pruebas siguen reproduciendo el kit publicado.
- **Reglas de `mechanics/`:** mantienen su parche de referencia; solo [`attack-counters.md`](../../lol-knowledge/mechanics/attack-counters.md) cambia, por la Espada ciclovoltaica.

## Limitaciones

- La evidencia secundaria (wiki) del catálogo no se ha vuelto a leer. Se ha contrastado con las notas del parche y con el cliente, y ninguno de los dos indica cambios.
- Las pruebas en Windows (`.\.venv\Scripts\python.exe`) no se han ejecutado sobre este estado.
