# Zaahen — Habilidades

- **Parche:** 16.20.1
- **Fuente:** [`data/current/champions/Zaahen.json`](../../../data/current/champions/Zaahen.json) (Data Dragon, `es_ES`)
- **Fecha de consulta:** 2026-10-18
- **Limitación:** los textos oficiales contienen marcadores con nombre (`initialdamage`, `healpercent`, `damageendcalc`, entre otros) y `effectBurn` viene con valores `0`. No se sustituyen: un cero no es el valor real y presentarlo como dato sería inventarlo.

## Pasiva (`Oficial`)

**Florescencia de la guerra.** Los ataques y habilidades de Zaahen contra campeones enemigos le otorgan acumulaciones de Determinación, lo que le otorga daño de ataque adicional por acumulación. Con el máximo de Determinación, Zaahen obtiene daño de ataque adicional y puede revivir.

## Resumen (`Oficial`)

| Habilidad | Nombre | Rango máximo | Coste | Enfriamiento | Alcance reportado |
|---|---|---|---|---|---|
| Q | La guja de los Oscuros | `5` | `25` | `10/9/8/7/6` | `25000` |
| W | Hendidura del retorno | `5` | `50` | `14/13.5/13/12.5/12` | `850` |
| E | Impulso áureo | `5` | `40` | `10/9.5/9/8.5/8` | `25000` |
| R | Redención funesta | `3` | `100` | `110/95/80` | `600` |

El alcance de Q y E aparece como `25000` en Data Dragon. Se copia tal cual: no se interpreta como alcance real ni como indicador de habilidad global.

## Q — La guja de los Oscuros (`Oficial`)

Zaahen golpea dos veces con su próximo ataque, lo que inflige daño adicional y lo cura. Zaahen puede reactivar esta habilidad para que su siguiente ataque inflija daño adicional y lance por los aires al objetivo.

- **Coste:** `25`
- **Enfriamiento:** `10/9/8/7/6`
- **Valores de daño y curación:** `Pendiente de verificación`.

## W — Hendidura del retorno (`Oficial`)

Zaahen golpea con su arma en una dirección, lo que inflige daño a los enemigos golpeados y los atrae hacia él.

- **Coste:** `50`
- **Enfriamiento:** `14/13.5/13/12.5/12`
- **Alcance reportado:** `850`
- **Valores de daño:** `Pendiente de verificación`.

## E — Impulso áureo (`Oficial`)

Zaahen se desliza hacia una ubicación y da un tajo a su alrededor.

- **Coste:** `40`
- **Enfriamiento:** `10/9.5/9/8.5/8`
- **Valores de daño:** `Pendiente de verificación`.

## R — Redención funesta (`Oficial`)

Zaahen se alza y asesta un golpe descendente, con lo que inflige daño a los enemigos y se cura parte del daño infligido.

- **Coste:** `100`
- **Enfriamiento:** `110/95/80`
- **Alcance reportado:** `600`
- **Efecto pasivo descrito:** penetración de armadura porcentual. El valor concreto no está publicado.
- **Valores de daño, curación y reducción de daño:** `Pendiente de verificación`.

## Por qué faltan números

El documento oficial trae la estructura correcta: nombres, costes, enfriamientos, rangos y texto descriptivo. Lo que no trae es la tabla de efectos. Sustituir `{{ initialdamage }}` por `0` o por un valor deducido sería una invención, no una conversión.

Cuando exista una fuente oficial con los valores, se actualizará este archivo y se anotará el parche. Mientras tanto, el hueco queda declarado.
