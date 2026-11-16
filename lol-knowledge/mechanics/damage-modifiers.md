# Modificadores de daño infligido y recibido

- **Ámbito:** regla general para los aumentos de daño del atacante (por ejemplo, Verdugo de gigantes de Recuerdos de lord Dominik) y las reducciones de daño del objetivo (por ejemplo, Placas de las Botas blindadas o Adaptabilidad de Presagio de Randuin). La usa `python -m lol_knowledge rotation`.
- **Parche de referencia:** cliente 16.22 (2026-11-15). La suma de los modificadores de daño infligido es así desde la V26.09, según M1.
- **Fecha de consulta:** 2026-11-15

## Fuentes

| Id | Fuente | Qué cubre | Naturaleza |
|---|---|---|---|
| M1 | LoL Wiki, `Damage_modifier`, consultada el 2026-11-15 (CC BY-SA 3.0) | El modificador cambia el daño en bruto y luego se aplica; los de daño infligido se suman entre sí desde la V26.09; los de daño recibido se multiplican | Fuente comunitaria secundaria |
| M2 | LoL Wiki, `Stacking` (revisión 3992485), consultada el 2026-11-15 | Los aumentos se multiplican con las reducciones salvo que se indique otra cosa | Fuente comunitaria secundaria |
| M3 | LoL Wiki, artículo `Damage` (copia de `leagueoflegends.fandom.com`, texto en inglés), consultada el 2026-11-15 | Los modificadores se multiplican con la armadura y la resistencia mágica | Fuente comunitaria secundaria |
| M4 | Descripción de Data Dragon 16.22.1 de cada efecto, en el [catálogo de objetos](../objects/catalog.json) | Valor y condición de Placas (−10 % de los ataques) y Adaptabilidad (−30 % de los críticos) | Oficial de Riot |

Ninguna fuente de la regla general es oficial de Riot. Las tres son de la misma wiki comunitaria y coinciden.

## Regla (`Derivado`, fuente comunitaria M1 + M2 + M3)

```text
daño final = daño mitigado × (1 + Σ infligido_i / 100) × Π (1 + recibido_j / 100)
```

- **Daño infligido** (del atacante, `direction: dealt`): los porcentajes se **suman** entre sí y luego multiplican (M1, desde la V26.09).
- **Daño recibido** (del objetivo, `direction: taken`): cada porcentaje **multiplica** por separado (M1). Una reducción es un porcentaje negativo.
- Ambos grupos multiplican entre sí y con el multiplicador de la resistencia (M2, M3). Por eso el orden respecto a la mitigación no cambia el resultado.
- La **reducción plana** de daño (restar una cantidad fija) no está modelada; ningún efecto curado del catálogo la tiene.

## Condiciones que aplica el motor

| Condición del catálogo | Cuándo se cumple |
|---|---|
| `target_is_champion` | El objetivo es un campeón. Con un objetivo manual sin `--target-kind`, el motor se niega a adivinarlo. |
| `critical_strike` | La parte es el daño del propio ataque en un paso `attack:crit`. El daño al impactar no critica. |
| Fuente `attack` (Placas) | La parte es el daño del propio ataque básico. No afecta a las habilidades. |
| Fuente `all` | Cualquier parte. |

**Pendiente de verificación:** si Placas reduce también el daño al impactar de los objetos (por ejemplo, Filo de la niebla). Desde el parche 25.4 reduce también las instancias de daño básico que llevan daño adicional en la misma instancia (resumen de notas en `riftpatchnotes.com`), pero no consta si el daño al impactar de un objeto es una instancia aparte. El motor no aplica Placas a ese daño y marca la parte `Pendiente de verificación` con una nota.

## Etiquetas

La etiqueta del resultado nunca es más fuerte que la del efecto aplicado: un efecto con `evidence_confidence: secondary` (como la pendiente del 1 % por cada 100 de vida adicional de Verdugo de gigantes) deja la parte en `Pendiente de verificación`.
