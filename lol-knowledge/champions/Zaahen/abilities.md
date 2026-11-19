# Zaahen — Habilidades

- **Parche:** 16.23.1 (datos oficiales; antes 16.22.1 y 16.20.1)
- **Fuente oficial:** [`data/current/champions/Zaahen.json`](../../../data/current/champions/Zaahen.json) (Data Dragon, `es_ES`)
- **Valores derivados:** CommunityDragon, build `16.20.8248524` (fuente **no oficial**), comprobados contra los bins del cliente 16.22 y 16.23 sin cambios en los valores publicados aquí ([diferencias 16.20 → 16.22](../../../research/reports/zaahen-bin-diff-16.22.md), [revisión 16.23](../../../research/reports/client-16.23.md)). Detalle y trazabilidad en [`sources.md`](sources.md).
- **Fecha de consulta:** 2026-10-18; snapshot 16.23.1 revisado el 2026-11-19
- **Limitación:** Data Dragon no publica los valores numéricos de los efectos de este campeón. Las cifras en code spans son oficiales; las cifras en texto plano son `Derivado` y no sustituyen a una fuente oficial de Riot.

## Pasiva — Florescencia de la guerra (`Oficial` + `Derivado`)

**Texto oficial.** Los ataques y habilidades de Zaahen contra campeones enemigos le otorgan acumulaciones de Determinación, lo que le otorga daño de ataque adicional por acumulación. Con el máximo de Determinación, Zaahen obtiene daño de ataque adicional y puede revivir.

**Valores derivados.** Máximo de 12 acumulaciones; cada acumulación otorga entre 1,5 % y 2,8 % de daño de ataque adicional según nivel, y el bono se duplica con la barra completa. El revive dura 4 s, restaura 30/45/60/75 % de la vida máxima según nivel (1/6/11/16) y tiene un enfriamiento de 300/240/180/120 s.

La wiki indica 2,95 % como máximo por acumulación; el bin y el historial de parches de la propia wiki apuntan a 2,8 %. La discrepancia sigue abierta y no se elige un valor por conveniencia.

## Resumen (`Oficial`)

| Habilidad | Nombre | Rango máximo | Coste | Enfriamiento | Alcance reportado |
|---|---|---|---|---|---|
| Q | La guja de los Oscuros | `5` | `25` | `8/7.5/7/6.5/6` | `25000` |
| W | Hendidura del retorno | `5` | `50` | `14/13.5/13/12.5/12` | `850` |
| E | Impulso áureo | `5` | `40` | `10/9.5/9/8.5/8` | `25000` |
| R | Redención funesta | `3` | `100` | `110/95/80` | `600` |

El alcance de Q y E aparece como `25000` en Data Dragon. Se copia tal cual: no se interpreta como alcance real ni como indicador de habilidad global.

## Q — La guja de los Oscuros (`Oficial` + `Derivado`)

**Texto oficial.** Zaahen golpea dos veces con su próximo ataque, lo que inflige daño adicional y lo cura. Zaahen puede reactivar esta habilidad para que su siguiente ataque inflija daño adicional y lance por los aires al objetivo.

- **Coste:** `25`
- **Enfriamiento:** `8/7.5/7/6.5/6` (en 16.20.1 era 10/9/8/7/6)
- **Daño adicional del primer golpe (`Derivado`):** 15 / 30 / 45 / 60 / 75 (+20 / 25 / 30 / 35 / 40 % de DA adicional).
- **Daño adicional del recast (`Derivado`):** 30 / 60 / 90 / 120 / 150 (+20 / 25 / 30 / 35 / 40 % de DA adicional).
- **Curación (`Derivado`):** 5 / 6 / 7 / 8 / 9 % de la vida máxima; se reduce al 50 % contra súbditos y monstruos.
- **Control (`Derivado`):** lanza por los aires 0,75 s; ventana de recast de 4 s; +25 de alcance.
- **Contra monstruos (`Derivado`):** 100 % de daño adicional, es decir, 200 % del daño base según el texto oficial del cliente. No se ha medido en partida.

Estas cifras cubren el daño adicional de la habilidad; el daño propio del ataque básico no está incluido.

