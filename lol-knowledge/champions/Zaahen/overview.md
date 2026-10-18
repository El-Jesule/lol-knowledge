# Zaahen — El Impertérrito

- **Parche:** 16.20.1
- **Fuente:** [`data/current/champions/Zaahen.json`](../../../data/current/champions/Zaahen.json) (Data Dragon, `es_ES`)
- **Fecha de consulta:** 2026-10-18
- **Limitación principal:** Data Dragon no publica los valores numéricos de las habilidades de este campeón. Ver [`abilities.md`](abilities.md) y [`sources.md`](sources.md).

## Identidad (`Oficial`)

| Campo | Valor |
|---|---|
| Id | `Zaahen` |
| Nombre | Zaahen |
| Título | El Impertérrito |
| Rol | Fighter |
| Recurso | Maná |

## Estadísticas base (`Oficial`)

| Estadística | Base | Crecimiento por nivel |
|---|---|---|
| Vida | `640` | `114` |
| Maná | `350` | `55` |
| Daño de ataque | `63` | `0` |
| Velocidad de ataque | `0.625` | `2.5` |
| Armadura | `36` | `5` |
| Resistencia mágica | `32` | `2.05` |
| Velocidad de movimiento | `345` | — |
| Alcance de ataque | `175` | — |
| Regeneración de vida | `7.5` | `0.8` |
| Regeneración de maná | `8.15` | `0.75` |
| Probabilidad de crítico | `0` | `0` |

La velocidad de ataque se expresa como proporción base y crecimiento porcentual por nivel, según la convención de Data Dragon.

## Lectura del kit (`Recomendación`)

Interpretación estratégica del texto oficial de las habilidades, no demostrada con estadísticas:

- **Duelo prolongado:** la pasiva acumula Determinación al golpear campeones y la Q cura; el kit favorece peleas largas más que ráfagas.
- **Control y reposicionamiento:** la W atrae enemigos y la E aporta desplazamiento, lo que da herramientas para iniciar o corregir posición.
- **Penetración y supervivencia en la definitiva:** la R aporta penetración de armadura y reducción de daño durante el lanzamiento, además de curación sobre el daño infligido.
- **Dependencia de maná:** el recurso base es Maná y las habilidades tienen costes medios; sin datos de eficiencia no se puede cuantificar el impacto.

## Advertencias de datos (`Pendiente de verificación`)

- Data Dragon reporta `0` como crecimiento de daño de ataque por nivel. No se corrige ni se interpreta como decisión de diseño: puede ser un hueco de datos del parche.
- Existe una discrepancia sobre ese crecimiento: un export del bin del cliente (CommunityDragon, fuente **no oficial**) indica otro valor, y la wiki (tercero) coincide con ese otro valor. Ninguno de los dos es fuente oficial y la discrepancia sigue abierta. Evidencia y detalle en [`../../../research/zaahen-research-handoff.md`](../../../research/zaahen-research-handoff.md).
- No hay valores de daño, escalados ni porcentajes de las habilidades en la fuente. Cualquier cifra de daño exigiría otra fuente oficial o medición propia.
- No hay consejos oficiales de aliados ni de enemigos: Data Dragon los publica vacíos para este campeón.
