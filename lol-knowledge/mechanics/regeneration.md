# Regeneración de vida y maná

- **Ámbito:** regla general de la regeneración de vida (`health_regen`) y de maná (`mana_regen`) de un campeón: unidad, crecimiento por nivel y aportes planos y porcentuales. La usa la hoja de estadísticas (`python -m lol_knowledge stats`).
- **Parche de referencia:** Data Dragon 16.22.1 (2026-11-16).
- **Fecha de consulta:** 2026-11-16

## Fuentes

| Id | Fuente | Qué cubre | Naturaleza |
|---|---|---|---|
| R1 | LoL Wiki, `Health_regeneration` (`HP5`), extractos del buscador consultados el 2026-11-16 | Se mide por cada 5 s y la interfaz la muestra por segundo; todo campeón salvo Briar tiene regeneración base, que crece por nivel; los aportes adicionales son todo lo que no viene del nivel; un ejemplo aplica el porcentaje sobre la base: `20,75 × (1 + 7) + 33` | Fuente comunitaria secundaria |
| R2 | LoL Wiki, `Mana_regeneration` (`MP5`), extractos del buscador consultados el 2026-11-16 | Base que crece por nivel; se suma punto por punto «tanto en valores planos como porcentuales» | Fuente comunitaria secundaria |
| R3 | LoL Wiki, `Champion_statistics`, consultada el 2026-11-15 y el 2026-11-16 | La regeneración de vida y la de maná usan la fórmula general de crecimiento ([Crecimiento de estadísticas](stat-growth.md)) | Fuente comunitaria secundaria |
| R4 | Data Dragon 16.22.1, `stats.hpregen`, `hpregenperlevel`, `mpregen` y `mpregenperlevel` de los campeones; `stats.FlatHPRegenMod` y descripciones de los objetos en `data/current/items.json` | Valores base y de crecimiento de los campeones; regeneración de los objetos | Oficial de Riot |

## Unidad de los objetos en Data Dragon (`Derivado`, R4)

En los campeones, Data Dragon da la regeneración por cada 5 s: Zaahen tiene `hpregen` 7,5. En los objetos, `stats.FlatHPRegenMod` va **por segundo**. Lo muestran los 18 objetos de 16.22.1 que tienen el campo: en todos, su descripción da exactamente 5 veces ese valor «cada 5 s». Por ejemplo:

| Objeto | `FlatHPRegenMod` | Descripción |
|---|---|---|
| 1054 Escudo de Doran | 0,8 | «Restaura 4 de vida cada 5 s» |
| 2051 Cuerno del guardián | 4 | «Restaura 20 de vida cada 5 s» |
| 773083 Armadura de Warmog (otro modo) | 6 | «30 de regeneración de vida cada 5 s» |

Por eso el modelo de objetos multiplica `FlatHPRegenMod` por 5 para expresarlo por cada 5 s, como los campeones y las descripciones. El valor convertido es `Derivado`: el número es oficial, pero la unidad se deduce de la comparación. Data Dragon no publica regeneración de maná en `stats`; solo en las descripciones.

## Regla (`Derivado`, R1 + R2 + R3; datos `Oficial`, R4)

```text
base(n) = base + g × (n − 1) × (0,7025 + 0,0175 × (n − 1))
regeneración(n) = base(n) × (1 + Σ porcentaje_i) + Σ plano_j        (por cada 5 s)
por segundo = regeneración / 5
```

- **Base y crecimiento:** `hpregen`/`hpregenperlevel` y `mpregen`/`mpregenperlevel` de Data Dragon, con la fórmula general (R3).
- **Porcentaje de la regeneración base** («100% de regeneración de vida básica»): multiplica la base del nivel, crecimiento incluido (R1). Varios porcentajes se suman entre sí (R2).
- **Aportes planos** («5 de regeneración de vida cada 5 s»): se suman (R2).
- **Briar:** no tiene regeneración de vida base (R1); Data Dragon le da 0.
- **Maná:** solo para campeones de maná. Con otro recurso (energía, furia…), la regeneración de maná no se calcula.

## Implementación (`Calculado`)

- `src/lol_knowledge/stats/registry.py` declara `health_regen` y `mana_regen` como cantidades aditivas por cada 5 s con `percent_of_base`. Un objeto con `kind: percent` se convierte en cantidad: porcentaje × base del nivel (aportes `base` de la hoja), con la nota `125% of base 13.955`. Su etiqueta nunca es más fuerte que la de la base.
- `src/lol_knowledge/objects/schema.py` multiplica `FlatHPRegenMod` por 5 y `src/lol_knowledge/objects/catalog.py` anota `unit_conversion` en la entrada. `src/lol_knowledge/stats/data.py` convierte esa anotación en un aporte `Derivado` con la nota `unit converted: …`.
- Ejemplo calculado: Zaahen a nivel 10 con Renovación de piedra lunar (125 % de regeneración de maná básica): 8,15 + 0,75 × 7,74 = 13,955 de base, más 125 % = 17,44375; total 31,39875 por cada 5 s.
- Pruebas: `tests/test_stats_regeneration.py` y `tests/test_objects_validator.py`.

## Fuera de alcance

- **Multiplicadores de regeneración** (poder de curación y escudos, Rostro espiritual): según R1 se suman entre sí y multiplican el total. No hay ninguno en el catálogo.
- Regeneración porcentual de la vida o el maná máximos (Armadura de Warmog, Abismo de los Lamentos), fuera de combate o en la fuente.
- Regeneración de otros recursos (energía, furia).
