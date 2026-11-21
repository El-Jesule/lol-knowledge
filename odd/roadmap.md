# Hoja de ruta: todo lo que falta para terminar LoL-Knowledge

- **Fecha:** 2026-11-18
- **Estado de partida:** fase 33 (kit de Ahri), `dev` en `b363a1b`, parche 16.22.1.
- **Avance del 2026-11-19:** fases 34 a 37 (documentación, parche 16.23 con procedimiento repetible, legalidad de builds, runas y fragmentos); `dev` en `85fc4be`, parche 16.23.1.
- **Avance del 2026-11-20:** decisiones `DEC-01` a `DEC-05` cerradas, validación en Windows superada (`OP-02`), CI de GitHub Actions añadido (`OP-03`, `e965d47`), 52 ramas locales integradas eliminadas (`OP-04`), **fases 38–40** (runas menores de estadísticas, combate y piedras angulares ofensivas), **fase 41** (verificación documental `wiki.leagueoflegends.com` + `V26.23`, `{ee18a47b}`, `MEC-13`, `OBJ-06`), **fase 42** (`MEC-04` a `MEC-07`, `heal_and_shield_power`, escudos, Heridas graves, curaciones de efectos) y **fase 43** (`MEC-08` reducción plana, `MEC-09` simulación inversa `survive` con tiempo hasta morir y daño recibido/s, `3053` Calibrador de Sterak y runas `8473`/`8444`/`8465` → **50/62** runas de árbol, cerrando toda la sección 4.2). Siguiente paso: `CH-02` y `CH-03` (automatizar kits y pasivas de campeón).
- **Método:** revisión de `README.md`, `lol-knowledge/` (fichas, reglas de `mechanics/`, `objects/README.md`), `odd/tasks/`, `research/`, los dos `kit.json` (campo `not_modelled`), el catálogo de objetos y los registros derivados. Cada punto cita el archivo donde consta. Si un punto procede de una tarea antigua y no se ha comprobado que siga vigente, se dice.
- **Objetivo final** (descripción del proyecto): a partir de una petición en lenguaje natural («la build de Jax que maximice su burst con AP»), una IA prepara el escenario, el motor determinista calcula y la IA explica el resultado, para cualquier campeón, objeto y runa, con todas las cifras trazables.

Cada punto lleva un identificador para poder citarlo en tareas y commits. Prioridad: **P0** bloquea lo demás, **P1** necesaria para el objetivo final, **P2** mejora la precisión, **P3** opcional.

## 0. Cómo retomar el trabajo

1. Leer [`AGENTS.md`](../AGENTS.md) y esta hoja de ruta.
2. `git status -sb` y `git log --oneline -5` en `dev`. Comparar con el estado de partida de arriba: lo que haya después de `b363a1b` es posterior a esta hoja de ruta.
3. Elegir el siguiente punto abierto con la prioridad más alta (sección 12) y abrir su rama de tarea.
4. Al cerrar una fase, marcar aquí el punto como hecho (`[x]`, con commit) y crear o actualizar su `odd/tasks/<slug>.md`.

## 1. Operativo y repositorio

- [x] **OP-01 (P0)** *Hecho: el 2026-11-19 `dev` e `integration` coinciden con `origin`.* Publicar el trabajo local: `dev` va 8 commits por delante de `origin/dev` e `integration` 125 por delante de `origin/integration`. El entorno del agente no puede hacer push (403); lo hace el usuario con `git push origin dev integration`.
- [x] **OP-02 (P0)** *Hecho el 2026-11-20: las cuatro validaciones de [`AGENTS.md`](../AGENTS.md) §5 y `pytest research/tests -q` pasan en Windows con `.\.venv\Scripts\python.exe` (995 + 216 pruebas, ruff check/format y `validate` con 215 archivos).* Ejecutar las cuatro validaciones de [`AGENTS.md`](../AGENTS.md) §5 en Windows con `.\.venv\Scripts\python.exe`.
- [x] **OP-03 (P2)** *Hecho el 2026-11-20 (`e965d47`, autorizado en DEC-04): flujo [`.github/workflows/ci.yml`](../.github/workflows/ci.yml) en Linux y Windows con Python 3.14.* Integración continua con las cuatro validaciones y la suite de `research/tests/`.
- [x] **OP-04 (P3)** *Hecho el 2026-11-20 (autorizado en DEC-04): eliminadas las 52 ramas locales de tarea tras verificar que tenían 0 commits sin integrar en `dev` (no se tocaron ramas remotas).* Limpiar las ramas de tarea ya integradas.
- [ ] **OP-05 (P2)** Resolver las cuatro cuestiones de [`research/evidence/usage-conditions.md`](../research/evidence/usage-conditions.md): si los recortes de `fixtures/` son redistribuibles, obligaciones de la licencia CC BY-SA 3.0 de la wiki sobre cifras, política de redistribución de CommunityDragon y aviso de no afiliación si el proyecto se publica.

## 2. Deuda de documentación (textos desactualizados)

*Hecho en la fase 34 (rama `docs/refresh-stale-texts`).*

Encontrados en esta revisión. Ninguno cambia cálculos, pero contradicen el estado real.

