# Cobertura mecánica de objetos y plan de integración — fase 6

- **Objetivo:** cerrar los cinco huecos mecánicos identificados en la fase 5, ampliar el catálogo solo con objetos justificados y auditar las dependencias Git sin fusionar nada.
- **Rama:** `feat/object-mechanics-coverage`, creada desde `feat/object-model` (`f4f4919`). La base es la rama que contiene el esquema `lol-object-model/1`; no se usa `dev` porque su modelo de objetos todavía no está integrado.
- **Entrega:** investigación con fuentes en `research/reports/object-mechanics-2026-10-20.md`, cambios de esquema/catálogo en `src/lol_knowledge/objects/` y `lol-knowledge/objects/`, pruebas en `tests/`, y este documento con el grafo Git y el plan de integración.
- **Runner:** `.\.venv\Scripts\python.exe -m pytest -q`; puertas completas (`ruff check`, `ruff format --check`, `lol_knowledge validate`, `python -m lol_knowledge.objects --validate`) al cerrar.

## Specs

### S1 — Inspección inicial y línea base

Antes de modificar nada: leer `AGENTS.md`, `README.md`, `lol-knowledge/objects/README.md`, los ODD de fases anteriores y los informes de investigación; comprobar rama, árbol, ramas locales/remotas, ancestros y diferencias; verificar que los hashes y métricas de los informes coinciden con el estado real; ejecutar la línea base.

Línea base observada el 2026-10-20 en `feat/object-model` (`f4f4919`), árbol limpio:

- `pytest -q`: `173 passed in 4.39s`.
- `pytest research -q`: `97 passed in 1.04s`.
- `lol_knowledge validate`: `valid: 183 files checked`, salida `0`.
- `python -m lol_knowledge.objects --validate`: `valid: 1 object catalog files checked`, salida `0`.
- `dev` = `integration` = `f3e2948`; `research/zaahen-formula-extraction` = `89e2dbe`; `feat/object-model` = `f4f4919`.

### S2 — Auditoría Git y plan de integración, sin fusionar

Inspeccionar el grafo y las diferencias; identificar qué cambios necesita el modelo de objetos de la rama de investigación; detectar commits compartidos, divergencias, conflictos y dependencias cruzadas; proponer una secuencia reproducible y segura.

Prohibido en esta fase: `git merge`, rebase de ramas compartidas, mover/resetear/reescribir referencias compartidas, `push`, borrar ramas o commits, operaciones destructivas, resolver conflictos eliminando cambios.

### S3 — Hoja del rey arruinado (BotRK): daño de impacto

Determinar la fórmula del daño adicional al impacto y sus variables: vida actual o máxima del objetivo; dependencia del tipo de objetivo; límites mínimos/máximos; modificadores por nivel, campeón, modo; reglas especiales para monstruos, súbditos y campeones. No deducir un ratio exacto de una descripción incompleta.

### S4 — BotRK: acumulaciones y efecto de ataques

Determinar número de impactos, tipos que cuentan, reinicio, persistencia entre objetivos, enfriamientos internos, condiciones de activación y diferencias entre campeones y otros objetivos. No confundir la descripción resumida con la implementación real.

### S5 — Recuerdos de Lord Dominik: curva completa

Verificar la relación entre vida adicional del objetivo y daño adicional: fórmula completa o tabla de puntos, umbrales, límites, interpolación, si la vida adicional se calcula antes o después de otros modificadores, y exclusiones. No interpolar sin evidencia; si solo se conocen los extremos, conservar la limitación.

### S6 — Reloj de arena de Zhonya: enfriamiento

Buscar el enfriamiento real de la activa y cómo se aplica: valor exacto, dependencia de parche/modo/condición, interacción con aceleración de objetos, habilidades o reducción de enfriamiento, y confirmar que el dato es el enfriamiento de la activa y no la duración de la estasis.

### S7 — Malla de espinas: daño reflejado

Investigar cantidad y fórmula del daño reflejado, distinguiendo componentes: daño base, ratios y estadísticas; condiciones de activación; tipo de daño; interacción con armadura, mitigaciones y reducciones; diferencias entre ataques básicos, impactos y otras fuentes; aplicación de Heridas graves y duración. No confundir el reflejo con las Heridas graves.

