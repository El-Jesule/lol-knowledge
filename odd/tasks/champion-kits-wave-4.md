# Kits de campeones: oleada 4 (`CH-01`) — fase 49 (cierre 173/173)

- **Objetivo:** completar el 100 % de la cobertura de `CH-01` con los **44 campeones finales curados y validados** sobre el cliente `16.23` (`16.23.8406595+branch.releases-16-23.content.release`), pasando de **129 a 173 campeones con `kit.json`** (100 % del plantel del snapshot `16.23.1`).
- **Rama:** `feat/champion-kits-wave-4`, creada desde `dev` (`8d49f4a`).

## Mejoras del compilador y extractor

- `research/binmodel/batch_kits.py`: se añade el prefijo `game_spell_<id>` al filtro de tooltips de campeón, resolviendo los tooltips principales y los hashes de cálculo de `Kayn` Q/W (`TotalDamage`, `DarkinFlatDamage`, `DarkinPercentDamage`).
- `research/binmodel/kitgen.py`: cuando la especificación declara explícitamente `max_rank`, prevalece sobre `level_count` del bin (necesario para `Aphelios` W, donde el bin tiene 5 entradas y Data Dragon declara `maxrank = 6`).

## Cobertura de la oleada 4 (44 nuevos → 173/173 = 100 %)

Todas las cifras y fórmulas proceden del cliente instalado `16.23` (`Derivado`, con `bin_sha256` registrado en cada `research/kits/<Id>.spec.json`) y los tipos de daño se contrastan con las etiquetas de los tooltips `es_ES`:

`Akshan`, `Ambessa`, `Aphelios`, `AurelionSol`, `Bard`, `Belveth`, `Corki`, `Elise`, `Gangplank`, `Gnar`, `Illaoi`, `Jayce`, `Jhin`, `Kaisa`, `Kalista`, `Karma`, `Katarina`, `Kayn`, `Khazix`, `Kindred`, `Locke`, `Lucian`, `Milio`, `Mordekaiser`, `Nidalee`, `Nilah`, `Olaf`, `Pyke`, `RekSai`, `Ryze`, `Senna`, `Smolder`, `Taric`, `Tryndamere`, `TwistedFate`, `Udyr`, `Urgot`, `Varus`, `Warwick`, `Yone`, `Yunara`, `Zac`, `Zeri`, `Zilean`.

Mecánicas destacadas incorporadas en esta oleada:

- **Coste de vida dinámico desde el bin:** `Olaf` E (`HealthCostCalc = 0,4 × TotalDamage`), aplicado en `rotation` respetando el suelo de `1` de vida (`MEC-01`).
- **Pasivas de acumulación y estadísticas permanentes:** `Ambessa` R (`armor_penetration_percent` `10/20/30 %`), `Mordekaiser` E (`magic_penetration_percent` `5..15 %`), `TwistedFate` E (`attack_speed_bonus` `15..55 %`) y `Senna` P (`--input mist_stacks`, `+0,75` DA por acumulación de Niebla).
- **Daño porcentual sobre vida máxima, actual y perdida del objetivo:** `Ambessa` Q (Q1 + Q2 con reactivación), `Belveth` R (explosión verdadera con 20 % vida faltante), `Elise` Q humana, `Gnar` W (Mini-Gnar), `Illaoi` W, `Jayce` E (martillo), `Jhin` P (4.º disparo), `Kaisa` P (5 cargas de Plasma), `Kayn` Q/R (Verdugo / Rhaast), `Kindred` W/E (0 marcas), `Mordekaiser` P (aura 1..5 % vida máxima/s), `RekSai` R (`15/20/25 %` vida máxima), `Senna` P (extracción de Niebla), `Udyr` Q/R (normal y Despertar), `Urgot` P, `Varus` W (1/3 cargas de Infección y activa W+Q), `Warwick` Q, `Yone` W (50 % físico + 50 % mágico) y `Zac` W.
- **Daño dual y verdadero:** `Yone` W y R (50 % físico + 50 % mágico exacto), `Belveth` R (pasiva y explosión), `Corki` P (`20 %` DA verdadero), `Gangplank` P y R (`Hija de la muerte`), `Olaf` E y `RekSai` E (furia máxima).
- **Tooltips indirectos resueltos:** `Gangplank` Q (`spell_gangplankqwrapper_tooltip_1`), `Karma` Q/W (`spell_karmaq_tooltip_0`, `spell_karmaw_tooltip_0`), `Kayn` Q/W/R (`game_spell_kayn_q_main_0`, `game_spell_kayn_w_maintext_0`, `spell_kayn_r_main_0`) y `RekSai` W (`spell_reksaiwburrowed_tooltip`).

## Verificación y límites

- `tests/test_champion_kits.py` exige paridad exacta (`173 == 173`) entre `lol-knowledge/champions/*/kit.json` y `data/current/champions/*.json`, evalúa todas las habilidades, todos los casos y una rotación `--timeline` sobre los **173 kits publicados** (pasando `--assume attackdamageperlevel=0` para `Senna` por `DAT-04`), y añade comprobaciones deterministas para la oleada 4 (`Ambessa`, `Mordekaiser`, `TwistedFate`, `Olaf`, `Senna`, `Yone`, `Kayn`, `Varus` y `Belveth`).
- Con esta oleada **se cierra `CH-01` al 100 %**. Quedan abiertos los huecos específicos de motor/extractor documentados en `not_modelled` y las reglas especiales de campeón (`CH-04`): nodos del bin sin traducir (`EffectValue` en `Kaisa` W y `Khazix` Q/W/E, `breakpoints` sin `level1_value` en `Mordekaiser` Q, maná adicional no resuelto en `Ryze` Q/W/E, `critical_strike_chance/damage` en `TwistedFate` W / `Zeri` W / `Yone` Q, letalidad en `Pyke` R), kits multiforma/multihechizo (`Aphelios`, `Elise`, `Jayce`, `Nidalee`, `Gnar`, `Kayn`, `Yunara`, `RekSai`), acumuladores infinitos en habilidades (`AurelionSol`, `Smolder`, `Kindred`, `Bard`, `Belveth`), habilidades que aplican efectos al impactar (`MEC-25`), escudos/curaciones/esteroides activos de habilidades y costes porcentuales de vida actual (`Zac`).
