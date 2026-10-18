# Zaahen — Fuentes

- **Parche:** 16.20.1
- **Locale:** `es_ES`
- **Fecha de consulta:** 2026-10-18
- **Snapshot:** [`data/current/manifest.json`](../../../data/current/manifest.json), con `sha256` por archivo.

## Fuentes consultadas (`Oficial`)

| Fuente | Uso | Cobertura | Limitación |
|---|---|---|---|
| `https://ddragon.leagueoflegends.com/api/versions.json` | Detectar el parche vigente | Lista de versiones | Solo versiones publicadas |
| `https://ddragon.leagueoflegends.com/cdn/16.20.1/data/es_ES/champion/Zaahen.json` | Identidad, estadísticas, pasiva, habilidades | Completo en nombres, costes, enfriamientos y rangos | Sin valores numéricos de efectos |
| `https://ddragon.leagueoflegends.com/cdn/16.20.1/data/es_ES/item.json` | Catálogo de objetos del parche | Nombres, costes y mapas | Sin datos de rendimiento |
| `https://ddragon.leagueoflegends.com/cdn/16.20.1/data/es_ES/runesReforged.json` | Árboles y runas del parche | Nombres e identificadores | Sin datos de rendimiento |

## Fuentes de terceros, no oficiales (`Pendiente de verificación`)

Se consultaron para **contrastar** los huecos de Data Dragon, nunca como fuente oficial. Ningún valor suyo se ha publicado como dato en esta base de conocimiento.

| Fuente | Naturaleza y licencia | Qué aporta | Límite |
|---|---|---|---|
| CommunityDragon | Proyecto comunitario bajo la política de Riot; **sin licencia SPDX declarada** | Export del bin del cliente con valores por campo y ruta exacta (contenido 16.20, `sha256` del origen `76e32de67667917769cc6022a818b13e5024ea521a23c70436dc48eea533ed0b`) | La ausencia de licencia no demuestra permiso ni prohibición; redistribuir el archivo original no está autorizado de forma clara |
| LoL Wiki | Contenido de terceros, **CC BY-SA 3.0** | Valores de contraste para Q, W, E, R y la pasiva | Su API respondió 403 a la consulta automatizada; los valores se transcribieron a mano de la página renderizada |
| Riot — Data Dragon | **Oficial** | Snapshot de `data/current/` | No publica los valores numéricos de las habilidades de este campeón |

Ambas fuentes de terceros quedan **bloqueadas como dato publicable** hasta que exista una decisión explícita de producto y la atribución y el aviso de no afiliación exigidos por las políticas de Riot. Detalle del análisis: [`../../../research/evidence/usage-conditions.md`](../../../research/evidence/usage-conditions.md).

## Qué no se pudo verificar (`Pendiente de verificación`)

- Daño, escalados y porcentajes de las habilidades: los textos usan marcadores con nombre y `effectBurn` viene a `0`.
- Multiplicador de Q contra monstruos: CommunityDragon y la wiki no coinciden; discrepancia abierta.
- AD por acumulación de la pasiva: CommunityDragon y la wiki no coinciden, y el historial de parches de la wiki contradice su propio resumen.
- Crecimiento de daño de ataque: Data Dragon publica `0`; CommunityDragon y la wiki dan otro valor.
- Consejos oficiales de aliados y enemigos: Data Dragon los devuelve vacíos para este campeón.
- Cualquier estadística de win rate, pick rate o build: no se consultó ninguna fuente comunitaria.

El estado completo de la investigación, con evidencia, hashes y líneas abiertas, está en [`../../../research/zaahen-research-handoff.md`](../../../research/zaahen-research-handoff.md).

## Fuentes descartadas por ahora

Se descartaron las estadísticas comunitarias porque no se ha verificado que su acceso respete sus condiciones de uso. No se afirma nada sobre lo que dicen.

## Reproducibilidad

```powershell
.\.venv\Scripts\python.exe -m lol_knowledge update --patch 16.20.1
.\.venv\Scripts\python.exe -m lol_knowledge validate
```

El snapshot se descarga de Data Dragon y se verifica por checksums. Si un archivo cambia, `validate` lo detecta antes de que se use.
