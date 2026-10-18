# Zaahen — Build

- **Parche:** 16.20.1
- **Objetivo por defecto:** rendimiento competitivo general.
- **Estado:** no hay build validada. Esta página separa lo que se puede demostrar de lo que solo es criterio.

## Cálculo determinista (`Calculado`)

Todavía no existe calculadora de daño ni de eficiencia de objetos (fase 4). Hay bases y ratios derivados publicados en [`abilities.md`](abilities.md), pero aquí no se afirma daño final, oro por estadística ni umbral de penetración.

## Insumos disponibles (`Derivado`)

- Q: 15/30/45/60/75 (+20/25/30/35/40 % de DA adicional); recast 30/60/90/120/150 con el mismo ratio.
- W: 40/60/80/100/120 (+50 % de DA adicional); segundo golpe 30/50/70/90/110 (+30 %).
- E: 40/60/80/100/120 (+50 %); borde 60/90/120/150/180 (+75 %) más 4–6 % de vida máxima como daño mágico.
- R: 250/400/550 (+200 % de DA adicional); 10/20/30 % de penetración de armadura.
- Pasiva: 1,5–2,8 % de DA por acumulación, duplicado al máximo.

Son datos del cliente, no de una API oficial de Riot. La calculadora que los combine sigue pendiente.

## Criterio estratégico (`Recomendación`)

Punto de partida razonado a partir del texto oficial del kit, **no demostrado** con datos de rendimiento:

- **Daño de ataque y penetración:** el kit inflige daño físico y la R aporta penetración de armadura porcentual. Con ratios derivados disponibles, la prioridad exacta sigue sin calcularse; la dirección general es daño de ataque con penetración.
- **Durabilidad:** la pasiva y la Q curan, y la R reduce el daño recibido durante el lanzamiento. La vida y la armadura son opciones coherentes con un campeón de cuerpo a cuerpo.
- **Aceleración de habilidades:** Q, W y E son las herramientas de intercambio y control; más aceleración aumenta su disponibilidad, a costa de daño por golpe.
- **Maná:** el recurso es Maná. No hay datos para decidir si hace falta maná adicional en la build.

Estas son hipótesis de trabajo, no conclusiones. Cualquier build concreta exige datos de rendimiento por parche, rango y región.

## Datos que faltan (`Pendiente de verificación`)

- Si el crecimiento de daño de ataque 0 de Data Dragon es un hueco o un valor real; el cliente indica 4,0.
- El máximo exacto de AD por acumulación de la pasiva (2,8 % frente a 2,95 %).
- Eficiencia de objetos en el parche 16.20.1.
- Rendimiento por rango y región.
- Medición en partida de los valores derivados.

Mientras no exista calculadora y no se resuelvan esos puntos, no se publica una build cuantificada: un cálculo con entradas no verificadas produciría cifras que parecen dato y no lo son. El estado de la investigación está en [`../../../research/zaahen-research-handoff.md`](../../../research/zaahen-research-handoff.md).

## Política de fuentes

Los valores marcados `Derivado` proceden de datos del cliente publicados por CommunityDragon y se incluyen con atribución y aviso de no afiliación (ver [`sources.md`](sources.md)). No se presentan como datos oficiales de Riot.

No se consultaron estadísticas comunitarias: la autorización vigente permite usarlas solo si el acceso es viable y respeta sus condiciones. Si se incorporan, deberán citar parche, rango, región, fecha y tamaño de muestra.
