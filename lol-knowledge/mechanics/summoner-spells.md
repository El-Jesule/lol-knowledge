# Hechizos de invocador

- **Ámbito:** los 9 hechizos de invocador de la Grieta del Invocador en hoja de estadísticas (`stats`), rotación (`rotation`, pasos `summoner:<hechizo>`), supervivencia inversa (`survive`), optimizador (`optimize`), contrato JSON (`contract`) y servidor MCP (`mcp`).
- **Parche de referencia:** Data Dragon `16.23.1` y cliente `16.23` (`16.23.8406595+branch.releases-16-23.content.release`).
- **Fecha de consulta:** 2026-11-22
- **Datos derivados:** [`lol-knowledge/derived/summoner-spells.json`](../derived/summoner-spells.json)
- **Código:** [`src/lol_knowledge/summoners.py`](../../src/lol_knowledge/summoners.py), [`src/lol_knowledge/rotation/`](../../src/lol_knowledge/rotation/), [`src/lol_knowledge/defense/`](../../src/lol_knowledge/defense/), [`research/binmodel/summoners.py`](../../research/binmodel/summoners.py)

## Fuentes

| Id | Fuente | Qué cubre | Naturaleza |
|---|---|---|---|
| S1 | Cliente `16.23` (`DATA/FINAL/Global.wad.client:shared`, registros `Shared/Spells/Summoner*` y `S12_SummonerTeleportUpgrade`, build `16.23.8406595+branch.releases-16-23.content.release`) | Enfriamientos, alcances, `DataValues` y curvas por nivel `1..18` de todos los hechizos de invocador de la Grieta | `Derivado` (datos del cliente, no API oficial) |
| S2 | Cliente `16.23` (`DATA/FINAL/Localized/Global.es_ES.wad.client`, claves `spell_summoner*`) | Nombres localizados y textos de descripción en español | `Derivado` |
| S3 | [`item-effects.json`](../derived/item-effects.json) y [`runes.json`](../derived/runes.json) (`16.23`) | Aceleración de hechizos de invocador: Perspicacia cósmica (`data:rune:8347`: `+18`), Botas jonias de la lucidez (`data:item:3158`: `+10`) y Lucidez carmesí (`data:item:3171`: `+20`) | `Derivado` |

## 1. Catálogo y valores exactos (`Derivado`, S1–S2)

| ID | Alias | Nombre | CD base | Efecto y cifras del cliente `16.23` | Estado |
|---|---|---|---|---|---|
| `SummonerDot` | `ignite` | Prender | 180 s | Daño verdadero por nivel: `70, 90, 110, 130, 150` (nv. 1–5) y `175..475` (`+25/nv.`, nv. 6–18) en `5 s` + `40 %` Heridas graves (`5 s`). Solo campeones | `evaluable` |
| `SummonerBarrier` | `barrier` | Barrera | 180 s | Escudo normal lineal `100..460` (nv. 1–18) durante `2,5 s`; escala con HSP y Revitalizar | `evaluable` |
| `SummonerHeal` | `heal` | Curar | 240 s | Curación lineal `80..318` (nv. 1–18; mitad con `--input heal_debuffed=1`), escalada con HSP, Revitalizar y Heridas graves + `+30 %` VM durante `1 s` | `evaluable` |
| `SummonerExhaust` | `exhaust` | Extenuación | 240 s | `-35 %` daño físico y mágico infligido por el objetivo (nunca reduce daño verdadero) y `-40 %` ralentización durante `3 s` | `evaluable` |
| `SummonerSmite` | `smite` | Aplastar | 15 s | Daño verdadero a monstruo/súbdito: `600` (`smite_tier=0`), `1000` (`smite_tier=1`), `1400` (`smite_tier=2`); contra campeón: `40` de daño verdadero + `-20 %` ralentización (`2 s`). No aplica a estructuras | `evaluable` |
| `SummonerHaste` | `ghost` | Fantasmal | 240 s | `+24 %..48 %` velocidad de movimiento porcentual lineal (nv. 1–18) durante `10 s` y estado fantasmal | `evaluable` |
| `SummonerBoost` | `cleanse` | Limpiar | 240 s | Elimina CC (excepto supresión y derribos aéreos) y efectos negativos de hechizos de invocador + `+75 %` tenacidad durante `3 s` | `evaluable` |
| `SummonerTeleport` | `teleport` | Teleportar | 300 s | Canalización `3 s`; evoluciona al minuto `10` a *Teleportar desatado* (CD base `330..150 s` por nivel, `+50 %` VM durante `4 s`) | `evaluable` |
| `SummonerFlash` | `flash` | Destello | 300 s | Teletransporte posicional de `400` unidades (utilidad pura; CD efectivo y legalidad modelados) | `excluded` |

