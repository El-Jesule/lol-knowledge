# Incertidumbres y discrepancias — Zaahen 16.20

Regla: una incertidumbre no se convierte en un valor por conveniencia. Cada fila indica qué falta y cómo se cerraría.

## 1. Pasiva

| # | Cuestión | Evidencia actual | Estado | Cómo cerrarla |
|---|---|---|---|---|
| P1 | Base sobre la que se aplica el porcentaje por acumulación | `142→146` con una carga a nivel 18 favorece AD total; AD base daría 145; AD adicional daría 142 | Abierta; evidencia sólida para AD total, no prueba | Medir con un objeto de AD grande (p. ej. +100 AD) y comparar el incremento por carga; si el bono escala con el AD adicional, la base es total |
| P2 | `MaxStacksMultiplier=2.0`: ¿duplica el total o cada acumulación en el estado máximo? | El tooltip dice «duplica la cantidad de daño de ataque otorgado»; el total observable es el mismo | Abierta; no afecta al total a 12 acumulaciones | Medir el AD mostrado a 11 y 12 acumulaciones; la diferencia revela si el salto es 2× o solo el último stack |
| P3 | `PercentBonusAD=0.025` | No lo usa `PercentBonusADCalc`; el nivel 1 medido es 1.5 %, no 2.5 % | Probable valor legado/no usado | Confirmar con una búsqueda en el script Lua o en el consumidor de la estadística; no usarlo en el modelo |
| P4 | `RevivePercent=0.6` frente a `RevivePercentCalc` | El tooltip usa `@RevivePercentCalc@`; el cálculo da 30/45/60/75 % | `RevivePercent=0.6` probablemente legado | Medir la vida tras revivir a niveles 1/6/11/16 |
| P5 | `ReviveBonusPerLevel` y `ReviveBonusPerLevelAtAndAfter` sin `values` | El cálculo devuelve parciales 0.30/0.45/0.60/0.75 | Abierta; no se sustituye por cero | Localizar el script Lua o el consumidor que asigna esos `DataValue`; medir la vida tras revivir |
| P6 | `MaxStacks=12` y el comportamiento exacto de la barra | Dato del bin; el tooltip dice máximo de acumulaciones `@MaxStacks@` | Dato explícito; comportamiento de la barra no medido | Medir el número de acumulaciones en la práctica |

## 2. Habilidades

| # | Cuestión | Evidencia actual | Estado | Cómo cerrarla |
|---|---|---|---|---|
| Q1 | Cura de Q: ¿% vida máxima o % daño infligido? | Tooltip principal: «% de su vida máxima»; `BotData` usa `mStat=12` (vida); la lista de nivel usa la etiqueta `HealPercentOfDamageDealt` | Discrepancia de etiqueta; la fórmula principal se apoya en el texto y `mStat=12` | Medir la cura con vida máxima distinta y daño distinto; la etiqueta de la lista es ambigua |
| Q2 | `MonsterDamagePercent=1.0`: ¿+100 % adicional o 100 % total? | Tooltip oficial: «`@MonsterDamagePercent*100@%` de daño adicional a monstruos» | Semántica inferida; no medida | Medir el daño a un monstruo con y sin el multiplicador |
| Q3 | `MinionHealPercent=0.5`: ¿50 % de la cura contra súbditos y monstruos? | `DataValue`; no está en el árbol | Dato explícito; aplicación no medida | Medir la cura contra súbditos |
| Q4 | Tipo de daño de Q/W/R | Tooltips usan `<physicalDamage>` | Inferido del texto oficial | Confirmar con la reducción de daño/armadura en práctica |
| W1 | `cooldownTime` legado (16/16/15/14/13/12/11) frente a `Cooldown.values` (14/13.5/13/12.5/12) | Data Dragon y wiki coinciden con `Cooldown.values` | Resuelto a favor del vector efectivo; el legado se conserva | No requiere más medición; documentar la discrepancia |
| W2 | `MaximumPullDistance=225`, `PullSpeed=900` | `DataValue`; no están en el árbol | Dato explícito; efecto no modelado | Medir la distancia/velocidad del arrastre |
| E1 | Daño del borde: `BonusDamageCalc` físico + `PercentHPDamage` mágico | Tooltip: «`@BonusDamageCalc@` físico + `@PercentHPDamage*100@%` de vida máxima mágico en su lugar» | Fórmula separada; el árbol solo contiene la parte física | Medir ambos componentes por separado |
| E2 | `DamageBonusBase` (60/90/120/150/180 en rangos 1–5) frente a `BonusDamageCalc` | `BonusDamageCalc` = `BaseDamageCalc * 1.5`; coincide con `DamageBonusBase` + 0.75 DA adicional | Coherente; `DamageBonusBase` se usa en la lista de nivel | No requiere más medición; conservar ambos |
| E3 | `MonsterDamageCap=400`, `MonsterDamageBonus=50` | `DataValue`; el tooltip menciona +50 físico a monstruos | Dato explícito; aplicación no modelada | Medir el daño a monstruos |
| R1 | `ArmorPen` 10/20/30 % | Bin, tooltip y wiki coinciden | Verificado por tres fuentes | Confirmar en partida con armadura conocida |
| R2 | Curación 33 % del daño a campeones | `HealPercent=0.33`; tooltip | Dato explícito; no medida | Medir la cura con daño conocido |
| R3 | `DamageReduction=0.5` durante el lanzamiento | `DataValue`; tooltip | Dato explícito; no medida | Medir el daño recibido durante el lanzamiento |

