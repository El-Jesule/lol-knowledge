# Supervivencia: escudos, curación de efectos, Heridas graves y poder de curaciones y escudos

- **Ámbito:** estadística de poder de curaciones y escudos (`heal_and_shield_power`), absorción de escudos del objetivo, escudos y curaciones directas generadas por el atacante (objetos y runas), seguimiento de la vida del atacante y reducción por Heridas graves (`grievous_wounds`). Lo usan `stats`, `ability` y `rotation`.
- **Parche de referencia:** cliente 16.23 y Data Dragon 16.23.1.
- **Fecha de consulta:** 2026-11-20
- **Código:** [`src/lol_knowledge/survival.py`](../../src/lol_knowledge/survival.py), [`src/lol_knowledge/stats/registry.py`](../../src/lol_knowledge/stats/registry.py), [`src/lol_knowledge/rotation.py`](../../src/lol_knowledge/rotation.py), [`src/lol_knowledge/rune_combat.py`](../../src/lol_knowledge/rune_combat.py) y [`src/lol_knowledge/rune_keystones.py`](../../src/lol_knowledge/rune_keystones.py).

## Fuentes

| Id | Fuente | Qué cubre | Naturaleza |
|---|---|---|---|
| V1 | Wiki oficial de League of Legends, `Heal_and_shield_power` (rev `4021804`) y `Template:Healing_modifiers` (rev `4021803`), consultadas el 2026-11-20 | El poder de curaciones y escudos se suma de forma aditiva y multiplica curaciones directas, drenaje y escudos; **no** afecta a robo de vida, omnivampirismo, regeneración de vida ni ganancias de vida máxima; multiplica con otros modificadores como el +10 % de Revitalizar (< 40 % de vida) y Heridas graves | Fuente comunitaria secundaria |
| V2 | Wiki oficial de League of Legends, `Grievous_Wounds` (rev `3969410`), consultada el 2026-11-20 | Heridas graves reduce en un `40 %` (`× 0,60`) toda curación (robo de vida, omnivampirismo, drenaje, curaciones de efectos y regeneración); **no** se acumula entre fuentes y **no** reduce escudos ni vida máxima | Fuente comunitaria secundaria |
| V3 | Wiki oficial de League of Legends, `Thornmail` (rev `4025130`), consultada el 2026-11-20 | Las Heridas graves aplicadas por Malla de espinas (40 % durante 3 s) al recibir un ataque básico se aplican **antes** de la curación de ese mismo ataque (robo de vida, etc.) | Fuente comunitaria secundaria |
| V4 | Wiki oficial de League of Legends, `Shield` (rev `4093144`), consultada el 2026-11-20 | Los escudos absorben daño posmitigación (tras armadura, RM y modificadores de daño) en lugar de la vida; tipos `normal` (físico, mágico y verdadero), `physical` (solo físico) y `magic` (solo mágico); no cuentan como vida para efectos basados en vida actual/máxima/perdida | Fuente comunitaria secundaria |
| V5 | Data Dragon 16.23.1 (`data/current/items.json`) y [`../objects/catalog-stats.json`](../objects/catalog-stats.json) | Porcentaje de «poder de curaciones y escudos» en las descripciones de los objetos de la Grieta | Oficial de Riot |
| V6 | Cliente 16.23 ([`../derived/runes.json`](../derived/runes.json) y [`../derived/item-effects.json`](../derived/item-effects.json)) | Valores de `Revitalize` (`8453`), `ShieldBash` (`8401`), `TasteOfBlood` (`8139`), `GraspOfTheUndying` (`8437`), `AbsorbLife` (`9101`), `Triumph` (`9111`), `FontOfLife` (`8463`), `2510` Amanecer y anochecer y `3075` Malla de espinas | `Derivado` |

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

## Limitaciones
- La **simulación inversa** (daño recibido por el campeón analizado, tiempo hasta morir, disparadores defensivos al recibir daño como Sterak, Protector, Fuerzas renovadas o Revestimiento de huesos) se aborda en `MEC-09` (siguiente fase).
- La interacción de `Serpent's Fang` (reducción de escudos) y `Spirit Visage` (+25 % a curaciones/escudos entrantes) entrará al curar esos objetos en `OBJ-01`.
