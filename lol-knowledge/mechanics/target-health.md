# Efectos según la vida del objetivo

- **Ámbito:** efectos de objeto que leen la vida del objetivo durante una rotación: crecer con la vida que le falta, activarse por debajo de un umbral o ejecutar. Los usa `python -m lol_knowledge rotation`.
- **Parche de referencia:** cliente 16.22 y Data Dragon 16.22.1.
- **Fecha de consulta:** 2026-11-16

## Fuentes

| Id | Fuente | Qué cubre | Naturaleza |
|---|---|---|---|
| T1 | Data Dragon 16.22.1: Verdugo de krakens («que aumenta en función de la vida que le falte»), Llamasombría («a los enemigos con menos de un 40% de la vida… un 20% de daño adicional») y Recaudadora («ejecuta a los campeones con menos del 5% de la vida») | Qué hace cada efecto y sus umbrales | Oficial de Riot |
| T2 | Cliente 16.22: [`../derived/item-effects.json`](../derived/item-effects.json): `MaxAmpNumber` 1,75 de Kraken, `HealthThreshold` 0,4 y `SpellItemDamageAmp` 0,2 de Llamasombría, `ExecuteThreshold` 0,05 de Recaudadora | Cifras | `Derivado` |
| T3 | LoL Wiki, `Kraken_Slayer` y `ARAM/Patch_history` (extractos del buscador, 2026-11-16) | Kraken: «increased by 0% – 75% (based on target's missing health)»; base de 150 – 200 en la Grieta (la página del objeto dice 150 – 210, en contra del cliente y del historial de ARAM) | Fuente comunitaria secundaria |

## Regla del motor (`Calculado`)

1. **Vida al inicio del paso:** todos los efectos leen la vida que el objetivo tiene al empezar el paso, como el resto de la rotación ([`basic-attacks-and-on-hit.md`](basic-attacks-and-on-hit.md)).
2. **Vida que falta** (`scope: missing_fraction`): (vida máxima − vida actual) / vida máxima, de 0 a 1. Kraken: daño × (1 + 0,75 × fracción que falta), lineal según la notación de la wiki (T3); el cliente solo da el máximo, ×1,75 (T2).
3. **Umbral** (`target_health_below`, en %): el efecto vale si la vida al inicio del paso está por debajo del porcentaje. Llamasombría suma +20 % al daño mágico y verdadero (`damage_types`) por debajo del 40 %.
4. **Ejecución** (componente `execute`): si tras el daño de un paso un campeón queda vivo por debajo del umbral de su vida máxima, el resto de su vida se inflige como una parte `execute` de daño verdadero, sin modificadores. Recaudadora: 5 %.

## Fuera de alcance

- La vida a mitad de un paso (por ejemplo, entre el ataque y su daño al impactar).
- El aumento de Llamasombría al daño a lo largo del tiempo: las rotaciones no lo tienen.
