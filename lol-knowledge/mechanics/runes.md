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
| R8 | Wiki oficial de League of Legends (`wiki.leagueoflegends.com`, consultada el 2026-11-20; `V26.23` rev `4096203` confirma sin cambios en runas): `Rune` (`4094440`), `Lethal_Tempo` (`4060427`) y `Template:Rune_data_Lethal_Tempo` (`4065934`), `Template:Rune_data_Press_the_Attack` (`4015574`), `Template:Rune_data_Conqueror` (`4060685`), `Template:Rune_data_Hail_of_Blades` (`4060661`), `Arcane_Comet` (`4024412`, `V26.09` rev `4050133`) y `Template:Rune_data_Arcane_Comet` (`4060639`), `Template:Rune_data_Summon_Aery` (`4062237`) | Progresión lineal `10 × nivel` del fragmento de vida; multiplicadores reales a distancia de Compás letal (`× 0,8` VA y `× 0,667` daño, error conocido en el texto de lobby); curvas lineales 1–18 de Ataque intensificado, Conquistador y Lluvia de cuchillas (corroborando `{ee18a47b}` = `ByCharLevelNamedDataValuesInterpolationCalculationPart` sin multiplicador de crecimiento); eliminación del reembolso de enfriamiento de Cometa arcano en V26.09 y rampa lineal `0–100 %` en `0–750` unidades; retorno de Aery dependiente de distancia | Fuente comunitaria secundaria (corrobora los cálculos de R1) |
| R9 | Wiki oficial de League of Legends (`wiki.leagueoflegends.com`, consultada el 2026-11-20): `Template:Rune_data_Revitalize` (`3825912`), `Template:Rune_data_Shield_Bash` (`4044093`), `Template:Rune_data_Taste_of_Blood` (`3997097`), `Template:Rune_data_Absorb_Life` (`3997095`), `Template:Rune_data_Triumph` (`3825924`), `Template:Rune_data_Font_of_Life` (`3996429`) y `Template:Healing_modifiers` (`4021803`) | Curva por tramos de Absorber vida (`1..23`), exclusión a vida completa de Sabor a sangre, multiplicador de Revitalizar (< 40 % de vida) sobre robo de vida, omnivampirismo, curaciones y escudos, y fórmulas de Golpe de escudo, Triunfo y Fuente de vida | Fuente comunitaria secundaria (corrobora los valores de R1) |

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

- **Progresión de vida (`Derivado`, R1 + R8):** `10 × nivel` entre nivel 1 (`10`) y 18 (`180`), corroborado por los extremos de R1 y la fórmula de R8 (`Rune` rev `4094440`).
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
| 8453 | `Revitalize` | Estadística + amplificador (`survival.md`) | Opcional `attacker_health_percent` | `+5 %` permanente a `heal_and_shield_power` en la hoja; en `rotation`, `+10 %` multiplicativo a curaciones (incluidos robo de vida y omnivampirismo) y escudos cuando la vida del atacante está por debajo del 40 % (R1 + R9) |
| 8401 | `ShieldBash` | Proc adaptable (`rune`) | `--target-kind` y escudo propio o `shield_amount` | Al obtener un escudo (de un objeto en la rotación o vía `--input shield_amount`), el siguiente ataque básico contra campeón inflige `5–30 + 2,5 % vida adicional + 15 % escudo` de daño adaptable (R1 + R9) |
| 8139 | `TasteOfBlood` | Curación directa (`survival.md`) | `--target-kind` | Al dañar a un campeón (salvo a vida completa si se pasa `attacker_health_percent=1`), cura `16–40 + 10 % DA adicional + 5 % PH` (enfriamiento 20 s en `--timeline`, escalada con HSP y Heridas graves; R1 + R9) |
| 9101 | `AbsorbLife` | Curación al matar (`survival.md`) | `--target-kind` (no estructura) | En el paso letal (`health_after == 0`), cura `1–23` por tramos de nivel (R1 + R9; escalada con HSP y Heridas graves) |
| 9111 | `Triumph` | Curación al derribar (`survival.md`) | `--target-kind` (`champion`) | En el paso letal contra campeón, cura `2,5 % vida máxima + 5 % vida perdida` del atacante (escalada con HSP y Heridas graves; +20 de oro anotado fuera; R1 + R9) |
| 8463 | `FontOfLife` | Curación directa (`survival.md`) | `target_impaired` (`0` o `1`), `--target-kind` y `--attacker-range` | Con `1`, al dañar a un campeón cura `10–50` (`× 0,7` a distancia; `BaseHeal` en R1 + R9), enfriamiento 20 s en `--timeline`, escalada con HSP y Heridas graves |

