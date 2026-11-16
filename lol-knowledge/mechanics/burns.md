# Quemaduras y amplificadores por tiempo en combate

- **Ámbito:** daño a lo largo del tiempo de objetos (quemaduras) y aumentos de daño que crecen con los segundos en combate. Los usa `python -m lol_knowledge rotation`.
- **Parche de referencia:** cliente 16.22 y Data Dragon 16.22.1.
- **Fecha de consulta:** 2026-11-16

## Fuentes

| Id | Fuente | Qué cubre | Naturaleza |
|---|---|---|---|
| B1 | Data Dragon 16.22.1: Tormento de Liandry, Antorcha de fuego negro, Cenizas predestinadas, Malignidad, Convergencia de Zeke, Disfraz encantado | Disparador, duración y, cuando la da, la cifra | Oficial de Riot |
| B2 | Cliente 16.22: [`../derived/item-effects.json`](../derived/item-effects.json) | Cifras que Data Dragon omite: Antorcha 20 (+2 % de AP) por segundo (40 contra monstruos), Cenizas 5 por segundo, Malignidad 60 (+5 % de AP) por segundo y −10 de resistencia mágica, tope de Liandry contra monstruos (40) | `Derivado` |
| B3 | Regla del motor sobre el omnivampirismo: 33 % contra súbditos y monstruos para el daño a lo largo del tiempo ([`life-steal-and-omnivamp.md`](life-steal-and-omnivamp.md)) | Curación de las quemaduras | Ya documentada |

## Regla del motor (`Calculado`; decisiones del usuario del 2026-11-16)

1. **Quemadura entera:** el daño por segundo × la duración se suma como una sola parte `burn` en el paso que la inicia, con su tipo de daño, su mitigación y los modificadores de daño (Llamasombría incluida).
2. **Una por rotación:** reaplicar una quemadura reinicia su duración en el juego; sin tiempo, se cuenta **una sola quemadura completa por efecto y rotación** (decisión del usuario).
3. **Disparadores:** `damaging_ability` (la primera habilidad que hace daño en el paso) y `cast` (la primera habilidad lanzada, haga o no daño). La condición `ultimate_ability` exige que sea la R.
4. **Tipos de objetivo:** cuando el efecto cambia contra súbditos o monstruos, el catálogo declara un efecto por tipo de objetivo. El tope de Liandry contra monstruos no se aplica porque no está claro si es por tic o por segundo; contra un monstruo, la rotación queda `Pendiente de verificación`.
5. **Curación:** las quemaduras no aplican robo de vida; el omnivampirismo cura un 33 % contra súbditos y monstruos y un 100 % contra campeones.
6. **Amplificadores por tiempo en combate** (Sufrimiento de Liandry, Locura del Disfraz encantado): se aplican **al máximo** (+6 %) contra campeones, como el resto de acumulaciones (escenario `max_stacks`).

## Sin aplicar

- Fuego negro de la Antorcha (+4 % de AP mientras dura la quemadura) y la reducción de resistencia mágica de Malignidad: dependen del tiempo; con un campeón como objetivo, la rotación queda `Pendiente de verificación`.
- Las ralentizaciones y la activa de Malignidad (está en el texto del cliente, no en la descripción de Data Dragon).
- Las auras que queman alrededor (Égida de fuego solar, Rescoldo de Bami, Fulgor vano): pendientes.
