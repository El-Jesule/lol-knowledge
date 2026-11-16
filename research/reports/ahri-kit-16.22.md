# Kit de Ahri desde el bin del cliente 16.22

- **Fecha:** 2026-11-16 (fase 33)
- **Cliente:** `16.22.8348910+branch.releases-16-22.content.release`
- **Bin:** `DATA/FINAL/Champions/Ahri.wad.client` → `data/characters/ahri/ahri.bin`, `sha256` `121997c9c4ef2ff0f671b659d64d2e22cb71208216ddcc3c4f552a17f196d2cb` (el mismo que registra [`../../lol-knowledge/derived/champion-records.json`](../../lol-knowledge/derived/champion-records.json))
- **Etiqueta:** `Derivado`

## Por qué sin CommunityDragon

El extractor (`python -m binmodel`) lee exports `.bin.json` de CommunityDragon, y CommunityDragon no es accesible desde el entorno de trabajo (la petición devuelve 403 en el proxy). `binmodel/bin2json.py` produce la misma forma desde el bin del cliente instalado:

- Recorre el bin con el lector estricto `propbin` y escribe cada entrada con sus campos y `__type`, como los exports.
- Resuelve los nombres con las listas de hashes de CommunityDragon (`hashes.binentries.txt`, `hashes.binfields.txt`, `hashes.bintypes.txt`, descargadas antes para los objetos), con los textos del propio bin (nombres de los `DataValues`), con los marcadores `@…@` de los tooltips (nombres de los cálculos) y con los nombres de modo de juego.
- Un hash sin nombre queda `{xxxxxxxx}`. Los floats conservan su float32, escrito como el doble que lo contiene, igual que los exports.

### Comprobación con Zaahen

1. **Comparación con CommunityDragon:** el bin 16.22 de Zaahen, convertido, se comparó campo a campo con el export 16.20 de la caché. Las diferencias son:
   - cambios reales entre parches (enfriamientos de la Q y la pasiva de la R);
   - valores `hash` que solo resuelve `hashes.binhashes.txt`, que no está disponible (efectos visuales, nombres de modos, posiciones), y rutas de ficheros;
   - mayúsculas distintas en nombres con el mismo hash (`catalogEntry`/`CatalogEntry`; `KnockUpDuration` sale como en el bin y CommunityDragon lo escribe `KnockupDuration`).
2. **Kit regenerado:** el kit de Zaahen compilado desde esa conversión es **idéntico** al publicado, salvo las cadenas de fuente con la versión de contenido.

## `mStat` ausente = poder de habilidad

Ninguna parte de escalado de Ahri lleva `mStat`. Un bin omite los valores por defecto de la clase, así que el campo vale 0, igual que `mStatFormula` ausente vale 0 («total»). Que 0 sea poder de habilidad se apoya en:

| Evidencia | Detalle |
|---|---|
| Nombres de los factores | W y E: `APRatio`; R: `RAPCoefficient` |
| Cifras de fuentes secundarias | Q 35/60/85/110/135 (+50 % AP) por pasada (riftpatchnotes.com); W 40–120 (+40 % AP) y E 80–240 (+85 % AP) (metasrc.com, 26.14); historial de la Q a 50 % (wiki de Fandom). Coinciden con el bin |
| Otro bin | Diente de Nashor: la parte sin `mStat` se llama `NashorsAPValue` (fase 23) |

`binmodel/stats.py` mapea ahora `mStat` 0 (o ausente) a `ability_power` con confianza `corroborated`. Para la R solo hay el nombre del dato, sin cifra externa.

## Kit

Especificación: [`../kits/Ahri.spec.json`](../kits/Ahri.spec.json). Kit: [`../../lol-knowledge/champions/Ahri/kit.json`](../../lol-knowledge/champions/Ahri/kit.json).

| Habilidad | Casos | Cálculo |
|---|---|---|
| Q | `out` (mágico), `back` (verdadero), `both` | `TotalDamage` = `BaseDamage` + 0,5 × AP. El tooltip lo muestra bajo `<magicDamage>` y `<trueDamage>`; `kitgen` admite ahora un valor bajo dos etiquetas si la parte declara cuál usa |
| W | `one`, `all` (100 % + 40 % + 40 %) | `SingleFireDamage` = `BaseDamage` + `APRatio` × AP; `MultiFireDamage` = `SingleFireDamage` × `RepeatDamageMod` (0,4) |
| E | `hit` | `TotalDamage` = `BaseDamage` + `APRatio` (0,85) × AP |
| R | `dash`, `recast` | `RCalculatedDamage` = `RBaseDamage` + `RAPCoefficient` (0,35) × AP; `RRecastWindow` 15, `RDashCooldown` 1 y 2 reactivaciones (tooltip: «reactivar hasta 2 veces más»; `RMaxCasts` 3) |

`kitgen` lee la ventana y el intervalo de la R del bin (`{"data_value": …}` en la especificación) y exige que no cambien con el rango. El modelo de kit admite `max_recasts` y `recast_interval_seconds`, y la línea de tiempo los aplica.

Los enfriamientos de `Cooldown.values` coinciden con Data Dragon (Q 7; W 9–5; E 12; R 140/120/100).

## Sin modelar

- **Pasiva:** solo cura, sin daño. Las curaciones usan interpolación por nivel.
- **R:** los lanzamientos extra y la ampliación de 10 s por derribos.
- **R contra varios objetivos:** 3 rayos a enemigos distintos (`RMaxTargetsPerCast`). Contra un objetivo se cuenta uno por impulso; no está medido.
- **W:** velocidad de movimiento y el daño doble a súbditos con poca vida.
- **E:** el hechizo.
- **Variantes `_jade` y textos antiguos:** también están en las cadenas del cliente, pero los cálculos del bin actual son los que usan las claves `Spell_AhriOrbofDeception_Tooltip`, `Spell_AhriFoxFire_Tooltip`, `Spell_AhriSeduce_Tooltip` y `Spell_AhriTumble_Tooltip`.

## Reproducir

```powershell
$env:PYTHONPATH="research"
.\.venv\Scripts\python.exe research\tools\extract_rst.py `
  --wad "<Game>\DATA\FINAL\Localized\Global.es_ES.wad.client" --hash-table <hashes.rst.xxh3.txt> `
  --output research\fixtures\ahri_tooltips_es_es.json --retrieved-at 2026-11-16 `
  --prefix spell_ahri --prefix buff_ahri --prefix generatedtip_spell_ahri `
  --prefix generatedtip_passive_ahri --prefix generatedtip_buff_ahri
.\.venv\Scripts\python.exe -m binmodel.bin2json --wad "<Game>\DATA\FINAL\Champions\Ahri.wad.client" `
  --entry data/characters/ahri/ahri.bin --hashes <carpeta con las listas de hashes> `
  --names research\fixtures\ahri_tooltips_es_es.json --output ahri.bin.json
.\.venv\Scripts\python.exe -m binmodel --input ahri.bin.json --json --game-version 16.22 `
  --content-version 16.22.8348910+branch.releases-16-22.content.release > ahri-extract.json
.\.venv\Scripts\python.exe -m binmodel.kitgen --extract ahri-extract.json `
  --tooltips research\fixtures\ahri_tooltips_es_es.json --spec research\kits\Ahri.spec.json `
  --output lol-knowledge\champions\Ahri\kit.json
```

El fixture recortado [`../fixtures/ahri_extract_min.json`](../fixtures/ahri_extract_min.json) reproduce el kit en las pruebas, sin el cliente.
