# Runas y fragmentos

- **Ámbito:** estructura de una página de runas, su legalidad y los fragmentos de estadísticas. Lo usan `stats`, `ability` y `rotation` con `--rune` y `--shard`.
- **Parche de referencia:** cliente 16.23 y Data Dragon 16.23.1.
- **Fecha de consulta:** 2026-11-19
- **Código:** [`src/lol_knowledge/runes.py`](../../src/lol_knowledge/runes.py). Datos: [`../derived/runes.json`](../derived/runes.json), generado con `python -m binmodel.perks` ([`research/README.md`](../../research/README.md)).

## Fuentes

| Id | Fuente | Qué cubre | Naturaleza |
|---|---|---|---|
| R1 | Cliente 16.23 (`16.23.8399929+branch.releases-16-23.content.release`): `DATA/FINAL/Global.wad.client` → `perks` → registros `PerkStyle`, `PerkSlot` y `Perk` | Los 5 árboles, sus filas (la piedra angular tiene `mType` 0; las demás, 3), los árboles secundarios permitidos, la runa extra por árbol secundario, las 3 filas de fragmentos y los valores (`mEffectAmount`), variantes por modo y cálculos de cada runa | Datos del cliente, no una API oficial |
| R2 | Textos es_ES del cliente (`Localized/Global.es_ES.wad.client`), por las claves de cada runa | Nombre, descripción y marcadores `@StatGain@` que nombran los valores de R1 | Datos del cliente |
| R3 | Data Dragon 16.23.1, `data/current/runes.json` | Árboles, filas e ids de las 62 runas, sin cifras ni fragmentos | Oficial de Riot |
| R4 | League of Legends Wiki, «Rune (League of Legends)» y «Adaptive force» (consultadas el 2026-11-19) | Valores de los fragmentos; la fuerza adaptable da el que sea mayor de DA adicional y PH; en un empate, depende del campeón | Fuente comunitaria secundaria |
| R5 | Cliente 16.23, `CharacterRecords/Root.mAdaptiveForceToAbilityPowerWeight` de cada campeón ([`champion-records.json`](../derived/champion-records.json), campo `adaptiveforceapweight`) | Vale 1 en 77 campeones (Ahri, Lux, Annie, Malphite…) y falta en los otros 96 | Datos del cliente; su significado es una interpretación |

`validate` comprueba que los árboles, las filas y los ids de R1 coinciden exactamente con R3.

## Página legal (`Derivado`, R1 y R3)

1. **Árbol principal:** una piedra angular (fila 0) y una runa de cada una de sus otras tres filas.
2. **Árbol secundario:** otro árbol, permitido por el principal (`allowed_secondary`), con dos runas de filas distintas que no sean la de la piedra angular.
3. **Fragmentos:** tres, uno por fila y en orden: ataque, flexible y defensa. La fuerza adaptable y la progresión de vida aparecen en dos filas.
4. Una página incompleta o ilegal sale con código 2; `--allow-illegal-build` la calcula igualmente y escribe las violaciones como aviso.

## Fragmentos (`Derivado`, R1 y R2, salvo donde se indica)

| Id | Clave del cliente | Aporte | Valor del cliente |
|---|---|---|---|
| 5008 | `Adaptive` | 5,4 de DA o 9 de PH (ver abajo) | `StatGain1` 5,4; `StatGain2` 9 |
| 5005 | `AttackSpeed` | +10 % de velocidad de ataque adicional | `StatGain` 10 |
| 5007 | `CDRScaling` | +8 de aceleración de habilidades | `HasteGain` 8 |
| 5010 | `MovementSpeed` | +2,5 % de velocidad de movimiento, porcentual sobre los aportes planos ([regla](move-speed.md)) | `StatGain1` 2,5 |
| 5001 | `HealthScaling` | +10–180 de vida según el nivel | `StatGainMin` 10, `StatGainMax` 180 |
| 5011 | `Health` | +65 de vida | `StatGain` 65 |
| 5013 | `Tenacity` | +15 % de tenacidad (grupo A, [regla](tenacity.md)) y de resistencia a ralentizaciones | `StatGain` 15 |

- **Progresión de vida (`Pendiente de verificación`):** el cliente solo da los extremos y el texto dice «según el nivel»; la wiki tampoco publica la curva. Se toma lineal entre el nivel 1 y el 18: 10 + 170 × (nivel − 1) / 17, que da 10 por nivel.
- **Resistencia a ralentizaciones:** no se modela; el informe lo anota.
- **Fuerza adaptable:** da DA si el DA adicional supera al PH, y PH si el PH supera al DA adicional (R4), comparando los objetos antes de añadir los fragmentos. En un empate, como sin objetos, decide el campeón: con `adaptiveforceapweight` = 1 se toma PH y sin el campo se toma DA. Esa lectura de R5 es una deducción (los campeones con el campo son los de daño mágico), así que el aporte queda `Pendiente de verificación` en los empates.
- Los fragmentos entran en la hoja antes de los amplificadores: el Sombrero mortal de Rabadon multiplica también el PH de los fragmentos.

## Lo que no se modela todavía (RUN-04)

- **Los efectos de las runas de los árboles** (piedras angulares y runas menores). La página se valida, cada runa se lista en las notas y el daño de `ability` y `rotation` queda `Pendiente de verificación`.
- **La runa extra por árbol secundario** (`secondary_bonus`): sus valores son 0 en 16.23 y no se aplica.
- Las variantes por modo de juego (`mode_overrides`).
- Las runas del campeón objetivo: solo se aceptan para el atacante.
