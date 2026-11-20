# Índice de la base de conocimiento

- **Parche:** 16.23.1
- **Última actualización:** 2026-11-20

## Por intención

| Quiero… | Ir a |
|---|---|
| Entender a Zaahen | [Resumen de Zaahen](champions/Zaahen/overview.md) |
| Ver sus habilidades | [Habilidades de Zaahen](champions/Zaahen/abilities.md) |
| Ver la build | [Build de Zaahen](champions/Zaahen/build.md) |
| Calcular el daño de sus habilidades | [Kit de Zaahen](champions/Zaahen/kit.json) y `python -m lol_knowledge ability` ([uso](../README.md)) |
| Comprobar las fuentes | [Fuentes de Zaahen](champions/Zaahen/sources.md) |
| Leer el dato crudo | [Zaahen.json](../data/current/champions/Zaahen.json) |
| Entender a Ahri y sus habilidades | [Resumen de Ahri](champions/Ahri/overview.md) y [habilidades](champions/Ahri/abilities.md) |
| Calcular el daño de Ahri | [Kit de Ahri](champions/Ahri/kit.json); fuentes en [sources.md](champions/Ahri/sources.md) |
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
| Calcular escudos, curación de efectos, Heridas graves y poder de curaciones y escudos | [Supervivencia](mechanics/survival.md) |
| Simular cuánto aguanta un campeón (daño recibido, tiempo hasta morir, Sterak, Revestimiento de huesos) | `python -m lol_knowledge survive` y [Supervivencia](mechanics/survival.md) |
| Calcular la tenacidad y cómo se combinan sus fuentes | [Tenacidad](mechanics/tenacity.md) |
| Calcular la regeneración de vida y maná | [Regeneración](mechanics/regeneration.md) |
| Calcular costes de habilidades, reservas (maná, energía, vida), Segador de esencia y Claridad mental | [Recursos y costes](mechanics/resources.md) |
| Calcular la velocidad de movimiento y sus límites suaves | [Velocidad de movimiento](mechanics/move-speed.md) |
| Aplicar aumentos y reducciones de daño | [Modificadores de daño](mechanics/damage-modifiers.md) |
| Encadenar ataques, daño al impactar y vida del objetivo | [Ataques básicos y daño al impactar](mechanics/basic-attacks-and-on-hit.md) |
| Calcular el golpe de Hoja encantada (Brillo, Trinidad, Liche…) | [Hoja encantada](mechanics/spellblade.md) |
| Calcular efectos cada N ataques y de Vigor (Kraken, Guinsoo, Cañón…) | [Contadores de ataques y Vigor](mechanics/attack-counters.md) |
| Calcular desde 0 las acumulaciones temporales de combate (Guinsoo, El final, Liandry, Disfraz encantado) | [Acumulaciones en combate](mechanics/combat-stacks.md) |
| Calcular efectos según la vida del objetivo (Kraken, Llamasombría, Recaudadora) | [Vida del objetivo](mechanics/target-health.md) |
| Calcular quemaduras y aumentos por tiempo en combate (Liandry, Antorcha…) | [Quemaduras](mechanics/burns.md) |
| Dar tiempos a una rotación (ataques, enfriamientos, esperas) | [Línea de tiempo](mechanics/timeline.md) |
| Repartir las quemaduras en el tiempo y aplicar efectos con duración (Tonada sanguina, Malignidad, Ciclovoltaica, Fuego negro) | [Línea de tiempo](mechanics/timeline.md), reglas 7 y 8 |
| Ráfaga de Yun Tal, caducidad de las acumulaciones (Kraken, Rompecascos) y ventana de 10 s de Hoja encantada | [Línea de tiempo](mechanics/timeline.md), reglas 9 a 11 |
| Ver las estadísticas base y por nivel extraídas del cliente | [champion-records.json](derived/champion-records.json) |
| Ver los valores, cálculos y textos de los efectos de los objetos, del cliente | [item-effects.json](derived/item-effects.json) |
| Ver el catálogo curado de objetos | [catalog.json](objects/catalog.json) |
| Ver las runas, sus valores y si una página es legal; aplicar los fragmentos | [Runas y fragmentos](mechanics/runes.md) y [runes.json](derived/runes.json) |
| Saber si unos objetos pueden ir juntos (únicos, botas, grupos exclusivos, huecos) | [Legalidad de la build](mechanics/build-legality.md) y [item-groups.json](derived/item-groups.json) |
| Ver la evidencia de las mecánicas de objetos | [Informe de mecánicas](../research/reports/object-mechanics-2026-10-20.md) |
| Continuar la investigación de datos de Zaahen | [Documento de continuidad](../research/zaahen-research-handoff.md) |

## Cobertura actual

Dos campeones con kit calculable (Zaahen, con análisis completo, y Ahri), datos oficiales de los 173 campeones en `data/current/` y sus estadísticas base y por nivel del cliente en [champion-records.json](derived/champion-records.json). La cobertura de kits crece de uno en uno: cada campeón nuevo reutiliza esta estructura.

El modelo de objetos tiene las estadísticas de los **218 objetos comprables de la Grieta**; los efectos están curados en **43 objetos** (66 efectos), elegidos por mecánica, y el resto queda `pending`. Las cifras que Data Dragon no publica se registran con fuente citada: la wiki (`secondary`) o los datos del cliente 16.23 (`derived`, `corroborated` si coinciden). Los límites están en [Modelo de objetos](objects/README.md).

## Aviso de fuentes

Los valores marcados `Derivado` proceden de datos del cliente, **no** de una API oficial de Riot: los de Zaahen, de los archivos del cliente 16.20 publicados por CommunityDragon ([Fuentes de Zaahen](champions/Zaahen/sources.md)); los de Ahri ([Fuentes de Ahri](champions/Ahri/sources.md)), los registros de campeones y los efectos de objetos de `derived/`, del cliente instalado 16.23. Se incluyen con atribución y aviso de no afiliación. El aviso completo está en [`../README.md`](../README.md).