- [x] **DOC-01 (P1)** [`README.md`](../README.md), sección «Kits de campeón»: dice «Solo existe el kit de Zaahen».
- [x] **DOC-02 (P1)** [`README.md`](../README.md), «Limitaciones conocidas»: dice que `ability` y `rotation` no simulan tiempo ni velocidad de ataque (existe `--timeline` desde la fase 30), «Solo Zaahen tiene kit» y que los efectos están curados en 16 objetos (son 42).
- [x] **DOC-03 (P1)** [`README.md`](../README.md), «Aviso legal», y [`lol-knowledge/INDEX.md`](../lol-knowledge/INDEX.md), «Aviso de fuentes»: atribuyen los valores `Derivado` solo a CommunityDragon y a Zaahen; los de Ahri y los registros de 16.22 salen del cliente instalado.
- [x] **DOC-04 (P1)** [`lol-knowledge/INDEX.md`](../lol-knowledge/INDEX.md), «Cobertura actual»: «un campeón con análisis completo» y «16 objetos».
- [x] **DOC-05 (P1)** [`lol-knowledge/objects/README.md`](../lol-knowledge/objects/README.md) §1, §8 y §10: «simular tiempo», «no hay simulación todavía» y «16 objetos».
- [x] **DOC-06 (P2)** [`lol-knowledge/champions/Zaahen/build.md`](../lol-knowledge/champions/Zaahen/build.md): «Mientras no exista calculadora…». La calculadora existe; lo que falta es resolver sus datos pendientes (CH-Z-01 a CH-Z-03).
- [x] **DOC-07 (P2)** Las tareas antiguas de `odd/tasks/` conservan listas de pendientes ya resueltos (Rabadon, Hoja encantada con tiempo, Kraken por vida perdida…). Basta con una nota «resuelto en fase N» o con remitir a esta hoja de ruta.

## 3. Datos y snapshot

- [x] **DAT-01 (P1)** *Hecho en la fase 35: snapshot 16.23.1 y cliente 16.23 ([revisión](../research/reports/client-16.23.md)).* Actualizar al parche vigente. El snapshot, el catálogo, los registros y los kits son de 16.22.1; `validate` impide aplicar el catálogo a otro parche. Cada actualización exige: `update`, regenerar `catalog-stats.json`, `champion-records.json` e `item-effects.json` desde el cliente, regenerar los kits y revisar los efectos curados contra las notas del parche ([`odd/tasks/snapshot-16-22.md`](tasks/snapshot-16-22.md)).
- [x] **DAT-02 (P1)** *Hecho en la fase 35: [procedimiento](procedures/patch-update.md) y `research/tools/refresh_patch.py`.* Convertir DAT-01 en un procedimiento repetible y documentado (un comando o un guion con pasos y comprobaciones), porque hoy es manual.
- [ ] **DAT-03 (P2)** Registros del cliente sin maná ni regeneración: `champion-records.json` solo trae vida, DA, armadura, RM, velocidad de movimiento, alcance, velocidad de ataque, ratio, crecimientos y multiplicador de crítico ([`odd/tasks/client-records.md`](tasks/client-records.md)). Las regeneraciones del bin van en otra unidad (por segundo).
- [ ] **DAT-04 (P2)** Senna: no tiene el campo de crecimiento de DA en el bin y su DA queda bloqueado por encima del nivel 1 ([`README.md`](../README.md)).
- [ ] **DAT-05 (P3)** Locale: el generador de estadísticas de objetos solo entiende `es_ES` ([`odd/tasks/item-stats.md`](tasks/item-stats.md)).
- [ ] **DAT-06 (P2)** Hechizos de invocador: Data Dragon los publica (`summoner.json`) pero `update` no los descarga ni hay modelo.
- [ ] **DAT-07 (P3)** Formatos del bin sin entender, según [`odd/tasks/bin-diff.md`](tasks/bin-diff.md) e [`odd/tasks/item-client-evidence.md`](tasks/item-client-evidence.md): tipo `0xb5` en `skin0.bin` de Zaahen, entradas de tipo 4 del WAD que `extract_rst.py` se salta y 10 registros ilegibles. No se ha comprobado si siguen vigentes.
- [ ] **DAT-08 (P3)** CommunityDragon devuelve 403 desde el entorno del agente. Ya no bloquea (existe `binmodel/bin2json`), pero impide contrastar exportaciones.

## 4. Motor: mecánicas generales pendientes

