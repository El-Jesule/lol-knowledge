# Runas y fragmentos

- **Ámbito:** estructura de una página de runas, su legalidad, los fragmentos de estadísticas, las runas menores de estadísticas en la hoja y las runas menores de combate y piedras angulares en `rotation`. Lo usan `stats`, `ability` y `rotation` con `--rune`, `--shard` y `--input`.
- **Parche de referencia:** cliente 16.23 y Data Dragon 16.23.1.
- **Fecha de consulta:** 2026-11-20
- **Código:** [`src/lol_knowledge/runes.py`](../../src/lol_knowledge/runes.py), [`src/lol_knowledge/rune_combat.py`](../../src/lol_knowledge/rune_combat.py) y [`src/lol_knowledge/rune_keystones.py`](../../src/lol_knowledge/rune_keystones.py). Datos: [`../derived/runes.json`](../derived/runes.json), generado con `python -m binmodel.perks` ([`research/README.md`](../../research/README.md)).

## Fuentes

| Id | Fuente | Qué cubre | Naturaleza |
|---|---|---|---|
| R1 | Cliente 16.23 (`16.23.8399929+branch.releases-16-23.content.release`): `DATA/FINAL/Global.wad.client` → `perks` → registros `PerkStyle`, `PerkSlot` y `Perk` | Los 5 árboles, sus filas (la piedra angular tiene `mType` 0; las demás, 3), los árboles secundarios permitidos, la runa extra por árbol secundario, las 3 filas de fragmentos y los valores (`mEffectAmount`), variantes por modo y cálculos de cada runa | Datos del cliente, no una API oficial |
| R2 | Textos es_ES del cliente (`Localized/Global.es_ES.wad.client`), por las claves de cada runa | Nombre, descripción y marcadores `@StatGain@` que nombran los valores de R1 | Datos del cliente |
| R3 | Data Dragon 16.23.1, `data/current/runes.json` | Árboles, filas e ids de las 62 runas, sin cifras ni fragmentos | Oficial de Riot |
| R4 | League of Legends Wiki, «Rune (League of Legends)» y «Adaptive force» (consultadas el 2026-11-19) | Valores de los fragmentos; la fuerza adaptable da el que sea mayor de DA adicional y PH; en un empate, depende del campeón (1 PH = 0,6 DA) | Fuente comunitaria secundaria |
| R5 | Cliente 16.23, `CharacterRecords/Root.mAdaptiveForceToAbilityPowerWeight` de cada campeón ([`champion-records.json`](../derived/champion-records.json), campo `adaptiveforceapweight`) | Vale 1 en 77 campeones (Ahri, Lux, Annie, Malphite…) y falta en los otros 96 | Datos del cliente; su significado es una interpretación |
| R6 | League of Legends Wiki / Fandom, artículos de «Celerity», «Conditioning», «Overgrowth» y «Jack of All Trades» (extractos consultados el 2026-11-20) | Amplificación del total en Condicionamiento y Sobrecrecimiento; separación entre estadísticas planas y porcentuales en Manitas; efecto del 7 % de Celeridad sobre bonificaciones de velocidad | Fuente comunitaria secundaria |
| R7 | League of Legends Wiki / Fandom, artículos de «Coup de Grace», «Cut Down», «Last Stand», «Axiom Arcanist», «Scorch» y «Omnivamp» (extractos consultados el 2026-11-20) | Amplificación también sobre daño verdadero (desde el parche 15.3); interpolación lineal de Último esfuerzo entre 60 % y 30 %; reducción en área de Arcanólogo axiomático; retardo de 1 s y enfriamiento de 10 s de Piroláser; omnivampirismo sobre procs de runas | Fuente comunitaria secundaria |

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

## Runas menores de estadísticas en la hoja (`Derivado`, R1, R2 y R6, salvo donde se indica)

### Permanentes o de tope fijo (se aplican sin `--input`)

Siguiendo la convención de [`combat-stacks.md`](combat-stacks.md), las acumulaciones permanentes con tope fijo usan por defecto el escenario `maximum stacks` (y aceptan ajuste explícito con `--input` cuando existe):

