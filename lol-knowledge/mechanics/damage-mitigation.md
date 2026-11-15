# Mitigación de daño: armadura, resistencia mágica, reducción y penetración

- **Ámbito:** regla general del juego, común a todos los campeones y objetos. Es la entrada del futuro motor de daño.
- **Parche de referencia:** vigente en el cliente 16.22 (2026-11-15). La conversión de la letalidad es así desde la V14.1.
- **Fecha de consulta:** 2026-11-15

## Fuentes

| Id | Fuente | Qué cubre | Naturaleza |
|---|---|---|---|
| S1 | Confirmación del responsable del proyecto, 2026-11-15 | Orden de aplicación; penetración y letalidad sobre la armadura total; misma regla para la resistencia mágica; pasiva de la R de Zaahen activa en enfriamiento | Conocimiento del juego del usuario, no medido en este repositorio |
| S2 | LoL Wiki, `Armor_penetration`, consultada el 2026-11-15 (CC BY-SA 3.0) | Orden de aplicación, apilamiento, mínimo 0, total frente a adicional, conversión de la letalidad | Fuente comunitaria secundaria, no oficial de Riot |
| S4 | LoL Fandom Wiki, página de armadura (`leagueoflegends.fandom.com/zh/wiki/护甲`, texto en inglés), consultada el 2026-11-15 (CC BY-SA) | Multiplicador de daño con resistencia ≥ 0 y ≤ 0, con ejemplos | Fuente comunitaria secundaria, no oficial de Riot |
| S5 | Millenium, «League of Theorycraft n°3» (`millenium.org/news/91591.html`), consultada el 2026-11-15 | Multiplicador con armadura negativa | Fuente comunitaria secundaria, no oficial de Riot |
| S3 | LoLTheory, «What is AD in League of Legends» (`blog.loltheory.gg/what-is-ad-league-of-legends/`), consultada el 2026-11-15 | Fórmula de daño mitigado con resistencia ≥ 0 | Fuente comunitaria secundaria, no oficial de Riot |

Ninguna de las dos es una fuente oficial de Riot. Las reglas que coinciden en S1 y S2 se marcan como corroboradas; las que solo tienen una fuente lo indican.

## Fórmula de daño mitigado

Con una resistencia efectiva `R` (armadura frente a daño físico, resistencia mágica frente a daño mágico):

```text
R ≥ 0:  daño = bruto × 100 / (100 + R)          # Derivado, corroborado S3 + S4
R < 0:  daño = bruto × (2 − 100 / (100 − R))    # Derivado, corroborado S4 + S5
```

Ejemplos de S4: 25 de armadura → ×0,8; 100 → ×0,5; −25 → ×1,2. La rama negativa nunca llega a duplicar el daño, lo que coincide con la página `Armor` de la wiki (S2, revisión 4073057): la armadura negativa no puede bajar la vida efectiva de la mitad de la real. El daño verdadero no se mitiga.

## Orden de aplicación (`Derivado`, corroborado S1 + S2)

La resistencia del objetivo se transforma en este orden:

1. **Reducción plana:** se resta. Varias fuentes se suman. **Puede** dejar la resistencia por debajo de 0.
2. **Reducción porcentual:** se multiplica por `(1 − r)`. Varias fuentes se apilan multiplicativamente. No actúa sobre resistencia ≤ 0.
3. **Penetración porcentual:** se multiplica por `(1 − p)`. Varias fuentes se apilan multiplicativamente. Solo afecta al atacante y no actúa sobre resistencia ≤ 0.
4. **Penetración plana (letalidad, en el caso físico):** se resta. Varias fuentes se suman. **No puede** dejar la resistencia por debajo de 0.

Las reducciones modifican al objetivo y afectan a todos sus atacantes. Las penetraciones solo afectan al daño de quien las tiene.

```text
R1 = R − Σ reducción_plana                               # puede ser < 0
R2 = R1 × Π(1 − r_i)        si R1 > 0, si no R1
R3 = R2 × Π(1 − p_j)        si R2 > 0, si no R2
R4 = max(0, R3 − Σ pen_plana)  si R3 > 0, si no R3
```

## Sobre qué se aplica (`Derivado`)

- **Penetración porcentual y letalidad:** sobre la **armadura total**, base más adicional. Corroborado por S1 y S2.
- **Penetración porcentual de armadura *adicional*:** es una estadística distinta que solo afecta a la armadura adicional. Según S2, la armadura base y la adicional se calculan por separado. Si el motor la necesita, tendrá que repartir la reducción plana entre base y adicional. `Pendiente de verificación`: el reparto exacto no está documentado aquí.
- **Letalidad:** equivale 1:1 a penetración plana, sin escalado por nivel desde la V14.1 (S2). Antes de la V14.1 escalaba con el nivel; esa fórmula no se aplica al parche actual.

## Resistencia mágica (`Derivado`, solo S1)

Misma regla y mismo orden que la armadura: reducción plana, reducción porcentual, penetración mágica porcentual y penetración mágica plana, todas sobre la resistencia mágica total. S2 no trata la resistencia mágica. **Fuente única**: falta una segunda fuente para considerarla corroborada.

## Implementación (`Calculado`)

Estas reglas están implementadas en `src/lol_knowledge/damage/` y se ejecutan con `python -m lol_knowledge damage` (ver [`../../README.md`](../../README.md)). El motor trabaja con aritmética exacta y no redondea. Sus pruebas (`tests/test_damage_mitigation.py`) fijan el orden, el apilamiento, el suelo en 0 de la penetración plana y los ejemplos de S4.

## Limitaciones

- Ninguna regla de este archivo se ha medido en partida dentro de este repositorio.
- El redondeo del daño mostrado no está documentado aquí.
- Los modificadores de daño que no son de resistencia (amplificaciones, reducciones de daño recibido, escudos) quedan fuera de este archivo.
