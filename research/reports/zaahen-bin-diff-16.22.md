# Zaahen — cambios del bin entre 16.20 y 16.22

- **Fecha de consulta:** 2026-11-15
- **Fuente nueva:** cliente local, `Champions/Zaahen.wad.client`, entrada `data/characters/zaahen/zaahen.bin`
- **Build del cliente:** `16.22.8348910+branch.releases-16-22.content.release` (de `Game/content-metadata.json`)
- **Bin 16.22:** 28 083 B, SHA-256 `44e0d68c38fc1d715926a8d721d48321acc1b1ff08d844c9955e0fef6b70db75`
- **Referencia:** `research/.cache/zaahen-16.20.bin.json` (CommunityDragon 16.20, SHA-256 `76e32de67667917769cc6022a818b13e5024ea521a23c70436dc48eea533ed0b`); el bin 16.20 registrado medía 28 038 B con SHA-256 `7f1e9369…844078d1`
- **Método:** `python -m binmodel.bindiff`, lector estricto, floats comparados en float32
- **Etiqueta:** `Derivado`. No es una API oficial de Riot; Data Dragon 16.22 no se ha consultado.

## Resultado

Las 44 entradas del bin casan con la referencia. Hay 14 diferencias, que corresponden a tres cambios:

| # | Campo | 16.20 | 16.22 | Alcance |
|---|---|---|---|---|
| 1 | `ZaahenQ.mSpell.Cooldown.values` | `[10, 10, 9, 8, 7, 6, 5]` | `[8, 8, 7.5, 7, 6.5, 6, 6]` | Enfriamiento de la Q |
| 2 | `ZaahenPassive.mSpell.DataValuesModeOverride{cherry}` → `PBonusADMax` | `0.02` | `0.01` | Solo el override del modo `cherry` (Arena) |
| 3 | `ZaahenR.mSpell.{1632f6fc}` (campo nuevo) | — | Lista con un objeto `{d45ebe4a}` que enlaza a `ZaahenRSpellPassive`, más un `bool` (`false`) y un `u8` (`0`) | Semántica desconocida |

Sin cambios, comprobados valor a valor: el resto de `DataValues` de las cinco habilidades (incluidos `Q1BaseDamage`, `MonsterDamagePercent`, `PBonusADMin`/`PBonusADMax` base y los valores de la R), los cálculos y `CharacterRecords/Root` (incluido `damagePerLevelModifiable`).

## Consecuencias

- Las discrepancias E.1, E.2, E.4 y E.5 de [`../zaahen-research-handoff.md`](../zaahen-research-handoff.md) no cambian con 16.22.
- El enfriamiento de la Q publicado en `lol-knowledge/` corresponde a 16.20.1 y **no** vale para 16.22. No se ha actualizado la base de conocimiento: el snapshot oficial sigue en 16.20.1 y el validador lo cruza contra él.
- **Pendiente de verificación:** qué índices del vector `Cooldown.values` corresponden a los rangos 1–5, y qué hace el campo `{1632f6fc}` de la R.
