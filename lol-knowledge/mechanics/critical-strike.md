# Impacto crítico

- **Ámbito:** regla general del juego para los ataques básicos que asestan un impacto crítico, y para la probabilidad de crítico. La usa `python -m lol_knowledge rotation` en los pasos `attack:crit`.
- **Parche de referencia:** cliente 16.22 (2026-11-15). El daño crítico base es 200 % desde el parche 26.1.
- **Fecha de consulta:** 2026-11-15 (probabilidad de crítico y pasivas de Yasuo y Yone: 2026-11-16)

## Fuentes

| Id | Fuente | Qué cubre | Naturaleza |
|---|---|---|---|
| C1 | Notas oficiales del parche 26.1 (`leagueoflegends.com/en-sg/news/game-updates/patch-26-1-notes/`), consultadas el 2026-11-15 | El daño crítico base de todos los campeones vuelve al 200 % | Oficial de Riot |
| C2 | Cliente local 16.22: `Characters/<Id>/CharacterRecords/Root.critDamageMultiplier`, extraído con `research/binmodel/records.py` y publicado en [`../derived/champion-records.json`](../derived/champion-records.json) como `critdamagemultiplier` | Multiplicador crítico base de cada campeón: 2,0 en 172 campeones y 1,0 en Ashe | `Derivado` del cliente |
| C3 | LoL Wiki, artículo `Damage` (copia de `leagueoflegends.fandom.com`), consultada el 2026-11-15 (CC BY-SA) | El crítico modifica el daño antes de la mitigación; la mayoría de efectos al impactar no se ven afectados | Fuente comunitaria secundaria |
| C4 | ARAM Mayhem, resumen del parche 26.1 (`arammayhem.com/patch/26-1/`), consultado el 2026-11-15 | Con Filo infinito el crítico pasa de 215 % a 230 % | Fuente comunitaria secundaria que resume las notas oficiales |
| C5 | Data Dragon 16.22.1, objeto 3031 (Filo infinito), en el [catálogo de objetos](../objects/catalog.json) | 30 % de daño crítico adicional | Oficial de Riot |
| C6 | LoL Wiki, `Critical_strike` (revisiones 3420516 y 3427204, y la página actual), extractos del buscador consultados el 2026-11-16 | La probabilidad no supera el 100 %, aunque algunos efectos aprovechan el exceso (W de Senna); no se gana al subir de nivel; se suma; corrección pseudoaleatoria de las tiradas | Fuente comunitaria secundaria |
| C7 | Comentario de un empleado de Riot (`/u/AzuBK`) en Reddit, recogido por `devtrackers.gg` (hacia 2020), consultado el 2026-11-16 | «Critical strike chance is implicitly capped at 100%», no solo para Yasuo, Yone o Rageblade | Declaración de Riot fuera de las notas de parche; antigua |
| C8 | Data Dragon 16.22.1, `stats.crit` y `stats.critperlevel` de cada campeón, y `stats.FlatCritChanceMod` de los objetos | Base y crecimiento de los campeones (`0` en los 173, comprobado el 2026-11-16); probabilidad de los objetos (entre 8 % y 50 %) | Oficial de Riot |
| C9 | LoL Wiki, `Yasuo`, `Yone` (revisión 4091148, del 28-10-2026) y `Yasuo/Patch_history` (revisión 4072894), extractos del buscador consultados el 2026-11-16 | Su pasiva duplica la probabilidad de crítico total del resto de fuentes y convierte cada 1 % por encima del 100 % en 0,5 de daño de ataque adicional (V14.10: multiplicador 2 y conversión 0,5); la reducción de daño crítico se aplica al daño crítico **total** (Yone: 190 % + 28,5 % con Filo infinito, el 95 % de lo normal) | Fuente comunitaria secundaria. El usuario confirmó la duplicación y la conversión el 2026-11-16 |
| C10 | Notas oficiales del parche 26.17 (`leagueoflegends.com/en-us/news/game-updates/league-of-legends-patch-26-17-notes`), consultadas el 2026-11-16; notas de 26.21 (en-sg) y resúmenes de 26.22, consultados el mismo día | Pasivas de Yasuo y Yone: «Critical Strike Damage Reduction: -10% ⇒ -5%». En 26.21 y 26.22 solo cambian sus Q, no las pasivas | Oficial de Riot (26.22, solo por resúmenes secundarios) |
| C11 | Data Dragon 16.22.1, objeto 3032 (Flechas de los Yun Tal): «0% de probabilidad de impacto crítico» y «Al atacar, obtienes probabilidad de impacto crítico de forma permanente, hasta un 25%.» | Sin crítico al comprarlo; crítico permanente por ataque hasta 25 % | Oficial de Riot |
| C12 | Cliente local 16.22 (`16.22.8348910`): `Global.wad.client` → `items` → `Items/3032.mDataValues`, y la plantilla `item_3032_tooltip` de `Localized/Global.es_ES.wad.client`, leídas el 2026-11-16 | `CritPerStackMelee` 0,4; `StackRangedMultiplier` 0,5; `CritMax` 25; el registro no tiene campo de crítico. La plantilla calcula `@CritPerStackCalc@` con el valor cuerpo a cuerpo y el multiplicador a distancia | `Derivado` del cliente. El usuario confirmó el 0 % inicial y la acumulación permanente hasta 25 % el 2026-11-16 |

