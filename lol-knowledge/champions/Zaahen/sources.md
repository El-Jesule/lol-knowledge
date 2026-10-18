# Zaahen — Fuentes

- **Parche:** 16.20.1
- **Locale:** `es_ES`
- **Fecha de consulta:** 2026-10-18
- **Snapshot:** [`data/current/manifest.json`](../../../data/current/manifest.json), con `sha256` por archivo.

## Fuentes oficiales (`Oficial`)

| Fuente | Uso | Cobertura | Limitación |
|---|---|---|---|
| `https://ddragon.leagueoflegends.com/api/versions.json` | Detectar el parche vigente | Lista de versiones | Solo versiones publicadas |
| `https://ddragon.leagueoflegends.com/cdn/16.20.1/data/es_ES/champion/Zaahen.json` | Identidad, estadísticas, pasiva y textos de habilidades | Completo en nombres, costes, enfriamientos y rangos | Sin valores numéricos de efectos |
| `https://ddragon.leagueoflegends.com/cdn/16.20.1/data/es_ES/item.json` | Catálogo de objetos del parche | Nombres, costes y mapas | Sin datos de rendimiento |
| `https://ddragon.leagueoflegends.com/cdn/16.20.1/data/es_ES/runesReforged.json` | Árboles y runas del parche | Nombres e identificadores | Sin datos de rendimiento |

## Fuente derivada (`Derivado`)

Los valores marcados `Derivado` en [`abilities.md`](abilities.md) y [`overview.md`](overview.md) proceden de los datos del cliente, publicados por CommunityDragon. **No son una API oficial de Riot** y no se presentan como tales.

| Campo | Valor |
|---|---|
| Fuente | CommunityDragon — export del bin del cliente |
| URL | `https://raw.communitydragon.org/16.20/game/data/characters/zaahen/zaahen.bin.json` |
| Build de contenido | `16.20.8248524+branch.releases-16-20.content.release` |
| `sha256` del archivo original | `76e32de67667917769cc6022a818b13e5024ea521a23c70436dc48eea533ed0b` |
| Fecha de descarga | 2026-10-18 |
| Locale de contraste | `es_ES` (textos del cliente en `Global.es_ES.wad.client`) |

**Método de extracción.** Lectura directa de `mSpell.DataValues`, `mSpell.mSpellCalculations`, `mSpell.Cooldown.values` y `CharacterRecords/Root`. Los enfriamientos efectivos se toman de `Cooldown.values`; `cooldownTime` se conserva solo como diagnóstico. La procedencia por campo, las rutas internas y el contraste con Data Dragon y RCP están en el [documento de continuidad](../../../research/zaahen-research-handoff.md).

**Límites.**

- La vinculación exacta entre el build `16.20.8248524` y la cadena `16.20.1` de Data Dragon no está demostrada; se comprobó que el bin del cliente y el export de CommunityDragon son idénticos byte a byte.
- La semántica de `mStat`/`mStatFormula` es una interpretación, no un enum publicado por Riot.
- Las cifras no se han medido en partida.
- El archivo original no se versiona; solo se publican valores derivados y su trazabilidad.

## Contraste, no fuente publicable (`Pendiente de verificación`)

| Fuente | Naturaleza y licencia | Uso | Límite |
|---|---|---|---|
| LoL Wiki | Contenido de terceros, CC BY-SA 3.0 | Contraste de valores | Su API respondió 403 a la consulta automatizada; los valores se transcribieron a mano. No se publican como dato propio |

La wiki no se usa como fuente de ningún valor publicado. Cuando discrepa del bin, la discrepancia queda declarada.

## Qué sigue abierto (`Pendiente de verificación`)

- **Crecimiento de daño de ataque:** Data Dragon publica `0`; el cliente indica 4,0. No se sustituye el dato oficial.
- **AD por acumulación de la pasiva:** el bin y el historial de la wiki apuntan a 2,8 %; el resumen de la wiki dice 2,95 %.
- **Multiplicador de Q contra monstruos:** el texto del cliente dice «daño adicional»; no se ha medido en partida.
- **Consejos oficiales de aliados y enemigos:** Data Dragon los devuelve vacíos.
- **Rendimiento:** no se consultó ninguna estadística comunitaria de win rate, pick rate o builds.

El estado completo, con evidencia, hashes y líneas abiertas, está en [`../../../research/zaahen-research-handoff.md`](../../../research/zaahen-research-handoff.md).

## Aviso de no afiliación

Este proyecto es una base de conocimiento no comercial. No está afiliado ni respaldado por Riot Games.

> LoL-Knowledge isn't endorsed by Riot Games and doesn't reflect the views or opinions of Riot Games or anyone officially involved in producing or managing Riot Games properties. Riot Games, and all associated properties are trademarks or registered trademarks of Riot Games, Inc.

Condiciones de uso investigadas y cuestiones pendientes: [`../../../research/evidence/usage-conditions.md`](../../../research/evidence/usage-conditions.md).

## Reproducibilidad

```powershell
.\.venv\Scripts\python.exe -m lol_knowledge update --patch 16.20.1
.\.venv\Scripts\python.exe -m lol_knowledge validate
```

El snapshot oficial se descarga de Data Dragon y se verifica por checksums. Los valores derivados no forman parte de `data/current/` y no se regeneran con `update`.
