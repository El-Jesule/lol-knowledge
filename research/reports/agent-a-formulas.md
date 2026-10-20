# Agente A — datos y fórmulas de Zaahen

- **Parche:** 16.20.1 (Data Dragon) / contenido 16.20 (CommunityDragon).
- **Artefacto:** `research/.cache/zaahen-16.20.bin.json`, SHA-256 `76e32de6…a533ed0b`.
- **Método:** recorrido genérico de `mSpellCalculations`, `DataValues` y `mTooltipData` con `research/binmodel/`. No hay lista manual de parámetros de Zaahen.
- **Validación:** tabla de AD del usuario y porcentajes de la pasiva; contraste con Data Dragon y la transcripción de la wiki.

## 1. Estadísticas del campeón

`Characters/Zaahen/CharacterRecords/Root`:

| Estadística | Base | Por nivel | Fuente |
|---|---:|---:|---|
| Daño de ataque | `63.0` | `4.0` | `baseDamageModifiable`, `damagePerLevelModifiable` |
| Vida | `640.0` | `114.0` | `baseHPModifiable`, `hpPerLevelModifiable` |
| Armadura | `36.0` | `5.0` | `baseArmorModifiable`, `armorPerLevelModifiable` |
| Resistencia mágica | `32.0` | `2.05` | `baseMR`, `mrPerLevel` |
| Velocidad de movimiento | `345.0` | — | `baseMoveSpeedModifiable` |
| Rango de ataque | `175.0` | — | `attackRangeModifiable` |
| Velocidad de ataque | `0.625` | `2.5 %` | `attackSpeedModifiable`, `attackSpeedPerLevelModifiable` |

### 1.1 Crecimiento de AD

El bin solo almacena base y crecimiento. La curva aplicada por el motor es un modelo externo:

```
nivel <= 18: 63 + 4*(n-1)*(0.7025 + 0.0175*(n-1))
nivel > 18:  63 + 4*17 + 4*(n-18)
```

Con dos runas adaptativas (`+5.4` AD cada una, `+10.8` total):

| Nivel | AD calculado | AD mostrado | Medición |
|---:|---:|---:|---:|
| 1 | 73.80 | 74 | 74 |
| 2 | 76.68 | 77 | 77 |
| 10 | 104.76 | 105 | 105 |
| 18 | 141.80 | 142 | 142 |

**Corrección importante:** la hipótesis «base 64 + 10 de runas» también reproduce la tabla porque los dos errores se compensan. La evidencia decisiva es el bin y Data Dragon, que dicen `63`, y el valor conocido de las runas adaptativas (`+5.4` AD cada una). El valor `64` de la solicitud es una interpretación, no un dato del bin. La columna «AD descontando las runas» de la solicitud resta `10`, no `10.8`.

`champion_growth` está marcado `inferred`: la fórmula no está en el bin, se valida contra las cuatro mediciones.

## 2. Pasiva — Florescencia de la guerra

Ruta: `Characters/Zaahen/Spells/ZaahenPassiveAbility/ZaahenPassive`.

### 2.1 AD adicional por acumulación

| Campo | Valor | Evidencia |
|---|---|---|
| `PBonusADMin` | `0.015` (`0.014999999664723873` float32) | `DataValues` |
| `PBonusADMax` | `0.028` (`0.02800000086426735` float32) | `DataValues` |
| Cálculo | `PercentBonusADCalc` | `mSpellCalculations` |
| Nodo | `{ee18a47b}` con `StartDataValue=PBonusADMin`, `EndDataValue=PBonusADMax` | árbol |
| Precisión | `mPrecision = 1` | `GameCalculation` |
| Presentación | `mDisplayAsPercent = true` | `GameCalculation` |

Fórmula candidata, validada contra las ocho mediciones:

```
percent(level) = 0.015 + (0.028 - 0.015) * (level - 1) / 17
```

| Nivel | Calculado | Mostrado | Medición |
|---:|---:|---:|---:|
| 1 | 1.500 % | 1.5 % | 1.5 % |
| 5 | 1.806 % | 1.8 % | 1.8 % |
| 6 | 1.882 % | 1.9 % | 1.9 % |
| 10 | 2.188 % | 2.2 % | 2.2 % |
| 11 | 2.265 % | 2.3 % | 2.3 % |
| 15 | 2.571 % | 2.6 % | 2.6 % |
| 16 | 2.647 % | 2.6 % | 2.6 % |
| 18 | 2.800 % | 2.8 % | 2.8 % |

`round_half_up` se usa solo para comparar con la pantalla; no se afirma que sea el redondeo interno del juego. La interpolación es `inferred` (el árbol guarda la operación, no su implementación interna).