### 4.1 Recursos y costes
- [x] **MEC-01 (P1)** *Hecho en la fase 44 (2026-11-20): costes oficiales por rango en `SpellData` (los 173 campeones de Data Dragon `16.23.1`), `CostSpec` opcional en `kit.json` para costes de vida o excepciones (reactivaciones gratuitas), seguimiento de reserva y regeneración continua en `rotation` (`src/lol_knowledge/resources.py`, `--attacker-resource`, `--allow-insufficient-resource`), tics cada 5 s de `8226` Banda de maná en `--timeline`, `8009` Claridad mental (`PresenceOfMind`: tabla 1–18 `6..44` maná / `× 0,8` a distancia / `6` energía / `8 s` CD / `15 %` al derribar) y costes de vida con suelo en `1` de vida (`Health` rev `4073062`); ver [`resources.md`](../lol-knowledge/mechanics/resources.md).* Coste de las habilidades (maná, energía, vida) y maná disponible en una rotación.
- [x] **MEC-02 (P2)** *Hecho en la fase 44 (2026-11-20): métrica `champion_resource(sheet)` (`metrics.resource`) y `ability_costs(sheet)` (`metrics.ability_costs`) en `stats`, cubriendo energía fija (`200` / `400` en Shen, `50/5 s` inmune a objetos de maná, `Energy` rev `4073066`), campeones sin reserva y recursos secundarios, manteniendo bloqueadas `mana`/`mana_regen` cuando el campeón no usa maná; ver [`resources.md`](../lol-knowledge/mechanics/resources.md).* Recursos distintos del maná.
- [x] **MEC-03 (P2)** *Hecho en la fase 44 (2026-11-20): componente `resource_restore` en `catalog.json` v22 para `3508` Segador de esencia (`0,5 × SpellbladeDamage = 62,5 % DA base + 25 × crítico`, previo a mitigación, cliente `16.23` corroborado por `Module:ItemData/data` rev `4095269`); ver [`spellblade.md`](../lol-knowledge/mechanics/spellblade.md) y [`resources.md`](../lol-knowledge/mechanics/resources.md).* Devolución de maná de Segador de esencia.

### 4.2 Defensa y supervivencia
El motor debe servir también para vida, resistencias, curación y supervivencia, no solo para daño.
- [x] **MEC-04 (P1)** *Hecho en la fase 42 (2026-11-20): escudos del objetivo (`--target-shield`, `--target-shield-type normal|physical|magic`, absorción posmitigación sin afectar a fórmulas de vida ni ejecuciones) y escudos generados por el atacante (`ShieldEvent`, escalados con HSP/Revitalizar e inmunes a Heridas graves, alimentando a `ShieldBash`); ver [`survival.md`](../lol-knowledge/mechanics/survival.md).* Escudos.
- [x] **MEC-05 (P1)** *Hecho en la fase 42 (2026-11-20): curaciones directas de efectos (`HealEvent` para objetos como `2510` Amanecer y anochecer y runas como Garras, Sabor a sangre, Absorber vida, Triunfo y Fuente de vida) y seguimiento de la vida del atacante con `effective_healing` al pasar `--input attacker_health_percent`; ver [`survival.md`](../lol-knowledge/mechanics/survival.md).* Curaciones de efectos y vida del atacante.
- [x] **MEC-06 (P1)** *Hecho en la fase 42 (2026-11-20): Heridas graves (`-40 %` no acumulable sobre toda curación, nunca sobre escudos), activable con `--input grievous_wounds=1` o automáticamente al atacar a un objetivo con `3075` Malla de espinas (antes de la curación del propio ataque disparador; [`survival.md`](../lol-knowledge/mechanics/survival.md)).* Heridas graves.
- [x] **MEC-07 (P1)** *Hecho en la fase 42 (2026-11-20): estadística aditiva `heal_and_shield_power` en la hoja, regenerado `catalog-stats.json` (objetos de enchanter pasan de `unmodelled_stats` a `stats`), `+5 %` permanente de `Revitalize` (`8453`) y aplicación a curaciones directas y escudos (sin afectar a robo de vida ni omnivampirismo; [`survival.md`](../lol-knowledge/mechanics/survival.md)).* Poder de curaciones y escudos.
- [x] **MEC-08 (P2)** *Hecho en la fase 43 (2026-11-20): reducción plana posmitigación (suelo 0, incluido daño verdadero) en `defense.py` / `survive` (`8473` Revestimiento de huesos y `--input flat_damage_reduction`; [`survival.md`](../lol-knowledge/mechanics/survival.md)).* Reducciones planas de daño.
- [x] **MEC-09 (P1)** *Hecho en la fase 43 (2026-11-20): subcomando `python -m lol_knowledge survive` (`defense.py`, `defense_report.py`), admite golpes manuales (`--incoming`) o rotación enemiga (`--enemy-champion` + `--steps`), calcula supervivencia, paso letal, `time_to_die`, `damage_taken_per_second`, `3053` Sterak Salvavidas, `8465` Protector, `8444` Fuerzas renovadas, `8473` Revestimiento de huesos y reflejo de `3075` Malla de espinas ([`survival.md`](../lol-knowledge/mechanics/survival.md)).* Simulación inversa.
- [ ] **MEC-10 (P2)** Reducciones de resistencia del objetivo (por ejemplo, de habilidades): `ability` no las admite ([`odd/tasks/ability-command.md`](tasks/ability-command.md)).