**Discrepancia registrada:** la página `Critical_strike` de la LoL Wiki aún dice 175 % (consultada el 2026-11-15). C1 y C2 dicen 200 %; se sigue a C1 y C2.

## Regla (`Derivado`, corroborada C1 + C2)

```text
daño bruto del crítico = daño del ataque × (multiplicador_base + Σ daño_crítico_adicional)
```

- `multiplicador_base` es el `critdamagemultiplier` del campeón (C2). Para 172 campeones es 2,0, el mismo valor que anuncian las notas oficiales (C1). Si el registro del campeón no tiene el campo, el paso crítico se rechaza.
- **Ashe (`Derivado`, `AshePassive.mSpellCalculations.DamageBonus` en el cliente `16.23`):** tiene `1,0` en el registro porque sus impactos críticos no multiplican el daño por `2,0`, sino que duplican la ralentización de *Tiro congelador*. En su lugar, todos sus ataques básicos (`attack` y `attack:crit`) multiplican su daño de ataque total por `1 + crit_chance × (1 + crit_damage_bonus)`. Cualquier otro campeón cuyo multiplicador de registro difiriera de `2,0` sigue recibiendo `Pendiente de verificación`.
- **Jhin (`Derivado`, `JhinPassive.DataValues.CritReductionPercent = 0.25`):** su pasiva reduce el daño crítico total un `25 %`, por lo que su multiplicador crítico es `(multiplicador_base + Σ daño_crítico_adicional) × 0,75` (`1,5` base; `1,725` con Filo infinito).
- `daño_crítico_adicional` es la estadística `crit_damage_bonus` (C5). Filo infinito suma 0,3: 2,0 + 0,3 = 2,3, el 230 % de C4.
- Con **varias fuentes** de daño crítico adicional, la suma no está verificada (solo hay un objeto en el catálogo). El motor las suma y marca el resultado `Pendiente de verificación`.
- El crítico se aplica **antes de la mitigación** (C3). Como la mitigación multiplica, el orden no cambia el resultado.
- El daño al impactar de los objetos **no** se multiplica por el crítico (C3: la mayoría de efectos al impactar no se ven afectados, salvo que se indique). Ningún objeto del catálogo indica lo contrario.
- **Yasuo y Yone** (valor `Oficial`, C10; forma de aplicarlo `Derivado`, C9): su pasiva reduce el daño crítico total un 5 %, así que el multiplicador es `(multiplicador_base + Σ daño_crítico_adicional) × 0,95`. Con Filo infinito: (2,0 + 0,3) × 0,95 = 2,185. Su registro del cliente dice 2,0 porque la reducción vive en el kit, no en el registro.

