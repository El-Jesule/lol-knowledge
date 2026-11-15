# Crecimiento de estadísticas por nivel

- **Ámbito:** regla general del juego para las estadísticas de campeón que crecen al subir de nivel.
- **Fecha de consulta:** 2026-11-15

## Fuentes

| Id | Fuente | Qué cubre | Naturaleza |
|---|---|---|---|
| S1 | LoL Wiki, `Champion_statistics`, consultada el 2026-11-15 (CC BY-SA 3.0) | Fórmula de crecimiento; la velocidad de ataque usa otra fórmula | Fuente comunitaria secundaria, no oficial de Riot |
| S2 | LoL Fandom Wiki, `Champion_statistic`, consultada el 2026-11-15 (CC BY-SA) | La misma fórmula y un ejemplo numérico: base 685, crecimiento 120, nivel 2 → 771,4 | Fuente comunitaria secundaria, no oficial de Riot |

## Fórmula (`Derivado`, corroborado S1 + S2)

```text
estadística(n) = base + g × (n − 1) × (0,7025 + 0,0175 × (n − 1))
```

- `base`: valor a nivel 1, de Data Dragon (`hp`, `armor`, …).
- `g`: crecimiento, de Data Dragon (`hpperlevel`, `armorperlevel`, …).
- `n`: nivel actual. Los aportes de objetos, runas y efectos se suman aparte como estadística adicional.

A nivel 1 el término de crecimiento es 0, así que el valor es exactamente el de Data Dragon (`Oficial`). A partir del nivel 2 interviene esta fórmula, que procede de fuentes secundarias, y el valor pasa a ser `Derivado`.

## Qué no cubre

- **Velocidad de ataque:** según S1 usa una fórmula distinta y depende del ratio de velocidad de ataque, que Data Dragon no publica. No se calcula.
- **Velocidad de movimiento y alcance:** no crecen por nivel.
- **Daño de ataque:** la fórmula vale, pero el snapshot no trae el crecimiento. Ver [Defectos conocidos de los datos](known-data-issues.md).
- **Nivel máximo:** la regla no depende del modo de juego. El motor acepta niveles de 1 a 30 y no valida el tope de cada modo.
- **Por encima del nivel 18 (`Pendiente de verificación`):** S1 dice que la fórmula vale para cualquier nivel y el motor la aplica así. El prototipo `research/binmodel/stats.py` suma en cambio un crecimiento completo por nivel desde el 18. Ninguna de las dos variantes se ha medido.

## Implementación (`Calculado`)

`src/lol_knowledge/stats/growth.py`, con aritmética exacta: `0,7025 = 281/400` y `0,0175 = 7/400`. La prueba `tests/test_stats_growth.py` reproduce el ejemplo de S2.