### 4.3 Daño y mitigación
- [ ] **MEC-11 (P2)** Penetración porcentual de armadura adicional ([`damage-mitigation.md`](../lol-knowledge/mechanics/damage-mitigation.md)).
- [ ] **MEC-12 (P3)** Redondeo del juego en el daño mostrado ([`README.md`](../README.md)).
- [x] **MEC-13 (P2)** *Hecho en la fase 41 (2026-11-20): `wiki.leagueoflegends.com/en-us/Plated_Steelcaps` (rev `4022248`) confirma que Placas no reduce el daño de efectos al impactar (`on-hit`); `rotation.py` ya no debilita esas partes a `Pendiente de verificación` ([`damage-modifiers.md`](../lol-knowledge/mechanics/damage-modifiers.md)).* Si Placas reduce también el daño al impactar de los objetos.
- [ ] **MEC-14 (P2)** Varias fuentes de daño crítico adicional: se suman sin verificar ([`critical-strike.md`](../lol-knowledge/mechanics/critical-strike.md)).
- [ ] **MEC-15 (P3)** Daño excesivo en el golpe letal: no se sabe si la curación usa el daño completo ([`life-steal-and-omnivamp.md`](../lol-knowledge/mechanics/life-steal-and-omnivamp.md)).
- [ ] **MEC-16 (P2)** Robo de vida y omnivampirismo en la misma parte: se suman sin fuente.
- [ ] **MEC-17 (P2)** Las habilidades contra súbditos o monstruos se curan al 100 % sin saber si son área, daño periódico o mascota.

### 4.4 Tiempo y ataques
- [ ] **MEC-18 (P2)** Tiempos de lanzamiento, animaciones de ataque y viaje de proyectiles: no hay datos ([`timeline.md`](../lol-knowledge/mechanics/timeline.md)).
- [ ] **MEC-19 (P2)** Si el temporizador del ataque se recalcula cuando cambia la velocidad de ataque a mitad de ciclo (Guinsoo, Ráfaga): `Pendiente de verificación` ([`combat-stacks.md`](../lol-knowledge/mechanics/combat-stacks.md)).
- [ ] **MEC-20 (P2)** Si el golpe que dispara un efecto con duración ya se beneficia de él (Hoja encantada, Vigor) ([`timeline.md`](../lol-knowledge/mechanics/timeline.md), regla 8).
- [ ] **MEC-21 (P2)** Informes por ventana de tiempo (daño en los primeros N segundos, DPS por tramo) ([`odd/tasks/timeline-windows.md`](tasks/timeline-windows.md)).
- [ ] **MEC-22 (P2)** Reducciones de velocidad de ataque y suelo de 0,2 (`Attack_speed` rev `4073067` en `wiki.leagueoflegends.com` confirma suelo exacto `1/5 = 0,2` ataques/s; falta implementarlo en la hoja, [`odd/tasks/attack-speed-and-vamp.md`](tasks/attack-speed-and-vamp.md)).
- [ ] **MEC-23 (P3)** Vida del objetivo a mitad de un paso ([`odd/tasks/target-health.md`](tasks/target-health.md)).
- [ ] **MEC-24 (P2)** Ataques potenciados por habilidades: no consta si aplican los efectos al impactar; hoy se escriben como habilidad + `attack` ([`basic-attacks-and-on-hit.md`](../lol-knowledge/mechanics/basic-attacks-and-on-hit.md)).
- [ ] **MEC-25 (P3)** Efectos al impactar de las habilidades del campeón (ninguno modelado, [`spellblade.md`](../lol-knowledge/mechanics/spellblade.md)).

### 4.5 Control, movimiento y otras estadísticas
- [ ] **MEC-26 (P2)** Controles de masas y su duración con tenacidad: hoy la tenacidad no cambia ningún cálculo ([`tenacity.md`](../lol-knowledge/mechanics/tenacity.md)). Falta también el grupo B de tenacidad y la tenacidad condicional.
- [ ] **MEC-27 (P3)** Ralentizaciones, resistencia a ralentizaciones y aportes multiplicativos de velocidad de movimiento ([`odd/tasks/move-speed.md`](tasks/move-speed.md)).
- [ ] **MEC-28 (P3)** Multiplicadores de regeneración y regeneración por vida o maná máximos ([`odd/tasks/regeneration.md`](tasks/regeneration.md)).
- [ ] **MEC-29 (P2)** *Parcial (fase 38): `basic_ability_haste` (Q/W/E) y `ultimate_haste` (R) ya se aplican en `ability_cooldowns` y `--timeline`.* Falta la aceleración de hechizos de invocador y de objetos, y enfriamientos que no son de habilidad ([`ability-haste.md`](../lol-knowledge/mechanics/ability-haste.md)). Tope de 500 sin confirmar.
- [ ] **MEC-30 (P3)** Estadísticas por encima del nivel 18 ([`stat-growth.md`](../lol-knowledge/mechanics/stat-growth.md)).
- [ ] **MEC-31 (P2)** Efectos de estadística a partir de otra estadística (por ejemplo, vida adicional que da DA) y auras.
- [ ] **MEC-32 (P3)** Mejoras y buffs externos: dragones, barón, elixires.

## 5. Objetos