Si el objetivo no coincide con el tipo de una runa (por ejemplo, Demoler contra un campeón o Golpe de gracia contra un súbdito), la runa no se aplica y no debilita la etiqueta. Si falta un `--input` condicional en una runa aplicable, queda en `not_applied` y deja el resultado en `Pendiente de verificación`.

## Piedras angulares ofensivas en `rotation` (`Derivado`, R1, R2, R4 y R8, salvo donde se indica)

Se aplican contra campeones en `python -m lol_knowledge rotation` (en `stats` constan como nota informativa; en `ability` permanecen en `pending_effects`). El daño adaptable usa la misma regla que los fragmentos (DA adicional > PH → físico; PH > DA adicional → mágico; empate decidido por `adaptiveforceapweight` con etiqueta `Pendiente de verificación`).

| Id | Clave del cliente | `--input` / requisito | Efecto en `rotation` |
|---|---|---|---|
| 8112 | `Electrocute` | `--target-kind` | Al 3.º golpe en 3 s (`WindowDuration`): 70–240 lineal + 10 % DA adicional + 5 % PH adaptable (`TotalDamage` en R1); enfriamiento 20 s en `--timeline` |
| 8128 | `DarkHarvest` | `dark_harvest_souls` (≥ 0) y `--target-kind` | Al dañar a un campeón por debajo del 50 % de vida: `30 + 11 × almas + 10 % DA adicional + 5 % PH` adaptable; suma 1 alma; enfriamiento 35 s en `--timeline` |
| 8005 | `PressTheAttack` | `--target-kind` | Al 3.º ataque básico: 40–160 lineal adaptable (R1 + R8) y activa +8 % de daño infligido en los golpes siguientes (caduca tras 6 s sin golpear en `--timeline`) |
| 8010 | `Conqueror` | `--target-kind`, `--attacker-range` | 2 acumulaciones por golpe (1 en ataques a distancia) hasta 12 durante 5 s: `1,8–4,0` lineal de fuerza adaptable por acumulación (R1 + R8) desde el paso siguiente (`combat-stacks.md`). Con 12 acumulaciones, cura 8 % (cuerpo a cuerpo) o 5 % (distancia) del daño infligido a campeones |
| 8008 | `LethalTempo` | `--target-kind`, `--attacker-range` | +6 % VA por ataque cuerpo a cuerpo o +4,8 % a distancia (`ASPerStack`: `× 0,8` en R1, corroborado por R8; `TTASPerStackRanged` 4 % es un texto de lobby desactualizado), hasta 6 durante 6 s. Al máximo, cada ataque inflige `9–30` (cuerpo a cuerpo) o `× 0,667` = `6,003–20,01` (a distancia; `NoteDamage` en R1 + R8, frente al error conocido 6–24 en `long_desc`) × `(1 + VA adicional)` de daño adaptable |
| 9923 | `HailOfBlades` | `--target-kind`, `--attacker-range` | Hasta 3 ataques (ventana de 3 s entre golpes, 10 s de enfriamiento en `--timeline`): +90 % / +60 % VA adicional entre ataques y `2–20 + 12 % DA adicional + 10 % PH` lineal de daño verdadero (`{ee18a47b}` = `ByCharLevelNamedDataValuesInterpolationCalculationPart` sin multiplicador de crecimiento en R1, corroborado por R8) |
| 8214 | `SummonAery` | `--target-kind` (opcional `aery_return_seconds` > 0 en `--timeline`) | En el primer golpe dañino: 10–50 lineal + 10 % DA adicional + 5 % PH adaptable (`DamageCalc` en R1). Como el retorno depende de la distancia y el movimiento (R8), sin `aery_return_seconds` solo dispara una vez y un segundo golpe dañino advierte y debilita a `Pendiente de verificación`; con `aery_return_seconds` en `--timeline` repite tras ese intervalo |
| 8229 | `ArcaneComet` | `comet_distance` (≥ 0) y `--target-kind` | Al golpear con una habilidad de daño: `(15–100 + 10 % DA adicional + 5 % PH) × (1 + min(dist, 750) / 750)` adaptable (rampa lineal 0–100 % en 0–750 unidades, R1 + R8). En `--timeline`: enfriamiento 20–8 s sin reembolso por golpe (eliminado en V26.09, R8; `PercentRefund` 0,2 en R1 es un campo legado ausente del tooltip 16.23) |
| 8992 | `DeathfireTouch` | `deathfire_duration` (`1`, `2` o `4`) y `--target-kind` | Quemadura mágica al golpear con habilidad: `3–12 + 2,5 % PH + 7 % DA adicional` por segundo (`DamageCalc` en R1); tras arder 3 s continuos (`TimeToAmp`) se amplifica un +75 % (`DamageMultiplier`). En `--timeline` se acumula de forma continua en `_accrue` |
| 8369 | `FirstStrike` | `first_strike` (`0` o `1`) y `--target-kind` si `1` | Ventana de 3 s (enfriamiento 25–15 s en `--timeline`): +7 % del daño posmitigación del paso como parte aparte de daño verdadero (sin volver a aplicar modificadores de daño). Oro adicional anotado fuera |
| 8437 | `GraspOfTheUndying` | `grasp_ready` (`0` o `1`), `--target-kind`, `--attacker-range` | En el siguiente ataque listo (o cada 4 s en combate en `--timeline`): inflige 3,5 % de vida máxima (× 0,4 a distancia) como daño mágico y **cura** 1,3 % de vida máxima (× 0,4 a distancia, escalada con HSP y Heridas graves; [`survival.md`](survival.md)). La vida máxima permanente (+5 / +2 por proc) se anota fuera |

