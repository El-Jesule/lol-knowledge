# Supervivencia: escudos, curación de efectos, Heridas graves y poder de curaciones y escudos

- **Ámbito:** estadística de poder de curaciones y escudos (`heal_and_shield_power`), absorción de escudos del objetivo, escudos y curaciones directas generadas por el atacante (objetos y runas), seguimiento de la vida del atacante, reducción por Heridas graves (`grievous_wounds`), reducción plana de daño (`MEC-08`) y simulación inversa de supervivencia (`MEC-09`). Lo usan `stats`, `ability`, `rotation` y `survive`.
- **Parche de referencia:** cliente 16.23 y Data Dragon 16.23.1.
- **Fecha de consulta:** 2026-11-20
- **Código:** [`src/lol_knowledge/survival.py`](../../src/lol_knowledge/survival.py), [`src/lol_knowledge/defense/`](../../src/lol_knowledge/defense/), [`src/lol_knowledge/defense_report.py`](../../src/lol_knowledge/defense_report.py), [`src/lol_knowledge/stats/registry.py`](../../src/lol_knowledge/stats/registry.py), [`src/lol_knowledge/rotation/`](../../src/lol_knowledge/rotation/), [`src/lol_knowledge/rune_combat.py`](../../src/lol_knowledge/rune_combat.py) y [`src/lol_knowledge/rune_keystones.py`](../../src/lol_knowledge/rune_keystones.py).

## Fuentes

| Id | Fuente | Qué cubre | Naturaleza |
|---|---|---|---|
| V1 | Wiki oficial de League of Legends, `Heal_and_shield_power` (rev `4021804`) y `Template:Healing_modifiers` (rev `4021803`), consultadas el 2026-11-20 | El poder de curaciones y escudos se suma de forma aditiva y multiplica curaciones directas, drenaje y escudos; **no** afecta a robo de vida, omnivampirismo, regeneración de vida ni ganancias de vida máxima; multiplica con otros modificadores como el +10 % de Revitalizar (< 40 % de vida) y Heridas graves | Fuente comunitaria secundaria |
| V2 | Wiki oficial de League of Legends, `Grievous_Wounds` (rev `3969410`), consultada el 2026-11-20 | Heridas graves reduce en un `40 %` (`× 0,60`) toda curación (robo de vida, omnivampirismo, drenaje, curaciones de efectos y regeneración); **no** se acumula entre fuentes y **no** reduce escudos ni vida máxima | Fuente comunitaria secundaria |
| V3 | Wiki oficial de League of Legends, `Thornmail` (rev `4025130`), consultada el 2026-11-20 | Las Heridas graves aplicadas por Malla de espinas (40 % durante 3 s) al recibir un ataque básico se aplican **antes** de la curación de ese mismo ataque (robo de vida, etc.) | Fuente comunitaria secundaria |
| V4 | Wiki oficial de League of Legends, `Shield` (rev `4093144`), consultada el 2026-11-20 | Los escudos absorben daño posmitigación (tras armadura, RM y modificadores de daño) en lugar de la vida; tipos `normal` (físico, mágico y verdadero), `physical` (solo físico) y `magic` (solo mágico); no cuentan como vida para efectos basados en vida actual/máxima/perdida | Fuente comunitaria secundaria |
| V5 | Data Dragon 16.23.1 (`data/current/items.json`) y [`../objects/catalog-stats.json`](../objects/catalog-stats.json) | Porcentaje de «poder de curaciones y escudos» en las descripciones de los objetos de la Grieta | Oficial de Riot |
| V6 | Cliente 16.23 ([`../derived/runes.json`](../derived/runes.json) y [`../derived/item-effects.json`](../derived/item-effects.json)) | Valores de `Revitalize` (`8453`), `ShieldBash` (`8401`), `TasteOfBlood` (`8139`), `GraspOfTheUndying` (`8437`), `AbsorbLife` (`9101`), `Triumph` (`9111`), `FontOfLife` (`8463`), `BonePlating` (`8473`), `SecondWind` (`8444`), `Guardian` (`8465`), `2510` Amanecer y anochecer, `3053` Calibrador de Sterak y `3075` Malla de espinas | `Derivado` |
| V7 | Wiki oficial de League of Legends (`wiki.leagueoflegends.com`, consultada el 2026-11-20): `Bone_Plating` (`4072632`) y `Template:Rune_data_Bone_Plating` (`3985159`), `Template:Rune_data_Second_Wind` (`3960974`), `Template:Rune_data_Guardian` (`4022993`), `Module:ItemData/data` (`4095269`, `Sterak's Gage`) | Revestimiento de huesos reduce daño posmitigación (incluido daño verdadero) tras activarse al recibir daño real a la vida (no a escudos); Fuerzas renovadas regenera 4 % de vida perdida en 10 s (solo afectada por Heridas graves); Salvavidas de Sterak salta antes de bajar del 30 % de vida con escudo del 60 % de vida adicional | Fuente comunitaria secundaria |

## Reglas (`Derivado`, V1–V4 y V6; estadísticas de objetos `Oficial`, V5)

