# Simulador de duelo 1v1 determinista (`duel`)

- **Parche:** `16.23.1` (`data/current/manifest.json`)
- **Etiqueta del motor:** `Calculado` sobre entradas `Oficial` / `Derivado` (propaga la etiqueta más débil; las partes no modeladas se declaran explícitamente)
- **Código:** [`src/lol_knowledge/duel.py`](../../src/lol_knowledge/duel.py), [`src/lol_knowledge/duel_report.py`](../../src/lol_knowledge/duel_report.py), [`src/lol_knowledge/rotation.py`](../../src/lol_knowledge/rotation.py) y [`src/lol_knowledge/defense.py`](../../src/lol_knowledge/defense.py)
- **Fecha de consulta / actualización:** 2026-11-25
- **Limitación:** el simulador modela combate 1v1 cuerpo a cuerpo o a distancia sobre una línea de tiempo determinista de eventos discretos (`Fraction` exacto). **No** modela posicionamiento espacial, kiting, colisiones/fallo de *skillshots*, tiempos de animación de lanzamiento ni bloqueos de control de masas (*stun*/*silence*/*suppress*).

## 1. Arquitectura acoplada sin doble conteo (`Calculado`)

Cada combatiente (`A` y `B`) mantiene dos sesiones acopladas sobre un único reloj exacto `clock: Fraction`:

1. **`RotationSession` (ofensiva, en [`rotation.py`](../../src/lol_knowledge/rotation.py)):** calcula cada paso de ataque, habilidad, activa de objeto o hechizo de invocador frente a la fotografía viva de resistencias, vida y escudo del rival (`DefenseSession.target_snapshot(t)`). Mantiene penetraciones, acumulaciones (*Conquistador*, *Compás letal*, *Cuchilla negra*, pasivas), quemaduras (*Prender*, *Liandry*, *Antorcha*, *Égida*), recursos (maná/energía/coste de vida) y esteroides ofensivos activos.
2. **`DefenseSession` (defensiva, en [`defense.py`](../../src/lol_knowledge/defense.py)):** mantiene la vida viva, vida máxima temporal, escudos con caducidad, reducciones de daño activas (`Alistar R`, `Leona W`, `Irelia W`, etc.), esquiva de ataques básicos (`Jax E`, `Shen W`, `Nilah W`), escudo de hechizos (`Sivir E`, `Nocturne W`), bloqueo de primer golpe (`Braum E`), invulnerabilidad e inmortalidad (`Kayle R`, `Tryndamere R`, `Kindred R`, `Taric R`, `Fiora W`), daño reciente almacenado (`Sett W`, `Mordekaiser W`, `Rengar W`, `Tahm Kench E`), *Revestimiento de huesos*, *Fuerzas renovadas*, *Salvavidas*, *Baile de la muerte*, *Malla de espinas* (reflejo + Heridas graves), *Ángel de la guarda* (estasis de 4 s + resurrección) y defensivos de invocador (*Barrera*, *Curar*, *Limpiar*).

Reglas de acoplamiento exacto:

- Las partes emitidas por `RotationSession` entran en la `DefenseSession` del rival con `already_mitigated=True, resistances_already_live=True` para no aplicar armadura ni resistencia mágica dos veces.
- El robo de vida, el omnivampirismo y las curaciones por daño infligido (`damage_dealt_heal`, p. ej. `Warwick Q`, `Briar W`) se escalan proporcionalmente al daño efectivo real tras reducciones/negaciones del defensor (`0` contra esquiva, invulnerabilidad o bloqueo de primer impacto) y se aplican por `DefenseSession.apply_self_survival(...)`, aplicando *Heridas graves* y *Rostro espiritual* una única vez.
- Todo escudo otorgado a un combatiente notifica a su `RotationSession` para armar *Golpe de escudo* (`8401`).
- *Extenuación* (`SummonerExhaust`) reduce en 35 % el daño no verdadero del rival durante 3 s; *Limpiar* (`SummonerBoost`) elimina la *Extenuación* activa.
- *Malla de espinas* (`3075`) devuelve daño mágico real a la `DefenseSession` del atacante y le aplica 3 s de *Heridas graves* antes de resolver su robo de vida.
- Durante los 4 s de estasis de *Ángel de la guarda* (`3026`), el campeón no puede ejecutar acciones y los impactos entrantes infligen `0` de daño hasta su resurrección.

## 2. Modos de acción (`--mode`)

| Modo | Comportamiento |
|---|---|
| `scripted_then_attack` *(por defecto)* | Ejecuta los pasos indicados (`--a-steps` / `--b-steps`) y luego continúa atacando con ataques básicos cada `1 / velocidad de ataque` hasta la muerte o `max_duration`. |
| `strict_scripted` | Ejecuta únicamente los pasos indicados y sus quemaduras/efectos diferidos pendientes. Si ambos sobreviven, termina en `draw_timeout`. |
| `priority_loop` | Tras cualquier paso inicial, lanza automáticamente las habilidades aprendidas listas y pagables según orden de prioridad (`R,Q,W,E` por defecto) e intercala ataques básicos. |

## 3. Desempate en marcas de tiempo idénticas (`--tie-break`)

| Regla | Comportamiento |
|---|---|
| `simultaneous` *(por defecto)* | Garantiza la invariante de simetría exacta `duel(A, B) == espejo(duel(B, A))`. En empates al mismo instante `t`: (1) ambos activan defensivos/hechizos de `t`, (2) ambos evalúan su ataque/habilidad contra las fotografías previas al golpe, (3) se entregan ambos impactos, reflejos y curaciones. Un espejo idéntico termina siempre en `draw_mutual_kill` o empate idéntico en `draw_timeout`. |
| `a_first` | `A` resuelve su acción completa antes que `B`; si `B` muere (o entra en estasis), `B` no ejecuta su acción en ese instante. |
| `b_first` | Inverso de `a_first`: `B` resuelve antes que `A`. |

## 4. Superficies disponibles y optimización

- **CLI:** `python -m lol_knowledge duel --a-champion ... --b-champion ... [--mode ...] [--tie-break ...] [--max-duration 30] [--json]`
- **Contrato JSON (`lol-knowledge-contract/1`):** operación `"duel"` en [`contract.py`](../../src/lol_knowledge/contract.py)
- **Servidor MCP local:** herramienta `lol_duel` en [`mcp_server.py`](../../src/lol_knowledge/mcp_server.py)
- **Optimizador de builds (`--objective duel`):** evalúa cada build candidata mediante duelo completo 1v1 contra el rival especificado (`--enemy-champion` / `enemy`), priorizando victoria con mayor % de vida restante y menor duración sobre empates y derrotas más largas (`verified_builds` separado de `pending_builds`).
