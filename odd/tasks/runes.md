# Runas y fragmentos — fase 37

- **Objetivo:** RUN-01 a RUN-03 de la [hoja de ruta](../roadmap.md) y la legalidad de página de RUN-04.
- **Rama:** `feat/runes`, desde `dev`.
- **Entorno de validación:** shell Linux de Claude en el equipo del usuario, Python 3.14.10. No ejecutado en Windows.

## Decisiones

1. **Fuente: el bin `perks` del cliente.** Tiene árboles, filas, fragmentos, valores y cálculos; Data Dragon solo tiene árboles y textos, y ningún fragmento. Los árboles, filas e ids del cliente coinciden exactamente con Data Dragon 16.23.1, y `validate` lo exige.
2. **Nombres de valores por sus marcadores.** Un valor se nombra si su hash FNV-1a coincide con un marcador `@…@` de cualquier texto de runa o efecto, porque el hash es el del nombre. Quedan 131 de 463 sin nombre: son valores que ningún texto muestra.
3. **Fuerza adaptable:** compara DA adicional y PH de la hoja sin los fragmentos (wiki). En un empate decide el campo del cliente `mAdaptiveForceToAbilityPowerWeight`, añadido a `champion-records.json` (`adaptiveforceapweight`): 1 = PH. Es una deducción, así que los empates quedan `Pendiente de verificación`.
4. **Progresión de vida lineal** entre los extremos del cliente, `Pendiente de verificación`.
5. **Runas de los árboles:** se validan y se listan, pero sus efectos no se modelan. La hoja las registra en `pending_effects` y `ability` y `rotation` quedan `Pendiente de verificación`, igual que con un objeto sin revisar.
6. **Página ilegal:** código 2, salvo con `--allow-illegal-build`, igual que una build de objetos ilegal.

## Cambios

- `research/binmodel/perks.py` y pruebas; `binmodel.records` lee `mAdaptiveForceToAbilityPowerWeight`; paso nuevo en `refresh_patch.py`.
- `lol-knowledge/derived/runes.json` (5 árboles, 3 filas de fragmentos, 89 runas).
- `src/lol_knowledge/runes.py`: datos, legalidad de página, fragmentos y fuerza adaptable.
- Hoja de estadísticas: `percent_extras`, `pending_effects` y el grupo de tenacidad declarado por la fuente.
- CLI: `--rune` y `--shard` en `stats`, `ability` y `rotation`.
- Regla: [`lol-knowledge/mechanics/runes.md`](../../lol-knowledge/mechanics/runes.md).

## Limitaciones

- Piedras angulares y runas menores sin efectos (resto de RUN-04).
- Sin runas para el campeón objetivo.
- Sin resistencia a ralentizaciones ni variantes por modo.
