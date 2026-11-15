# Velocidad de ataque

- **Ámbito:** regla general para la velocidad de ataque total de un campeón: base, ratio, crecimiento por nivel, aportes adicionales y tope.
- **Parche de referencia:** Data Dragon 16.22.1 y cliente 16.22 (2026-11-15). El tope es 3,0 desde el parche 25.S1.3.
- **Fecha de consulta:** 2026-11-15

## Fuentes

| Id | Fuente | Qué cubre | Naturaleza |
|---|---|---|---|
| V1 | Notas oficiales del parche 25.S1.3 (`leagueoflegends.com/en-ph/news/game-updates/patch-2025-s1-3-notes/`), consultadas el 2026-11-15 | «Baseline Attack Speed Cap: 2.5 ⇒ 3.0» | Oficial de Riot |
| V2 | Notas oficiales del parche 26.1 (`leagueoflegends.com/en-sg/news/game-updates/patch-26-1-notes/`), consultadas el 2026-11-15 | Corrigen que Zeri «could reach over the attack speed cap»: el tope sigue existiendo en 2026 (no da el valor) | Oficial de Riot |
| V3 | LoL Fandom Wiki, `Attack_speed`, última edición indicada «August 14th, 2024 – V14.16», consultada el 2026-11-15 (CC BY-SA) | Fórmula `base + ratio × adicional`; el crecimiento usa la fórmula general; los aportes adicionales se suman; suelo 0,2; reducciones multiplicativas; campeones que cambian el tope | Fuente comunitaria secundaria. **Desfasada en el tope:** aún dice 2,5 |
| V4 | Cliente local 16.22: `Characters/<Id>/CharacterRecords/Root.attackSpeedModifiable`, `attackSpeedPerLevelModifiable` y `attackSpeedRatioModifiable`, extraídos con `research/binmodel/records.py` y publicados en [`../derived/champion-records.json`](../derived/champion-records.json) | Base, crecimiento y ratio de cada campeón | `Derivado` del cliente |
| V5 | Data Dragon 16.22.1, `stats.attackspeed` y `stats.attackspeedperlevel` de cada campeón en `data/current/champions/` | Base y crecimiento (en puntos porcentuales) | Oficial de Riot; no publica el ratio |
| V6 | LoL Wiki, `List_of_champions/Attack_speed`, solo el extracto del buscador (la página no se pudo abrir), consultado el 2026-11-15 | Habla de un tope de 3 (1,5 para Zeri) | Fuente comunitaria secundaria; corrobora V1 |

**Contraste de datos (`Derivado`, comprobado el 2026-11-15):** en los 173 campeones, la base y el crecimiento del cliente (V4) coinciden con Data Dragon (V5). Bel'Veth y Jhin no traen el crecimiento en el cliente y Data Dragon publica `0` para ambos. El ratio es distinto de la base en 60 campeones; Jhin tiene ratio 0.

## Fórmula (`Derivado`, V3 + V4; tope `Oficial`, V1)

```text
adicional(n) = crecimiento(n) + Σ aportes_i
crecimiento(n) = (g / 100) × (n − 1) × (0,7025 + 0,0175 × (n − 1))
velocidad(n) = min(base + ratio × adicional(n), 3,0)
```

- `base`: `attackspeed` de Data Dragon, en ataques por segundo (`Oficial`). A nivel 1 y sin aportes, la velocidad es exactamente la base.
- `g`: `attackspeedperlevel` de Data Dragon, en puntos porcentuales (2,5 = 2,5 %). Usa la misma fórmula de crecimiento que el resto de estadísticas ([Crecimiento de estadísticas](stat-growth.md)), pero el resultado es **velocidad de ataque adicional**, no una cantidad que se sume a la base (V3).
- `aportes_i`: velocidad de ataque adicional de objetos, runas y efectos, como fracción (25 % = 0,25). Se **suman** entre sí (V3).
- `ratio`: `attackspeedratio` del cliente (V4). Data Dragon no lo publica. Multiplica toda la velocidad adicional, incluido el crecimiento.
- **Tope:** 3,0 ataques por segundo desde el parche 25.S1.3 (V1). V2 confirma que sigue habiendo tope en 2026 y V6 da el mismo valor.

Comprobación con el ejemplo de V3: Twisted Fate (base 0,625 y ratio 0,651 en el cliente 16.22) con 97,35 % adicional → 0,625 + 0,651 × 0,9735 ≈ 1,2588. Con `g` = 2,5, el crecimiento a nivel 10 es 2,5 % × 9 × (0,7025 + 0,0175 × 9) = 19,35 %. Ambos ejemplos están en las pruebas.

## Fuera de alcance

- **Reducciones de velocidad de ataque** (V3: se multiplican y se aplican sobre el total) y el **suelo de 0,2** (V3, sin confirmar después de 2024).
- Modos con otro tope (por ejemplo, ARURF: 10,0 en V1).
- Tiempos de lanzamiento del ataque y ritmo de ataques: la rotación no modela el tiempo.
