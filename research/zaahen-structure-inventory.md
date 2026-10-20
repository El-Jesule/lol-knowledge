# Inventario de estructuras y cálculos de Zaahen (16.20)

- **Fuente:** `research/.cache/zaahen-16.20.bin.json`, SHA-256 `76e32de6…a533ed0b`.
- **Conteo global:** 45 objetos de nivel superior; 24 `GameCalculation`; 10 cálculos de nivel superior en `mSpellCalculations`; 5 habilidades (P, Q, W, E, R); 55 `SpellDataValue` (46 base + 9 en `DataValuesModeOverride/cherry`).

## 1. Cálculos de nivel superior

| Objeto | Cálculo | Tipo | Partes |
|---|---|---|---|
| `ZaahenPassive` | `ReviveCooldownCalc` | `GameCalculation` | `ByCharLevelBreakpointsCalculationPart` + 3 `Breakpoint` |
| `ZaahenPassive` | `RevivePercentCalc` | `GameCalculation` | `{4ce08984}` + 3 `{0333530c}` |
| `ZaahenPassive` | `PercentBonusADCalc` | `GameCalculation` | `{ee18a47b}` |
| `ZaahenQ` | `InitialDamage` | `GameCalculation` | `NamedDataValueCalculationPart` + `StatByNamedDataValueCalculationPart` |
| `ZaahenQ` | `SecondHitDamage` | `GameCalculation` | `NamedDataValueCalculationPart` + `StatByNamedDataValueCalculationPart` |
| `ZaahenW` | `InitialDamage` | `GameCalculation` | `NamedDataValueCalculationPart` + `StatByCoefficientCalculationPart` |
| `ZaahenW` | `SecondaryDamage` | `GameCalculation` | `NamedDataValueCalculationPart` + `StatByCoefficientCalculationPart` |
| `ZaahenE` | `BaseDamageCalc` | `GameCalculation` | `NamedDataValueCalculationPart` + `StatByCoefficientCalculationPart` |
| `ZaahenE` | `BonusDamageCalc` | `GameCalculationModified` | `NamedDataValueCalculationPart` (`SweetSpotDamageMod`) |
| `ZaahenR` | `DamageEndCalc` | `GameCalculation` | `NamedDataValueCalculationPart` + `StatByNamedDataValueCalculationPart` |

## 2. Las 24 `GameCalculation` del documento

Las 10 primeras son las de la tabla anterior. Las otras 14 están en `BotData` y en el hechizo hijo `ZaahenQ2`:

| # | Ruta |
|---:|---|
| 1 | `/Characters/Zaahen/Spells/ZaahenPassiveAbility/ZaahenPassive/mSpell/mSpellCalculations/ReviveCooldownCalc` |
| 2 | `/Characters/Zaahen/Spells/ZaahenPassiveAbility/ZaahenPassive/mSpell/mSpellCalculations/RevivePercentCalc` |
| 3 | `/Characters/Zaahen/Spells/ZaahenPassiveAbility/ZaahenPassive/mSpell/mSpellCalculations/PercentBonusADCalc` |
| 4 | `/Characters/Zaahen/Spells/ZaahenQAbility/ZaahenQ/mSpell/mSpellCalculations/InitialDamage` |
| 5 | `/Characters/Zaahen/Spells/ZaahenQAbility/ZaahenQ/mSpell/mSpellCalculations/SecondHitDamage` |
| 6 | `/Characters/Zaahen/Spells/ZaahenQAbility/ZaahenQ/BotData/{6d548702}` |
| 7 | `/Characters/Zaahen/Spells/ZaahenQAbility/ZaahenQ/BotData/{ec17e271}/0/EffectCalculation` |
| 8 | `/Characters/Zaahen/Spells/ZaahenQAbility/ZaahenQ2/BotData/{6d548702}` |
| 9 | `/Characters/Zaahen/Spells/ZaahenQAbility/ZaahenQ2/BotData/{ec17e271}/0/EffectCalculation` |
| 10 | `/Characters/Zaahen/Spells/ZaahenEAbility/ZaahenE/mSpell/mSpellCalculations/BaseDamageCalc` |
| 11 | `/Characters/Zaahen/Spells/ZaahenEAbility/ZaahenE/BotData/{6d548702}` |
| 12 | `/Characters/Zaahen/Spells/ZaahenEAbility/ZaahenE/BotData/{ec17e271}/0/EffectCalculation` |
| 13 | `/Characters/Zaahen/Spells/ZaahenRAbility/ZaahenR/mSpell/mSpellCalculations/DamageEndCalc` |
| 14 | `/Characters/Zaahen/Spells/ZaahenRAbility/ZaahenR/BotData/{6d548702}` |
| 15 | `/Characters/Zaahen/Spells/ZaahenRAbility/ZaahenR/BotData/{ec17e271}/0/EffectCalculation` |
| 16 | `/Characters/Zaahen/Spells/ZaahenRAbility/ZaahenR/BotData/{ec17e271}/1/EffectCalculation` |
| 17 | `/Characters/Zaahen/Spells/ZaahenRAbility/ZaahenR/BotData/{ec17e271}/2/EffectCalculation` |
| 18 | `/Characters/Zaahen/Spells/ZaahenWAbility/ZaahenW/mSpell/mSpellCalculations/InitialDamage` |
| 19 | `/Characters/Zaahen/Spells/ZaahenWAbility/ZaahenW/mSpell/mSpellCalculations/SecondaryDamage` |
| 20 | `/Characters/Zaahen/Spells/ZaahenWAbility/ZaahenW/BotData/{6d548702}` |
| 21 | `/Characters/Zaahen/Spells/ZaahenWAbility/ZaahenW/BotData/{ec17e271}/0/EffectCalculation` |
| 22 | `/Characters/Zaahen/Spells/ZaahenWAbility/ZaahenW/BotData/{ec17e271}/1/EffectCalculation` |
| 23 | `/Characters/Zaahen/Spells/ZaahenWAbility/ZaahenW/BotData/{ec17e271}/2/EffectCalculation` |
| 24 | `/Characters/Zaahen/Spells/ZaahenWAbility/ZaahenW/BotData/{ec17e271}/3/EffectCalculation` |

