# Hoja de ruta: todo lo que falta para terminar LoL-Knowledge

- **Fecha:** 2026-11-18
- **Estado de partida:** fase 33 (kit de Ahri), `dev` en `b363a1b`, parche 16.22.1.
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
- [ ] **OP-02 (P0)** Ejecutar las cuatro validaciones de [`AGENTS.md`](../AGENTS.md) §5 en Windows con `.\.venv\Scripts\python.exe`. Desde la fase 30 solo se han ejecutado en el shell Linux del agente; en Windows constan como no ejecutadas.
- [ ] **OP-03 (P2)** Integración continua: no hay CI ([`README.md`](../README.md), «Limitaciones conocidas»). Un flujo de GitHub Actions con las cuatro validaciones evitaría depender de ejecuciones manuales.
- [ ] **OP-04 (P3)** Limpiar las ramas de tarea ya integradas (hay más de 40 locales). Solo con autorización: borrar ramas no está en el flujo de `AGENTS.md`.
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
- [ ] **MEC-01 (P1)** Coste de las habilidades (maná, energía, vida) y maná disponible en una rotación. Hoy el kit no tiene costes y la rotación no gasta recursos.
- [ ] **MEC-02 (P2)** Recursos distintos del maná: la hoja solo modela maná; con otro recurso bloquea esas estadísticas ([`odd/tasks/stat-sheet.md`](tasks/stat-sheet.md)).
- [ ] **MEC-03 (P2)** Devolución de maná de Segador de esencia (no hay maná en la rotación, [`spellblade.md`](../lol-knowledge/mechanics/spellblade.md)).

### 4.2 Defensa y supervivencia
El motor debe servir también para vida, resistencias, curación y supervivencia, no solo para daño.
- [ ] **MEC-04 (P1)** Escudos: ni los del objetivo absorben daño ni los del atacante se calculan ([`README.md`](../README.md)).
- [ ] **MEC-05 (P1)** Curaciones de efectos (objetos y kits) y vida del atacante a lo largo de la rotación. Hoy solo se informa la curación por robo de vida y omnivampirismo, sin tope por vida perdida ([`life-steal-and-omnivamp.md`](../lol-knowledge/mechanics/life-steal-and-omnivamp.md)).
- [ ] **MEC-06 (P1)** Heridas graves sobre el atacante y sobre el objetivo (Malla de espinas las declara; no se aplican a la curación).
- [ ] **MEC-07 (P1)** Poder de curaciones y escudos: está en `unmodelled_stats` del catálogo y no se aplica.
- [ ] **MEC-08 (P2)** Reducciones planas de daño ([`README.md`](../README.md)).
- [ ] **MEC-09 (P1)** Simulación inversa: el objetivo ataca al campeón analizado (tiempo hasta morir, daño recibido por segundo). La vida efectiva existe, pero no frente a una rotación enemiga.
- [ ] **MEC-10 (P2)** Reducciones de resistencia del objetivo (por ejemplo, de habilidades): `ability` no las admite ([`odd/tasks/ability-command.md`](tasks/ability-command.md)).

### 4.3 Daño y mitigación
- [ ] **MEC-11 (P2)** Penetración porcentual de armadura adicional ([`damage-mitigation.md`](../lol-knowledge/mechanics/damage-mitigation.md)).
- [ ] **MEC-12 (P3)** Redondeo del juego en el daño mostrado ([`README.md`](../README.md)).
- [ ] **MEC-13 (P2)** Si Placas reduce también el daño al impactar de los objetos: `Pendiente de verificación` ([`damage-modifiers.md`](../lol-knowledge/mechanics/damage-modifiers.md)).
- [ ] **MEC-14 (P2)** Varias fuentes de daño crítico adicional: se suman sin verificar ([`critical-strike.md`](../lol-knowledge/mechanics/critical-strike.md)).
- [ ] **MEC-15 (P3)** Daño excesivo en el golpe letal: no se sabe si la curación usa el daño completo ([`life-steal-and-omnivamp.md`](../lol-knowledge/mechanics/life-steal-and-omnivamp.md)).
- [ ] **MEC-16 (P2)** Robo de vida y omnivampirismo en la misma parte: se suman sin fuente.
- [ ] **MEC-17 (P2)** Las habilidades contra súbditos o monstruos se curan al 100 % sin saber si son área, daño periódico o mascota.

