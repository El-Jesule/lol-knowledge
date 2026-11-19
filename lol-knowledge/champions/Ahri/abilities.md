# Ahri — Habilidades

- **Parche:** 16.23.1 (datos oficiales; sin cambios respecto a 16.22.1)
- **Fuente oficial:** [`data/current/champions/Ahri.json`](../../../data/current/champions/Ahri.json) (Data Dragon, `es_ES`)
- **Valores derivados:** bin del cliente 16.22 (`Ahri.wad.client`, `data/characters/ahri/ahri.bin`), leído directamente y sin cambios en el bin 16.23 ([revisión 16.23](../../../research/reports/client-16.23.md)); fuente **no oficial**. Detalle en [`sources.md`](sources.md).
- **Fecha de consulta:** 2026-11-16
- **Limitación:** las cifras en code spans son oficiales; las cifras en texto plano son `Derivado` y no sustituyen a una fuente oficial de Riot.

## Resumen (`Oficial`)

| Habilidad | Nombre | Rango máximo | Coste | Enfriamiento | Alcance reportado |
|---|---|---|---|---|---|
| Q | Orbe del engaño | `5` | `55/65/75/85/95` | `7` | `970` |
| W | Fuego zorruno | `5` | `30` | `9/8/7/6/5` | `700` |
| E | Hechizar | `5` | `60` | `12` | `975` |
| R | Impulso espiritual | `3` | `100` | `140/120/100` | `450` |

Los enfriamientos del bin (`Cooldown.values`) coinciden con los de Data Dragon.

## Pasiva — Robo de esencias (`Oficial` + `Derivado`)

**Texto oficial.** Ahri se cura tras matar a 9 súbditos o monstruos. Ahri se cura más cantidad tras eliminar a un campeón enemigo.

**Valores derivados.** 9 fragmentos (`MaxStacks`); ventana de 3 s tras dañar a un campeón para que su derribo cuente (`TakedownWindow`). Las curaciones (`MinionHeal`, `ChampionHeal`) crecen con el nivel (interpolación por nivel) más un 20 % y un 30 % del poder de habilidad. Durante Impulso espiritual, un derribo amplía su ventana 10 s y da un lanzamiento más. No se modela: no es daño.

## Q — Orbe del engaño (`Oficial` + `Derivado`)

**Texto oficial.** Ahri lanza y recupera su orbe, lo que inflige daño mágico al lanzarlo y daño verdadero al recuperarlo.

- **Daño por pasada (`Derivado`):** 35 / 60 / 85 / 110 / 135 (+50 % del poder de habilidad), **mágico a la ida y verdadero a la vuelta** (`TotalDamage`; el tooltip del cliente lo muestra bajo las dos etiquetas).
- **Casos del kit:** `Q.out` (ida), `Q.back` (vuelta) y `Q.both` (ida y vuelta sobre el mismo objetivo).

## W — Fuego zorruno (`Oficial` + `Derivado`)

**Texto oficial.** Ahri obtiene una breve mejora de velocidad de movimiento y lanza tres fuegos zorrunos que fijan y atacan a los enemigos cercanos.

- **Daño del primer fuego (`Derivado`):** 40 / 60 / 80 / 100 / 120 (+40 % del poder de habilidad), mágico (`SingleFireDamage`).
- **Fuegos siguientes sobre el mismo objetivo (`Derivado`):** 40 % de ese daño (`MultiFireDamage` = `SingleFireDamage` × `RepeatDamageMod` 0,4).
- **Casos del kit:** `W.one` (un fuego) y `W.all` (los tres sobre el mismo objetivo: 100 % + 40 % + 40 %).
- **Sin modelar:** 40 % de velocidad de movimiento que decae en 2 s; daño doble a súbditos por debajo del 20 % de vida.

## E — Hechizar (`Oficial` + `Derivado`)

**Texto oficial.** Ahri lanza un beso que daña y hechiza al enemigo al que alcance primero, con lo que cancela instantáneamente todas sus habilidades de movimiento y hace que avance hacia ella de forma inofensiva.

- **Daño (`Derivado`):** 80 / 120 / 160 / 200 / 240 (+85 % del poder de habilidad), mágico (`TotalDamage`).
- **Hechizo (`Derivado`):** 1,2 / 1,35 / 1,5 / 1,65 / 1,8 s; sin modelar.

## R — Impulso espiritual (`Oficial` + `Derivado`)

**Texto oficial.** Ahri se desliza hacia delante y libera rayos de esencia que infligen daño a los enemigos cercanos. Impulso espiritual puede usarse hasta tres veces antes de entrar en enfriamiento y las eliminaciones de campeones enemigos otorgan lanzamientos adicionales.

- **Daño por rayo (`Derivado`):** 75 / 125 / 175 (+35 % del poder de habilidad), mágico (`RCalculatedDamage`).
- **Rayos (`Derivado`):** 3 por impulso, a enemigos distintos (`RMaxTargetsPerCast` 3); contra un único objetivo, uno por impulso. Que no repitan objetivo se deduce del nombre del dato; no está medido.
- **Reactivaciones (`Derivado`):** hasta 2 más en 15 s (`RRecastWindow`), con 1 s como mínimo entre impulsos (`RDashCooldown`). Casos del kit: `R.dash` y `R.recast`; con `--timeline` se comprueban la ventana, el número de reactivaciones y el intervalo ([`../../mechanics/timeline.md`](../../mechanics/timeline.md)).
- **Sin modelar:** los lanzamientos extra y la ampliación de la ventana por derribos.