**Valor legado:** `PercentBonusAD = 0.025` aparece en `DataValues` pero no lo usa `PercentBonusADCalc`. Si fuera el valor efectivo, el nivel 1 mostraría 2.5 %, no 1.5 %. Se conserva como dato no usado.

### 2.2 Acumulaciones y máximo

| Campo | Valor |
|---|---|
| `MaxStacks` | `12` |
| `MaxStacksMultiplier` | `2.0` |
| `ReviveDuration` | `4` s |
| `RevivePercent` | `0.6` (posible valor legado; el tooltip usa `RevivePercentCalc`) |

El tooltip oficial dice: «Con el máximo de Determinación, Zaahen duplica la cantidad de daño de ataque otorgado». `MaxStacksMultiplier=2.0` es coherente con esa frase. No se puede distinguir desde el bin si el multiplicador se aplica al total o a cada acumulación en el estado máximo; el total observable es el mismo.

### 2.3 Base de aplicación del porcentaje

El bin no dice sobre qué estadística se aplica el porcentaje. Hipótesis y evidencia:

| Base | Bonificación con una carga a nivel 18 | Total mostrado | ¿Coincide con 142→146? |
|---|---:|---:|---|
| AD base (`131`) | `+3.668` | 145 | no |
| AD total (`141.8`) | `+3.970` | 146 | sí |
| AD adicional (`10.8`) | `+0.302` | 142 | no |

La observación aislada favorece **AD total**, pero no es prueba: el redondeo de pantalla y la base exacta pueden cambiar el resultado. Se marca como cuestión abierta. El experimento propuesto está en `research/zaahen-uncertainties.md`.

### 2.4 Revivir

`ReviveCooldownCalc` usa `ByCharLevelBreakpointsCalculationPart` con `mLevel1Value=300` y breakpoints de `-60` en 6, 11 y 16:

| Nivel | Enfriamiento |
|---:|---:|
| 1–5 | 300 s |
| 6–10 | 240 s |
| 11–15 | 180 s |
| 16–18 | 120 s |

`RevivePercentCalc` usa `{4ce08984}` con:

- `ReviveLevel1Value = 0.3`
- `ReviveAdditionalBonusAtThisLevel = 0.15` en 6, 11 y 16
- `ReviveBonusPerLevel` y `ReviveBonusPerLevelAtAndAfter` **sin `values`**

El cálculo devuelve `complete=False` y valores parciales `0.30 / 0.45 / 0.60 / 0.75` en 1/6/11/16. Coincide con la KB, pero el extractor no sustituye los valores ausentes por cero. El `RevivePercent=0.6` constante es un dato separado que no usa este cálculo.

## 3. Q — La guja de los Oscuros

Ruta: `Characters/Zaahen/Spells/ZaahenQAbility/ZaahenQ`. Rangos: 5.

| Cálculo | Fórmula | Evidencia |
|---|---|---|
| `InitialDamage` | `Q1BaseDamage[rank] + QCoeff[rank] * bonusAD` | `NamedDataValueCalculationPart` + `StatByNamedDataValueCalculationPart` (`mStat=2`, `mStatFormula=2`) |
| `SecondHitDamage` | `Q2BaseDamage[rank] + QCoeff[rank] * bonusAD` | igual |

| Parámetro | Rangos 1–5 |
|---|---|
| `Q1BaseDamage` | 15 / 30 / 45 / 60 / 75 |
| `Q2BaseDamage` | 30 / 60 / 90 / 120 / 150 |
| `QCoeff` | 0.20 / 0.25 / 0.30 / 0.35 / 0.40 |
| `HealPercent` | 5 / 6 / 7 / 8 / 9 % vida máxima |
| `KnockUpDuration` | 0.75 s |
| `RecastWindow` | 4 s |
| `QBonusRange` | 25 |
| `MonsterDamagePercent` | 1.0 |
| Enfriamiento | 10 / 9 / 8 / 7 / 6 s |
| Maná | 25 |

**Cura:** el tooltip oficial dice «restaura un `@HealPercent*100@%` de su vida máxima». `MinionHealPercent=0.5` reduce la cura al 50 % contra súbditos y monstruos. El `BotData` contiene un cálculo `StatBySubPart` con `mStat=12` y `HealPercent*100`; se conserva como estructura auxiliar, no se usa como fórmula principal.

**Monstruos:** `MonsterDamagePercent=1.0` es daño **adicional** según el tooltip oficial del cliente (`@MonsterDamagePercent*100@% de daño adicional a monstruos`), es decir, 200 % del daño base. Es una interpretación semántica, no una medición.

**Etiqueta del tooltip:** la lista de nivel usa `Spell_ListType_HealPercentOfDamageDealt` para `HealPercent`, pero el texto principal dice «% de su vida máxima» y el `BotData` usa `mStat=12`. Hay una discrepancia de etiqueta que se documenta; la fórmula principal se apoya en el texto y en `mStat=12`.