El test `research/tests/test_binmodel_provenance.py::test_all_24_game_calculations_have_a_typed_tree` comprueba que las 24 tengan un árbol o una entrada explícita con puntero JSON.

## 3. Tipos por frecuencia

| Tipo | Apariciones | Nota |
|---|---:|---|
| `SpellDataValue` | 55 | `DataValue` base + cherry |
| `{150d1b92}` | 36 | `BotData` sin semántica |
| `GameCalculation` | 24 | 10 superiores + 14 en `BotData`/hijo |
| `{0a0eddc9}` | 24 | `Cooldown`/`castRangeValues` |
| `ModifiableFloat` | 21 | estadísticas |
| `SpellObject` | 20 | objetos de hechizo |
| `TooltipInstanceListElement` | 15 | listas de nivel |
| `NamedDataValueCalculationPart` | 12 | hojas de `DataValue` |
| `{b09016f6}` | 10 | efectos de `BotData` |
| `NumberCalculationPart` | 7 | constantes |
| `{f3cbe7b2}` | 6 | referencias internas |
| `ProductOfSubPartsCalculationPart` | 5 | productos |
| `{630af303}` | 4 | `manaValues` |
| `StatByNamedDataValueCalculationPart` | 3 | ratios |
| `StatBySubPartCalculationPart` | 3 | ratios con subparte |
| `StatByCoefficientCalculationPart` | 3 | ratios constantes |
| `Breakpoint` | 3 | cooldown de revivir |
| `{0333530c}` | 3 | breakpoints con nombres |
| `ByCharLevelBreakpointsCalculationPart` | 1 | revivir |
| `{4ce08984}` | 1 | revivir % |
| `{ee18a47b}` | 1 | pasiva % |
| `{ba007871}` | 1 | referencia externa |
| `{9e9e2e5c}` | 1 | `DataValue` externo |
| `GameCalculationModified` | 1 | E borde |
| `{6c87d653}` | 1 | struct vacío |
| `SpellEffectAmount` | 1 | `{f9c2333e}` de E |

## 4. `DataValue` base por habilidad

| Habilidad | `DataValue` |
|---|---|
| Pasiva | `PercentBonusAD`, `FallOffDuration`, `RevivePercent`, `MaxStacks`, `ReviveDuration`, `NumberOfTicks`, `MaxStacksMultiplier`, `PBonusADMin`, `PBonusADMax`, `ReviveLevel1Value`, `ReviveBonusPerLevel`, `ReviveAdditionalBonusAtThisLevel`, `ReviveBonusPerLevelAtAndAfter` |
| Q | `Q1BaseDamage`, `KnockUpDuration`, `RecastWindow`, `TimeBetweenAttacks`, `HealPercent`, `MinionHealPercent`, `Q2BaseDamage`, `QBonusRange`, `QCoeff`, `MonsterDamagePercent` |
| W | `InitialBaseDamage`, `SecondaryBaseDamage`, `MaximumPullDistance`, `PullSpeed` |
| E | `Damage_Base`, `DashDistance`, `DashSpeed`, `MaximumRadius`, `MinimumRadius`, `PercentHPDamage`, `MonsterDamageCap`, `MonsterDamageBonus`, `SweetSpotDamageMod`, `DamageBonusBase` |
| R | `DashMaxDistance`, `DashMinDistance`, `EndDamage`, `DashSpeed`, `HealPercent`, `AoESize`, `DamageReduction`, `ArmorPen`, `BonusADDamageRatio` |

`DataValuesModeOverride/cherry` repite un subconjunto con valores distintos: pasiva (`PBonusADMin`, `PBonusADMax`, `ReviveLevel1Value`, `ReviveAdditionalBonusAtThisLevel`), Q (`QCoeff`, `HealPercent`), R (`EndDamage`, `BonusADDamageRatio`, `ArmorPen`). El extractor los separa por `mode` y no los mezcla con el modo base.

## 5. Estructuras no resueltas

| Estructura | Apariciones | Estado |
|---|---:|---|
| `{150d1b92}` | 36 | `unresolved`; `BotData` de IA |
| `BotsSpellData` | 5 | `unresolved`; raíz de `BotData` |
| `{6c87d653}` | 1 | `unresolved`; struct vacío |
| `{0a3e0478}` | 24 | campo escalar sin nombre; se preserva |
| `ReviveBonusPerLevel` | 1 | sin `values`; referencia no resuelta |
| `ReviveBonusPerLevelAtAndAfter` | 1 | sin `values`; referencia no resuelta |
| `mStat=13` | 1 | `unresolved_stat` en `R.BotData` |

## 6. Hechizos hijos

`ZaahenQAbility.mChildSpells` incluye `ZaahenQ2`, `ZaahenQAttack` y `ZaahenQ2Attack`. El extractor los guarda en `child_spells` con sus `DataValues`, cálculos y `BotData`. `ZaahenQ2` aporta dos de las 24 `GameCalculation`. Los hijos no se tratan como habilidades independientes del kit.
