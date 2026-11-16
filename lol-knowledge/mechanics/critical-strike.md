# Impacto crítico

- **Ámbito:** regla general del juego para los ataques básicos que asestan un impacto crítico, y para la probabilidad de crítico. La usa `python -m lol_knowledge rotation` en los pasos `attack:crit`.
- **Parche de referencia:** cliente 16.22 (2026-11-15). El daño crítico base es 200 % desde el parche 26.1.
- **Fecha de consulta:** 2026-11-15 (probabilidad de crítico: 2026-11-16)

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
| C9 | LoL Wiki, `Yasuo` y `Yone` (revisión 4091148 de Yone, del 28-10-2026), extractos del buscador consultados el 2026-11-16 | Su pasiva duplica la probabilidad de crítico total del resto de fuentes y convierte el exceso sobre el 100 % en daño de ataque adicional | Fuente comunitaria secundaria |

**Discrepancia registrada:** la página `Critical_strike` de la LoL Wiki aún dice 175 % (consultada el 2026-11-15). C1 y C2 dicen 200 %; se sigue a C1 y C2.

## Regla (`Derivado`, corroborada C1 + C2)

```text
daño bruto del crítico = daño del ataque × (multiplicador_base + Σ daño_crítico_adicional)
```

- `multiplicador_base` es el `critdamagemultiplier` del campeón (C2). Para 172 campeones es 2,0, el mismo valor que anuncian las notas oficiales (C1). Si el registro del campeón no tiene el campo, el paso crítico se rechaza.
- **Ashe** tiene 1,0 en el registro: su pasiva cambia cómo funcionan sus críticos. El motor no la modela; cualquier campeón cuyo multiplicador difiera de 2,0 obtiene `Pendiente de verificación` y una nota.
- `daño_crítico_adicional` es la estadística `crit_damage_bonus` (C5). Filo infinito suma 0,3: 2,0 + 0,3 = 2,3, el 230 % de C4.
- Con **varias fuentes** de daño crítico adicional, la suma no está verificada (solo hay un objeto en el catálogo). El motor las suma y marca el resultado `Pendiente de verificación`.
- El crítico se aplica **antes de la mitigación** (C3). Como la mitigación multiplica, el orden no cambia el resultado.
- El daño al impactar de los objetos **no** se multiplica por el crítico (C3: la mayoría de efectos al impactar no se ven afectados, salvo que se indique). Ningún objeto del catálogo indica lo contrario.

## Probabilidad de crítico (`Derivado`, C6 + C7; datos `Oficial`, C8)

```text
probabilidad = min(base + crecimiento(n) + Σ objetos_i, 100 %)
```

- **Base y crecimiento:** `stats.crit` y `stats.critperlevel` de Data Dragon (C8). Valen `0` en los 173 campeones: ningún campeón gana probabilidad de crítico al subir de nivel (C6).
- **Aportes:** objetos y efectos, como fracción (25 % = 0,25). Se **suman** (C6).
- **Tope:** 100 % (C6, C7). Algunos efectos aprovechan el exceso (C6: W de Senna; C9: Yasuo y Yone lo convierten en daño de ataque adicional), así que el exceso se conserva aparte del total.
- **Tiradas:** la probabilidad no es una tirada independiente pura: el juego corrige la suerte para evitar rachas, y por debajo del 100 % no garantiza el crítico (C6). No afecta a la estadística.
- **Yasuo y Yone (`Pendiente de verificación`):** su pasiva duplica la probabilidad del resto de fuentes (C9). No está modelada.
- **Sin confirmación oficial reciente:** C7 es una declaración de Riot de hacia 2020. Las notas de 26.1 a 26.21 consultadas solo cambian habilidades que escalan con la probabilidad, no la regla.

**Implementación (`Calculado`):** `src/lol_knowledge/stats/registry.py` declara `crit_chance` como fracción aditiva con `cap` 1. La hoja añade la base de Data Dragon como aporte `Oficial`; si `crit` o `critperlevel` dejaran de valer 0, la estadística se bloquea, porque su unidad no está documentada. El total respeta el tope y `bonus` conserva el exceso (el texto añade `(capped at 1)`). Yasuo y Yone quedan `Pendiente de verificación` con una nota. Pruebas: `tests/test_stats_crit_chance.py`.

## Fuera de alcance

- **Valor esperado del crítico:** la rotación no usa la probabilidad. Cada paso dice si critica (`attack:crit`) o no (`attack`).
- **Habilidades que critican** y reducciones específicas de campeón: dependen del kit de cada campeón.
