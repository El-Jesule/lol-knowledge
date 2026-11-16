# Ahri — Fuentes

- **Parche:** 16.22.1 (datos oficiales); cliente 16.22 para los derivados
- **Locale:** `es_ES`
- **Fecha de consulta:** 2026-11-16
- **Snapshot:** [`data/current/manifest.json`](../../../data/current/manifest.json), con `sha256` por archivo.

## Fuentes oficiales (`Oficial`)

| Fuente | Uso | Limitación |
|---|---|---|
| `https://ddragon.leagueoflegends.com/cdn/16.22.1/data/es_ES/champion/Ahri.json` | Identidad, estadísticas, textos, costes, enfriamientos y alcances | Sin valores numéricos de los efectos |

## Fuente derivada (`Derivado`)

Los valores `Derivado` de [`abilities.md`](abilities.md) y del [kit](kit.json) salen del bin del cliente instalado. **No son una API oficial de Riot.**

| Campo | Valor |
|---|---|
| Archivo | `DATA/FINAL/Champions/Ahri.wad.client`, entrada `data/characters/ahri/ahri.bin` |
| `sha256` del bin | `121997c9c4ef2ff0f671b659d64d2e22cb71208216ddcc3c4f552a17f196d2cb` |
| Build de contenido | `16.22.8348910+branch.releases-16-22.content.release` |
| Textos | `Localized/Global.es_ES.wad.client` → [`../../../research/fixtures/ahri_tooltips_es_es.json`](../../../research/fixtures/ahri_tooltips_es_es.json) (122 cadenas) |
| Nombres de los hashes | Listas de CommunityDragon (`hashes.binentries/binfields/bintypes.txt`), los textos del bin y los marcadores `@…@` de los tooltips |

**Método.** `python -m binmodel.bin2json` convierte el bin al formato de los exports de CommunityDragon; `python -m binmodel` extrae los cálculos; `python -m binmodel.kitgen` compila el kit con la especificación [`../../../research/kits/Ahri.spec.json`](../../../research/kits/Ahri.spec.json). El método se comprobó regenerando el kit de Zaahen desde su bin 16.22: sale idéntico al publicado. Detalle en [`../../../research/reports/ahri-kit-16.22.md`](../../../research/reports/ahri-kit-16.22.md).

## Fuentes secundarias de contraste

| Fuente | Qué confirma |
|---|---|
| riftpatchnotes.com, Ahri (consulta del 2026-11-16) | Q 35/60/85/110/135 (+50 % AP) por pasada |
| metasrc.com, Ahri (parche 26.14) | W 40–120 (+40 % AP), E 80–240 (+85 % AP) |
| Wiki de Fandom (historial) | Cambio de la Q a 50 % de AP por pasada |

No sustituyen al bin: solo corroboran que las partes sin `mStat` escalan con poder de habilidad.
