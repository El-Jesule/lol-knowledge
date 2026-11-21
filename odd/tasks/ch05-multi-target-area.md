# Varios objetivos y daño en área en habilidades y rotaciones (`CH-05`) — fase 52

- **Fecha:** 2026-11-21
- **Rama:** `feat/ch05-multi-target-area` (desde `dev`)
- **Parche de referencia:** Data Dragon `16.23.1`, cliente `16.23.8406595+branch.releases-16-23.content.release` y `wiki.leagueoflegends.com` (consultada el 2026-11-21)
- **Etiqueta de las reglas y datos compilados:** `Derivado` (cálculos y `DataValues` del bin del cliente corroborados con `wiki.leagueoflegends.com`) y `Calculado` (evaluación en `ability` y `rotation`)

## 1. Objetivo

Resolver `CH-05` ([`odd/roadmap.md`](../roadmap.md)): permitir que `ability` y `rotation` evalúen habilidades de área y multiobjetivo frente a `N` objetivos (`--target-count <N>`, o por paso `SLOT.case@<N>`), respetando los topes de objetivos por lanzamiento (`max_targets`, como los 3 rayos de la R de Ahri en `RMaxTargetsPerCast = 3`), los factores de daño reducido en objetivos secundarios (`secondary_damage_ratio`, como el `80 %` de la R de Jinx en `AoEDamageMult = 0.8` o el `50 %` del bumerán de Mini-Gnar en `MiniSubsequentMult = 0.5`), el seguimiento de vida/escudo del objetivo principal y la reducción del omnivampirismo al `33 %` en habilidades de área contra súbditos y monstruos.

## 2. Modelo declarativo en `kit.json` (`lol-champion-kit/1`) y `kitgen.py`

Cada caso (`CaseSpec` en [`src/lol_knowledge/kit/model.py`](../../src/lol_knowledge/kit/model.py)) admite tres atributos opcionales (declarables en `spec.json` a nivel de habilidad como valor por defecto o a nivel de caso en [`research/binmodel/kitgen.py`](../../research/binmodel/kitgen.py)):

| Atributo | Tipo | Significado (`Derivado`) |
|---|---|---|
| `aoe` | `bool \| None` | `true` si la habilidad es de área (`spelleffects = aoe / area`); `false` si es de objetivo único (`single target / spell`); `None` si el kit aún no lo declara |
| `max_targets` | `int >= 1 \| None` | Número máximo de objetivos distintos que pueden recibir el caso en un lanzamiento (`1` = objetivo único o aislado; `M >= 2` = multiobjetivo acotado como `RMaxTargetsPerCast = 3`; `None` = sin tope cuando `aoe: true`) |
| `secondary_damage_ratio` | `Fraction` en `(0, 1]` | Multiplicador del daño sobre cada uno de los `targets_hit - 1` objetivos secundarios respecto al objetivo principal (por defecto `1`; no combinable con `max_targets: 1`) |

### Regla de resolución (`CaseSpec.resolve_targets(target_count)`)

1. Si `target_count == 1`: `targets_hit = 1`, `unverified = False`.
2. Si `target_count > 1`:
   - Si `max_targets` está definido: `targets_hit = min(target_count, max_targets)`.
   - Si `max_targets` es `None` y `aoe is True`: `targets_hit = target_count`.
   - Si `max_targets` es `None` y `aoe is False`: `targets_hit = 1`.
   - Si `max_targets` es `None` y `aoe is None`: se evalúa sobre `1` objetivo (`targets_hit = 1`) y el resultado se debilita a `Pendiente de verificación` con una nota explícita.

## 3. Evaluación en `ability` y `rotation` (`Calculado`)

- **Desglose primario vs secundario (`Part`, `StepOutcome`, `RotationOutcome`, `CaseOutcome`):**
  - `primary_damage` / `primary_total`: daño posmitigación y posmodificadores sobre el objetivo principal (`100 %`).
  - `secondary_damage` / `secondary_total`: `primary_damage × (targets_hit - 1) × secondary_damage_ratio`.
  - `damage` / `total`: `primary_damage + secondary_damage` (daño total agregado sobre los `targets_hit` objetivos).
- **Seguimiento de vida, escudo, ejecución y `survive`:**
  - La barra de vida y el escudo seguidos paso a paso en `rotation` pertenecen al **objetivo principal**: cada paso absorbe en escudo y descuenta de la vida únicamente `primary_total` (`health_damage = primary_total - shield_absorbed`). Las ejecuciones (`execute`) y la conversión a impactos entrantes de `survive` (`hits_from_rotation`) leen igualmente `primary_damage`.
- **Curación por omnivampirismo:**
  - El atacante se cura a partir del daño total infligido por la parte a todos los objetivos alcanzados (`part.damage`).
  - Contra súbditos y monstruos (`minion`, `monster`), un caso con `aoe: true` aplica la reducción oficial del parche 26.1 al `33 %` (`omnivamp / 3`, `Derivado`) y un caso con `aoe: false` cura al `100 %` (`Derivado`); si `aoe` es `None`, mantiene el `100 %` con etiqueta `Pendiente de verificación`.