## 3. Crecimiento de estadísticas

| # | Cuestión | Evidencia actual | Estado |
|---|---|---|---|
| S1 | AD base 63 frente a la hipótesis 64 de la solicitud | Bin y Data Dragon dicen 63; con +10.8 de runas la tabla se reproduce exactamente; con 64 y +10 también, porque los errores se compensan | Resuelto a favor de 63; la hipótesis 64 es una interpretación |
| S2 | Fórmula de crecimiento | `base + growth*(n-1)*(0.7025+0.0175*(n-1))`; validada en 1/2/10/18 | Modelo externo `inferred`; no está en el bin |
| S3 | Niveles > 18 | El modelo suma un crecimiento completo por nivel | `inferred`; no medido |
| S4 | Redondeo de pantalla | Se usa `round_half_up` para comparar | Modelo de comparación, no fórmula del juego |

## 4. Estructuras binarias

| # | Cuestión | Evidencia actual | Estado |
|---|---|---|---|
| B1 | `{150d1b92}` (36 apariciones en `BotData`) | Dos campos: `{e38f54f7}` U32 y `{717e686}` bool | Desconocido; se preserva |
| B2 | `{6c87d653}` | Struct sin propiedades | Desconocido; se preserva |
| B3 | `{0a3e0478}` | Escalar de `Cooldown`/`castRangeValues`; no está en la clase pública | Desconocido; se preserva |
| B4 | `mStat=13` | Aparece en `R.BotData`; sin muestra cruzada | Desconocido; `unresolved_stat` |
| B5 | `EffectValueCalculationPart` | Kha'Zix Q/W/E; requiere `SpellEffectAmount` | Tipado, no evaluable |
| B6 | `GameCalculationConditional` | Kha'Zix Q/W/E/R; requiere un buff/condición | Tipado, no evaluable |
| B7 | Tipo de daño en el árbol | No hay `DamageType` en los cálculos de Zaahen; el tipo aparece en el marcado de los tooltips | Fuera del árbol; modelar desde la localización o desde una tabla externa |

## 5. Localización

| # | Cuestión | Evidencia actual | Estado |
|---|---|---|---|
| L1 | Asociación ranura → cadena RST v5 | Resuelta con 38 bits; `item_1001_name → Botas` y las claves de Zaahen | Verificada en `Global.es_ES.wad.client` 16.20 |
| L2 | Asociación slot de hechizo → clave | `mClientData.mTooltipData.mLocKeys` da `keyName`, `keySummary`, `keyTooltip`, etc. | Verificada para Zaahen |
| L3 | Etiqueta `HealPercentOfDamageDealt` para la cura de Q | El texto principal dice «% vida máxima»; la etiqueta de la lista dice «% del daño curado» | Discrepancia documentada; no bloquea la extracción |
| L4 | Otra locale o build | El parser usa 38 bits; el handoff anterior documenta 39 bits en `cdragon-rst` 0.2.0 | Repetir la comprobación de bits si cambia la locale/build |

## 6. Licencias y redistribución

- El bin y el WAD originales no se versionan; solo fixtures recortados y valores derivados.
- La wiki es CC BY-SA 3.0 y se usa solo como contraste, nunca como fuente oficial.
- CommunityDragon no declara una licencia SPDX; su uso se apoya en la política de Riot para proyectos comunitarios.
- La publicación de valores derivados en `lol-knowledge/` ya fue aprobada en la fase anterior con la etiqueta `Derivado`, atribución y aviso de no afiliación. Esta fase no cambia esa decisión.

## 7. Prioridad de cierre

1. **P1** (base del porcentaje de la pasiva) y **P2** (multiplicador máximo): afectan a cualquier cálculo de AD.
2. **P4/P5** (revivir): afectan a la supervivencia, no al daño.
3. **Q1** (cura): afecta a la supervivencia.
4. **B1/B4** (`BotData`, `mStat=13`): no afectan a las fórmulas principales de Zaahen; documentar y dejar como no resueltos.
5. **B5/B6**: relevantes para generalizar a Kha'Zix y otros campeones con evoluciones/condiciones.
