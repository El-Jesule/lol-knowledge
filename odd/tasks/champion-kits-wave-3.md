# Kits de campeones: oleada 3 (`CH-01`) — fase 48

- **Objetivo:** ampliar la cobertura de `CH-01` con **44 nuevos campeones curados y validados** sobre el cliente `16.23` (`16.23.8406595+branch.releases-16-23.content.release`), pasando de **85 a 129 campeones con `kit.json`** (74,6 % de los 173 del snapshot `16.23.1`, dejando exactamente 44 campeones para la oleada 4 final).
- **Rama:** `feat/champion-kits-wave-3`, creada desde `dev` (`961c84c`).

## Cobertura de la oleada 3 (44 nuevos → 129 totales)

Todas las cifras y fórmulas proceden del cliente instalado `16.23` (`Derivado`, con `bin_sha256` registrado en cada `research/kits/<Id>.spec.json`) y los tipos de daño se contrastan con las etiquetas de los tooltips `es_ES`:

- **Top (11):** `Aatrox`, `Fiora`, `DrMundo`, `Kled`, `KSante`, `Yorick`, `Rumble`, `Chogath`, `Nasus`, `Shen`, `Singed`.
- **Jungla (10):** `Briar`, `Shaco`, `Hecarim`, `Shyvana`, `Ivern`, `Trundle`, `Viego`, `Graves`, `MasterYi`, `JarvanIV`.
- **Mid (10):** `Mel`, `Hwei`, `Zoe`, `Naafiri`, `Azir`, `Heimerdinger`, `Zed`, `Yasuo`, `Malzahar`, `Taliyah`.
- **Tirador (5):** `MissFortune`, `Draven`, `Ashe`, `Sivir`, `Twitch`.
- **Apoyo (8):** `Braum`, `Soraka`, `Lulu`, `Sona`, `Janna`, `Renata`, `Thresh`, `Yuumi`.

Mecánicas destacadas incorporadas en esta oleada:

- **Costes de vida reales desde el bin:** `DrMundo` Q (`HealthCost = 50..90` vida) y E (`FlatHealthCost = 10..70` vida), aplicados en `rotation` respetando el suelo de `1` de vida (`MEC-01`).
- **Pasivas de acumulación y estadísticas permanentes en `abilities.P.passive_effects` y `passive_stats`:** `Nasus` P (`life_steal` `10/15/20 %` en niveles 1/7/13), `JarvanIV` E (`attack_speed_bonus` `20..30 %` pasivo en la hoja), `Thresh` P (`--input souls`, `+1` armadura y `+1` PH por alma) y `Shyvana` P (`--input passive_stacks`, `+0,3` armadura y `+0,3` RM por carga).
- **Daño porcentual sobre vida máxima, actual y perdida del objetivo:** `Aatrox` P, `Fiora` P (punto vital y 4 puntos vitales de R en daño verdadero), `DrMundo` Q (`20..30 %` vida actual), `Kled` W/R, `KSante` P/W, `Yorick` E/R, `Rumble` P/Q, `Chogath` E (base sin cargas de Festín), `Nasus` R, `Shen` Q (base y potenciado), `Singed` E, `Briar` W (vida faltante), `Shyvana` Q/E, `Trundle` R, `Viego` Q (vida actual) y R (vida faltante), `JarvanIV` P (vida actual), `Hwei` Q (QQ), `Malzahar` R (zona) y `Renata` P.
- **Daño verdadero y mixto:** `Fiora` P, `Chogath` R (campeones y monstruos), `MasterYi` E, `Twitch` P (verdadero) y E (físico + mágico en `per_stack` y `max_stacks`), `Shyvana` Q (físico + `%` vida máxima mágico) y `Zoe` E (despertar verdadero).
- **Reactivaciones con ventana del bin:** `Kled` E, `KSante` Q, `Shyvana` Q y `Naafiri` Q/R.

## Verificación y límites

- `tests/test_champion_kits.py` evalúa todas las habilidades, todos los casos y una rotación `--timeline` sobre los **129 kits publicados**, además de comprobaciones deterministas específicas de la oleada 3 (`Fiora` P daño verdadero `%` vida máxima, `DrMundo` Q/E costes planos de vida y `%` vida actual, `Nasus` P robo de vida 10/15/20 % + R `%` vida máxima, `JarvanIV` E velocidad de ataque pasiva + P `%` vida actual, `Thresh` P almas, `Shyvana` P cargas de escamas, `Viego` R vida faltante, `Twitch` E físico+mágico, `Hwei` Q QQ y `Renata` P).
- Quedan exactamente **44 campeones** pendientes para la oleada 4 final de `CH-01` (alcanzando 173/173 = 100 %), además de los efectos no modelados declarados en `not_modelled` de cada kit y las reglas especiales de `CH-04`.