### 1. Poder de curaciones y escudos (`MEC-07`)
- Estadística aditiva de la hoja (`heal_and_shield_power`, fracción `0..∞`).
- Aporta el factor `1 + heal_and_shield_power` a:
  - Curaciones directas de efectos (objetos y runas: Garras, Sabor a sangre, Absorber vida, Triunfo, Fuente de vida, Amanecer y anochecer).
  - Escudos generados por el atacante.
- **No** afecta a robo de vida ni a omnivampirismo (V1; ver [`life-steal-and-omnivamp.md`](life-steal-and-omnivamp.md)).
- **`Revitalize` (`8453`):** suma `+5 %` permanente a `heal_and_shield_power` en la hoja; cuando la vida del atacante está por debajo del `40 %`, añade un multiplicador independiente `× 1,10` sobre curaciones (incluidos robo de vida y omnivampirismo) y escudos propios (V1).

### 2. Heridas graves (`MEC-06`)
- Multiplicador `1 − 0,40 = 0,60` sobre **toda** curación del atacante (robo de vida, omnivampirismo, drenaje y curaciones directas de efectos).
- **No** se acumula entre fuentes (se toma el máximo, `40 %`).
- **No** afecta a escudos ni a aumentos de vida máxima (V2).
- En `rotation` se activa de dos formas:
  1. Explícita como escenario: `--input grievous_wounds=1` (o `0` para inactiva).
  2. Automática desde los objetos del objetivo: si un objetivo campeón equipa un objeto con componente `status` `grievous_wounds` al recibir ataques (como `3075` Malla de espinas, `40 %` durante `3 s`), cualquier ataque básico activa Heridas graves **antes** de calcular la curación de ese ataque (V3) y la mantiene `3 s` en `--timeline`.

### 3. Escudos (`MEC-04`)
- **Escudo del objetivo (`--target-shield`, `--target-shield-type normal|physical|magic`):**
  - El daño de cada parte ya mitigado y modificado (`part.damage`) se absorbe primero contra el escudo si su tipo coincide (`normal` absorbe físico, mágico y verdadero; `physical` solo físico; `magic` solo mágico).
  - El remanente reduce la vida real del objetivo (`health_after`).
  - Las ejecuciones (`execute`, p. ej. La Recaudadora) comprueban siempre la vida real, nunca `vida + escudo` (V4).
  - Las fórmulas basadas en vida actual, máxima o perdida leen siempre la vida real (V4).
- **Escudos generados por el atacante:**
  - Escalan con `(1 + heal_and_shield_power) × (1 + revitalizar_extra)` y nunca se reducen con Heridas graves (V1, V2).
  - Alimentan automáticamente a `8401` Golpe de escudo (`ShieldBash`).

### 4. Curaciones de efectos y vida del atacante (`MEC-05`)
- Si se pasa `--input attacker_health_percent=<0..1>`, la rotación sigue la vida real del atacante desde `vida_máx × porcentaje` hasta un tope de `vida_máx`, informando tanto la curación generada (`healing`) como la curación efectiva acotada por vida perdida (`effective_healing`).
- Si no se especifica `attacker_health_percent`, la rotación informa la curación generada sin acotar (compatible con el comportamiento previo de robo de vida y omnivampirismo).

### 5. Reducción plana de daño (`MEC-08`) y simulación inversa (`MEC-09`, `survive`)
- `python -m lol_knowledge survive` evalúa al campeón analizado como **defensor** frente a golpes manuales (`--incoming "attack:400, attack:crit:600, magic:300, true:150, wait:1"`) o frente a la rotación de un campeón enemigo (`--enemy-champion` + `--steps`).
- **Reducción plana (`MEC-08`, V7):** se resta al daño posmitigación (incluido daño verdadero) con suelo `0`. Aplica `--input flat_damage_reduction=<n>` y `8473` Revestimiento de huesos (se activa tras recibir > 0 de daño real a la vida, no solo a escudos; reduce los 3 golpes siguientes en `30–60` durante `1,5 s`, `55 s` CD en `--timeline`).
- **Escudos previos al daño:** `3053` Calibrador de Sterak (`Salvavidas`: antes de bajar del `30 %` de vida máxima, otorga un escudo del `60 %` de vida adicional durante `4,5 s`, `90 s` CD) y `8465` Protector (con `--input guardian_ally=1`, al recibir `50–165` de daño en `2,5 s` o daño letal, otorga `40–150 + 20 % PH + 6 % vida adicional` durante `1,5 s`, `75–40 s` CD). Ambos escalan con HSP y Revitalizar y absorben el golpe disparador inmediatamente (los escudos que caducan antes absorben primero, V4).
- **Regeneración defensiva:** `8444` Fuerzas renovadas regenera un `4 %` de vida perdida en `10 s` tras recibir daño de campeón (reducida por Heridas graves y sin escalar con HSP ni Revitalizar, V1/V7).
- **Reflejo reactivo:** `3075` Malla de espinas informa el daño mágico en bruto reflejado (`20 + 10 %` armadura adicional) por cada ataque básico recibido.
- **Métricas de salida:** daño total recibido, reducción plana total, escudos otorgados/absorbidos, curación defensiva, vida restante, supervivencia (`survived`), paso letal, **tiempo hasta morir** (`time_to_die`) y **daño recibido por segundo** (`damage_taken_per_second`) con `--timeline`.