- [ ] **OBJ-01 (P1)** Efectos de los objetos sin curar: de los 218 comprables de la Grieta, 42 tienen efectos curados y 176 solo estadísticas; 132 de estos tienen efectos en la descripción que siguen `pending` ([`objects/README.md`](../lol-knowledge/objects/README.md) §5). Mientras un objeto esté `pending`, cualquier rotación que lo use queda `Pendiente de verificación`. Conviene hacerlo por mecánica (escudos, auras, activas…) y no por objeto, porque cada mecánica nueva exige una regla.
- [ ] **OBJ-02 (P1)** Objetos descartados el 2026-10-20 por falta de fórmula verificable ([`objects/README.md`](../lol-knowledge/objects/README.md) §7). Las cifras ya están en [`item-effects.json`](../lol-knowledge/derived/item-effects.json) (cliente 16.22, `Derivado`); lo que falta es capacidad del motor. Verdugo de krakens figuraba en esa lista, pero ya está curado.
  - **Compañero de Luden / Eco de Luden (6655):** Eco, 6 ecos de 75 (+5 % AP) mágico al objetivo y a los cercanos; los sobrantes golpean al objetivo principal al 20 % (intervalos de 0,25 s, máximo 2 × daño contra 1 objetivo, corroborado en `Module:ItemData/data` rev `4095269`); enfriamiento 12 s. Contra un único objetivo se puede modelar ya con la línea de tiempo; el área necesita CH-05.
  - **Eclipse (6692):** Luna creciente, 2 ataques o habilidades independientes contra un campeón en 2 s: 8 % de la vida máxima como daño físico (×0,625 a distancia) y escudo de 150 + 40 % de DA adicional (×0,5 a distancia) durante 2 s; enfriamiento 6 s. El daño cabe en la línea de tiempo (ventana de 2 golpes); el escudo necesita MEC-04.
  - **Calibrador de Sterak (3053):** *curado en la fase 43 (`catalog.json` v21):* DA adicional del 50 % del DA base en la hoja (`the-claws-that-catch`) y escudo del 60 % de vida adicional al bajar del 30 % de vida máxima durante 4,5 s (90 s CD) en `survive` (`lifeline`). Queda solo la curva de decaimiento de los 4,5 s en `--timeline`.
- [ ] **OBJ-03 (P2)** Rayo de Statikk: `Module:ItemData/data` (rev `4095269`) y `Statikk_Shiv` (rev `4053478`) confirman que golpea al objetivo atacado y rebota en cadena (ahora es un objeto de Vigor: 15 cargas por ataque, 60 mágico a campeones / 90 a no campeones); pendiente de activar en el catálogo junto con `OBJ-04` ([`attack-counters.md`](../lol-knowledge/mechanics/attack-counters.md)).
- [ ] **OBJ-04 (P2)** Recarga de Vigor: depende del movimiento, que no se modela; varios objetos de Vigor a la vez, sin verificar.
- [ ] **OBJ-05 (P2)** Impactos fantasma de Guinsoo como acumulación extra del Kraken, y su duración (`Kraken_Slayer` rev `4069877` y `Module:ItemData/data` rev `4095269` confirman caso especial de interacción Guinsoo → Kraken al impactar y duración de 4 s tanto para Phantom como para Kraken; falta implementar la interacción en `rotation.py`, [`timeline.md`](../lol-knowledge/mechanics/timeline.md)).
- [x] **OBJ-06 (P2)** *Hecho en la fase 41 (2026-11-20): `Module:ItemData/data` (rev `4095269`) corrobora que `MonsterDamageCap = 40` del cliente 16.23 son 40/s (20 por tic de 0,5 s, 120 en 3 s); `6653 torment-monsters` ya es `evaluable` con límite `40/s` en `rotation.py` ([`burns.md`](../lol-knowledge/mechanics/burns.md)).* Tope de Liandry contra monstruos.
- [ ] **OBJ-07 (P2)** Activa de Malignidad y efectos secundarios declarados y no aplicados de Hoja encantada: velocidad de movimiento de Trinidad, campo de Guantelete de hielo, curación de Amanecer y anochecer ([`spellblade.md`](../lol-knowledge/mechanics/spellblade.md)).
- [ ] **OBJ-08 (P2)** Quemaduras de aura (Égida de fuego solar, Rescoldo de Bami, Fulgor vano) y Creagrietas ([`odd/tasks/burns.md`](tasks/burns.md)).
- [ ] **OBJ-09 (P3)** Persistencia entre objetivos de las acumulaciones de Hoja del rey arruinado, modificadores por modo, radio de Humildad, aceleración de objetos en las activas de Zhonya y Randuin ([`objects/README.md`](../lol-knowledge/objects/README.md) §7).
- [ ] **OBJ-10 (P2)** Inicio de la alternancia de El final (se supone luminoso) y si las acumulaciones de Kraken se renuevan con cada golpe al campeón ([`combat-stacks.md`](../lol-knowledge/mechanics/combat-stacks.md), [`timeline.md`](../lol-knowledge/mechanics/timeline.md)).
- [ ] **OBJ-11 (P2)** Pendiente lineal de Verdugo de gigantes: solo hay fuente secundaria ([`damage-modifiers.md`](../lol-knowledge/mechanics/damage-modifiers.md)).
- [ ] **OBJ-12 (P2)** *Alcance decidido en DEC-03 (2026-11-20):*
  - **Entran:** **consumibles** y **mejoras de Ornn**, con la condición de que **solo un objeto de la build** puede ser el mejorado y asegurando que sea el que más contribuya al objetivo de la build (regla de legalidad + optimizador).
  - **Quedan fuera:** **trinkets** (abalorios/centinelas) y **variantes de otros modos** (solo Grieta del Invocador). Generación de oro y compañeros de jungla siguen fuera de alcance salvo decisión posterior.