| Id | Clave del cliente | Aporte en la hoja | Escenario / `--input` opcional |
|---|---|---|---|
| 8210 | `Transcendence` | +5 de aceleración de habilidades desde nivel 5; +10 desde nivel 8 (`HasteBonus1`/`HasteBonus2` × 100). La reducción al eliminar (nivel 11) se anota fuera de la hoja | Depende del nivel |
| 9104 | `LegendAlacrity` | +3 % de velocidad de ataque base + 1,5 % por acumulación, hasta 10 (+18 %) | `legend_stacks` (`0..10`; por defecto 10) |
| 9105 | `LegendHaste` | +1,5 de `basic_ability_haste` (Q, W, E) por acumulación, hasta 10 (+15) ([regla](ability-haste.md)) | `legend_stacks` (`0..10`; por defecto 10) |
| 9103 | `LegendBloodline` | +0,45 % de robo de vida por acumulación hasta 15 (+6,75 %) y +85 de vida al máximo | `legend_stacks` (`0..15`; por defecto 15) |
| 8226 | `ManaflowBand` | +250 de maná máximo (solo campeones con maná). La regeneración de maná perdido se anota fuera de la hoja | Tope permanente (250) |
| 8106 | `UltimateHunter` | +6 de `ultimate_haste` (R) + 5 por eliminación única, hasta 5 (+31) ([regla](ability-haste.md)) | `bounty_stacks` (`0..5`; por defecto 5) |
| 8234 | `Celerity` | +1 % de velocidad de movimiento (`Derivado`) y +7 % de eficacia sobre otras bonificaciones planas y porcentuales de velocidad (`Pendiente de verificación`: no se ha medido el orden ni si amplifica su propio 1 %) | Siempre activa |
| 8316 | `JackOfAllTrades` | +1 de aceleración de habilidades por estadística distinta de objetos (separando planas y porcentuales, incluido poder de curaciones y escudos; excluyendo oro cada 10 s); +8 de fuerza adaptable con 5–9 o +20 con ≥ 10 (× 0,6 para DA, × 1 para PH). Si un objeto tiene una estadística desconocida queda `Pendiente de verificación` | Calculada desde `--item` |
| 8304 | `MagicalFootwear` | +10 de velocidad de movimiento plana si la build contiene botas (grupo `Boots` de [`item-groups.json`](../derived/item-groups.json)); si no lleva botas, +0 con nota | Calculada desde `--item` |
| 8345 | `BiscuitDelivery` | +30 de vida máxima permanente por galleta (1 cada 2 min hasta el min 6: máximo +90). La curación consumible se anota fuera de la hoja | `game_minutes` (por defecto máximo: 3 galletas) |

### Condicionales, por minuto o sin tope (exigen `--input`)

El motor no inventa el minuto de partida, las unidades absorbidas ni la posición del campeón. Si falta su `--input`, la runa permanece en `pending_effects` indicando la clave necesaria:

| Id | Clave del cliente | `--input` requerido | Aporte en la hoja |
|---|---|---|---|
| 8236 | `GatheringStorm` | `game_minutes` (≥ 0) | Cada 10 min (`n = ⌊min / 10⌋`): `8 × n × (n + 1) / 2` de PH o × 0,6 de DA (0 antes del min 10) |
| 8429 | `Conditioning` | `game_minutes` (≥ 0) | Desde el min 12: +8 de armadura, +8 de RM y +3 % del total de armadura y RM (como amplificador; 0 antes del min 12) |
| 8451 | `Overgrowth` | `overgrowth_units` (entero ≥ 0) | +3 de vida por cada 8 unidades absorbidas y, desde 120 unidades, +3,5 % de vida máxima (como amplificador) |
| 8233 | `AbsoluteFocus` | `attacker_health_percent` (`0..1`) | Por encima del 70 % de vida: fuerza adaptable lineal 3–30 por nivel (`AdaptiveForceCalc` en R1; en el límite exacto 0,7 queda `Pendiente de verificación`) |
| 8232 | `Waterwalking` | `in_river` (`0` o `1`) | Con `1`: +10 de velocidad de movimiento plana y fuerza adaptable lineal 13–30 por nivel (`AdaptiveForceCalc` en R1) |

### Runas menores sin efecto en estadísticas ni daño 1v1

Las runas estrictamente de visión, oro, abalorios (excluidos por DEC-03), velocidad fuera de combate (`move-speed.md`) o sustitución de Destello se listan como nota informativa y **no** degradan la etiqueta de daño:

- `8137` Sexto sentido, `8140` Recuerdo macabro, `8141` Guardián de profundidad, `8135` Cazador de tesoros, `8105` Cazador incesante, `8306` Destello hextech y `8321` Reembolso.

## Runas menores de combate en `rotation` (`Derivado`, R1, R2 y R7, salvo donde se indica)

Se aplican en `python -m lol_knowledge rotation` (en `stats` se anotan como informativas; en `ability` siguen en `pending_effects` porque `ability` no evalúa efectos de combate). Los modificadores de daño infligido se suman aditivamente con los de los objetos ([regla](damage-modifiers.md)) y afectan a daño físico, mágico y verdadero (R7). Los procs de daño de runas (`kind: "rune"`) no aplican robo de vida y sí aplican omnivampirismo contra campeones (R7).