### 4.4 Tiempo y ataques
- [ ] **MEC-18 (P2)** Tiempos de lanzamiento, animaciones de ataque y viaje de proyectiles: no hay datos ([`timeline.md`](../lol-knowledge/mechanics/timeline.md)).
- [ ] **MEC-19 (P2)** Si el temporizador del ataque se recalcula cuando cambia la velocidad de ataque a mitad de ciclo (Guinsoo, Ráfaga): `Pendiente de verificación` ([`combat-stacks.md`](../lol-knowledge/mechanics/combat-stacks.md)).
- [ ] **MEC-20 (P2)** Si el golpe que dispara un efecto con duración ya se beneficia de él (Hoja encantada, Vigor) ([`timeline.md`](../lol-knowledge/mechanics/timeline.md), regla 8).
- [ ] **MEC-21 (P2)** Informes por ventana de tiempo (daño en los primeros N segundos, DPS por tramo) ([`odd/tasks/timeline-windows.md`](tasks/timeline-windows.md)).
- [ ] **MEC-22 (P2)** Reducciones de velocidad de ataque y suelo de 0,2 ([`odd/tasks/attack-speed-and-vamp.md`](tasks/attack-speed-and-vamp.md)).
- [ ] **MEC-23 (P3)** Vida del objetivo a mitad de un paso ([`odd/tasks/target-health.md`](tasks/target-health.md)).
- [ ] **MEC-24 (P2)** Ataques potenciados por habilidades: no consta si aplican los efectos al impactar; hoy se escriben como habilidad + `attack` ([`basic-attacks-and-on-hit.md`](../lol-knowledge/mechanics/basic-attacks-and-on-hit.md)).
- [ ] **MEC-25 (P3)** Efectos al impactar de las habilidades del campeón (ninguno modelado, [`spellblade.md`](../lol-knowledge/mechanics/spellblade.md)).

### 4.5 Control, movimiento y otras estadísticas
- [ ] **MEC-26 (P2)** Controles de masas y su duración con tenacidad: hoy la tenacidad no cambia ningún cálculo ([`tenacity.md`](../lol-knowledge/mechanics/tenacity.md)). Falta también el grupo B de tenacidad y la tenacidad condicional.
- [ ] **MEC-27 (P3)** Ralentizaciones, resistencia a ralentizaciones y aportes multiplicativos de velocidad de movimiento ([`odd/tasks/move-speed.md`](tasks/move-speed.md)).
- [ ] **MEC-28 (P3)** Multiplicadores de regeneración y regeneración por vida o maná máximos ([`odd/tasks/regeneration.md`](tasks/regeneration.md)).
- [ ] **MEC-29 (P2)** Aceleración de definitiva y de hechizos de invocador, y enfriamientos que no son de habilidad ([`ability-haste.md`](../lol-knowledge/mechanics/ability-haste.md)). Tope de 500 sin confirmar.
- [ ] **MEC-30 (P3)** Estadísticas por encima del nivel 18 ([`stat-growth.md`](../lol-knowledge/mechanics/stat-growth.md)).
- [ ] **MEC-31 (P2)** Efectos de estadística a partir de otra estadística (por ejemplo, vida adicional que da DA) y auras.
- [ ] **MEC-32 (P3)** Mejoras y buffs externos: dragones, barón, elixires.

## 5. Objetos