- [x] **OBJ-13 (P1)** *Hecho en la fase 36: grupos del cliente en `item-groups.json`, regla en [`build-legality.md`](../lol-knowledge/mechanics/build-legality.md) y comprobación en `stats`, `ability` y `rotation`.* Legalidad de la build: objetos únicos, un solo par de botas, grupos exclusivos y número de huecos. La hoja no lo valida ([`README.md`](../README.md)). Es imprescindible para el optimizador.

## 6. Campeones

- [x] **CH-01 (P1)** *Hecho en las fases 46–49 (2026-11-20/21, oleadas 1 a 4: [`champion-kits-wave-1.md`](tasks/champion-kits-wave-1.md), [`champion-kits-wave-2.md`](tasks/champion-kits-wave-2.md), [`champion-kits-wave-3.md`](tasks/champion-kits-wave-3.md) y [`champion-kits-wave-4.md`](tasks/champion-kits-wave-4.md)) y ampliado en la fase 50 ([`champion-wave-mechanics.md`](tasks/champion-wave-mechanics.md)): **173 de 173 campeones** (100 %) tienen `kit.json` curado, compilado y validado en los 5 roles sobre el cliente `16.23`.*
- [x] **CH-02 (P1)** *Hecho en la fase 45 y ampliado en la fase 50 (2026-11-20/21): [`research/binmodel/specdraft.py`](../research/binmodel/specdraft.py) (`python -m binmodel.specdraft`) genera borradores compilables de `spec.json`; [`kitgen.py`](../research/binmodel/kitgen.py) traduce `ByCharLevelInterpolationCalculationPart`, `{ee18a47b}`, `ByCharLevelBreakpointsCalculationPart` (incluido `mLevel1Value` omitido = `0.0`), `{b22609db}`, `ByCharLevelFormulaCalculationPart`, `EffectValueCalculationPart` (`mSpell.mEffectAmount`), `AbilityResourceByCoefficientCalculationPart` (maná), `BuffCounterByCoefficientCalculationPart` / `BuffCounterByNamedDataValueCalculationPart` (acumulaciones `--input` con `default: 0`), `mStat` `0/1/2/4/6/7/8/9/12/18/29`, referencias cruzadas entre ranuras/tooltips (`{{include}}`), `sum`, `product`, `passive_effects` y `cost`.* Automatizar todo lo posible de CH-01.
- [x] **CH-03 (P1)** *Hecho en la fase 45 y ampliado en la fase 50 (2026-11-20/21): motor declarativo de pasivas en [`src/lol_knowledge/passives.py`](../src/lol_knowledge/passives.py) (`PassiveEffectSpec`: `stat_bonus`, `stacking_stat`, `heal`, `damage_proc` y operador exacto `linear_by_level` en `ABILITY_OPS`), integrado en `stats`, `ability` y `rotation` (`--timeline` incluido); ver [`passives.md`](../lol-knowledge/mechanics/passives.md).* Pasivas de campeón en la hoja y en la rotación.
- [x] **CH-04 (P2)** *Hecho en las fases 50 y 51 (2026-11-21, [`champion-wave-mechanics.md`](tasks/champion-wave-mechanics.md) y [`ch04-champion-mechanics.md`](tasks/ch04-champion-mechanics.md)): resueltos en `binmodel`/`kitgen` `EffectValueCalculationPart`, `ByCharLevelBreakpointsCalculationPart` (`level1=0`), `AbilityResourceByCoefficientCalculationPart` (maná), `{b22609db}` (Irelia P), `mStat` de velocidad de ataque/velocidad de movimiento/probabilidad y daño crítico/robo de vida/letalidad, `BuffCounter` con `--input <cargas>` (`default: 0`) y casos multiforma/evolucionados (Gnar Mega, Rek'Sai enterrada, Nidalee Puma, Elise araña, Yunara R+W, Kai'Sa Q 6/12 misiles, Graves 4/6 perdigones, Corki P crítica); y modeladas en `sheet.py` y `rotation.py` las reglas especiales de velocidad de ataque de **Bel'Veth** (sin tope + `lavender_stacks`), **Zeri** (tope `1,5` + `60 %` del exceso a DA adicional), **Jhin** (VA fija `0,625..0,94375`, amplificador `TotalADPercent` y `-25 %` daño crítico), **Sion** (tope normal vivo + `soul_furnace_*_kills`) y **Graves** (cadencia entre los 2 cartuchos) ([`attack-speed.md`](../lol-knowledge/mechanics/attack-speed.md)), la conversión de críticos de **Ashe** (`1 + crit_chance × (1 + crit_damage_bonus)`, [`critical-strike.md`](../lol-knowledge/mechanics/critical-strike.md)) y la amplificación de velocidad de movimiento de **Cassiopeia** (`5 %..35,6 %`, [`move-speed.md`](../lol-knowledge/mechanics/move-speed.md)).*
- [ ] **CH-05 (P2)** Varios objetivos y área: la rotación evalúa un único objetivo (la R de Ahri dispara 3 rayos a objetivos distintos y solo cuenta uno).

