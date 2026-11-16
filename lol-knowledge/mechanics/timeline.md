# Línea de tiempo de las rotaciones

- **Ámbito:** `python -m lol_knowledge rotation --timeline`: cada paso tiene un momento, en segundos desde el inicio de la rotación.
- **Fecha:** 2026-11-16 (fase 29, primera de la línea de tiempo; fase 30, quemaduras en el tiempo y efectos con duración; fase 31, Ráfaga de Yun Tal y ventanas de acumulaciones y de Hoja encantada).

## Decisiones del usuario (2026-11-16)

1. **Tiempos mixtos:** el motor encadena los pasos lo antes posible, y el usuario puede intercalar esperas (`wait:<segundos>`).
2. **Enfriamientos:** lanzar una habilidad en enfriamiento es un **error**, no una espera automática.
3. **Acumulaciones al máximo:** se mantienen como opción para simular a mitad de partida, pero solo para acumulaciones permanentes. Las temporales que solo existen en combate empiezan siempre en 0 (decisión de la fase 32, [`combat-stacks.md`](combat-stacks.md)).
4. **Lo que no tiene datos se ignora** y queda declarado: tiempos de lanzamiento de las habilidades, la animación previa al golpe de los ataques y el viaje de los proyectiles.

## Decisiones del usuario (fase 30, 2026-11-16)

5. **Quemaduras continuas:** su daño se reparte de forma continua en el tiempo, sin tics. El cliente da un tic cada 0,5 s para Liandry, Antorcha y Cenizas (`TickFrequency`), pero no para Malignidad ni Zeke, ni si el primer tic cae al aplicarla; el total es el mismo.
6. **El daño posterior cuenta:** la rotación termina cuando se apaga la última quemadura; la duración y el daño por segundo lo incluyen.
7. **Efectos con duración de esta fase:** la marca de Tonada sanguina, la reducción de resistencia mágica de Malignidad, la letalidad de la Espada ciclovoltaica y Fuego negro de la Antorcha. La Ráfaga de Yun Tal queda para otra fase: cambia la velocidad de ataque y su enfriamiento se reduce al atacar.

## Fuentes de la fase 31

| Id | Fuente | Qué cubre | Naturaleza |
|---|---|---|---|
| T1 | Data Dragon 16.22.1, Flechas de los Yun Tal: «Al atacar a un campeón enemigo, obtienes un 30% de velocidad de ataque durante 6 s (30 s de enfriamiento).» | Ráfaga | Oficial de Riot |
| T2 | Cliente 16.22, [`../derived/item-effects.json`](../derived/item-effects.json), objeto 3032: `ASMod` 0,3, `ASDuration` 6, `Cooldown` 30, `AACDR` 1, `CritCDR` 2 («Los ataques reducen este enfriamiento en 1 s, que aumenta hasta 2 s en el caso de los impactos críticos») | Reducción del enfriamiento | `Derivado` |
| T3 | Notas recopiladas de 26.15 (riftpatchnotes.com, Yun Tal Wildarrows): «Launching a basic attack against an enemy champion grants you 30% bonus attack speed for 6 seconds (30 second cooldown, reduced by 1 second on-hit and 2 seconds if the attack critically strikes)» | La Ráfaga se activa al lanzar el ataque y la reducción llega al impactar | Fuente secundaria |
| T4 | Cliente 16.22, objetos 6672 y 3181: `BuffDuration` 4 (Kraken) y la ventana de 10 s de Rompecascos, ya en el catálogo (`stacks.window_seconds`) | Ventanas de acumulaciones | `Derivado` |
| T5 | LoL Wiki, `Kraken_Slayer` (consulta del 2026-11-16): las acumulaciones se renuevan al atacar estructuras; no dice si se renuevan contra campeones. Su texto (3 s, 2 acumulaciones) es anterior al cliente 16.22 | Renovación de las acumulaciones | Fuente secundaria |
| T6 | LoL Wiki, `Dusk_and_Dawn`, revisión 4015331: «your next basic attack within 10 seconds» | Ventana de Hoja encantada | Fuente secundaria |

## Decisiones del usuario (fase 31, 2026-11-16)

8. Implementar la Ráfaga de Yun Tal, la ventana de acumulaciones de Kraken y la ventana de 10 s de Hoja encantada. La regla de las ventanas es la misma para todos los contadores que declaran `stacks.window_seconds`, así que también se aplica a Rompecascos.

## Regla (`Calculado`)

1. **Ataques:** un ataque empieza en cuanto el reloj llega al siguiente ataque disponible; el siguiente queda disponible 1 / velocidad de ataque después ([`attack-speed.md`](attack-speed.md)), con la velocidad en vigor justo después del ataque (la de la hoja, más la Ráfaga si está activa). El daño del ataque cae en ese mismo instante. El informe da el intervalo con la velocidad de la hoja.
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
9. **Ráfaga de Yun Tal** (T1-T3): al lanzar un ataque contra un campeón, +30 % de velocidad de ataque adicional durante 6 s, multiplicada por el ratio de velocidad de ataque del campeón como cualquier bonificación ([`attack-speed.md`](attack-speed.md)). El enfriamiento de 30 s empieza al activarse; cada ataque que impacta mientras corre le resta 1 s (2 s si es crítico), **incluido el que la activó**, porque su impacto llega después del lanzamiento (T3). No se reactiva mientras dura el enfriamiento. Como no consta si el juego recalcula el tiempo hasta el siguiente ataque cuando cambia la velocidad de ataque entre dos ataques, una rotación en la que la Ráfaga se activa queda `Pendiente de verificación`.
10. **Ventanas de acumulaciones** (T4, T5): un contador con `stacks.window_seconds` vuelve a cero si el ataque llega esa ventana o más tarde después del ataque anterior (4 s en Kraken, 10 s en Rompecascos); cada ataque renueva las acumulaciones, como da a entender T5. El paso en el que caducan queda `Pendiente de verificación`. Los contadores sin ventana (impactos fantasma de Guinsoo) no caducan.
11. **Ventana de Hoja encantada** (T6): la carga dura 10 s desde la última habilidad que la cargó; un ataque posterior no se potencia, pierde la carga y queda `Pendiente de verificación`. Lanzar otra habilidad mientras hay carga la renueva.

## Pendiente (fases siguientes)

- Los impactos fantasma de Guinsoo como acumulación extra del Kraken (T5).