- [ ] **OBJ-01 (P1)** Efectos de los objetos sin curar: de los 218 comprables de la Grieta, 42 tienen efectos curados y 176 solo estadísticas; 132 de estos tienen efectos en la descripción que siguen `pending` ([`objects/README.md`](../lol-knowledge/objects/README.md) §5). Mientras un objeto esté `pending`, cualquier rotación que lo use queda `Pendiente de verificación`. Conviene hacerlo por mecánica (escudos, auras, activas…) y no por objeto, porque cada mecánica nueva exige una regla.
- [ ] **OBJ-02 (P1)** Objetos descartados el 2026-10-20 por falta de fórmula verificable ([`objects/README.md`](../lol-knowledge/objects/README.md) §7). Las cifras ya están en [`item-effects.json`](../lol-knowledge/derived/item-effects.json) (cliente 16.22, `Derivado`); lo que falta es capacidad del motor. Verdugo de krakens figuraba en esa lista, pero ya está curado.
  - **Compañero de Luden (6655):** Eco, 6 ecos de 75 (+5 % AP) mágico al objetivo y a los cercanos; los sobrantes golpean al objetivo principal al 20 %; máximo contra un objetivo = 2 × daño (`SingleTargetMax`); enfriamiento 12 s. Contra un único objetivo se puede modelar ya con la línea de tiempo. El reparto «1 eco completo + 5 al 20 %» cuadra con el máximo, pero es una deducción sin medir (`Pendiente de verificación`). El área necesita CH-05.
  - **Eclipse (6692):** Luna creciente, 2 ataques o habilidades independientes contra un campeón en 2 s: 8 % de la vida máxima como daño físico (×0,625 a distancia) y escudo de 150 + 40 % de DA adicional (×0,5 a distancia) durante 2 s; enfriamiento 6 s. El daño cabe en la línea de tiempo (ventana de 2 golpes); el escudo necesita MEC-04.
  - **Calibrador de Sterak (3053):** escudo del 60 % de `mStat 12` durante 4,5 s por debajo del 30 % de vida; enfriamiento 90 s; DA del 50 % de `mStat 2` (fórmula 1). Necesita MEC-04, MEC-05/MEC-09 (vida del atacante) y MEC-31. Qué estadísticas son `mStat 12` y `mStat 2` con esa fórmula es una interpretación sin confirmar (`Pendiente de verificación`).
- [ ] **OBJ-03 (P2)** Rayo de Statikk: no se aplica porque no consta si alcanza al objetivo atacado ([`attack-counters.md`](../lol-knowledge/mechanics/attack-counters.md)).
- [ ] **OBJ-04 (P2)** Recarga de Vigor: depende del movimiento, que no se modela; varios objetos de Vigor a la vez, sin verificar.
- [ ] **OBJ-05 (P2)** Impactos fantasma de Guinsoo como acumulación extra del Kraken, y su duración (4 s o 6 s) ([`timeline.md`](../lol-knowledge/mechanics/timeline.md)).
- [ ] **OBJ-06 (P2)** Tope de Liandry contra monstruos: no se sabe si es por tic o por aplicación ([`burns.md`](../lol-knowledge/mechanics/burns.md)).
- [ ] **OBJ-07 (P2)** Activa de Malignidad y efectos secundarios declarados y no aplicados de Hoja encantada: velocidad de movimiento de Trinidad, campo de Guantelete de hielo, curación de Amanecer y anochecer ([`spellblade.md`](../lol-knowledge/mechanics/spellblade.md)).
- [ ] **OBJ-08 (P2)** Quemaduras de aura (Égida de fuego solar, Rescoldo de Bami, Fulgor vano) y Creagrietas ([`odd/tasks/burns.md`](tasks/burns.md)).
- [ ] **OBJ-09 (P3)** Persistencia entre objetivos de las acumulaciones de Hoja del rey arruinado, modificadores por modo, radio de Humildad, aceleración de objetos en las activas de Zhonya y Randuin ([`objects/README.md`](../lol-knowledge/objects/README.md) §7).
- [ ] **OBJ-10 (P2)** Inicio de la alternancia de El final (se supone luminoso) y si las acumulaciones de Kraken se renuevan con cada golpe al campeón ([`combat-stacks.md`](../lol-knowledge/mechanics/combat-stacks.md), [`timeline.md`](../lol-knowledge/mechanics/timeline.md)).
- [ ] **OBJ-11 (P2)** Pendiente lineal de Verdugo de gigantes: solo hay fuente secundaria ([`damage-modifiers.md`](../lol-knowledge/mechanics/damage-modifiers.md)).
- [ ] **OBJ-12 (P3)** Consumibles, centinelas, trinkets, generación de oro, compañeros de jungla, mejoras de Ornn y variantes de otros modos: fuera de alcance declarado; decidir si entran.
- [ ] **OBJ-13 (P1)** Legalidad de la build: objetos únicos, un solo par de botas, grupos exclusivos y número de huecos. La hoja no lo valida ([`README.md`](../README.md)). Es imprescindible para el optimizador.

