# Zaahen — Build

- **Parche:** 16.20.1
- **Objetivo por defecto:** rendimiento competitivo general.
- **Estado:** no hay build validada. Esta página separa lo que se puede demostrar de lo que solo es criterio.

## Cálculo determinista (`Calculado`)

Todavía no existe calculadora de daño ni de eficiencia de objetos (fase 4). Aquí no se afirma ninguna cifra de daño, oro por estadística ni umbral de penetración.

## Criterio estratégico (`Recomendación`)

Punto de partida razonado a partir del texto oficial del kit, **no demostrado** con datos de rendimiento:

- **Daño de ataque y penetración:** el kit inflige daño físico y la R aporta penetración de armadura porcentual. Sin ratios publicados, la prioridad exacta no se puede calcular; la dirección general es daño de ataque con penetración.
- **Durabilidad:** la pasiva y la Q curan, y la R reduce el daño recibido durante el lanzamiento. La vida y la armadura son opciones coherentes con un campeón de cuerpo a cuerpo.
- **Aceleración de habilidades:** Q, W y E son las herramientas de intercambio y control; más aceleración aumenta su disponibilidad, a costa de daño por golpe.
- **Maná:** el recurso es Maná. No hay datos para decidir si hace falta maná adicional en la build.

Estas son hipótesis de trabajo, no conclusiones. Cualquier build concreta exige datos de rendimiento por parche, rango y región.

## Datos que faltan (`Pendiente de verificación`)

- Ratios y daño base de Q, W, E y R.
- Si el crecimiento de daño de ataque `0` es un hueco de datos o un valor real. Un export del bin del cliente (CommunityDragon, **no oficial**) y la wiki (tercero) dan otro valor; la discrepancia sigue abierta.
- Porcentaje de AD que aporta cada acumulación de la pasiva. El bin del cliente y la wiki difieren, y el historial de parches de la propia wiki contradice su propio resumen.
- Tipo y valores de la penetración de armadura de la R (la R la describe como porcentual, sin cifra publicada).
- Eficiencia de objetos en el parche 16.20.1.
- Rendimiento por rango y región.

Mientras estos datos no existan, no se publica ninguna build cuantificada: un cálculo con entradas no verificadas produciría cifras que parecen dato y no lo son. El estado de la investigación, con evidencia y líneas abiertas, está en [`../../../research/zaahen-research-handoff.md`](../../../research/zaahen-research-handoff.md).

## Política de fuentes

No se consultaron estadísticas comunitarias: la autorización vigente permite usarlas solo si el acceso es viable y respeta sus condiciones. Si se incorporan, deberán citar parche, rango, región, fecha y tamaño de muestra.

Las fuentes no oficiales ya consultadas (CommunityDragon y la wiki) se registran en [`sources.md`](sources.md), con su naturaleza, su licencia y sus límites.
