# Registros de estadísticas de campeón del cliente 16.22

- **Fecha de consulta:** 2026-11-15
- **Fuente:** cliente local, `DATA/FINAL/Champions/<Id>.wad.client` → `data/characters/<id>/<id>.bin` → `Characters/<Id>/CharacterRecords/Root`
- **Build:** `16.22.8348910+branch.releases-16-22.content.release` (de `Game/content-metadata.json`)
- **Método:** `python -m binmodel.records` (lector PROP estricto de `binmodel.propbin`); cada float32 se escribe como el decimal más corto que vuelve al mismo float32; un campo ausente no se rellena.
- **Resultado publicado:** [`../../lol-knowledge/derived/champion-records.json`](../../lol-knowledge/derived/champion-records.json), con el SHA-256 de cada bin. No se versiona ningún archivo del cliente.
- **Etiqueta:** `Derivado`. No es una API oficial de Riot.

## Por qué

Data Dragon 16.20.1 publica `attackdamageperlevel = 0` para los 173 campeones (`ddragon-attack-damage-growth` en [`../../lol-knowledge/mechanics/known-data-issues.md`](../../lol-knowledge/mechanics/known-data-issues.md)). El bin de cada campeón trae su crecimiento real.

## Resultado

- **173 de 173** campeones del índice de Data Dragon leídos sin fallos.
- `attackdamageperlevel` presente en 172. El crecimiento va de 1,5 a 4,0 y hay valores no redondos (uno es 3.1415927).
- `attackspeedratio` (ratio de velocidad de ataque) presente en los 173. Data Dragon no lo publica; servirá para modelar la velocidad de ataque.

### Campos ausentes en el bin (no se rellenan)

| Campeón | Campo ausente |
|---|---|
| Senna | `attackdamageperlevel` |
| Thresh | `armorperlevel` |
| Bel'Veth | `attackspeedperlevel` |
| Jhin | `attackspeedperlevel` |

Todos coinciden con campeones conocidos por no crecer en esa estadística, así que el valor por defecto de la clase probablemente es 0. **No está demostrado**: el volcado de clases no publica valores por defecto. La estadística de DA de Senna sigue bloqueada por encima del nivel 1.

### Diferencias con Data Dragon 16.20.1 (sin contar `attackdamageperlevel`)

| Campeón | Campo | Data Dragon 16.20.1 | Cliente 16.22 | Lectura |
|---|---|---|---|---|
| Jinx | `hp` | 630 | 610 | Cambio de equilibrado entre parches |
| Mel | `hp`, `hpperlevel`, `armorperlevel`, `attackdamage`, `attackspeedperlevel` | 630, 99, 5,2, 54, 2,5 | 590, 107, 5,4, 52, 2,75 | Cambio de equilibrado |
| Sion | `hpperlevel` | 87 | 95 | Cambio de equilibrado |
| Thresh | `attackdamage` | 56 | 54 | Cambio de equilibrado |
| Viktor | `hpperlevel`, `movespeed` | 100, 335 | 105, 330 | Cambio de equilibrado |
| Diana, Leona | `armorperlevel` | 4,3 / 4,8 | 4,2999997 / 4,7999997 | Representación: el float32 del bin está un paso por debajo del redondeo de Data Dragon |

El resto de campos coincide en 166 campeones. Que coincidan no demuestra que su crecimiento de DA no haya cambiado entre parches.

## Cómo se usa

La hoja de estadísticas sustituye un campo con defecto abierto por el valor de esta tabla. Si el cliente y el snapshot son de parches distintos, el aporte se marca `Pendiente de verificación` y el informe lo explica; con los dos en 16.22 es `Derivado`.

**Actualización 2026-11-15:** con el snapshot en Data Dragon 16.22.1, las diferencias de la tabla anterior de Jinx, Mel, Sion, Thresh y Viktor coinciden exactamente con los cambios de Data Dragon entre 16.20.1 y 16.22.1. Es una corroboración independiente de que el extractor lee bien los registros.

## Reproducir

```powershell
$env:PYTHONPATH="research"
.\.venv\Scripts\python.exe -m binmodel.records `
  --wad-dir "D:\Games\Riot Games\League of Legends\Game\DATA\FINAL\Champions" `
  --index data\current\champion-index.json `
  --content-version 16.22.8348910+branch.releases-16-22.content.release `
  --retrieved-at 2026-11-15 --output lol-knowledge\derived\champion-records.json
```