## Probabilidad de crítico (`Derivado`, C6 + C7; datos `Oficial`, C8)

```text
probabilidad = min(base + crecimiento(n) + Σ objetos_i, 100 %)
```

- **Base y crecimiento:** `stats.crit` y `stats.critperlevel` de Data Dragon (C8). Valen `0` en los 173 campeones: ningún campeón gana probabilidad de crítico al subir de nivel (C6).
- **Aportes:** objetos y efectos, como fracción (25 % = 0,25). Se **suman** (C6).
- **Tope:** 100 % (C6, C7). Algunos efectos aprovechan el exceso (C6: W de Senna; C9: Yasuo y Yone lo convierten en daño de ataque adicional), así que el exceso se conserva aparte del total.
- **Tiradas:** la probabilidad no es una tirada independiente pura: el juego corrige la suerte para evitar rachas, y por debajo del 100 % no garantiza el crítico (C6). No afecta a la estadística.
- **Yasuo y Yone (`Derivado`, C9):** su pasiva duplica la probabilidad del resto de fuentes antes del tope, y cada 1 % por encima del 100 % da 0,5 de daño de ataque adicional. Con 60 % en objetos: 120 % → probabilidad 100 % y 20 × 0,5 = 10 de daño de ataque.
- **Flechas de los Yun Tal (C11, C12):** el objeto da 0 % de crítico (cero confirmado, `Oficial`) y su pasiva suma crítico permanente con cada ataque: 0,4 puntos porcentuales cuerpo a cuerpo y 0,2 a distancia (0,4 × 0,5), hasta 25 %. El tope se alcanza a los 63 ataques cuerpo a cuerpo (25 / 0,4 = 62,5) o 125 a distancia (`Calculado`). Ese crítico cuenta como cualquier otro aporte, así que Yasuo y Yone también lo duplican. **Escenario del motor:** acumulaciones al máximo (decisión del usuario del 2026-11-16), es decir, +25 % (`Derivado`, porque modela la descripción); no se calculan acumulaciones parciales. En ARAM y ARAM: Mayhem el cliente sube el valor cuerpo a cuerpo a 1,0; no se modela.
- **Sin confirmación oficial reciente:** C7 es una declaración de Riot de hacia 2020. Las notas de 26.1 a 26.21 consultadas solo cambian habilidades que escalan con la probabilidad, no la regla.

**Implementación (`Calculado`):** `src/lol_knowledge/stats/registry.py` declara `crit_chance` como fracción aditiva con `cap` 1. La hoja añade la base de Data Dragon como aporte `Oficial`; si `crit` o `critperlevel` dejaran de valer 0, la estadística se bloquea, porque su unidad no está documentada. El total respeta el tope y `bonus` conserva el exceso (el texto añade `(capped at 100%)`). Para Yasuo y Yone, la hoja añade un aporte igual a la suma del resto (la duplicación) y, si el total pasa del 100 %, un aporte de daño de ataque adicional con el exceso. `rotation` aplica la reducción del 5 % a su multiplicador crítico con una nota. Las Flechas de los Yun Tal entran por el escenario `max_stacks` del catálogo ([objetos](../objects/README.md)), con la nota `scenario: maximum stacks`. Pruebas: `tests/test_stats_crit_chance.py`, `tests/test_rotation.py`, `tests/test_stats_item_scenarios.py` y `tests/test_stats_real_items.py`.

## Fuera de alcance

- **Valor esperado del crítico:** la rotación no usa la probabilidad. Cada paso dice si critica (`attack:crit`) o no (`attack`).
- **Habilidades que critican** y otras reducciones específicas de campeón: dependen del kit de cada campeón. Las de Yasuo y Yone sí están modeladas, porque afectan a su hoja y a sus ataques básicos.
