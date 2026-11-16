# Línea de tiempo de las rotaciones

- **Ámbito:** `python -m lol_knowledge rotation --timeline`: cada paso tiene un momento, en segundos desde el inicio de la rotación.
- **Fecha:** 2026-11-16 (fase 29, primera de la línea de tiempo; fase 30, quemaduras en el tiempo y efectos con duración).

## Decisiones del usuario (2026-11-16)

1. **Tiempos mixtos:** el motor encadena los pasos lo antes posible, y el usuario puede intercalar esperas (`wait:<segundos>`).
2. **Enfriamientos:** lanzar una habilidad en enfriamiento es un **error**, no una espera automática.
3. **Acumulaciones al máximo:** se mantendrán como opción para simular a mitad de partida cuando la línea de tiempo calcule las acumulaciones (fase posterior). Hoy los escenarios `max_stacks` siguen aplicándose al máximo.
4. **Lo que no tiene datos se ignora** y queda declarado: tiempos de lanzamiento de las habilidades, la animación previa al golpe de los ataques y el viaje de los proyectiles.

## Decisiones del usuario (fase 30, 2026-11-16)

5. **Quemaduras continuas:** su daño se reparte de forma continua en el tiempo, sin tics. El cliente da un tic cada 0,5 s para Liandry, Antorcha y Cenizas (`TickFrequency`), pero no para Malignidad ni Zeke, ni si el primer tic cae al aplicarla; el total es el mismo.
6. **El daño posterior cuenta:** la rotación termina cuando se apaga la última quemadura; la duración y el daño por segundo lo incluyen.
7. **Efectos con duración de esta fase:** la marca de Tonada sanguina, la reducción de resistencia mágica de Malignidad, la letalidad de la Espada ciclovoltaica y Fuego negro de la Antorcha. La Ráfaga de Yun Tal queda para otra fase: cambia la velocidad de ataque y su enfriamiento se reduce al atacar.

## Regla (`Calculado`)

1. **Ataques:** un ataque empieza en cuanto el reloj llega al siguiente ataque disponible; el siguiente queda disponible 1 / velocidad de ataque después (velocidad de ataque de la hoja, [`attack-speed.md`](attack-speed.md)). El daño del ataque cae en ese mismo instante.
2. **Habilidades:** son instantáneas: no avanzan el reloj ni esperan al ataque. Su enfriamiento empieza al lanzarlas y vale lo que da la hoja con la aceleración de habilidades ([`ability-haste.md`](ability-haste.md)) para el rango aprendido.
3. **Reactivaciones:** un caso del kit marcado `recast` no inicia enfriamiento; exige un lanzamiento previo sin reactivar y, si el kit declara `recast_window_seconds`, que no haya pasado esa ventana (Zaahen Q: 4 s, de [`../champions/Zaahen/abilities.md`](../champions/Zaahen/abilities.md)).
4. **Esperas:** `wait:<segundos>` avanza el reloj; sin `--timeline` es un error.
5. **Hoja encantada:** con la línea de tiempo, su recarga de 1,5 s (del catálogo) se respeta: una habilidad lanzada durante la recarga no carga el siguiente ataque ([`spellblade.md`](spellblade.md)).
6. **Duración y daño por segundo:** la duración es el momento del último paso, o el final de la última quemadura si es posterior (paso final `burns`); el daño por segundo es el daño total entre esa duración (no se da si la duración es 0).
7. **Quemaduras en el tiempo** ([`burns.md`](burns.md)): una quemadura empieza en el paso que la aplica y hace su daño por segundo de forma continua hasta que acaba; aplicarla otra vez reinicia su duración. El daño acumulado desde el paso anterior se suma al principio de cada paso (también de las esperas), en tramos que se cortan cuando acaba una quemadura o un efecto con duración, y cada tramo se mitiga y se amplifica con lo que esté en vigor. El daño por segundo es el del momento en que se aplicó; si las estadísticas cambian después (Fuego negro), el tramo queda `Pendiente de verificación`, porque no se sabe si el juego lo actualiza.
8. **Efectos con duración:** empiezan después del daño del paso que los dispara y duran su `duration_seconds`; dispararlos otra vez reinicia la duración. Su valor se calcula al dispararse.
   - Sobre el atacante (letalidad de la Ciclovoltaica, Fuego negro): se suman a la hoja mientras duran. Un porcentaje del total se calcula sobre el total sin otros amplificadores, como hace la hoja; junto a otro amplificador (Rabadon), queda `Pendiente de verificación`.
   - Sobre el daño (marca de Tonada sanguina): un aumento de daño infligido más, que se suma a los demás.
   - Sobre el objetivo (Malignidad): una reducción plana de su resistencia, que se aplica antes de la penetración ([`damage-mitigation.md`](damage-mitigation.md)). Se supone que el objetivo se queda en la niebla, como ya se supone para su quemadura.
   - Si el disparador es un golpe (Hoja encantada, Vigor), no se sabe si ese golpe ya se beneficia: el paso que lo dispara queda `Pendiente de verificación`.
   - Sin `--timeline`, estos efectos no se aplican; se listan y, si pueden afectar al objetivo, la rotación queda `Pendiente de verificación`.

## Pendiente (fases siguientes)

- La Ráfaga de Yun Tal (velocidad de ataque temporal con enfriamiento que reducen los ataques).
- Ventanas de acumulaciones (Kraken, Rompecascos) y la ventana de 10 s de Hoja encantada.
- Acumulaciones calculadas (Guinsoo, Liandry, Disfraz encantado, El final), con «al máximo» como opción.