- **CLI y sintaxis de pasos:**
  - `--target-count <N>` (entero `>= 1`, por defecto `1`) en `python -m lol_knowledge ability` y `python -m lol_knowledge rotation`.
  - Sufijo opcional `@<N>` por paso de habilidad en `rotation` (por ejemplo, `R.dash@3, Q.both@2, E.hit`).

## 4. Kits curados con metadatos multiobjetivo y de área (16 campeones)

| Campeón | Casos / habilidades curadas | Datos del bin (`16.23`) y fuente |
|---|---|---|
| `Ahri` | `Q` (`aoe: true`), `W.one` (`aoe: false, max_targets: 3`), `W.all` (`aoe: false, max_targets: 1`), `E` (`aoe: false, max_targets: 1`), `R.dash`/`R.recast` (`aoe: true, max_targets: 3`) | `RMaxTargetsPerCast = 3.0`, `Template:Data_Ahri/*` revs `4074380`, `4074423`, `4074445`, `4074438` |
| `Sona` | `Q.bolt` (`aoe: true, max_targets: 2`), `Q.aura_on_hit`/`staccato` (`1`), `R` (`aoe: true`) | `SonaQ.DataValues.EnemiesToHit = 2.0` |
| `Katarina` | `P` (`aoe: true`), `Q` (`aoe: true, max_targets: 3`), `E` (`1`), `R` (`aoe: true, max_targets: 3`) | `KatarinaQ.DataValues.MaxBounces = 2.0` (1 + 2), `KatarinaR` (3 campeones) |
| `Kindred` | `Q` (`aoe: true, max_targets: 3`), `W` (`1`), `E` (`1`) | `KindredQ` (3 flechas) |
| `MonkeyKing` | `Q` (`1`), `E` (`aoe: true, max_targets: 3`), `R` (`aoe: true`) | `MonkeyKingNimbus.DataValues.ExtraTargets = 2.0` (1 + 2) |
| `Lux` | `P` (`1`), `Q` (`aoe: true, max_targets: 2`), `E` (`aoe: true`), `R` (`aoe: true`) | `LuxLightBinding.Effect3Amount = 2.0` |
| `Bard` | `P` (`aoe: true`), `Q` (`aoe: true, max_targets: 2`) | `BardQ` (hasta 2 enemigos) |
| `Karthus` | `Q.multi` (`aoe: true`), `Q.isolated` (`aoe: true, max_targets: 1`), `E` (`aoe: true`), `R` (`aoe: true, max_targets: 5`) | `KarthusFallenOne` (5 campeones) |
| `Caitlyn` | `Q.first` (`aoe: true, secondary_damage_ratio: 0.6`), `Q.passthrough` (`max_targets: 1`), `W`/`E`/`R` (`1`) | `CaitlynQ.DataValues.SecondaryMult = 0.6` |
| `Jinx` | `Q` (`aoe: true`), `W` (`1`), `E` (`aoe: true`), `R` (`aoe: true, secondary_damage_ratio: 0.8`) | `JinxR.DataValues.AoEDamageMult = 0.8` |
| `Gnar` | `Q.mini` (`aoe: true, secondary_damage_ratio: 0.5`), `Q.mega` (`aoe: true`), `W.mini_proc` (`1`), `W.mega`/`E`/`R` (`aoe: true`) | `GnarQ.DataValues.MiniSubsequentMult = 0.5` |
| `Ambessa` | `Q` (`aoe: true, secondary_damage_ratio: 0.5`), `W` (`aoe: true`), `E` (`aoe: true`), `R` (`1`) | `AmbessaQ.DataValues.Damage_1_Min_Ratio = 0.5` |
| `Qiyana` | `Q` (`aoe: true, secondary_damage_ratio: 0.75`), `W`/`E` (`1`), `R` (`aoe: true`) | `QiyanaQ.DataValues.FalloffMod = 0.75` |
| `Pantheon` | `Q.tap`/`empowered_bonus` (`aoe: true`), `Q.hold`/`execute` (`aoe: true, secondary_damage_ratio: 0.5`), `W` (`1`), `E`/`R` (`aoe: true`) | `PantheonQ.DataValues.DamageFalloff = 0.5` |
| `Ashe` | `Q` (`1`), `W` (`aoe: true`), `R` (`aoe: true, secondary_damage_ratio: 0.5`) | `EnchantedCrystalArrow` (50 % en área secundaria) |
| `Zoe` | `P` (`1`), `Q` (`aoe: true, secondary_damage_ratio: 0.8`), `W`/`E` (`1`) | `ZoeQ` (80 % a objetivos secundarios) |

## 5. Limitaciones y pendientes

- Los objetivos secundarios comparten las resistencias y estadísticas iniciales del objetivo principal (grupo homogéneo) y no llevan seguimiento independiente de su barra de vida ni de quemaduras/efectos de objeto por objetivo secundario.
- Las caídas progresivas objetivo a objetivo (por ejemplo, `-15 %` por unidad atravesada hasta un suelo en `Sivir Q`, `Varus Q`, `Ezreal R` o `Draven R`) siguen declaradas en `not_modelled` cuando el factor cambia según el índice de cada objetivo secundario.