## 4. W — Hendidura del retorno

Ruta: `Characters/Zaahen/Spells/ZaahenWAbility/ZaahenW`. Rangos: 5.

| Cálculo | Fórmula |
|---|---|
| `InitialDamage` | `InitialBaseDamage[rank] + 0.5 * bonusAD` |
| `SecondaryDamage` | `SecondaryBaseDamage[rank] + 0.3 * bonusAD` |

| Parámetro | Rangos 1–5 |
|---|---|
| `InitialBaseDamage` | 40 / 60 / 80 / 100 / 120 |
| `SecondaryBaseDamage` | 30 / 50 / 70 / 90 / 110 |
| Enfriamiento efectivo | 14 / 13.5 / 13 / 12.5 / 12 s |
| Enfriamiento legado | 16 / 16 / 15 / 14 / 13 / 12 / 11 s |
| Maná | 50 |
| Rango | 850 |

El enfriamiento efectivo es `Cooldown.values`; coincide con Data Dragon y la wiki. `cooldownTime` es un espejo obsoleto y se conserva como diagnóstico.

## 5. E — Impulso áureo

Ruta: `Characters/Zaahen/Spells/ZaahenEAbility/ZaahenE`. Rangos: 5.

| Cálculo | Fórmula |
|---|---|
| `BaseDamageCalc` | `Damage_Base[rank] + 0.5 * bonusAD` |
| `BonusDamageCalc` | `BaseDamageCalc * SweetSpotDamageMod` (`1.5`) |

| Parámetro | Rangos 1–5 |
|---|---|
| `Damage_Base` | 40 / 60 / 80 / 100 / 120 |
| `PercentHPDamage` | 4 / 4.5 / 5 / 5.5 / 6 % vida máxima (mágico, borde) |
| `MonsterDamageCap` | 400 |
| `MonsterDamageBonus` | 50 |
| Enfriamiento | 10 / 9.5 / 9 / 8.5 / 8 s |
| Maná | 40 |
| Dash | 350 unidades a 900 de velocidad |
| Radio | 200–375 |

El daño del borde es `BonusDamageCalc` físico **más** `PercentHPDamage * maxHP` mágico, según el tooltip oficial. El árbol solo contiene la parte física; la parte mágica es un `DataValue` separado que no aparece en `mSpellCalculations`.

## 6. R — Redención funesta

Ruta: `Characters/Zaahen/Spells/ZaahenRAbility/ZaahenR`. Rangos: 3.

| Cálculo | Fórmula |
|---|---|
| `DamageEndCalc` | `EndDamage[rank] + BonusADDamageRatio * bonusAD` |

| Parámetro | Rangos 1–3 |
|---|---|
| `EndDamage` | 250 / 400 / 550 |
| `BonusADDamageRatio` | 2.0 |
| `ArmorPen` | 10 / 20 / 30 % |
| `DamageReduction` | 0.5 (50 %) |
| `HealPercent` | 0.33 (33 % del daño a campeones) |
| Enfriamiento | 110 / 95 / 80 s |
| Maná | 100 |
| Rango | 600 |
| Dash | 10–600 a 2800 de velocidad |
| AoE | 550 |

La penetración de armadura y la reducción de daño son datos del hechizo, no partes del árbol de daño. La curación es posterior al daño y no se modela como nodo.

## 7. Evaluación de control

Con nivel 18, rango 1 y `100` de DA adicional:

| Cálculo | Resultado |
|---|---:|
| `q.InitialDamage` | 35 |
| `q.SecondHitDamage` | 50 |
| `w.InitialDamage` | 90 |
| `w.SecondaryDamage` | 60 |
| `e.BaseDamageCalc` | 90 |
| `e.BonusDamageCalc` | 135 |
| `r.DamageEndCalc` | 450 |

Son valores deterministas del árbol, no mediciones en partida. Los ratios se aplican a DA adicional (`mStat=2`, `mStatFormula=2`).

## 8. Cobertura y límites

- **Cubierto:** las 10 cálculos de nivel superior de Zaahen, las 24 `GameCalculation` del documento (incluidas las de `BotData` y los hechizos hijos), los `DataValue` base y `cherry`, los enfriamientos, el maná, el rango y las estadísticas.
- **No evaluable:** `RevivePercentCalc` completo (faltan dos `DataValue`), `mStat=13` en `R.BotData`, los `{150d1b92}` de `BotData`, y la aplicación de la pasiva (está fuera del árbol, probablemente en Lua).
- **No modelado:** tipo de daño dentro del árbol (solo aparece en el marcado de los tooltips), condiciones de impacto, acumulaciones y efectos secundarios.
- **Contraste:** los valores de Q/W/E/R coinciden con la transcripción de la wiki y con la KB; la wiki es una fuente de contraste, no oficial.
