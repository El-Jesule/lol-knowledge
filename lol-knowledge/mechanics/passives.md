# Pasivas de campeón en hoja y rotación

- **Ámbito:** evaluación declarativa de las pasivas de campeón (`abilities.P.passive_effects` en `kit.json`) sobre la hoja de estadísticas (`stats`, `ability`) y en combate (`rotation`, `rotation --timeline`), más la automatización de borradores de kit (`CH-02`).
- **Parche de referencia:** Data Dragon `16.23.1` y cliente `16.23` (`16.23.8399929+branch.releases-16-23.content.release`).
- **Fecha de consulta:** 2026-11-20
- **Código:** [`src/lol_knowledge/passives.py`](../../src/lol_knowledge/passives.py), [`src/lol_knowledge/kit/model.py`](../../src/lol_knowledge/kit/model.py), [`src/lol_knowledge/rotation.py`](../../src/lol_knowledge/rotation.py), [`research/binmodel/specdraft.py`](../../research/binmodel/specdraft.py) y [`research/binmodel/kitgen.py`](../../research/binmodel/kitgen.py).

## Fuentes

| Id | Fuente | Qué cubre | Naturaleza |
|---|---|---|---|
| P1 | Cliente `16.23` / fixtures verificados ([`Zaahen/kit.json`](../champions/Zaahen/kit.json), [`Ahri/kit.json`](../champions/Ahri/kit.json), `research/kits/*.spec.json`) | `ZaahenPassive`: `PercentBonusADCalc` (`{ee18a47b}` `PBonusADMin = 0,015`, `PBonusADMax = 0,028`), `MaxStacks = 12`, `MaxStacksMultiplier = 2`, `FallOffDuration = 5`; `AhriPassive`: `ChampionHeal` (`75..165 + 30 % PH`), `MinionHeal` (`35..95 + 20 % PH`), `MaxStacks = 9` | `Derivado` (datos del cliente, no API oficial) |
| P2 | Wiki oficial de League of Legends (`wiki.leagueoflegends.com`, consultada el 2026-11-20): `Template:Data_Zaahen/Cultivation_of_War` (rev `4060321`), `Template:Data_Ahri/Essence_Theft` (rev `4038191`), `Template:Passive_progression_level` (rev `4060729`) y `Module:Ability_progression` (rev `4039181`) | Regla de Determinación de Zaahen (`1,5 %` a `2,8 %` DA lineal 1–18 por acumulación contra campeones, hasta `12`, duplicado `× 2` al máximo, duración `5 s`); curación de Robo de esencias de Ahri (`75–165 + 30 % PH` al derribar campeón, `35–95 + 20 % PH` al consumir 9 fragmentos de súbdito/monstruo; progresión lineal `1..18`) | Fuente comunitaria secundaria (corrobora P1) |

## 1. Modelo declarativo de pasivas (`Calculado`)

El motor no codifica nombres de campeón en Python: cualquier campeón declara sus efectos pasivos en `abilities.P.passive_effects` dentro de `kit.json` (`lol-champion-kit/1`), compilado desde el bin mediante `python -m binmodel.kitgen`:

| `kind` | Dónde aplica | Semántica |
|---|---|---|
| `stat_bonus` | Hoja (`stats`, `ability`, `rotation`) | Aporte fijo (`mode: "flat"`) o amplificador del total (`mode: "percent"`), permanente o condicionado a `--input <input_name>` |
| `stacking_stat` | Hoja con `--input <input_name>=0..N`; combate automático en `rotation` | Acumulaciones temporales de combate que empiezan en `0` ([`combat-stacks.md`](combat-stacks.md)) —o en `--input <input_name>` si se declara—, suben `+1` tras cada golpe que cumple `trigger` (`champion_hit`, `attack`, `ability_hit`, `any_hit`), se duplican/multiplican por `max_stacks_multiplier` al alcanzar `max_stacks` y caducan tras `duration_seconds` en `--timeline` |
| `heal` | `rotation` (`HealEvent`) | Curación directa al cumplirse `trigger` (`on_champion_takedown`, `on_minion_monster_kill`, `on_hit`, `on_ability_hit`), con `stacks_required` / `input_name` opcionales; escala con `heal_and_shield_power`, Revitalizar y Heridas graves ([`survival.md`](survival.md)) |
| `damage_proc` | `rotation` (`kind: "ability"`, slot `P`) | Daño adicional pasivo por disparo (`on_attack`, `on_hit`, `every_n_attacks`) con enfriamiento opcional `cooldown_seconds` en `--timeline` |