### 6.1 Zaahen (`not_modelled` del kit y fichas)
- [x] **CH-Z-01 (P1)** *Hecho en la fase 45 (2026-11-20): compilado en [`Zaahen/kit.json`](../lol-knowledge/champions/Zaahen/kit.json) desde `PercentBonusADCalc` (`{ee18a47b}`, `1,5 %`–`2,8 %` DA lineal 1–18 por acumulación, hasta `12`, duplicado `× 2` al máximo, `5 s` en `--timeline`, `--input determination_stacks` en `stats`/`ability`; [`passives.md`](../lol-knowledge/mechanics/passives.md)).* Pasiva: DA por acumulación.
- [ ] **CH-Z-02 (P2)** Pasiva: revivir (faltan valores en el bin).
- [ ] **CH-Z-03 (P2)** Crecimiento de DA: Data Dragon publica 0 y el cliente 4,0; el motor usa el cliente, la ficha mantiene el oficial.
- [ ] **CH-Z-04 (P2)** Q contra monstruos y curación; E contra monstruos (+50 físico, tope de 400 del mágico); R: reducción de daño durante el lanzamiento y curación.
- [ ] **CH-Z-05 (P3)** Semántica de `mStat`/`mStatFormula` (interpretación, no enum publicado) y las líneas abiertas de [`research/zaahen-uncertainties.md`](../research/zaahen-uncertainties.md) (P1, P2, P4/P5, Q1, B1/B4, B5/B6).

### 6.2 Ahri (`not_modelled` del kit)
- [x] **CH-A-01 (P2)** *Hecho en la fase 45 (2026-11-20): compilado en [`Ahri/kit.json`](../lol-knowledge/champions/Ahri/kit.json) desde `ChampionHeal` (`75–165 + 30 % PH` al derribar campeón) y `MinionHeal` (`35–95 + 20 % PH` al consumir 9 fragmentos con `--input essence_fragments`; [`passives.md`](../lol-knowledge/mechanics/passives.md)).* Pasiva: curación tras 9 súbditos o monstruos o tras derribar a un campeón.
- [ ] **CH-A-02 (P2)** R: reactivaciones extra y ampliación de la ventana al derribar campeones; 3 rayos a enemigos distintos.
- [ ] **CH-A-03 (P3)** Q: el caso `both` supone que ida y vuelta alcanzan al mismo objetivo.
- [ ] **CH-A-04 (P3)** W: velocidad de movimiento (40 % que decae en 2 s) y daño doble a súbditos por debajo del 20 %.
- [ ] **CH-A-05 (P3)** E: hechizo y ralentización.

## 7. Runas y fragmentos

- [x] **RUN-01 (P1)** *Hecho en la fase 37: [`runes.json`](../lol-knowledge/derived/runes.json) y [`runes.md`](../lol-knowledge/mechanics/runes.md).* Modelo de runas: no hay ninguno. El snapshot trae los 5 árboles de Data Dragon (62 runas), pero solo con descripciones, sin cifras estructuradas.
- [x] **RUN-02 (P1)** *Hecho en la fase 37: `binmodel.perks`, valores con nombre cuando un texto lo da (332 de 463).* Cifras de las runas desde el cliente, con el mismo método que `item-effects.json` (bin + textos), etiquetadas `Derivado`.
- [x] **RUN-03 (P1)** *Hecho en la fase 37 (y actualizado en fase 41): los fragmentos salen del cliente y se aplican en la hoja; progresión de vida `10 × nivel` corroborada (`Derivado`, `Rune` rev `4094440`); empates de la fuerza adaptable siguen `Pendiente de verificación`.* Fragmentos de estadísticas: no están en `runes.json` de Data Dragon; hacen falta fuente y modelo.
- [x] **RUN-04 (P1)** *Hecho en las fases 37–44 dentro de las mecánicas actuales del motor: legalidad de página, 16 runas menores de estadísticas (incluida `Revitalize` y los tics cada 5 s de `ManaflowBand` en `--timeline`), 7 no-combate, 14 runas menores de combate/supervivencia/recursos (incluida `8009` `PresenceOfMind`), 11 piedras angulares ofensivas con curación de Garras y 3 runas defensivas en `survive` (`BonePlating`, `SecondWind`, `Guardian`; **51 de 62** runas de árbol; [`runes.md`](../lol-knowledge/mechanics/runes.md)). Las 5 piedras angulares y 6 runas menores restantes dependen de mecánicas pendientes (`MEC-26`, `MEC-27`, `MEC-29`, `DAT-06`, `OBJ-04`, `OBJ-12`) y entrarán con ellas.* Piedras angulares en la rotación y runas menores en la hoja; legalidad de la página.

## 8. Optimizador de builds