### S8 — Ampliación selectiva del catálogo

Elegir un conjunto pequeño de objetos representativos para builds de daño explosivo, físico, poder de habilidad, efectos de impacto/daño según vida del objetivo y supervivencia/mitigación. Antes de añadir cada objeto: comprobar qué estadísticas ya se derivan de Data Dragon; añadir solo lo que el modelo no puede representar; conservar procedencia y versión; distinguir extraído, inferido y desconocido; representar efectos condicionales sin reducirlos a una cifra incondicional; comprobar que la clasificación de evaluabilidad se deriva de los componentes. No modelar los 870 objetos ni declarar completa una categoría no investigada.

### S9 — Compatibilidad con el modelo existente

Estudiar `src/lol_knowledge/objects/schema.py`, `catalog.py`, `formula.py`, `validate.py`, `interface.py`, `lol-knowledge/objects/catalog.json` y `README.md`; reutilizar abstracciones. Mantener: versión del juego compatible con el manifiesto; serialización determinista; procedencia y confianza explícitas; convención de porcentajes; recetas como multiconjunto; distinción entre cero real, ausencia, desconocido, no soportado y excluido; ningún total fiable con dependencias no evaluables; ningún número automático de prosa sin validación; ningún dato inferido presentado como fuente directa. Toda modificación de esquema debe documentar motivación, compatibilidad y pruebas. Evitar refactorizaciones generales.

### S10 — Pruebas obligatorias

Añadir pruebas para cada mecánica modelada y regresión: fórmula con entradas/salidas esperadas; límites y umbrales; cero real frente a desconocido; datos ausentes/malformados; dependencias no soportadas; efectos condicionales y condiciones incumplidas; referencias y versiones incorrectas; procedencia incompleta; determinismo; contradicciones entre fuentes; regresión de bugs reales. Las pruebas deben ser independientes de la lógica de producción: cálculos manuales verificables, fixtures controlados o referencias externas justificadas. No repetir la misma lógica de producción para validar su resultado. Sin red.

