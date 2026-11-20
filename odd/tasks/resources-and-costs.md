# Recursos y costes — fase 44

- **Objetivo:** cerrar el bloque 4.1 de la hoja de ruta (`MEC-01`, `MEC-02` y `MEC-03`): costes de habilidades (maná, energía y vida), seguimiento de la reserva de recurso y regeneración en `rotation`, soporte de recursos distintos del maná en la hoja (`stats`), devolución de maná de Segador de esencia (`3508`), runa `8009` Claridad mental (`PresenceOfMind`) y regeneración por maná perdido de `8226` Banda de maná en `--timeline`.
- **Rama:** `feat/resources-and-costs`, creada desde `dev` (`d28cd3a`).
- **Entrega:**
  - `src/lol_knowledge/stats/data.py`, `sheet.py`, `metrics.py`, `report.py`: costes oficiales por rango en `SpellData`, métricas `champion_resource(sheet)` (`ResourcePool`) y `ability_costs(sheet)` (`AbilityCosts`) para maná, energía (`200` / `400` en Shen, `50/5 s`), sin recurso y recursos secundarios.
  - `src/lol_knowledge/kit/model.py`: declaración opcional `cost` (`CostSpec`: `mana`, `energy`, `health`, `none`) en habilidades y casos del esquema `lol-champion-kit/1`.
  - `src/lol_knowledge/resources.py`: `resolve_ability_cost`, `ResourceTracker`, `StepResourceCost`, `ResourceEvent` y `ResourceSummary` con aritmética exacta (`Fraction`), regeneración pasiva en `--timeline`, tics de 5 s de Banda de maná, validación de recurso suficiente (`--allow-insufficient-resource`), y regla de costes de vida con suelo en `1` de vida.
  - `src/lol_knowledge/objects/schema.py`, `validate.py` y `lol-knowledge/objects/catalog.json` (v22): nuevo componente `resource_restore` y devolución de maná de `3508` Segador de esencia (`0,5 × SpellbladeDamage` previo a mitigación).
  - `src/lol_knowledge/runes.py` y `rune_combat.py`: lectura de tablas por nivel `{2421b258}` / `{34474c3b}` del cliente 16.23, soporte completo de `8009` Claridad mental (maná cuerpo a cuerpo/distancia, energía, enfriamiento de 8 s y 15 % al derribar) y tics de `8226` Banda de maná (**51/62** runas de árbol cubiertas).
  - `src/lol_knowledge/rotation.py`, `rotation_report.py` y `cli.py`: integración completa y opciones `--attacker-resource` y `--allow-insufficient-resource`.
  - `lol-knowledge/mechanics/resources.md`, actualización de `INDEX.md`, `runes.md`, `spellblade.md`, `regeneration.md`, `README.md`, `odd/roadmap.md` y pruebas en `tests/test_resources.py`.

## Decisiones de diseño

1. **Costes oficiales por defecto desde Data Dragon:** los 173 campeones ya tienen `spells[*].cost` en `data/current/champions/*.json`; `kit.json` solo necesita declarar `cost` para costes de vida o excepciones, y las reactivaciones (`recast: true`) cuestan `0` automáticamente.
2. **Energía separada del maná en la hoja:** `sheet["mana"]` y `sheet["mana_regen"]` siguen bloqueadas en campeones de energía (los objetos de maná no otorgan energía); `metrics.resource` resuelve el recurso real del campeón (`Oficial`).
3. **Validación estricta por defecto:** lanzar sin recurso suficiente falla con `RotationError` (consistente con el enfriamiento en `--timeline`); `--allow-insufficient-resource` permite simularlo degradando el resultado a `Pendiente de verificación`.
4. **Costes de vida sin suicidio:** según `Health` (rev `4073062`), los costes de vida nunca matan al lanzador y dejan al menos `1` de vida, activando automáticamente el seguimiento de vida del atacante.
5. **Devolución de Segador de esencia previa a mitigación:** corroborado simultáneamente por el cliente `16.23` (`TotalManaRefund = 0.5 × SpellbladeDamage`) y `Module:ItemData/data` (rev `4095269`).

## Limitaciones

Ver [`lol-knowledge/mechanics/resources.md`](../../lol-knowledge/mechanics/resources.md) §Fuera de alcance y la [hoja de ruta](../roadmap.md).