- [ ] **OPT-01 (P1)** Definir objetivos medibles: daño de una rotación, DPS en N segundos, vida efectiva, tiempo hasta morir, curación, con restricciones (oro, nivel, objetos obligatorios o prohibidos).
- [ ] **OPT-02 (P1)** Búsqueda sobre builds legales (OBJ-13, RUN-04) con poda; el espacio completo es enorme y hay que medir antes de optimizar ([`AGENTS.md`](../AGENTS.md) §9).
- [ ] **OPT-03 (P1)** Que el resultado arrastre la etiqueta más débil de sus entradas y separe las builds con todo `Derivado` de las que dependen de efectos `Pendiente de verificación`.
- [ ] **OPT-04 (P2)** Orden de compra y builds parciales por oro (curva de potencia por tiempo de partida).
- [ ] **OPT-05 (P2)** Elección de la rotación: hoy la escribe quien llama; el optimizador necesita rotaciones tipo por campeón o generarlas.

## 9. Capa de IA

- [ ] **IA-01 (P1)** Contrato entre la IA y el motor: una entrada estructurada (JSON) para escenarios y una salida con cifras, etiquetas y supuestos. La CLI ya da `--json`; falta un esquema único y versionado para `stats`, `ability`, `rotation` y el optimizador.
- [ ] **IA-02 (P1)** Interpretar la petición en lenguaje natural y traducirla a un escenario: campeón, nivel, objetivo, restricciones y métrica. La IA nunca calcula; si falta un dato, pregunta o lo declara como supuesto.
- [ ] **IA-03 (P1)** Explicar el resultado citando las etiquetas y lo no modelado, sin redondear las incertidumbres.
- [ ] **IA-04 (P1)** *Interfaz decidida y aprobada en DEC-02 (2026-11-20):* **servidor MCP local** para poder usarlo desde OpenCode, Antigravity o cualquier cliente MCP compatible (aprobado como excepción a la ausencia de servicio de [`AGENTS.md`](../AGENTS.md) §1). Pendiente su implementación sobre el contrato de `IA-01`.

## 10. Calidad y verificación

- [ ] **QA-01 (P2)** Medición en partida (herramienta de práctica): ninguna regla del motor se ha medido en el juego; muchas salen de fuentes secundarias ([`odd/tasks/damage-engine.md`](tasks/damage-engine.md), [`odd/tasks/stat-sheet.md`](tasks/stat-sheet.md)). Un conjunto de casos medidos serviría como pruebas de aceptación.
- [ ] **QA-02 (P2)** Pruebas de mutación periódicas sobre `rotation.py` y `stats/sheet.py`, que son los módulos más grandes (1702 y 704 líneas).
- [ ] **QA-03 (P3)** Dividir `rotation.py` cuando crezca más: ya concentra tiempo, acumulaciones, ventanas y efectos.

## 11. Decisiones del usuario (resueltas el 2026-11-20)

- [x] **DEC-01** *Resuelta:* terminar **runas** primero (`RUN-04`), después kits (`CH-02`, `CH-03`, `CH-01`) y efectos de objeto (`OBJ-01`).
- [x] **DEC-02** *Resuelta:* **servidor MCP local** para poder usarlo desde OpenCode, Antigravity o cualquier cliente MCP compatible (`IA-04`).
- [x] **DEC-03** *Resuelta:* entran **consumibles** y **mejoras de Ornn** (con la condición de que solo un objeto de la build puede ser el mejorado, asegurando que sea el que más contribuya al objetivo de la build); **no** entran **trinkets** ni **otros modos** (`OBJ-12`).
- [x] **DEC-04** *Resuelta:* autorizados el CI (`OP-03`) y el borrado de ramas locales integradas (`OP-04`) tras verificar que no haya código sin integrar en `dev` (o que solo sea código antiguo obsoleto). Ambas tareas ejecutadas el 2026-11-20 (0 commits sin integrar en las 52 ramas locales eliminadas).
- [x] **DEC-05** *Resuelta:* **no se admiten estadísticas comunitarias** (win rate, builds populares) bajo ninguna condición ([`lol-knowledge/champions/Zaahen/build.md`](../lol-knowledge/champions/Zaahen/build.md)).

## 12. Orden propuesto (`Recomendación`)

1. ~~OP-01, OP-02~~ (hechos), ~~OP-03, OP-04~~ (hechos).
2. ~~DOC-01 a DOC-07~~ (hechos en fase 34).
3. ~~RUN-01 a RUN-04 y OBJ-13~~ (hechos en fases 36–40).
4. **Siguiente:** **CH-02 y CH-03** (automatizar kits y pasivas), y después CH-01 por lotes de campeones.
5. MEC-01, MEC-04 a MEC-07 y MEC-09 (recursos y supervivencia).
6. OBJ-01 por mecánicas, OBJ-02 y alcance decidido de OBJ-12 (consumibles y mejoras de Ornn).
7. IA-01, IA-04 (servidor MCP local) y OPT-01 a OPT-03 (contrato, servidor MCP y primer optimizador).
8. ~~DAT-01 y DAT-02~~ (hechos en fase 35).
9. El resto según su prioridad.
