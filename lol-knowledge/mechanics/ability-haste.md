# Aceleración de habilidades y enfriamientos

- **Ámbito:** regla general del juego para el enfriamiento de habilidades.
- **Fecha de consulta:** 2026-11-15

## Fuentes

| Id | Fuente | Qué cubre | Naturaleza |
|---|---|---|---|
| S1 | LoL Wiki, `Haste` (revisión 4070414), consultada el 2026-11-15 (CC BY-SA 3.0) | Fórmula; 100 de aceleración → enfriamiento al 50 %, 200 → al 33,3 % | Fuente comunitaria secundaria, no oficial de Riot |
| S2 | LoLTheory, «Ability Haste in LoL» (`blog.loltheory.gg/ability-haste-lol/`), consultada el 2026-11-15 | La misma fórmula y su equivalente en reducción porcentual | Fuente comunitaria secundaria, no oficial de Riot |

## Fórmula (`Derivado`, corroborado S1 + S2)

```text
enfriamiento = enfriamiento_base × 100 / (100 + aceleración)
reducción    = aceleración / (100 + aceleración)
```

- `enfriamiento_base`: el de Data Dragon para el rango (`spells[].cooldown`), `Oficial`.
- `aceleración`: suma de todas las fuentes aplicables (se apila de forma aditiva):
  - Habilidades básicas (`Q`, `W`, `E`): `ability_haste + basic_ability_haste` (por ejemplo, Leyenda: Velocidad).
  - Definitiva (`R`): `ability_haste + ultimate_haste` (por ejemplo, Cazador definitivo).
- Sin aceleración, el enfriamiento es el de Data Dragon y conserva la etiqueta `Oficial`.

## Pendiente de verificación

- **Tope:** algunas fuentes citan un máximo de 500 de aceleración y otras dicen que no hay tope. El motor no aplica ninguno; por debajo de 500 la diferencia no existe.
- **Aceleración de hechizos de invocador y de objetos:** no se modelan todavía.
- **Enfriamientos que no son de habilidad** (pasivas, efectos de objeto): no se modelan.

## Implementación (`Calculado`)

`src/lol_knowledge/stats/metrics.py` (`ability_cooldowns`) y `src/lol_knowledge/stats/registry.py` (`ability_haste`, `basic_ability_haste`, `ultimate_haste`). Las pruebas fijan los ejemplos de S1 y la separación entre habilidades básicas y definitiva.
