# Kits de campeones: oleada 1 (`CH-01`) — fase 46

- **Objetivo:** iniciar la cobertura sistemática de `CH-01` pasando de 2 a **40 campeones con `kit.json` curado y validado** sobre el cliente `16.23` (`16.23.8406595+branch.releases-16-23.content.release`), resolviendo los casos límite del barrido sobre los 173 campeones del snapshot `16.23.1`.
- **Rama:** `feat/champion-kits-wave-1`, creada desde `dev` (`0f4d122`).

## Mejoras de pipeline sobre los 173 campeones

El barrido completo de los 173 campeones del cliente `16.23` con `python -m binmodel.batch_kits --survey` alcanzó **173 / 173 compilaciones válidas** tras:

1. `research/binmodel/traverse.py`: `find_champion_root` desambigua los bins con varios `CharacterRecord` (`Braum`, `Cassiopeia`, `Milio`) seleccionando la entrada única que termina en `/CharacterRecords/Root`.
2. `research/binmodel/kitgen.py`:
   - Normalización de `ability_power/bonus` a `ability_power/total` (el PH base es siempre `0`; desbloquea p. ej. E y R de Jax).
   - Traducción de `{4ce08984}` (`by_char_level_named_breakpoints`) a tablas `by_level` de 18 niveles.
   - Soporte de `{"op": "calculation", "name": ...}` dentro de fórmulas `custom` (para daño porcentual de vida del objetivo sin copiar constantes a mano) y de `"scale"` en `passive_stats` (para `DataValues` en puntos porcentuales como la E de Darius o la W de Nocturne).
   - Validación defensiva cuando `level_count` o `mNumber` son `None`.
3. `research/binmodel/specdraft.py`: respaldo de `level_count` ausente con `maxrank` de Data Dragon (`missing_level_count`), coherencia de casos y parámetros de reactivación (`recast`), y guardia `percent_damage_calc` para cálculos con `display_as_percent: true`.
4. `research/binmodel/batch_kits.py`: herramienta CLI reutilizable que carga una única vez `Global.es_ES.wad.client` y las 4 listas de hashes para `--survey`, `--compile` y `--compile-all`.
5. `research/tools/refresh_patch.py`: reutiliza `batch_kits` para comprobar todos los kits publicados en una única carga de tablas.

## Cobertura de la oleada 1 (38 nuevos → 40 totales)

Todas las cifras y fórmulas proceden del cliente instalado `16.23` (`Derivado`, con `bin_sha256` en cada `research/kits/<Id>.spec.json`) y todos los tipos de daño se contrastan con las etiquetas de los tooltips `es_ES`:

- **Top (10):** `Jax`, `Darius`, `Malphite`, `Pantheon`, `Renekton`, `Riven`, `Teemo`, `Sett`, `Camille`, `Garen`.
- **Jungla (7):** `Amumu`, `Diana`, `Evelynn`, `Karthus`, `Sejuani`, `Vi`, `Nocturne`.
- **Mid (12):** `Annie`, `Lux`, `Veigar`, `Orianna`, `Syndra`, `Viktor`, `Xerath`, `Ziggs`, `Anivia`, `Leblanc`, `Lissandra`, `Brand`.
- **Tirador (4):** `Ezreal`, `Jinx`, `Xayah`, `Vayne`.
- **Apoyo (5):** `Morgana`, `Leona`, `Nautilus`, `Alistar`, `Nami`.
- **Previos (2):** `Zaahen`, `Ahri`.

Pasivas y estadísticas pasivas activas en el motor:

- `Annie` R (`magic_penetration_percent` `10/15/20 %`), `Darius` E (`armor_penetration_percent` `20..40 %`), `Pantheon` R (`armor_penetration_percent` `10/20/30 %`), `Nocturne` W (`attack_speed_bonus` `30..50 %`), `Veigar` P (`phenomenal_evil_stacks`, `+1` PH plano por acumulación vía `--input`), además de `Zaahen` P/R y `Ahri` P.

## Verificación y límites

- `tests/test_champion_kits.py` evalúa cada habilidad y cada caso de los 40 kits publicados a nivel 11 y 18, ejecuta una rotación con `--timeline` para los 40 campeones y realiza comprobaciones exactas (`Jax` burst AP con Rabadon + Liche, `Annie`, `Darius`, `Pantheon`, `Nocturne`, `Veigar`, `Garen`, `Vayne`, `Syndra`).
- Quedan 133 campeones pendientes en futuras oleadas de `CH-01`, además de los efectos no modelados declarados en `not_modelled` de cada kit y las mecánicas especiales de `CH-04`.
