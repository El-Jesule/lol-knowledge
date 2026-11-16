# Acumulaciones en combate

- **Ámbito:** acumulaciones de objetos que caducan o que solo existen en combate. Las calcula `python -m lol_knowledge rotation`; la hoja de estadísticas (`stats`) no las incluye.
- **Parche de referencia:** cliente 16.22 y Data Dragon 16.22.1.
- **Fecha:** 2026-11-16 (fase 32).

## Decisiones del usuario (2026-11-16)

1. **Desde 0:** los objetos cuyas acumulaciones son temporales y solo existen en combate **nunca empiezan al máximo**, sino en 0. El escenario `max_stacks` («al máximo», para simular a mitad de partida) queda solo para las acumulaciones permanentes: hoy, la probabilidad de crítico de las Flechas de los Yun Tal.
2. **El final empieza luminoso:** ninguna fuente dice con qué golpe empieza la alternancia; el primero es luminoso, y lo que dependa del orden queda `Pendiente de verificación`.
3. **Impactos fantasma de Guinsoo:** el ataque que completa las 4 acumulaciones ya cuenta para el tercer ataque.
4. **Sin `--timeline`:** las acumulaciones por ataque se cuentan igual, desde 0 y sin caducar; las que crecen por segundos se quedan en 0, y la rotación contra un campeón queda `Pendiente de verificación`.
5. **Segundos en combate:** se cuentan desde el inicio de la rotación, porque el combate ya empezó cuando el campeón recibió daño.

## Fuentes

| Id | Fuente | Qué cubre | Naturaleza |
|---|---|---|---|
| A1 | Data Dragon 16.22.1: Guinsoo («Los ataques otorgan un 8% de velocidad de ataque durante 4 s (se acumula hasta 4 veces)»), El final, Tormento de Liandry y Disfraz encantado («2% … 6% como máximo … por cada segundo en combate») | Qué da cada acumulación | Oficial de Riot |
| A2 | Cliente 16.22, [`../derived/item-effects.json`](../derived/item-effects.json): Guinsoo `AttackSpeedPerStack` 0,08, `MaxStacks` 4, `BuffDuration` 4 y el texto «Con el máximo de acumulaciones, cada tercer ataque aplica dos veces los efectos al impactar»; El final `PenPerHit` 0,1, `PenMax` 0,3, `BuffDuration` 5 y la armadura por golpe luminoso por nivel; Liandry `DamageIncreasePerSecond` 0,02, `DamageIncreaseMax` 0,06, `MaxStackNumber` 3 | Cifras, topes y duraciones | `Derivado` |
| A3 | Leaguepedia, `Terminus` (historial): «Juxtaposition Stack Cap: 5 each (10 total) ⇒ 3 each (6 total)»; `Guinsoo's_Rageblade`: una nota antigua dice que el ataque que lleva las acumulaciones al máximo se beneficia | Tope de 3 por tipo; el ataque que completa las acumulaciones | Fuente comunitaria secundaria |

## Regla del motor (`Calculado`)

1. **Una acumulación por ataque** (`stacks.required: 1`): cada ataque básico que cumple las condiciones del efecto suma una, hasta `max_stacks`. Cuenta desde el paso siguiente al ataque que la da. Con `--timeline`, las acumulaciones caducan si pasan `stacks.window_seconds` desde el último ataque que sumó una (se renuevan con cada ataque); sin línea de tiempo no caducan.
2. **Guinsoo (Golpe furioso):** +8 % de velocidad de ataque adicional por acumulación, hasta 4 (+32 %), durante 4 s. Con `--timeline` cambia el tiempo hasta el siguiente ataque ([`timeline.md`](timeline.md), regla 1), así que la rotación queda `Pendiente de verificación`, como con la Ráfaga.
3. **Impactos fantasma** (condición `stacks_full`): solo cuentan los ataques hechos con Golpe furioso al máximo, el que lo completa incluido; el tercero repite los efectos al impactar ([`attack-counters.md`](attack-counters.md)). Desde 0, el primero cae en el 6.º ataque. La repetición queda `Pendiente de verificación` (decisión 3, apoyada solo en A3).
4. **El final (Yuxtaposición)** (campo `alternation`): contra campeones, los golpes se alternan, empezando por uno luminoso: luminosos los impares (armadura y resistencia mágica: 6, 7 u 8 por golpe según el nivel) y sombríos los pares (10 % de penetración de armadura y mágica por golpe). Hasta 3 de cada tipo, durante 5 s. Lo que dependa de estas acumulaciones queda `Pendiente de verificación` (decisión 2). Contra otros objetivos no hay alternancia ni acumulaciones.
5. **Por segundo en combate** (disparador `in_combat`; Sufrimiento de Liandry, Locura del Disfraz encantado): +2 % de daño infligido a campeones por **segundo completo** desde el inicio de la rotación, hasta el límite `maximum` (6 %): 0 % antes del segundo 1, 2 % desde el 1, 4 % desde el 2, 6 % desde el 3. Sin línea de tiempo se queda en 0.
6. **Quemaduras:** sus tramos se cortan también donde caducan acumulaciones y en cada segundo completo, si hay un efecto por segundo en combate ([`burns.md`](burns.md)).

## Objetos

| Objeto | Acumulación | Antes (hasta la fase 31) | Ahora |
|---|---|---|---|
| Hoja de furia de Guinsoo (3124) | +8 % de velocidad de ataque, hasta 4, 4 s | Al máximo en la hoja | Desde 0, en la rotación |
| El final (3302) | Golpes luminosos y sombríos, hasta 3 de cada, 5 s | Al máximo en la hoja | Desde 0, alternando desde uno luminoso |
| Tormento de Liandry (6653), Disfraz encantado (3147) | +2 % por segundo en combate, hasta 6 % | +6 % en la rotación | Desde 0, por segundos (solo con `--timeline`) |
| Flechas de los Yun Tal (3032) | +0,4 % de crítico por ataque, permanente | Al máximo en la hoja | Igual: es permanente |

## Fuera de alcance

- Los impactos fantasma como acumulación extra del Kraken (la wiki lo dice, sin cifra para la versión actual).
- La duración de las acumulaciones fantasma de Guinsoo (las fuentes no coinciden: 4 o 6 s); su cuenta no caduca.
- Si la alternancia de El final se reinicia tras salir de combate.