## 6. Campeones

- [ ] **CH-01 (P1)** Kits de los 171 campeones restantes: solo Zaahen y Ahri tienen `kit.json` (de 173). El método actual (`bin2json` + `kitgen` + `research/kits/<Id>.spec.json` + ficha + pruebas) necesita curar los casos a mano por campeón.
- [ ] **CH-02 (P1)** Automatizar todo lo posible de CH-01: generar el borrador de la especificación, detectar los valores con doble tipo de daño, los ajustes de reactivación y los escalados sin `mStat`, y dejar la curación a mano solo para los casos.
- [ ] **CH-03 (P1)** Pasivas de campeón en la hoja y en la rotación: hoy no se aplican ([`README.md`](../README.md)).
- [ ] **CH-04 (P2)** Mecánicas de kit aún sin soporte en el modelo: transformaciones y evoluciones (Kha'Zix), cargas y munición, mascotas, formas (Nidalee, Elise), recursos propios, y kits que cambian el tope o el ratio de velocidad de ataque (Bel'Veth, Graves, Jhin, Sion, Zeri) ([`attack-speed.md`](../lol-knowledge/mechanics/attack-speed.md)), los críticos (Ashe, [`critical-strike.md`](../lol-knowledge/mechanics/critical-strike.md)) o la velocidad de movimiento (Cassiopeia, [`move-speed.md`](../lol-knowledge/mechanics/move-speed.md)).
- [ ] **CH-05 (P2)** Varios objetivos y área: la rotación evalúa un único objetivo (la R de Ahri dispara 3 rayos a objetivos distintos y solo cuenta uno).

### 6.1 Zaahen (`not_modelled` del kit y fichas)
- [ ] **CH-Z-01 (P1)** Pasiva: DA por acumulación (depende de la interpolación por nivel `{ee18a47b}`) y máximo por acumulación, 2,8 % en el bin frente a 2,95 % en la wiki.
- [ ] **CH-Z-02 (P2)** Pasiva: revivir (faltan valores en el bin).
- [ ] **CH-Z-03 (P2)** Crecimiento de DA: Data Dragon publica 0 y el cliente 4,0; el motor usa el cliente, la ficha mantiene el oficial.
- [ ] **CH-Z-04 (P2)** Q contra monstruos y curación; E contra monstruos (+50 físico, tope de 400 del mágico); R: reducción de daño durante el lanzamiento y curación.
- [ ] **CH-Z-05 (P3)** Semántica de `mStat`/`mStatFormula` (interpretación, no enum publicado) y las líneas abiertas de [`research/zaahen-uncertainties.md`](../research/zaahen-uncertainties.md) (P1, P2, P4/P5, Q1, B1/B4, B5/B6).

