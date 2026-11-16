# Línea de tiempo de las rotaciones

- **Ámbito:** `python -m lol_knowledge rotation --timeline`: cada paso tiene un momento, en segundos desde el inicio de la rotación.
- **Fecha:** 2026-11-16 (fase 29, primera de la línea de tiempo).

## Decisiones del usuario (2026-11-16)

1. **Tiempos mixtos:** el motor encadena los pasos lo antes posible, y el usuario puede intercalar esperas (`wait:<segundos>`).
2. **Enfriamientos:** lanzar una habilidad en enfriamiento es un **error**, no una espera automática.
3. **Acumulaciones al máximo:** se mantendrán como opción para simular a mitad de partida cuando la línea de tiempo calcule las acumulaciones (fase posterior). Hoy los escenarios `max_stacks` siguen aplicándose al máximo.
4. **Lo que no tiene datos se ignora** y queda declarado: tiempos de lanzamiento de las habilidades, la animación previa al golpe de los ataques y el viaje de los proyectiles.

## Regla (`Calculado`)

1. **Ataques:** un ataque empieza en cuanto el reloj llega al siguiente ataque disponible; el siguiente queda disponible 1 / velocidad de ataque después (velocidad de ataque de la hoja, [`attack-speed.md`](attack-speed.md)). El daño del ataque cae en ese mismo instante.
2. **Habilidades:** son instantáneas: no avanzan el reloj ni esperan al ataque. Su enfriamiento empieza al lanzarlas y vale lo que da la hoja con la aceleración de habilidades ([`ability-haste.md`](ability-haste.md)) para el rango aprendido.
3. **Reactivaciones:** un caso del kit marcado `recast` no inicia enfriamiento; exige un lanzamiento previo sin reactivar y, si el kit declara `recast_window_seconds`, que no haya pasado esa ventana (Zaahen Q: 4 s, de [`../champions/Zaahen/abilities.md`](../champions/Zaahen/abilities.md)).
4. **Esperas:** `wait:<segundos>` avanza el reloj; sin `--timeline` es un error.
5. **Hoja encantada:** con la línea de tiempo, su recarga de 1,5 s (del catálogo) se respeta: una habilidad lanzada durante la recarga no carga el siguiente ataque ([`spellblade.md`](spellblade.md)).
6. **Duración y daño por segundo:** la duración es el momento del último paso; el daño por segundo es el daño total entre esa duración (no se da si la duración es 0). Las quemaduras se siguen contando enteras ([`burns.md`](burns.md)), así que el daño por segundo incluye su daño posterior.

## Pendiente (fases siguientes)

- Duraciones de efectos (Ráfaga, letalidad de la Ciclovoltaica, Fuego negro, reducción de resistencia de Malignidad, marca de Tonada sanguina) y quemaduras con tics.
- Ventanas de acumulaciones (Kraken, Rompecascos) y la ventana de 10 s de Hoja encantada.
- Acumulaciones calculadas (Guinsoo, Liandry, Disfraz encantado, El final), con «al máximo» como opción.
