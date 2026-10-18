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

## Qué no se pudo verificar (`Pendiente de verificación`)

- Daño, escalados y porcentajes de las habilidades: los textos usan marcadores con nombre y `effectBurn` viene a `0`.
- Consejos oficiales de aliados y enemigos: Data Dragon los devuelve vacíos para este campeón.
- Cualquier estadística de win rate, pick rate o build: no se consultó ninguna fuente comunitaria.

## Fuentes descartadas por ahora

Se descartaron las estadísticas comunitarias porque no se ha verificado que su acceso respete sus condiciones de uso. No se afirma nada sobre lo que dicen.

## Reproducibilidad

```powershell
.\.venv\Scripts\python.exe -m lol_knowledge update --patch 16.20.1
.\.venv\Scripts\python.exe -m lol_knowledge validate
```

El snapshot se descarga de Data Dragon y se verifica por checksums. Si un archivo cambia, `validate` lo detecta antes de que se use.