| Id | Clave del cliente | Tipo | `--input` / requisito | Efecto en `rotation` |
|---|---|---|---|---|
| 8014 | `CoupDeGrace` | Modificador (`dealt`) | `--target-kind` | +8 % de daño contra campeones por debajo del 40 % de vida actual |
| 8017 | `CutDown` | Modificador (`dealt`) | `--target-kind` | +8 % de daño contra campeones por encima del 60 % de vida actual |
| 8299 | `LastStand` | Modificador (`dealt`) | `attacker_health_percent` (`0..1`) y `--target-kind` si ≤ 0,6 | +5 % a +11 % lineal contra campeones entre el 60 % y el 30 % de vida del atacante (+11 % ≤ 30 %; en el límite exacto 0,6 queda `Pendiente de verificación`) |
| 8224 | `NullifyingOrb` (Arcanólogo axiomático) | Modificador (`dealt`, solo `R`) | `ultimate_aoe` (`0` o `1`, solo si la rotación lanza `R`) | +12 % (`0`) o +8 % (`1`) al daño de la definitiva (`R`). La curación/escudo y la reducción de enfriamiento al eliminar se anotan fuera |
| 8237 | `Scorch` | Proc mágico (`rune`) | `--target-kind` | Al golpear a un campeón con una habilidad de daño: 20–40 de daño mágico lineal por nivel (`DamageCalc` en R1). Sin `--timeline` salta una vez; con `--timeline` aterriza tras 1 s (`dotduration`) con 10 s de enfriamiento (`BurnlockoutDuration`) |
| 8126 | `CheapShot` | Proc verdadero (`rune`) | `target_impaired` (`0` o `1`) y `--target-kind` si `1` | Con `1`, al dañar a un campeón: 10–45 de daño verdadero lineal por nivel (`DamageCalc` en R1), con 4 s de enfriamiento en `--timeline` (una vez sin línea de tiempo) |
| 8143 | `SuddenImpact` | Proc verdadero (`rune`) | `sudden_impact` (`0` o `1`) y `--target-kind` si `1` | Con `1`, al dañar a un campeón: 20–80 de daño verdadero lineal por nivel (`BaseDamage` en R1), con 10 s de enfriamiento en `--timeline` (una vez sin línea de tiempo; repetir en línea de tiempo anota el supuesto de rearmado) |
| 8446 | `Demolish` | Proc físico (`rune`) | `--target-kind` y `--attacker-range` si es `structure` | Solo contra estructuras: cada 3.º ataque básico inflige 85 + 28 % de vida máxima (cuerpo a cuerpo) o 50 + 20 % (a distancia) de daño físico, con 30 s de enfriamiento en `--timeline` |

Si el objetivo no coincide con el tipo de una runa (por ejemplo, Demoler contra un campeón o Golpe de gracia contra un súbdito), la runa no se aplica y no debilita la etiqueta. Si falta un `--input` condicional en una runa aplicable, queda en `not_applied` y deja el resultado en `Pendiente de verificación`.

## Piedras angulares ofensivas en `rotation` (`Derivado`, R1, R2 y R4, salvo donde se indica)

Se aplican contra campeones en `python -m lol_knowledge rotation` (en `stats` constan como nota informativa; en `ability` permanecen en `pending_effects`). El daño adaptable usa la misma regla que los fragmentos (DA adicional > PH → físico; PH > DA adicional → mágico; empate decidido por `adaptiveforceapweight` con etiqueta `Pendiente de verificación`).

