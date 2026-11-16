# Velocidad de movimiento

- **Ámbito:** regla general de la velocidad de movimiento de un campeón: base, aportes planos y porcentuales, y límites suaves.
- **Parche de referencia:** Data Dragon 16.22.1 (2026-11-16).
- **Fecha de consulta:** 2026-11-16

## Fuentes

| Id | Fuente | Qué cubre | Naturaleza |
|---|---|---|---|
| M1 | LoL Wiki, `Movement_speed` (`MS`), extracto del buscador consultado el 2026-11-16; la página no se pudo abrir | Fórmula `(base + planos) × (1 + Σ porcentajes aditivos) × Π(1 + multiplicativos) × (1 − ralentización mayor)`; entre 415 y 490 cuenta el 80 %, por encima de 490 el 50 %; ejemplo: 600 en bruto → 530 | Fuente comunitaria secundaria |
| M2 | LoL Fandom Wiki, `Flat_movement_speed` y edición en chino de `Movement_speed`, extractos del buscador consultados el 2026-11-16 | Fórmulas simplificadas: entre 415 y 490, `bruto × 0,8 + 83`; por encima de 490, `bruto × 0,5 + 230`; por debajo de 220, `bruto × 0,5 + 110`; primero los planos, luego los porcentajes | Fuente comunitaria secundaria |
| M3 | NerfPlz, «Movement speed explained» (2026-09-09), consultado el 2026-11-16 | Los mismos límites; por debajo de 220 se recupera la mitad de lo que falta (180 → 200) y por debajo de 0 se queda en torno a 110; casi todos los porcentajes se suman y unos pocos multiplican; solo cuenta la ralentización más fuerte | Guía comunitaria secundaria; corrobora M1 y M2 |
| M4 | Data Dragon 16.22.1: `stats.movespeed` de los campeones (de 315 a 355) y `FlatMovementSpeedMod`/`PercentMovementSpeedMod` de los objetos | Base de cada campeón; aportes planos (Botas: 25; botas de nivel 2 del catálogo: 45) y porcentuales | Oficial de Riot |
| M5 | Resumen de U.GG de las notas oficiales del parche 26.1, consultado el 2026-11-16 | Pasiva de Cassiopeia: «Increased effectiveness of all Movement Speed buffs by 6-40% (based on level)» | Resumen secundario de notas oficiales |

## Regla (`Derivado`, M1 + M2, corroborada M3; datos `Oficial`, M4)

```text
bruto = (base + Σ planos) × (1 + Σ porcentajes aditivos)
velocidad = bruto                         si 220 ≤ bruto ≤ 415
          = bruto × 0,8 + 83              si 415 < bruto ≤ 490
          = bruto × 0,5 + 230             si bruto > 490
          = max(bruto, 0) × 0,5 + 110     si bruto < 220
```

- **Orden:** primero se suman los aportes planos a la base y después se aplican los porcentajes, todos a la vez (M1, M2, M3). Dos aportes del 10 % dan un 20 %.
- **Límites suaves:** los tramos se encadenan. 600 en bruto: 415 + 75 × 0,8 + 110 × 0,5 = 530 (M1). Las fórmulas simplificadas de M2 dan lo mismo: 600 × 0,5 + 230 = 530.
- **Por debajo de 220:** solo con ralentizaciones; sin ellas, ninguna base de Data Dragon baja de 315.
- **Cassiopeia (`Pendiente de verificación`):** su pasiva aumenta la eficacia de todos los aumentos de velocidad (M5). No está modelada.

## Fuera de alcance

- **Aportes multiplicativos** (unos pocos efectos según M3) y **ralentizaciones** (solo cuenta la mayor y se reduce con la resistencia a ralentizaciones): no hay ninguno en el catálogo y el motor no aplica efectos al atacante.
- Efectos que ignoran los límites suaves o fijan la velocidad, y bonificaciones condicionales o temporales (fuera de combate, por la jungla, activas).
