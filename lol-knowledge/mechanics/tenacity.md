# Tenacidad

- **Ámbito:** regla general de la tenacidad de un campeón: qué reduce, cómo se combinan sus fuentes y su tope. La usa la hoja de estadísticas (`python -m lol_knowledge stats`).
- **Parche de referencia:** Data Dragon 16.22.1 (2026-11-16).
- **Fecha de consulta:** 2026-11-16

## Fuentes

| Id | Fuente | Qué cubre | Naturaleza |
|---|---|---|---|
| T1 | LoL Fandom Wiki, `Tenacity` (versión de hace unos 109 días según el buscador), extracto del buscador consultado el 2026-11-16 (CC BY-SA); la página no se pudo abrir | Las fuentes se combinan de forma multiplicativa o aditiva según el grupo: dentro de un grupo, multiplicativa; entre grupos, aditiva. Grupo A: Elixir de hierro, Botas de mercurio, Calibrador de Sterak, Final del ingenio, fragmento de tenacidad y resistencia a ralentizaciones, Plaga Quimtech. Grupo C: Fragilidad (reduce la tenacidad) | Fuente comunitaria secundaria |
| T2 | LoL Fandom Wiki, `Tenacity_(stat)` (edición en chino), extracto del buscador consultado el 2026-11-16 | Reduce la duración de cegueras, acciones forzadas (encanto, terror, miedo, provocación), pacificación, silencio, ralentización y aturdimiento; no reduce el aire (empujes, derribos, atracciones), la reducción de velocidad de ataque ni la supresión. Con X de tenacidad, la duración baja un X % | Fuente comunitaria secundaria |
| T3 | Data Dragon 16.22.1, objeto 3111 (Botas de mercurio), `data/current/items.json` | «30% de tenacidad» solo en la descripción; Data Dragon no la trae en `stats` | Oficial de Riot |
| T4 | Guías comunitarias (`dodge.gg`, guía de botas 2026; `esports.net`; `eloboost24.eu`), consultadas el 2026-11-16 | Botas de mercurio (30 %) y Legend: Tenacidad (20 %) dan 1 − 0,7 × 0,8 = 44 %; tope de 100 %; duración mínima de 0,3 s | Fuentes secundarias de menor calidad; solo corroboran T1 |

**Discrepancia registrada:** una guía (`eloking.com`) dice que Botas de mercurio y Calibrador de Sterak se suman. T1 los pone a los dos en el grupo A, que se multiplica. Se sigue a T1, que es la wiki y es más reciente.

## Regla (`Derivado`, T1; dato de las Botas de mercurio `Oficial`, T3)

```text
tenacidad_grupo = 1 − Π (1 − t_i)        para las fuentes t_i de un mismo grupo
tenacidad = Σ tenacidad_grupo            sumando los grupos A, B y C
duración del control = duración × (1 − tenacidad)
```

- **Objetos:** todos los objetos con tenacidad que cita T1 están en el grupo A, así que entre objetos se multiplica. Botas de mercurio sola: 30 %.
- **Grupo B (`Pendiente de verificación`):** el extracto de T1 no lista sus fuentes. Las runas como Legend: Tenacidad aparecen en las guías, pero sin grupo confirmado.
- **Grupo C:** reducciones de tenacidad sobre el objetivo, como Fragilidad. El motor no aplica efectos al atacante.
- **Tope:** 100 % según T4. Con fuentes del grupo A entre 0 y 100 %, el producto nunca lo supera.
- **Qué no reduce (T2):** aire (empujes, derribos, atracciones), reducción de velocidad de ataque y supresión. Las guías de T4 añaden somnolencia, visión reducida y estasis.
- **Duración mínima:** 0,3 s según T4. No afecta a la estadística.

## Implementación (`Calculado`)

- `src/lol_knowledge/stats/registry.py` declara `tenacity` como fracción **multiplicativa**: todas sus fuentes se tratan como grupo A, que es el grupo de todos los objetos según T1.
- Los aportes que no vienen de objetos (por ejemplo, la pasiva de un kit) se multiplican también, pero quedan `Pendiente de verificación` con la nota `stacking group not declared`, porque su grupo no está documentado. El grupo B y la suma entre grupos no están modelados.
- El [catálogo de objetos](../objects/catalog.json) admite `tenacity` (`kind: percent`) desde la descripción y declara las Botas de mercurio (3111) con su 30 %.
- Pruebas: `tests/test_stats_tenacity.py`, `tests/test_objects_model.py` y `tests/test_objects_validator.py`.

## Fuera de alcance

- **Reducción de duraciones:** la rotación no modela el tiempo ni los controles, así que la tenacidad no cambia ningún cálculo de daño.
- **Resistencia a ralentizaciones:** es otra estadística (el fragmento de T1 da ambas); no está modelada.
- Tenacidad condicional o temporal de objetos (Calibrador de Sterak, Final del ingenio), elixires, runas y habilidades.
