# Índice de la base de conocimiento

- **Parche:** 16.23.1
- **Última actualización:** 2026-11-25

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
| Simular un duelo 1v1 determinista acoplado (ataques, habilidades, CC con tenacidad, purgas, defensivos, hechizos, quemaduras, estasis) | `python -m lol_knowledge duel` y [Simulador de duelo 1v1](mechanics/duel.md) |
| Calcular la tenacidad y cómo se combinan sus fuentes | [Tenacidad](mechanics/tenacity.md) |
| Calcular la regeneración de vida y maná | [Regeneración](mechanics/regeneration.md) |
| Calcular costes de habilidades, reservas (maná, energía, vida), Segador de esencia y Claridad mental | [Recursos y costes](mechanics/resources.md) |
| Aplicar pasivas de campeón en hoja, rotación y supervivencia (`134/173` automatizadas) y generar borradores de kit | [Pasivas de campeón](mechanics/passives.md) |
| Aplicar escudos, curaciones, reducciones de daño, esquivas, invulnerabilidades, purgas/inmunidades a CC y esteroides activos en `Q/W/E/R` (`135/173` campeones, `309` efectos) | [Habilidades defensivas y esteroides activos](mechanics/active-abilities.md) |
| Calcular la velocidad de movimiento y sus límites suaves | [Velocidad de movimiento](mechanics/move-speed.md) |
| Aplicar aumentos y reducciones de daño | [Modificadores de daño](mechanics/damage-modifiers.md) |
| Encadenar ataques, daño al impactar y vida del objetivo | [Ataques básicos y daño al impactar](mechanics/basic-attacks-and-on-hit.md) |
| Calcular el golpe de Hoja encantada (Brillo, Trinidad, Liche…) | [Hoja encantada](mechanics/spellblade.md) |
| Calcular efectos cada N ataques y de Vigor (Kraken, Guinsoo, Cañón…) | [Contadores de ataques y Vigor](mechanics/attack-counters.md) |
| Calcular desde 0 las acumulaciones temporales de combate (Guinsoo, El final, Liandry, Disfraz encantado) | [Acumulaciones en combate](mechanics/combat-stacks.md) |
| Calcular efectos según la vida del objetivo (Kraken, Llamasombría, Recaudadora) | [Vida del objetivo](mechanics/target-health.md) |
| Calcular quemaduras y aumentos por tiempo en combate (Liandry, Antorcha…) | [Quemaduras](mechanics/burns.md) |
| Dar tiempos a una rotación (ataques, enfriamientos, esperas, informes por ventana `--window`) | [Línea de tiempo](mechanics/timeline.md) |
| Repartir las quemaduras en el tiempo y aplicar efectos con duración (Tonada sanguina, Malignidad, Ciclovoltaica, Fuego negro) | [Línea de tiempo](mechanics/timeline.md), reglas 7 y 8 |
| Ráfaga de Yun Tal, caducidad de las acumulaciones (Kraken, Rompecascos, Impacto fantasma Guinsoo→Kraken) y ventana de 10 s de Hoja encantada | [Línea de tiempo](mechanics/timeline.md), reglas 9 a 11 |
| Aplicar elixires de la Grieta (`2138`/`2139`/`2140`) o una mejora de obra maestra de Ornn (`--elixir`, `--ornn-item`, `--ornn-upgrade`) | [Motor v1.0](../odd/tasks/engine-v1.md) y [uso](../README.md) |
| Ver las estadísticas base y por nivel extraídas del cliente | [champion-records.json](derived/champion-records.json) |
| Ver los valores, cálculos y textos de los efectos de los objetos, del cliente | [item-effects.json](derived/item-effects.json) |
| Ver el catálogo curado de objetos | [catalog.json](objects/catalog.json) |
| Ver las runas, sus valores y si una página es legal; aplicar los fragmentos | [Runas y fragmentos](mechanics/runes.md) y [runes.json](derived/runes.json) |
| Calcular hechizos de invocador (Prender, Barrera, Curar, Extenuación, Aplastar, Fantasmal, Limpiar, Destello, Teleportar) | [Hechizos de invocador](mechanics/summoner-spells.md) y [summoner-spells.json](derived/summoner-spells.json) |
| Saber si unos objetos pueden ir juntos (únicos, botas, grupos exclusivos, huecos) | [Legalidad de la build](mechanics/build-legality.md) y [item-groups.json](derived/item-groups.json) |
| Optimizar una build legal por daño, DPS, vida efectiva, supervivencia, curación o duelo 1v1 (con curva de compra `--purchase-curve`, puntos de control de oro `--gold-checkpoints`, rotación automática y mejora de Ornn) | `python -m lol_knowledge optimize`, [Optimizador de builds](../odd/tasks/build-optimizer.md) y [Motor v1.0](../odd/tasks/engine-v1.md) |
| Conectar una IA mediante contrato JSON o servidor MCP local | [Capa de IA y servidor MCP](ai-layer.md) y `python -m lol_knowledge mcp` |
| Ver la evidencia de las mecánicas de objetos | [Informe de mecánicas](../research/reports/object-mechanics-2026-10-20.md) |
| Continuar la investigación de datos de Zaahen | [Documento de continuidad](../research/zaahen-research-handoff.md) |

## Cobertura actual

