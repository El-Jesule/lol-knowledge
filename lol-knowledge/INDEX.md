# Índice de la base de conocimiento

- **Parche:** 16.22.1
- **Última actualización:** 2026-11-15

## Por intención

| Quiero… | Ir a |
|---|---|
| Entender a Zaahen | [Resumen de Zaahen](champions/Zaahen/overview.md) |
| Ver sus habilidades | [Habilidades de Zaahen](champions/Zaahen/abilities.md) |
| Ver la build | [Build de Zaahen](champions/Zaahen/build.md) |
| Calcular el daño de sus habilidades | [Kit de Zaahen](champions/Zaahen/kit.json) y `python -m lol_knowledge ability` ([uso](../README.md)) |
| Comprobar las fuentes | [Fuentes de Zaahen](champions/Zaahen/sources.md) |
| Leer el dato crudo | [Zaahen.json](../data/current/champions/Zaahen.json) |
| Comprobar el snapshot | [manifest.json](../data/current/manifest.json) |
| Entender el modelo mecánico de objetos | [Modelo de objetos](objects/README.md) |
| Saber cómo se mitiga el daño (armadura, RM, reducción, penetración) | [Mitigación de daño](mechanics/damage-mitigation.md) |
| Calcular el daño tras resistencias | `python -m lol_knowledge damage` ([uso](../README.md)) |
| Ver las estadísticas de un campeón por nivel y objetos | `python -m lol_knowledge stats` ([uso](../README.md)) |
| Entender el crecimiento por nivel | [Crecimiento de estadísticas](mechanics/stat-growth.md) |
| Entender enfriamientos y aceleración | [Aceleración de habilidades](mechanics/ability-haste.md) |
| Entender la vida efectiva | [Vida efectiva](mechanics/effective-health.md) |
| Saber qué datos oficiales son defectuosos | [Defectos conocidos de los datos](mechanics/known-data-issues.md) |
| Calcular un impacto crítico o la probabilidad de crítico | [Impacto crítico](mechanics/critical-strike.md) |
| Calcular la velocidad de ataque (base, ratio, crecimiento y tope) | [Velocidad de ataque](mechanics/attack-speed.md) |
| Calcular la curación por robo de vida y omnivampirismo | [Robo de vida y omnivampirismo](mechanics/life-steal-and-omnivamp.md) |
| Calcular la tenacidad y cómo se combinan sus fuentes | [Tenacidad](mechanics/tenacity.md) |
| Calcular la regeneración de vida y maná | [Regeneración](mechanics/regeneration.md) |
| Calcular la velocidad de movimiento y sus límites suaves | [Velocidad de movimiento](mechanics/move-speed.md) |
| Aplicar aumentos y reducciones de daño | [Modificadores de daño](mechanics/damage-modifiers.md) |
| Encadenar ataques, daño al impactar y vida del objetivo | [Ataques básicos y daño al impactar](mechanics/basic-attacks-and-on-hit.md) |
| Calcular el golpe de Hoja encantada (Brillo, Trinidad, Liche…) | [Hoja encantada](mechanics/spellblade.md) |
| Ver las estadísticas base y por nivel extraídas del cliente | [champion-records.json](derived/champion-records.json) |
| Ver los valores, cálculos y textos de los efectos de los objetos, del cliente | [item-effects.json](derived/item-effects.json) |
| Ver el catálogo curado de objetos | [catalog.json](objects/catalog.json) |
| Ver la evidencia de las mecánicas de objetos | [Informe de mecánicas](../research/reports/object-mechanics-2026-10-20.md) |
| Continuar la investigación de datos de Zaahen | [Documento de continuidad](../research/zaahen-research-handoff.md) |

## Cobertura actual

Un campeón con análisis completo y datos oficiales de los 173 campeones en `data/current/`. La cobertura crece de uno en uno: cada campeón nuevo reutiliza esta estructura.

El modelo de objetos tiene las estadísticas de los **218 objetos comprables de la Grieta**; los efectos están curados en **16 objetos** elegidos por diversidad mecánica, y el resto queda `pending`. Las cifras que Data Dragon no publica se registran con fuente citada y confianza secundaria. Los límites están en [Modelo de objetos](objects/README.md).

## Aviso de fuentes

Los valores marcados `Derivado` proceden de datos del cliente publicados por CommunityDragon, **no** de una API oficial de Riot. Se incluyen con atribución y aviso de no afiliación; el detalle está en [Fuentes de Zaahen](champions/Zaahen/sources.md). El aviso completo está en [`../README.md`](../README.md).
