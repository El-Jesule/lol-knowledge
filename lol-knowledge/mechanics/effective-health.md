# Vida efectiva

- **Ámbito:** cuánto daño bruto de un tipo necesita recibir un campeón para perder toda su vida.
- **Fecha de consulta:** 2026-11-15

## Fuentes

| Id | Fuente | Qué cubre | Naturaleza |
|---|---|---|---|
| S1 | LoL Wiki, `Armor` (revisión 4073057), consultada el 2026-11-15 (CC BY-SA 3.0) | Vida efectiva = (1 + armadura / 100) × vida; la armadura negativa no baja la vida efectiva de la mitad de la real | Fuente comunitaria secundaria, no oficial de Riot |
| — | [Mitigación de daño](damage-mitigation.md) | Multiplicador de daño con resistencia positiva y negativa | Regla del proyecto, `Derivado` |

## Fórmula (`Derivado`)

```text
vida_efectiva = vida / multiplicador(resistencia)
```

Con resistencia ≥ 0 equivale a `vida × (1 + R / 100)` (S1). Con resistencia negativa se usa la rama negativa del multiplicador de [Mitigación de daño](damage-mitigation.md), coherente con el mínimo del 50 % que indica S1. Frente al daño verdadero, la vida efectiva es la vida.

## Qué no cubre

- Reducciones de daño, escudos, curación y regeneración durante el combate.
- Las penetraciones del atacante: esta métrica mide la resistencia del propio campeón. Para un atacante concreto, usar `python -m lol_knowledge damage`.

## Implementación (`Calculado`)

`src/lol_knowledge/stats/metrics.py` (`effective_health`), que reutiliza el multiplicador del motor de daño.
