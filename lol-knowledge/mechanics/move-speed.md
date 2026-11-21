# Velocidad de movimiento

- **Ámbito:** regla general de la velocidad de movimiento de un campeón: base, aportes planos y porcentuales, y límites suaves. La usa la hoja de estadísticas (`python -m lol_knowledge stats`).
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
- **Cassiopeia (`Derivado`, `CassiopeiaPassive.mSpellCalculations.PercentHasteMod` en el cliente `16.23`):** su pasiva *Elegancia serpentina* aumenta la eficacia de todas las bonificaciones planas y porcentuales de velocidad de movimiento en `5 % + 1,8 % × (nivel − 1)` (`5 %` a nivel 1 hasta `35,6 %` a nivel 18). Sin bonificaciones de velocidad de movimiento, su velocidad base (`335`) permanece `Oficial`.
- **Hecarim (`Derivado`, `Characters/Hecarim/Spells/HecarimPassiveAbility/HecarimPassive` en el cliente `16.23.8406595+branch.releases-16-23.content.release`):** su pasiva *Sendero de guerra* convierte un porcentaje de la velocidad de movimiento adicional **efectiva** (tras porcentajes y límites suaves: `max(0, total − base)`) en DA adicional según el nivel: `12 %` (niveles 1–2), `14 %` (3–5), `16 %` (6–8), `18 %` (9–11), `20 %` (12–14), `22 %` (15–17) y `24 %` (nivel 18). Sin velocidad de movimiento adicional, su DA base permanece `Oficial`.
- **Janna (`Derivado`, `TailwindSelf` / `Zephyr` en el cliente `16.23`):** su pasiva *Empuje* y su W *Céfiro* leen igualmente la velocidad de movimiento adicional efectiva poslímite suave (`max(0, total − base)`).
- **Marcha veloz (`data:item:3170`, `Fervor noxiano`, `Oficial` en el texto del objeto + regla de fuerza adaptable `Derivado` de `lol-knowledge/mechanics/runes.md`):** otorga un `5 %` de la velocidad de movimiento total (poslímite suave) como fuerza adaptable (`0,6` DA adicional o `1,0` PH por punto), antes de los amplificadores finales (como Sombrero mortal de Rabadon o la pasiva de Jhin).

## Implementación (`Calculado`)

- `src/lol_knowledge/stats/registry.py` declara `move_speed` como cantidad aditiva con `percent_of: flat` y `soft_cap` (`move_speed_soft_cap`, con aritmética exacta: 0,8 = 4/5).
- La hoja aplica los porcentajes al final, cuando ya conoce todos los aportes planos (base, objetos y efectos), así que el orden de los objetos no importa. Cada porcentaje se convierte en una cantidad con la nota `10% of flat 390` y una etiqueta que nunca es más fuerte que la de los aportes planos.
- El total aplica el límite suave; `base` y `bonus` en el desglose de `StatValue` quedan en bruto, mientras que las fórmulas de kits (`sheet_stats`) y las conversiones desde velocidad de movimiento (*Sendero de guerra* de Hecarim, *Empuje/Céfiro* de Janna y *Fervor noxiano* de `3170`) leen los valores efectivos poslímite suave. Si el límite cambia el total, el texto añade `(soft cap from 429)`, el JSON trae `raw` y `soft_capped`, y la etiqueta baja como mucho a `Derivado`, porque la regla viene de fuentes secundarias.
- En rotaciones con `--timeline`, los efectos temporales de velocidad de movimiento de objetos (`3078` Trinidad, `3044` Bacteriófago, `3071` Cuchilla negra, `4629` Impulso cósmico, `3073` Hexarmadura, `3095` Navaja de asalto y `3171` Lucidez carmesí) se aplican dinámicamente mediante `with_bonus` / `with_percent_bonus`, recomputando porcentajes, límites suaves y las conversiones de Hecarim, Janna y `3170`. Sin `--timeline`, omitir una bonificación temporal de velocidad de movimiento solo degrada la etiqueta a `Pendiente de verificación` cuando el campeón o la build escalan daño con velocidad de movimiento.
- Pruebas: `tests/test_stats_move_speed.py`, `tests/test_move_speed_damage.py` y, con objetos reales (Bailarín espectral: 10 % con Botas de mercurio), `tests/test_stats_real_items.py`. Una de las mutaciones (`> 490` frente a `>= 490`) es equivalente: las dos fórmulas dan 475 justo en 490.

## Fuera de alcance

- **Aportes multiplicativos** (unos pocos efectos según M3) y **ralentizaciones** (solo cuenta la mayor y se reduce con la resistencia a ralentizaciones): ningún efecto curado del catálogo los tiene.
- Efectos que ignoran los límites suaves o fijan la velocidad, y bonificaciones fuera de combate, por activas o defensivas acumulables (como `3142` Filo fantasmal de Youmuu, `3742` Coraza del hombre muerto, `2065` Shurelya, `3139` Cimitarra mercurial o `4401` Fuerza de la naturaleza).
