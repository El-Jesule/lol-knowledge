# Impacto crítico

- **Ámbito:** regla general del juego para los ataques básicos que asestan un impacto crítico. La usa `python -m lol_knowledge rotation` en los pasos `attack:crit`.
- **Parche de referencia:** cliente 16.22 (2026-11-15). El daño crítico base es 200 % desde el parche 26.1.
- **Fecha de consulta:** 2026-11-15

## Fuentes

| Id | Fuente | Qué cubre | Naturaleza |
|---|---|---|---|
| C1 | Notas oficiales del parche 26.1 (`leagueoflegends.com/en-sg/news/game-updates/patch-26-1-notes/`), consultadas el 2026-11-15 | El daño crítico base de todos los campeones vuelve al 200 % | Oficial de Riot |
| C2 | Cliente local 16.22: `Characters/<Id>/CharacterRecords/Root.critDamageMultiplier`, extraído con `research/binmodel/records.py` y publicado en [`../derived/champion-records.json`](../derived/champion-records.json) como `critdamagemultiplier` | Multiplicador crítico base de cada campeón: 2,0 en 172 campeones y 1,0 en Ashe | `Derivado` del cliente |
| C3 | LoL Wiki, artículo `Damage` (copia de `leagueoflegends.fandom.com`), consultada el 2026-11-15 (CC BY-SA) | El crítico modifica el daño antes de la mitigación; la mayoría de efectos al impactar no se ven afectados | Fuente comunitaria secundaria |
| C4 | ARAM Mayhem, resumen del parche 26.1 (`arammayhem.com/patch/26-1/`), consultado el 2026-11-15 | Con Filo infinito el crítico pasa de 215 % a 230 % | Fuente comunitaria secundaria que resume las notas oficiales |
| C5 | Data Dragon 16.22.1, objeto 3031 (Filo infinito), en el [catálogo de objetos](../objects/catalog.json) | 30 % de daño crítico adicional | Oficial de Riot |

**Discrepancia registrada:** la página `Critical_strike` de la LoL Wiki aún dice 175 % (consultada el 2026-11-15). C1 y C2 dicen 200 %; se sigue a C1 y C2.

## Regla (`Derivado`, corroborada C1 + C2)

```text
daño bruto del crítico = daño del ataque × (multiplicador_base + Σ daño_crítico_adicional)
```

- `multiplicador_base` es el `critdamagemultiplier` del campeón (C2). Para 172 campeones es 2,0, el mismo valor que anuncian las notas oficiales (C1). Si el registro del campeón no tiene el campo, el paso crítico se rechaza.
- **Ashe** tiene 1,0 en el registro: su pasiva cambia cómo funcionan sus críticos. El motor no la modela; cualquier campeón cuyo multiplicador difiera de 2,0 obtiene `Pendiente de verificación` y una nota.
- `daño_crítico_adicional` es la estadística `crit_damage_bonus` (C5). Filo infinito suma 0,3: 2,0 + 0,3 = 2,3, el 230 % de C4.
- Con **varias fuentes** de daño crítico adicional, la suma no está verificada (solo hay un objeto en el catálogo). El motor las suma y marca el resultado `Pendiente de verificación`.
- El crítico se aplica **antes de la mitigación** (C3). Como la mitigación multiplica, el orden no cambia el resultado.
- El daño al impactar de los objetos **no** se multiplica por el crítico (C3: la mayoría de efectos al impactar no se ven afectados, salvo que se indique). Ningún objeto del catálogo indica lo contrario.

## Fuera de alcance

- **Probabilidad de crítico:** el motor no calcula valores esperados. Cada paso dice si critica (`attack:crit`) o no (`attack`).
- **Habilidades que critican** y reducciones específicas de campeón: dependen del kit de cada campeón.