**173 de 173 campeones con kit calculable** (`lol-knowledge/champions/<Id>/kit.json`, **100 % del plantel**): Zaahen (con análisis completo), Ahri (con fichas) y los 171 campeones restantes completados en cuatro oleadas sobre el cliente `16.23` (ver [`champion-kits-wave-1.md`](../odd/tasks/champion-kits-wave-1.md), [`champion-kits-wave-2.md`](../odd/tasks/champion-kits-wave-2.md), [`champion-kits-wave-3.md`](../odd/tasks/champion-kits-wave-3.md) y [`champion-kits-wave-4.md`](../odd/tasks/champion-kits-wave-4.md)). Datos oficiales de los 173 campeones en `data/current/` y sus estadísticas base y por nivel del cliente en [champion-records.json](derived/champion-records.json).

**134 de 173 pasivas de campeón automatizadas** ([Pasivas de campeón](mechanics/passives.md)): `123` campeones con `passive_effects` declarativos compilados desde el cliente `16.23` (`Derivado`) más `11` reglas globales de hoja/rotación; los `39` campeones restantes corresponden a pasivas puramente de utilidad, oro, visión, experiencia, geometría, estado post-muerte o contadores ya integrados en `Q/W/E/R`.

**135 de 173 campeones con efectos activos defensivos, de curación, purgas/inmunidades y esteroides en `Q/W/E/R`** ([Habilidades defensivas y esteroides activos](mechanics/active-abilities.md)): `309` efectos declarativos en `220` habilidades (`49` escudos normales y mágicos, `46` curaciones instantáneas y *HoT*, `8` curaciones por daño post-mitigación infligido, `5` escudos/curaciones por daño recibido reciente con suelo mínimo cuando existe, `17` reducciones de daño porcentuales y planas con tope, `3` esquivas de ataques básicos, `2` escudos de hechizos, `1` bloqueo de primer impacto, `5` invulnerabilidades/inmortalidades, `8` purgas/inmunidades a CC y `165` esteroides temporales de estadísticas) integrados en `rotation`, `survive` (`--defender-cast`), `duel`, `optimize`, `contract` y `mcp`.

**62 de 62 runas y 9 de 9 fragmentos modelados** ([Runas y fragmentos](mechanics/runes.md)): cobertura completa de runas clave, runas menores de estadística y combate, y runas/fragmentos del defensor (`--target-rune`, `--target-shard`, `target.runes`, `target.shards` y `enemy.runes`/`enemy.shards`) en CLI, contrato JSON, servidor MCP y optimizador.

**9 de 9 hechizos de invocador de la Grieta modelados** ([Hechizos de invocador](mechanics/summoner-spells.md)): Prender, Barrera, Curar, Extenuación, Aplastar (`tier 0/1/2` y PvP), Fantasmal, Limpiar, Destello y Teleportar / Teleportar desatado extraídos de `Global.wad.client:shared` (`16.23`), integrados en `stats`, `rotation` (`summoner:<hechizo>`), `survive`, `duel`, `optimize`, `contract` y `mcp`.

**Simulador de duelo 1v1 determinista con bloqueos por control de masas** ([Simulador de duelo 1v1](mechanics/duel.md), [`duel-simulator.md`](../odd/tasks/duel-simulator.md)): motor acoplado sobre reloj exacto `Fraction` reutilizando `rotation.py` y `defense.py` sin doble conteo, con `112/173` campeones (`148` habilidades, `154` `cc_effects` declarativos compilados desde el cliente `16.23`), tenacidad con suelo de `0,3 s`, purgas (*Limpiar*, QSS, `Alistar R`, `Gangplank W`, `Olaf R`, `Rengar W.empowered`, `Milio R`), inmunidades (`Olaf R`, `Fiora W`, `Morgana E`) e interceptación por escudo de hechizos; modos `scripted_then_attack`, `strict_scripted` y `priority_loop`, desempates `simultaneous` (invariante de simetría), `a_first` y `b_first`, expuesto en CLI (`duel`), contrato JSON (`operation: "duel"`), servidor MCP (`lol_duel`) y optimizador (`--objective duel`).

El modelo de objetos cubre los **218 objetos comprables de la Grieta** con revisión completa (**218/218 en `effect_review: complete`**, `0` pendientes): **174 entradas curadas** en `catalog.json` (`catalog_version: 28`; `166` objetos con `234` efectos documentados: `185` `evaluable`, `1` `partially_evaluable` y `48` `excluded` de utilidad pura no combativa, más las `4` transformaciones de Lágrima `3040`, `3042`, `3121` y `2530` y `52` objetos solo de estadísticas), los **3 elixires de la Grieta** (`2138` Hierro, `2139` Brujería, `2140` Cólera) y la **mejora de obra maestra de Ornn** (`OrnnP.DataValues` `16.23`, `1000 g` en estadísticas exactas sobre un único objeto completado no-botas; [`engine-v1.md`](../odd/tasks/engine-v1.md)). Las cifras que Data Dragon no publica se registran con fuente citada: la wiki (`secondary`) o los datos del cliente 16.23 (`derived`, `corroborated` si coinciden). Los límites están en [Modelo de objetos](objects/README.md).

## Aviso de fuentes

Los valores marcados `Derivado` proceden de datos del cliente, **no** de una API oficial de Riot: los de Zaahen, de los archivos del cliente 16.20 publicados por CommunityDragon ([Fuentes de Zaahen](champions/Zaahen/sources.md)); los de Ahri ([Fuentes de Ahri](champions/Ahri/sources.md)), los registros de campeones y los efectos de objetos de `derived/`, del cliente instalado 16.23. Se incluyen con atribución y aviso de no afiliación. El aviso completo está en [`../README.md`](../README.md).