### 6.2 Ahri (`not_modelled` del kit)
- [ ] **CH-A-01 (P2)** Pasiva: curación tras 9 súbditos o monstruos o tras derribar a un campeón.
- [ ] **CH-A-02 (P2)** R: reactivaciones extra y ampliación de la ventana al derribar campeones; 3 rayos a enemigos distintos.
- [ ] **CH-A-03 (P3)** Q: el caso `both` supone que ida y vuelta alcanzan al mismo objetivo.
- [ ] **CH-A-04 (P3)** W: velocidad de movimiento (40 % que decae en 2 s) y daño doble a súbditos por debajo del 20 %.
- [ ] **CH-A-05 (P3)** E: hechizo y ralentización.

## 7. Runas y fragmentos

- [ ] **RUN-01 (P1)** Modelo de runas: no hay ninguno. El snapshot trae los 5 árboles de Data Dragon (62 runas), pero solo con descripciones, sin cifras estructuradas.
- [ ] **RUN-02 (P1)** Cifras de las runas desde el cliente, con el mismo método que `item-effects.json` (bin + textos), etiquetadas `Derivado`.
- [ ] **RUN-03 (P1)** Fragmentos de estadísticas: no están en `runes.json` de Data Dragon; hacen falta fuente y modelo.
- [ ] **RUN-04 (P1)** Piedras angulares en la rotación (Electrocutar, Conquistador, Cometa, Primer golpe…) y runas menores en la hoja; legalidad de la página (árbol principal y secundario, una por fila).

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
- [ ] **IA-04 (P2)** Elegir la interfaz: CLI con un agente, servidor MCP local o aplicación. [`AGENTS.md`](../AGENTS.md) §1 prohíbe web, servicio o base de datos sin necesidad demostrada y aprobada; requiere decisión del usuario.

## 10. Calidad y verificación

- [ ] **QA-01 (P2)** Medición en partida (herramienta de práctica): ninguna regla del motor se ha medido en el juego; muchas salen de fuentes secundarias ([`odd/tasks/damage-engine.md`](tasks/damage-engine.md), [`odd/tasks/stat-sheet.md`](tasks/stat-sheet.md)). Un conjunto de casos medidos serviría como pruebas de aceptación.
- [ ] **QA-02 (P2)** Pruebas de mutación periódicas sobre `rotation.py` y `stats/sheet.py`, que son los módulos más grandes (1702 y 704 líneas).
- [ ] **QA-03 (P3)** Dividir `rotation.py` cuando crezca más: ya concentra tiempo, acumulaciones, ventanas y efectos.

## 11. Decisiones que necesitan al usuario

- [ ] **DEC-01** Orden de trabajo entre runas (RUN), kits (CH-01/02) y efectos de objeto (OBJ-01). Recomendación: runas primero, porque sin ellas el optimizador no compara builds completas.
- [ ] **DEC-02** Interfaz de la capa de IA (IA-04).
- [ ] **DEC-03** Alcance de objetos fuera de la Grieta y de los modos (OBJ-12).
- [ ] **DEC-04** Autorización para borrar ramas integradas (OP-04) y para añadir CI (OP-03).
- [ ] **DEC-05** Si se admiten estadísticas comunitarias (win rate, builds populares) y con qué condiciones ([`lol-knowledge/champions/Zaahen/build.md`](../lol-knowledge/champions/Zaahen/build.md)).

## 12. Orden propuesto (`Recomendación`)

1. OP-01, OP-02 (publicar y validar en Windows).
2. DOC-01 a DOC-07 (una sola fase pequeña de documentación).
3. RUN-01 a RUN-04 y OBJ-13 (runas y legalidad de builds).
4. CH-02 y CH-03 (automatizar kits y pasivas), y después CH-01 por lotes de campeones.
5. MEC-01, MEC-04 a MEC-07 y MEC-09 (recursos y supervivencia).
6. OBJ-01 por mecánicas.
7. IA-01 y OPT-01 a OPT-03 (contrato y primer optimizador).
8. DAT-01 y DAT-02 (actualizar al parche vigente con un procedimiento repetible).
9. El resto según su prioridad.