## W — Hendidura del retorno (`Oficial` + `Derivado`)

**Texto oficial.** Zaahen golpea con su arma en una dirección, lo que inflige daño a los enemigos golpeados y los atrae hacia él.

- **Coste:** `50`
- **Enfriamiento:** `14/13.5/13/12.5/12`
- **Alcance reportado:** `850`
- **Daño inicial (`Derivado`):** 40 / 60 / 80 / 100 / 120 (+50 % de DA adicional).
- **Daño secundario (`Derivado`):** 30 / 50 / 70 / 90 / 110 (+30 % de DA adicional).
- **Arrastre (`Derivado`):** 225 unidades.

## E — Impulso áureo (`Oficial` + `Derivado`)

**Texto oficial.** Zaahen se desliza hacia una ubicación y da un tajo a su alrededor.

- **Coste:** `40`
- **Enfriamiento:** `10/9.5/9/8.5/8`
- **Daño base (`Derivado`):** 40 / 60 / 80 / 100 / 120 (+50 % de DA adicional).
- **Daño del borde (`Derivado`):** 60 / 90 / 120 / 150 / 180 (+75 % de DA adicional).
- **Daño mágico del borde (`Derivado`):** 4 / 4,5 / 5 / 5,5 / 6 % de la vida máxima; máximo de 400 contra monstruos.
- **Contra monstruos (`Derivado`):** +50 de daño físico.

## R — Redención funesta (`Oficial` + `Derivado`)

**Texto oficial.** Zaahen se alza y asesta un golpe descendente, con lo que inflige daño a los enemigos y se cura parte del daño infligido.

- **Coste:** `100`
- **Enfriamiento:** `110/95/80`
- **Alcance reportado:** `600`
- **Daño (`Derivado`):** 250 / 400 / 550 (+200 % de DA adicional).
- **Penetración de armadura (`Derivado`):** 10 / 20 / 30 %, porcentual, sobre la armadura total. Es la parte **pasiva** de la habilidad: se obtiene al aprender la R, se mantiene con la R en enfriamiento y afecta a todo el daño físico de Zaahen. Se aplica en el tercer paso de la [mitigación de daño](../../mechanics/damage-mitigation.md) y se apila multiplicativamente con otras penetraciones porcentuales.
- **Reducción de daño (`Derivado`):** 50 % durante el lanzamiento.
- **Curación (`Derivado`):** 33 % del daño premítigación infligido a campeones.

## Modelo calculable (`Derivado`)

Los daños de esta página están también en forma evaluable en [`kit.json`](kit.json) (esquema `lol-champion-kit/1`), generado desde los árboles de cálculo del bin y el marcado de los tooltips del cliente. Cada habilidad tiene *casos* alternativos con sus partes de daño:

- **Q:** primer golpe y reactivación (daño adicional al ataque, sin el ataque básico).
- **W:** golpe y atracción (el mismo enemigo recibe las dos partes).
- **E:** tajo, o borde del tajo, que lo sustituye y añade daño mágico según la vida máxima del objetivo.
- **R:** golpe descendente, y la penetración de armadura como estadística pasiva.
- **Pasiva:** no modelada todavía (la curva de acumulaciones no está medida).

Lo que el kit no modela está listado en cada habilidad (`not_modelled`): curaciones, reducción de daño, y bonificaciones y topes contra monstruos.

## Qué queda pendiente (`Pendiente de verificación`)

- Crecimiento de daño de ataque: Data Dragon publica 0; el cliente indica 4,0. La discrepancia no se resuelve aquí.
- Máximo de AD por acumulación de la pasiva: 2,8 % en el bin frente a 2,95 % en el resumen de la wiki.
- Multiplicador de Q contra monstruos: la lectura de «daño adicional» es coherente con el texto del cliente, pero no se ha medido en partida.
- Semántica de `mStat`/`mStatFormula`: la equivalencia con «DA adicional» es una interpretación, no un enum publicado por Riot.

Los valores derivados no se presentan como datos oficiales de Riot. Su trazabilidad completa está en [`sources.md`](sources.md).