## Pasivas defensivas de objetos en `defense/` / `survive` (`Derivado`, cliente `16.23`, `catalog_version: 28`)
- **Malla del guardián (`data:item:3082`, *Como una roca*):** reducción plana posmitigación de `15` contra ataques básicos (`attack`/`crit`), limitada al `20 %` del daño posmitigación del ataque.
- **Jak'Sho el Proteico (`data:item:6665`, *Resiliencia del Vacío*, `Oficial`):** en `--timeline`, tras `5 s` de combate desde el primer golpe recibido, aumenta la armadura y la resistencia mágica adicionales en un `30 %` para el resto del combate (incluyendo la RM adicional activa de Fuerza de la naturaleza si coexisten).
- **Fuerza de la naturaleza (`data:item:4401`, *Entereza*):** tras recibir `8` instancias de daño mágico (ventana/duración de `7 s` en `--timeline`), otorga `+70` de resistencia mágica adicional renovable al recibir daño mágico.
- **Arnés de protoplasma (`data:item:2525`, *Salvavidas*):** al bajar del `30 %` de vida máxima (`90 s` CD), otorga `100..300` de vida máxima y actual temporal durante `5 s` y regenera `100..400 + 175 % armadura adicional + 175 % RM adicional` a lo largo de `5 s` (integrado de forma continua en `--timeline`, afectado por Heridas graves y Rostro espiritual).
- **Baile de la muerte (`data:item:6333`, *Ignora el dolor*):** en `--timeline`, difiere el `30 %` (cuerpo a cuerpo) o `10 %` (a distancia) del daño físico y mágico posmitigación en una hemorragia continua de daño verdadero durante `3 s`, con cálculo exacto del instante letal (`time_to_die`) combinado con regeneración activa.
- **Detracción celestial (`data:item:3869`, *Bendición de la montaña*):** reduce un `35 %` (cuerpo a cuerpo) o `25 %` (a distancia) el daño físico y mágico recibido en el primer golpe y durante los `2 s` siguientes (`18 s` CD en `--timeline`).
- **Escudos de hechizos (`data:item:3102` Velo del hada, `data:item:3814` Filo de la noche, `data:item:4632` Barrera frondosa, *Anular*):** bloquean por completo el siguiente golpe de tipo `ability` (`40 s` CD en `3102`/`3814`, `60 s` CD en `4632`).
- **Escudo de Doran (`data:item:1054`, *Concentración inquebrantable*):** tras recibir daño de campeón, regenera de forma continua durante `8 s` hasta `40` (cuerpo a cuerpo) o `30` (a distancia) de vida escalada linealmente por la fracción de vida faltante (`× 0,66` con `--input aoe_dot=1`).
- **Corazón de Warmog (`data:item:3083`):** con `≥ 2000` de vida adicional y `≥ 8 s` fuera de combate en `--timeline`, regenera un `3 %` de la vida máxima por segundo.
- **Ángel de la guarda (`data:item:3026`, *Renacimiento*):** ante daño letal (`300 s` CD), entra en estasis invulnerable durante `4 s` (limpia hemorragias pendientes) y revive con el `50 %` de la vida básica.
- **Abrazo del serafín (`3040`, transformación de `data:item:3003` a `360` cargas de Flujo de maná):** *Salvavidas* otorga un escudo del `18 %` del maná máximo durante `3 s` (`90 s` CD) al bajar del `30 %` de vida.
- **Colmillo de serpiente (`data:item:6695`, *Siegaescudos*):** reduce escudos existentes y nuevos en un `50 %` (cuerpo a cuerpo) o `35 %` (a distancia) durante `3 s` tanto en `rotation` como en `survive` (automático cuando `--enemy-champion` lleva `6695`, o vía `--input shield_reaver`).
- **Pociones (`data:item:2003`/`data:item:2031`), Tejesueños (`data:item:3870`, burbuja azul) y Promesa de caballero (`data:item:3109`, *Sacrificio*):** regeneración continua de pociones (`--input potion_active=1`), reducción plana contra ataques de `50..194` por nivel (`--input dream_maker_active=1`) y redirección del `14 %` del daño del aliado digno por encima del `30 %` de vida (`--input worthy_ally_damage_taken`).

## Limitaciones
- La curva de decaimiento del escudo de `3053` Salvavidas (`4,5 s` tras `0,75 s`) se anota como pendiente dentro de `--timeline`; el escudo caduca completo al final de los `4,5 s`.
- En objetivos estáticos de EHP (`effective_health_*`), las pasivas defensivas activadas en combate (`6665`, `4401`, `3082`, `2525`, `6333`, `3869`, `3026`, `1054`) siguen marcándose como no modeladas en EHP estático; su efecto verificado se evalúa en `survive` y en el objetivo `time_to_die` del optimizador.
- Sigue excluida la limpieza de hemorragia por derribo de `6333` (*Desafío*) en simulaciones sin derribo.