Comandos de cierre obligatorios:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m pytest research -q
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check .
.\.venv\Scripts\python.exe -m lol_knowledge validate
.\.venv\Scripts\python.exe -m lol_knowledge.objects --validate
```

### S11 — Documentación y ODD

Documentar objetivo y alcance; estado inicial observado; decisiones de diseño; fuentes y evidencias; objetos y mecánicas cubiertos; mecánicas no resueltas; pruebas y resultados reales; limitaciones y riesgos; grafo Git y propuesta de integración; próximas tareas. Actualizar el índice/README del catálogo solo si es necesario. No duplicar informes ni datos derivables del manifiesto.

### S12 — Política Git y permisos

Rama local de tarea desde base verificada; no trabajar en `dev`, `integration` ni en la rama de investigación; no push, no fusiones, no reescribir historia compartida, no borrar trabajo ajeno; no incluir temporales, cachés, rutas absolutas personales ni datos locales accidentales. Conventional Commits en inglés, asunto ≤ 72 caracteres, commits pequeños y coherentes **solo si se autoriza a confirmar**. **No ejecutar ningún commit sin autorización explícita.** No pedir permiso para lecturas, pruebas o cambios dentro del alcance. Detenerse ante ampliación de alcance, modificación de rama compartida u operación destructiva.

### S13 — Criterios de aceptación

1. Las cinco mecánicas investigadas con conclusión respaldada o incertidumbre explícita.
2. Las mecánicas suficientemente verificadas incorporadas con procedencia, confianza y pruebas.
3. Los valores desconocidos no convertidos en cero ni en fórmulas ficticias.
4. Catálogo ampliado solo con objetos justificados y evidencia suficiente.
5. Validador, esquema y salidas deterministas funcionando.
6. Pruebas nuevas cubren comportamientos añadidos y regresiones.
7. Comprobaciones finales ejecutadas con resultados reales.
8. Informe Git con dependencias y plan futuro, sin ejecutarlo.
9. Árbol sin cambios ajenos y sin ramas compartidas modificadas.
10. Sin commits ni push sin autorización.

## Tasks

| ID | Tarea | Specs | Ruta | Estado |
|---|---|---|---|---|
| T1 | Inspección, línea base y rama de tarea | S1, S12 | inline | hecho: `feat/object-mechanics-coverage` desde `f4f4919` |
| T2 | Auditoría Git y plan de integración | S2 | inline | hecho: sección 6 del informe |
| T3 | Investigación de las cinco mecánicas | S3-S7 | inline | hecho: `research/reports/object-mechanics-2026-10-20.md` |
| T4 | Extensión de esquema: procedencia secundaria, `percent_of`, `min`, variantes por rango | S8, S9 | inline | hecho: `schema.py`, `formula.py`, `validate.py`, `interface.py` |
| T5 | Actualización del catálogo: BotRK, LDR, Zhonya, Thornmail, Randuin, Botas de hechicero | S3-S9 | inline | hecho: 15 objetos, 10 efectos, `catalog_version: 2` |
| T6 | Pruebas de mecánicas, procedencia y regresión | S10 | inline | hecho: 214 pruebas (41 más que la base) |
| T7 | Documentación, ODD e índice del catálogo | S11 | inline | hecho: README del catálogo, README raíz, INDEX, research/README y este documento |
| T8 | Puertas de calidad e informe final | S10-S13 | inline | hecho: gates verdes; sin commits por instrucción |

## Log

### L1 — Solicitud original (resumen fiel)

Continuar LoL-Knowledge desde el estado real del repositorio. Prioridad: mejorar cobertura y fiabilidad del conocimiento de objetos, resolver cinco mecánicas pendientes y ampliar el catálogo de forma selectiva. En paralelo, auditar dependencias entre ramas y preparar un plan de integración **sin ejecutar fusiones ni modificar ramas compartidas**. Trabajar con Gentle-AI y agentes especializados si están disponibles; paralelizar investigación solo si hay paralelismo real; si no, trabajar secuencialmente sin simular agentes. Implementar las mejoras justificables con evidencia, pruebas de regresión y documentación; no limitarse a redactar un plan.

Mecánicas: A) BotRK, daño de impacto; B) BotRK, acumulaciones y efecto de ataques; C) Lord Dominik, curva de daño adicional; D) Zhonya, enfriamiento de la activa; E) Malla de espinas, daño reflejado. Para cada una: fórmula/dato, fuente y versión, referencia exacta, evidencia reproducible, confianza y justificación, contradicciones, preguntas pendientes y decisión (implementable, parcialmente modelable o no verificable). No inventar valores; conservar lo desconocido.

Fuentes: datos del juego del parche seleccionado; fuentes oficiales de Riot; binarios/archivos/CommunityDragon con versión y hashes; wiki comunitaria como corroboración; pruebas controladas si hacen falta. No tratar ausencia de campo como cero ni dos fuentes que copian el mismo dato como independientes.

Ampliación: objetos representativos para daño explosivo, físico, AP, impacto/vida del objetivo y supervivencia/mitigación. Antes de añadir: comprobar derivación desde Data Dragon, añadir solo lo no representable, conservar procedencia/versión, distinguir extraído/inferido/desconocido, representar efectos condicionales, derivar evaluabilidad de componentes. No modelar 870 objetos ni declarar completa una categoría.

Pruebas: fórmula, límites, cero real vs desconocido, ausentes/malformados, dependencias no soportadas, condiciones, referencias/versiones, procedencia incompleta, determinismo, contradicciones, regresión. Independientes de la lógica de producción. Sin red. Comandos listados en S10.

Git: rama local desde base verificada; no `dev`/`integration`/rama de investigación; no push, no fusiones, no reescribir historia, no borrar trabajo ajeno; Conventional Commits en inglés ≤ 72 caracteres; **ningún commit sin autorización explícita**; no pedir permiso para lecturas/pruebas/cambios dentro del alcance; detenerse ante ampliación de alcance, rama compartida u operación destructiva.

Informe final en el orden de la sección 10 de la solicitud, distinguiendo aceptación estructural, evidencia mecánica y verificación empírica. Exactitud antes que cobertura aparente.

### L2 — Estado inicial observado (2026-10-20)

- Árbol limpio en `feat/object-model` (`f4f4919`). `dev` e `integration` en `f3e2948`; `research/zaahen-formula-extraction` en `89e2dbe`; `feat/object-model` está 12 commits por delante de `dev` e incluye los 5 de la rama de investigación.
- `dev` e `integration` son la misma punta; no hay divergencia entre ellas.
- `feat/object-model` no está integrada. `research/zaahen-formula-extraction` es ancestro de `feat/object-model`.
- Línea base de pruebas y validaciones en S1; sin fallos de entorno.
- No hay trabajo local ajeno: el árbol estaba limpio antes de crear la rama.

### L3 — Evidencia de las mecánicas (2026-10-20)

Fuente principal de los números ausentes en Data Dragon: LoL Wiki (contenido comunitario, CC BY-SA 3.0), páginas en `action=raw` consultadas el 2026-10-20. La coherencia de identidad/balance se comprobó contra `data/current/items.json`: BotRK 40 AD / 25 % AS / 10 % LS / 3200 oro; LDR 35 AD / 35 % penetración / 25 % crítico / 3300 oro; Zhonya 105 AP / 50 armadura / 3250 oro; Thornmail 150 vida / 75 armadura / 2450 oro; Randuin 350 vida / 75 armadura / 2700 oro; Botas de hechicero 45 velocidad / 1100 oro. La wiki y el snapshot coinciden en todos esos valores, lo que corrobora que describen el mismo estado de balance.

- **BotRK (A):** 9 % (melee) / 6 % (ranged) de la vida **actual** del objetivo como daño físico adicional al impactar; máximo 100 contra súbditos y monstruos; sin mínimo publicado; no aplica a estructuras; el ratio depende del portador (melee/ranged), no del objetivo; ARAM 12 %/10 %, Arena 8 %/5 %; el daño se calcula al inicio del evento de daño y no dispara eventos on-hit; beneficia de robo de vida/omnivamp.
- **BotRK (B):** ataques básicos on-hit contra campeones aplican una acumulación durante 6 s, hasta 3; la tercera consume todas y ralentiza 30 % durante 1 s; enfriamiento interno 15 s; no lo bloquea el escudo de hechizos. La persistencia entre objetivos no está publicada: se registra como inferencia (acumulaciones sobre el objetivo) y no como hecho verificado.
- **Lord Dominik (C):** 1 % de daño adicional por cada 100 de vida adicional del objetivo, hasta 15 % con 1500; solo contra campeones; la vida adicional es la estadística del objetivo. Es una rampa lineal con tope, no solo dos extremos.
- **Zhonya (D):** activa de 120 s; estasis 2,5 s; el enfriamiento es de la activa, no la duración. Los activos de objeto se reducen con aceleración de objetos (p. ej. Perspicacia cósmica), no con aceleración de habilidades; esta interacción queda como nota y no se modela como fórmula.
- **Thornmail (E):** 20 + 10 % de armadura **adicional** como daño mágico reactivo al atacante; se activa al recibir un ataque básico/on-hit aunque el daño se mitigue, no si el ataque se esquiva/bloquea/falla; no es proyectil; aplica 40 % de Heridas graves durante 3 s a campeones; el daño reactivo se mitiga con la RM del atacante; las reducciones de armadura planas/porcentuales afectan al ratio de armadura adicional, la penetración no.

Decisión: A y E son implementables con una extensión mínima del evaluador; C es implementable con `percent_of` + `min`; B es implementable en estructura y valores, con la persistencia entre objetivos marcada como inferida; D es implementable como dato de enfriamiento con fuente secundaria. La confianza numérica es `secondary` (wiki) salvo los extremos que también publica Data Dragon; no se presenta como oficial de Riot.

### L4 — Decisiones de diseño

- Se conserva `schema_version: 1` porque los cambios son aditivos: nuevos campos opcionales (`sources`, `evidence_confidence`), nuevas operaciones (`percent_of`, `min`, `by_holder_range`), nueva estadística (`magic_penetration_flat`) y nuevo estado de base (`external_evidence_explicit`). Los documentos existentes siguen siendo válidos.
- Toda cifra que no aparezca en la descripción de Data Dragon debe estar respaldada por una cita de una fuente declarada en `sources`; el validador comprueba que cada número del efecto aparezca en la descripción o en alguna cita. Esto evita números huérfanos sin convertir la wiki en fuente oficial.
- `evidence_confidence` distingue `official`, `corroborated`, `secondary` y `unverified`. La wiki se marca `secondary`; la coincidencia de estadísticas con Data Dragon se documenta como corroboración de identidad, no como fuente oficial del número.
- BotRK necesita una entrada de contrato nueva: `ChampionState.attack_range` (`melee`/`ranged`). Sin ese dato, el evaluador falla explícitamente (`missing_holder_range`) en lugar de asumir melee.
- `TargetProfile.bonus_health` pasa a ser obligatorio: Lord Dominik lo usa y un cero implícito falsearía la curva. Es preferible un error de construcción a un resultado silenciosamente incorrecto.
- Las fuentes comunitarias no pueden declararse `official`; `corroborated` exige dos fuentes. Las claves desconocidas de una fórmula se rechazan para que un error tipográfico no cambie el sujeto de una estadística.
- La persistencia de acumulaciones de BotRK entre objetivos queda como nota inferida; no se modela como comportamiento verificado.

### L5 — Implementación, pruebas y estado final (2026-10-20)

**Esquema.** Se añadieron `magic_penetration_flat`, las operaciones `percent_of`, `min` y `by_holder_range`, el campo `subject` para desambiguar estadísticas del objetivo/portador, `sources` + `evidence_confidence` por efecto, el estado de base `external_evidence_explicit` y la verificación `secondary_source_verified`. `schema_version` sigue en `1` porque los cambios son aditivos; `catalog_version` pasa a `2`.

**Catálogo.** BotRK: 9 %/6 % de vida actual, cap 100 vs súbditos/monstruos, acumulaciones 3/6 s/15 s. Lord Dominik: `min(1 % de vida adicional, 15)`. Zhonya: enfriamiento 120 s. Thornmail: `20 + 10 % de armadura adicional`. Añadidos Botas de hechicero (`magic_penetration_flat`) y Randuin (crit −30 %, slow 70 %/2 s, 90 s). Total: 15 objetos, 10 efectos; 9 evaluables y 1 parcial (persistencia de acumulaciones de BotRK no verificada).

**Pruebas.** `pytest -q`: `214 passed in 4.18s`. `pytest research -q`: `97 passed in 0.73s`. `ruff check .`: limpio. `ruff format --check .`: `94 files already formatted` tras formatear `interface.py` y `test_objects_validator.py`. `lol_knowledge validate`: `valid: 183 files checked`, salida `0`. `python -m lol_knowledge.objects --validate`: `valid: 1 object catalog files checked`, salida `0`.

**Regresiones cubiertas.** El validador ya no lanza `KeyError` ante una fuente sin `quote`; `bonus_health` del objetivo se clasifica con `subject: target` y no como estadística del campeón; un número sin cita se reporta como violación; una fórmula `by_holder_range` sin rango falla con `missing_holder_range` en lugar de asumir melee. Tras la verificación independiente se endurecieron además: una fuente comunitaria no puede marcarse `official`, `corroborated` exige dos fuentes, los contadores y ventanas de acumulaciones entran en la regla de números citados, las claves desconocidas de una fórmula se rechazan (`subjet` ya no cae silenciosamente en la convención de campeón) y `TargetProfile.bonus_health` es obligatorio (sin cero implícito).

**Git.** Rama `feat/object-mechanics-coverage` desde `f4f4919`. Sin commits, sin push, sin fusiones, sin rebase. Los cambios están en el árbol de trabajo. `dev` = `integration` = `f3e2948`; `research` = `89e2dbe`; `feat/object-model` = `f4f4919`. Plan de integración en la sección 9 de `research/reports/object-mechanics-2026-10-20.md`.

**Limitaciones.** La wiki es fuente secundaria; no se hicieron mediciones en partida. La persistencia de acumulaciones de BotRK entre objetivos sigue sin verificar. Kraken Slayer, Luden's Companion, Eclipse y Sterak's Gage se evaluaron y se dejaron fuera por falta de fórmula completa verificable. El pipeline de mitigaciones y el orden de daño quedan para el futuro motor.