## Runas defensivas en `survive` (`Derivado`, R1 y V7 de [`survival.md`](survival.md))

Se evalúan en la simulación inversa `python -m lol_knowledge survive` (en `stats` y `rotation` ofensiva constan como nota informativa sin debilitar el daño ofensivo):

| Id | Clave del cliente | `--input` / requisito | Efecto en `survive` |
|---|---|---|---|
| 8473 | `BonePlating` | Ninguno | Al recibir > 0 de daño real a la vida (no solo a escudos), activa 3 cargas durante 1,5 s (55 s CD en `--timeline`): los siguientes 3 golpes (incluido daño verdadero) infligen `30–60` menos de daño posmitigación (`MEC-08`) |
| 8444 | `SecondWind` | Ninguno | Tras recibir daño de campeón, regenera un `4 %` de la vida perdida durante 10 s (continuo y reiniciable en `--timeline`), reducido por Heridas graves y sin escalar con HSP ni Revitalizar |
| 8465 | `Guardian` | `guardian_ally` (`0` o `1`) | Con `1`, al recibir `50–165` de daño en 2,5 s o daño letal, otorga escudo `40–150 + 20 % PH + 6 % vida adicional` durante 1,5 s (`ShieldDuration` del cliente 16.23; 75–40 s CD), escalado con HSP y Revitalizar |

## Lo que no se modela todavía (dependencias de futuras mecánicas)

Las **5 piedras angulares** y **7 runas menores** restantes dependen de mecánicas aún no construidas; siguen en `pending_effects` y dejan `ability` y `rotation` en `Pendiente de verificación`:

- **Piedras angulares (5):** `8021` Pies veloces (`OBJ-04`), `8230` Tensión del saqueador de tormentas (`MEC-27`), `8351` Mejora glacial (`MEC-26`), `8360` Libro de hechizos (`DAT-06`) y `8439` Reverberacción (`MEC-26`).
- **Runas menores (7):**
  - Recursos / maná (`MEC-01`): `8009` Claridad mental.
  - CC / velocidad condicional (`MEC-26`): `8410` Velocidad de acercamiento y `8242` Inquebrantable.
  - Hechizos de invocador / aceleración de objetos (`DAT-06`, `MEC-29`): `8275` Capa del nimbo y `8347` Perspicacia cósmica.
  - Consumibles / elixires (`OBJ-12`): `8313` Tónico triple y `8352` Tónico de distorsión temporal.
- **La runa extra por árbol secundario** (`secondary_bonus`): sus valores son 0 en 16.23 y no se aplica.
- Las variantes por modo de juego (`mode_overrides`).
- Las runas del campeón objetivo: solo se aceptan para el atacante.