## 2. Reglas de cálculo (`Calculado`)

- **Legalidad:** un campeón puede equipar como máximo **2** hechizos de invocador distintos (`--summoner <hechizo>` repetible o `summoners: [...]`). Duplicados o más de 2 lanzan error (salvo `--allow-illegal-build`).
- **Aceleración de hechizos de invocador (S3):**
  $$CD_{\text{efectivo}} = CD_{\text{base}} \times \frac{100}{100 + \text{Aceleración de hechizos}}$$
  combina `data:rune:8347` (`+18`), `data:item:3158` (`+10`) y `data:item:3171` (`+20`).
- **En `stats`:** `--summoner` registra los CD efectivos en notas y activa los buffs temporales de hoja mediante `--input`: `ghost_active=1` (`+24..48 %` VM), `heal_ms_active=1` (`+30 %` VM), `teleport_haste=1` (`+50 %` VM) y `cleanse_active=1` (`+75 %` tenacidad, grupo de apilamiento no declarado en [`tenacity.md`](tenacity.md)).
- **En `rotation`:** los pasos `summoner:<alias|id|nombre>` (p. ej. `summoner:ignite`, `summoner:smite`, `summoner:barrier`, `summoner:heal`, `summoner:ghost`) se lanzan de forma instantánea (sin retrasar el temporizador de ataques básicos), respetan enfriamientos en `--timeline`, no aplican robo de vida ni omnivampirismo y `summoner:barrier` activa además Golpe de escudo (`data:rune:8401`). Con `--timeline`, `summoner:ignite` reparte su daño verdadero de forma continua durante `5 s` (completándose en la cola de quemaduras) y `summoner:ghost`/`summoner:heal` inyectan su bonificación porcentual de VM en `_set_moment` (beneficiando también pasivas que escalan con VM como Hecarim). El modificador `--input exhausted=1` reduce el daño físico y mágico del atacante en `-35 %` sin tocar el daño verdadero.
- **En `survive` y `optimize --objective time_to_die`:** `--summoner barrier` activa el escudo normal (`2,5 s` en `--timeline`), `--summoner heal` cura de forma proactiva (si el defensor empieza herido) o reactiva tras el primer impacto no letal, `--summoner exhaust` reduce en `-35 %` el daño físico y mágico entrante durante `3 s` en `--timeline` (o en toda la secuencia sin `--timeline`) y `--summoner cleanse` registra la purga de CC/debuffs y `+75 %` de tenacidad.

## 3. Limitaciones

- **Sin simulación espacial ni de mapa:** el desplazamiento de Destello (`400` unidades), la canalización de Teleportar (`3 s`) y la distancia de alianza de Curar (`900` unidades) no tienen representación geométrica.
- **Limpiar en `survive`:** registra la eliminación de CC y efectos negativos de hechizos de invocador y el `+75 %` de tenacidad, pero no retira retroactivamente una quemadura de Prender ya preconvertida en impactos manuales; si se desea simular un escenario sin Prender o sin Extenuación, omite el debuff en las entradas.
- **Tenacidad de Limpiar:** su grupo de apilamiento frente a objetos sigue el tratamiento conservador de [`tenacity.md`](tenacity.md) (marcado `Pendiente de verificación` al combinarse en hoja).