| Id | Clave del cliente | `--input` / requisito | Efecto en `rotation` |
|---|---|---|---|
| 8112 | `Electrocute` | `--target-kind` | Al 3.º golpe en 3 s (`WindowDuration`): 70–240 lineal + 10 % DA adicional + 5 % PH adaptable (`TotalDamage` en R1); enfriamiento 20 s en `--timeline` |
| 8128 | `DarkHarvest` | `dark_harvest_souls` (≥ 0) y `--target-kind` | Al dañar a un campeón por debajo del 50 % de vida: `30 + 11 × almas + 10 % DA adicional + 5 % PH` adaptable; suma 1 alma; enfriamiento 35 s en `--timeline` |
| 8005 | `PressTheAttack` | `--target-kind` | Al 3.º ataque básico: 40–160 adaptable (`Pendiente de verificación` en niveles 2–17, sin curva en el bin) y activa +8 % de daño infligido en los golpes siguientes (caduca tras 6 s sin golpear en `--timeline`) |
| 8010 | `Conqueror` | `--target-kind`, `--attacker-range` | 2 acumulaciones por golpe (1 en ataques a distancia) hasta 12 durante 5 s: `1,8–4,0` de fuerza adaptable por acumulación (`Pendiente de verificación` en niveles 2–17) desde el paso siguiente (`combat-stacks.md`). Con 12 acumulaciones, cura 8 % (cuerpo a cuerpo) o 5 % (distancia) del daño infligido a campeones |
| 8008 | `LethalTempo` | `--target-kind`, `--attacker-range` | +6 % VA por ataque cuerpo a cuerpo (`Derivado`) o +4 % a distancia (`Pendiente de verificación`: discrepancia 4 % tooltip frente a 4,8 % `ASPerStack` en 16.23), hasta 6 durante 6 s. Al máximo, cada ataque inflige `9–30` (cuerpo a cuerpo) o `6–24` (a distancia, `Pendiente de verificación`: 24 frente a 20 en `NoteDamage`) × `(1 + VA adicional)` de daño adaptable |
| 9923 | `HailOfBlades` | `--target-kind`, `--attacker-range` | Hasta 3 ataques (ventana de 3 s entre golpes, 10 s de enfriamiento en `--timeline`): +90 % / +60 % VA adicional entre ataques y `2–20 + 12 % DA adicional + 10 % PH` de daño verdadero (`Pendiente de verificación` en niveles 2–17 por la curva `{ee18a47b}`) |
| 8214 | `SummonAery` | `--target-kind` | En el primer golpe dañino: 10–50 lineal + 10 % DA adicional + 5 % PH adaptable (`DamageCalc` en R1). Como el retorno depende de la distancia, solo dispara una vez; si hay más golpes dañinos se anota y debilita a `Pendiente de verificación` |
| 8229 | `ArcaneComet` | `comet_distance` (≥ 0) y `--target-kind` | Al golpear con una habilidad de daño: `(15–100 + 10 % DA adicional + 5 % PH) × (1 + min(dist, 750) / 750)` adaptable (`Pendiente de verificación` para distancias intermedias `0 < dist < 750`). En `--timeline`: enfriamiento 20–8 s con reembolso del 20 % por habilidad de daño |
| 8992 | `DeathfireTouch` | `deathfire_duration` (`1`, `2` o `4`) y `--target-kind` | Quemadura mágica al golpear con habilidad: `3–12 + 2,5 % PH + 7 % DA adicional` por segundo (`DamageCalc` en R1); tras arder 3 s continuos (`TimeToAmp`) se amplifica un +75 % (`DamageMultiplier`). En `--timeline` se acumula de forma continua en `_accrue` |
| 8369 | `FirstStrike` | `first_strike` (`0` o `1`) y `--target-kind` si `1` | Ventana de 3 s (enfriamiento 25–15 s en `--timeline`): +7 % del daño posmitigación del paso como parte aparte de daño verdadero (sin volver a aplicar modificadores de daño). Oro adicional anotado fuera |
| 8437 | `GraspOfTheUndying` | `grasp_ready` (`0` o `1`), `--target-kind`, `--attacker-range` | En el siguiente ataque listo (o cada 4 s en combate en `--timeline`): 3,5 % de vida máxima (× 0,4 a distancia) como daño mágico. Curación y vida permanente anotadas como no modeladas (`MEC-05`) |

## Lo que no se modela todavía (dependencias de futuras mecánicas)

Las **6 piedras angulares** y **15 runas menores** restantes dependen de mecánicas aún no construidas; siguen en `pending_effects` y dejan `ability` y `rotation` en `Pendiente de verificación`:

- **Piedras angulares (6):** `8021` Pies veloces (`MEC-05`, `OBJ-04`), `8230` Tensión del saqueador de tormentas (`MEC-27`), `8351` Mejora glacial (`MEC-26`), `8360` Libro de hechizos (`DAT-06`), `8439` Reverberacción (`MEC-26`, `MEC-09`) y `8465` Protector (`MEC-04`, `MEC-09`).
- **Runas menores (15):**
  - Curación de efectos / vida del atacante (`MEC-05`): `9101` Absorber vida, `9111` Triunfo, `8139` Sabor a sangre, `8463` Fuente de vida y `8444` Fuerzas renovadas.
  - Recursos / maná (`MEC-01`): `8009` Claridad mental.
  - Escudos (`MEC-04`) y poder de curaciones/escudos (`MEC-07`): `8401` Golpe de escudo y `8453` Revitalizar.
  - Reducción plana de daño (`MEC-08`): `8473` Revestimiento de huesos.
  - CC / velocidad condicional (`MEC-26`): `8410` Velocidad de acercamiento y `8242` Inquebrantable.
  - Hechizos de invocador / aceleración de objetos (`DAT-06`, `MEC-29`): `8275` Capa del nimbo y `8347` Perspicacia cósmica.
  - Consumibles / elixires (`OBJ-12`): `8313` Tónico triple y `8352` Tónico de distorsión temporal.
- **La runa extra por árbol secundario** (`secondary_bonus`): sus valores son 0 en 16.23 y no se aplica.
- Las variantes por modo de juego (`mode_overrides`).
- Las runas del campeón objetivo: solo se aceptan para el atacante.