Para interpolaciones lineales `1..18` del cliente (`ByCharLevelInterpolationCalculationPart` y `{ee18a47b}` sin multiplicador de crecimiento), las fórmulas de kit disponen del operador exacto `linear_by_level` (`min + (max - min) × (nivel - 1) / 17` en `Fraction`). Los contadores de cargas del bin (`BuffCounterByCoefficientCalculationPart` y `BuffCounterByNamedDataValueCalculationPart`) se compilan a `{"op": "input", "name": "<cargas>", "default": 0}`, evaluando a `0` cargas por defecto y escalando al pasar `--input <cargas>=N` (p. ej. `siphoning_strike_stacks`, `feast_stacks`, `stardust_stacks`, `kindred_marks`, `dragon_practice_stacks`, `souls`, `soul_fragments`, `accelerando_stacks`, `courage_stacks`).

## 2. Pasivas modeladas hoy (`Derivado`, P1 + P2)

### Zaahen — *Florescencia de la guerra* (`data:champion:Zaahen`, `CH-Z-01`)

- **Efecto (`determination`, `stacking_stat`):** cada ataque básico o habilidad que daña a un campeón enemigo (`--target-kind champion`) suma `1` acumulación de Determinación (hasta `12`, duración `5 s` reiniciable en `--timeline`).
- **Aporte:** amplificador de daño de ataque total (entra como DA adicional, beneficiando tanto a los básicos como a los escalados por DA adicional de Q/W/E/R) de `1,5 %` a nivel 1 hasta `2,8 %` a nivel 18 lineal por acumulación; al llegar a `12` acumulaciones el bono se duplica (`× 2`, es decir, `36 %` a nivel 1 y `67,2 %` a nivel 18).
- **En `stats` y `ability`:** pasa `--input determination_stacks=<0..12>` para inspeccionar la hoja o el daño de una habilidad a cualquier número de acumulaciones; sin ese `--input` se añade una nota informativa y la hoja permanece en 0 acumulaciones.
- **No modelado aún:** la resurrección (`RevivePercentCalc`, `ReviveCooldownCalc`, `CH-Z-02`) y el decaimiento gradual por tramos cada `0,5 s` tras expirar los `5 s` (en `--timeline` caduca al cumplirse `FallOffDuration = 5 s`).

### Ahri — *Robo de esencias* (`data:champion:Ahri`, `CH-A-01`)

- **Derribo de campeón (`essence_theft_champion`, `heal`):** al matar a un campeón (`--target-kind champion`) en `rotation`, cura `75..165` (lineal `1..18`) `+ 30 % PH`, escalada por poder de curaciones y escudos, Revitalizar y Heridas graves.
- **9 fragmentos de súbdito/monstruo (`essence_theft_minion`, `heal`):** al matar un súbdito o monstruo (`--target-kind minion|monster`) alcanzando `9` fragmentos (por ejemplo con `--input essence_fragments=8`), consume los fragmentos y cura `35..95` (lineal `1..18`) `+ 20 % PH`.
- **No modelado aún:** ampliación de ventana y reactivación extra de la R al derribar campeones (`PDurationExtension`, `CH-A-02`).

## 3. Automatización de borradores de kit (`CH-02`)

El generador [`research/binmodel/specdraft.py`](../../research/binmodel/specdraft.py) (`python -m binmodel.specdraft`) produce automáticamente un borrador compilable de `research/kits/<Id>.spec.json` y un informe estructurado de revisión (`review.findings`) que detecta:

1. **Valores con doble tipo de daño** (`dual_damage_type`, p. ej. Q de Ahri bajo `<magicDamage>` y `<trueDamage>`), generando casos separados con `damage_type` explícito.
2. **Referencias de daño en `DataValues`** fuera de `mSpellCalculations` (`tooltip_data_value_damage`, p. ej. E de Zaahen `PercentHPDamage`).
3. **Ajustes de reactivación** (`recast_detected`: ventanas, intervalos, contadores y pares como `InitialDamage`/`SecondHitDamage`).
4. **Escalados sin `mStat`** (`omitted_mstat_default`, valor por defecto `0` = PH) y estadísticas no corroboradas (`uncorroborated_stat`) o nodos no traducibles (`untranslatable_node`).
5. **Curaciones/escudos** en tooltip (`healing_or_shield_calc`), **candidatos a estadísticas pasivas** (`passive_stat_candidate`) y **costes de vida** sin fórmula (`health_cost_needed` desde Data Dragon).

## Fuera de alcance / limitaciones

- La resurrección de Zaahen (`CH-Z-02`) y la extensión de la R de Ahri (`CH-A-02`).
- Pasivas que alteran reglas globales de estadísticas aún pendientes en `CH-04` (tope/ratio de velocidad de ataque de Bel'Veth/Graves/Jhin/Sion/Zeri, críticos de Ashe, velocidad de movimiento de Cassiopeia).
- Decaimiento escalonado de acumulaciones (en `--timeline` las acumulaciones caducan al cumplirse `duration_seconds` sin golpes).
