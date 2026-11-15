# Object mechanical model — fase 5

- **Objetivo:** auditar las garantías del extractor de `research/zaahen-formula-extraction`, corregir los defectos reales que invaliden su fiabilidad y entregar un modelo mecánico de objetos versionado, validado y preparado para un motor determinista de daño.
- **Rama:** `feat/object-model` (base: `research/zaahen-formula-extraction`, no `dev`, porque el extractor auditado todavía no está integrado). Sin push, sin merge a `dev`/`integration`.
- **Entrega:** código en `src/lol_knowledge/objects/`, catálogo curado en `lol-knowledge/objects/`, pruebas en `tests/` y `research/tests/`, auditoría en `research/reports/agent-d-extractor-audit.md`.
- **Runner:** `.\.venv\Scripts\python.exe -m pytest -q`; puertas completas (`ruff check`, `ruff format --check`, `lol_knowledge validate`) al cerrar.

## Specs

### S1 — Inspección y protección del repositorio

Leer `AGENTS.md`, `README.md`, `research/README.md`, la documentación de investigación y el ODD de extracción. Inspeccionar ramas, commits, árbol de trabajo y diferencias. No descartar, sobrescribir ni reorganizar trabajo existente. Si una comprobación falla, clasificar el fallo (entorno, instalación, implementación o documentación) antes de corregirlo.

Evidencia de línea base al empezar:

- `research/zaahen-formula-extraction` en `89e2dbe`, árbol limpio, 5 commits por delante de `dev` (`f3e2948`).
- `pytest -q`: `105 passed`.
- `pytest research -q`: `82 passed`.
- `ruff check .`: `All checks passed!`; `ruff format --check .`: `76 files already formatted`.
- `lol_knowledge validate`: `valid: 181 files checked`, código de salida `0`.

### S2 — Auditoría de garantías del extractor

Comprobar y documentar con evidencia reproducible:

1. Los valores desconocidos o referencias sin resolver nunca se convierten silenciosamente en cero.
2. La procedencia y la confianza sobreviven a extracción, referencias y overrides.
3. Los tipos provisionales no se presentan como semántica confirmada.
4. El evaluador rechaza explícitamente cálculos no soportados, ciclos y datos malformados.
5. Las fórmulas extraídas se distinguen de las inferidas y de las convenciones externas al binario.
6. Los resultados y diagnósticos son deterministas.

Cada defecto encontrado debe citar archivo y línea, una reproducción y su impacto. No se refactoriza nada fuera del alcance.

### S3 — Corrección de defectos reales con regresión

Solo se corrigen defectos reales y relevantes, con un test de regresión que falla antes y pasa después. No se toca código ajeno a la tarea. Los defectos identificados en la auditoría inicial son:

- Campos numéricos ausentes en `by_char_level_breakpoints` sustituidos por `0.0` (`evaluate.py`).
- Nodos `number`, `by_char_level_interpolation` y `stat_scaled` malformados que escapan como `TypeError`/`KeyError` en lugar de `FormulaError`.
- `GameCalculation` sin `mFormulaParts` y `SumOfSubPartsCalculationPart` sin `mSubparts` que se evalúan como `0.0`.
- `EvaluationContext.dependencies` que se acumula entre evaluaciones del mismo contexto.
- Entradas de `unresolved` sin `source_sha256` ni `content_version`.

### S4 — Esquema de objetos versionado

Esquema `lol-object-model/1`, con:

- identidad (`id` de Data Dragon), nombre y `game_version` enlazada al snapshot;
- estadísticas planas y porcentuales normalizadas (`flat`/`percent`, porcentaje en puntos);
- penetración de armadura y mágica, letalidad, aceleración de habilidades y robo de vida;
- efectos pasivos y activos con nombre, disparador, objetivo, condiciones, enfriamiento, acumulaciones, duración y límites;
- fórmulas de daño, curación, escudo y modificación de estadísticas;
- disponibilidad: compra, mapa, modo cuando exista, requisitos de campeón/aliado;
- fuente, versión, procedencia, confianza y estado de verificación por dato;
- componentes y receta como multiconjunto (Data Dragon repite ids para exigir dos copias).

### S5 — Sin duplicación y distinción de ausencias

No se repite en el catálogo curado lo que Data Dragon ya publica de forma estructurada: estadísticas planas/porcentuales, precio, mapas, `from`/`into`, `depth`, `requiredChampion`, `requiredAlly`, `inStore`, `hideFromAll`, `consumed`, `stacks`, `specialRecipe`. Se derivan del snapshot versionado.

El catálogo solo declara lo que Data Dragon no estructura: letalidad, aceleración de habilidades, penetraciones, estadísticas de crítico y efectos. Cada valor declarado cita una frase literal de la descripción oficial; el validador comprueba que la cita existe en la descripción normalizada del snapshot.

Se distinguen explícitamente:

- `value: 0` (cero numérico real);
- `{"op": "unknown", "reason": ...}` (dato ausente);
- `{"op": "unsupported", "reason": ..., "needed": [...]}` (efecto no modelado);
- `model_status: "excluded"` (efecto excluido por falta de información).

Ningún `null`, ausencia o desconocido se convierte en cero.

### S6 — Muestra representativa y cobertura explícita

Modelar una muestra mecánicamente diversa, no una supuesta cobertura total. Mínimo: estadística plana, porcentaje, crítico, robo de vida, letalidad, penetración porcentual de armadura y mágica, aceleración de habilidades, modificador porcentual de estadística, daño `on-hit` con ratio desconocido, daño basado en vida del objetivo, reducción de daño entrante, control con acumulaciones, activo con enfriamiento desconocido, reflejo con placeholder cero y heridas graves. Incluir componentes y recetas.

### S7 — Validador determinista e integrado

`lol_knowledge validate` valida también el catálogo de objetos cuando `lol-knowledge/objects/` existe. Códigos de violación explícitos para: versión de esquema, parche, id desconocido, duplicados, estadística desconocida o duplicada, cita no encontrada, valor declarado ausente de la cita, fórmula inválida, estado de modelo incoherente, referencia de receta rota y disponibilidad malformada. La salida es determinista y el orden de claves no altera el modelo canónico.

### S8 — Evaluador de fórmulas de objeto

Operaciones soportadas: `constant`, `stat`, `add`, `mul`. Rechazo explícito y tipado de `unknown`, `unsupported`, operación desconocida, estadística ausente, constante no finita y profundidad excesiva. `0` solo cuando el árbol dice `constant: 0`.

### S9 — Interfaz del motor de daño

Definir, sin implementar el motor ni una búsqueda de builds, las entradas de una evaluación de daño explosivo: campeón, nivel, rangos, estadísticas, objetos, runas, objetivo, resistencias, condiciones de impacto y rotación. La interfaz debe clasificar resultados en `evaluable`, `partially_evaluable`, `excluded` y `unreliable`, y validar que una petición no tenga campos ausentes o incoherentes.

### S10 — Pruebas

Cubrir: estadísticas y porcentajes; efectos con condiciones; fórmulas soportadas y no soportadas; referencias inválidas; versiones y procedencia; ausencia de sustitución silenciosa por cero; determinismo de extracción y validación; regresiones del extractor. Tests sin red.

### S11 — Documentación

Crear o actualizar: `research/reports/agent-d-extractor-audit.md`, `lol-knowledge/objects/README.md`, `lol-knowledge/INDEX.md`, `research/README.md`, `odd/tasks/object-model.md` y el log de `odd/tasks/zaahen-formula-extraction.md`. Cada afirmación importante con fuente, ruta, valor bruto, transformación y nivel de confianza. Declarar límites y lo no modelado.

### S12 — Flujo Git y entrega

Conventional Commits en inglés, asunto ≤ 72 caracteres, sin atribución de IA. Un commit por unidad coherente con tests y documentación. Sin push, sin merge a `dev`/`integration`, sin operaciones destructivas. Informe final con auditoría, esquema, objetos modelados, inventario no soportado, interfaz, pruebas reales, archivos, rama, commits, coste disponible y siguientes tareas.

## Tasks

| ID | Tarea | Specs | Ruta | Estado |
|---|---|---|---|---|
| T1 | Auditoría del extractor y evidencia | S1, S2 | inline | hecho: `research/reports/agent-d-extractor-audit.md` |
| T2 | Regresiones y correcciones acotadas | S3 | inline | hecho: 6 defectos, 15 pruebas; commit `61b1d8e` |
| T3 | Esquema y catálogo curado (13 objetos) | S4, S5, S6 | inline | hecho: `lol-object-model/1`, 8 efectos |
| T4 | Carga, modelo canónico y validador determinista | S4, S5, S7 | inline | hecho: `objects/catalog.py`, `objects/validate.py` |
| T5 | Evaluador de fórmulas e interfaz de daño | S8, S9 | inline | hecho: `objects/formula.py`, `objects/interface.py` |
| T6 | Pruebas del modelo y del validador | S10 | inline | hecho: 68 pruebas nuevas, 173 totales |
| T7 | Documentación, índice y auditoría publicada | S11 | inline | hecho: KB, índice, README raíz y `research/` |
| T8 | Puertas de calidad y commits | S12 | inline | hecho: `dde181d`, `61b1d8e`, `215e19c`, `c6bc5c3`, `69dca32` |

## Log

### L1 — Solicitud original

# LoL-Knowledge — Fase siguiente: auditoría del extractor y diseño del modelo mecánico de objetos

## Objetivo

Preparar la siguiente etapa de LoL-Knowledge para construir un motor determinista de evaluación y optimización de builds.

El extractor genérico de binarios se ha desarrollado en la rama `research/zaahen-formula-extraction`. Antes de implementar el optimizador, audita el estado real de esa rama, valida sus garantías y diseña la siguiente fase: un modelo estructurado de objetos y efectos que pueda utilizar posteriormente el motor de daño.

No empieces implementando el optimizador completo. Esta tarea debe entregar una base fiable y una implementación acotada del modelo de objetos, con pruebas y documentación.

## 1. Inspección y protección del repositorio

1. Lee `AGENTS.md`, `README.md`, la documentación de `research/` y el ODD relacionado con la extracción de fórmulas.
2. Inspecciona las ramas, commits, estado del árbol de trabajo y diferencias con las ramas base. No presupongas que el informe anterior describe el estado actual.
3. Verifica el extractor con las pruebas pertinentes, Ruff, el validador y el resto de comprobaciones exigidas por el proyecto.
4. Si falla una comprobación, determina si es un problema de instalación, entorno, implementación o documentación antes de corregirlo.
5. No descartes, sobrescribas ni reorganices cambios existentes sin autorización.

## 2. Auditar las garantías del extractor

Comprueba específicamente:

- Que los valores desconocidos o las referencias sin resolver nunca se conviertan silenciosamente en cero.
- Que la procedencia y la confianza sobrevivan a la extracción, las referencias y los overrides.
- Que los tipos identificados provisionalmente no se presenten como semántica confirmada.
- Que el evaluador rechace cálculos no soportados, ciclos y datos malformados de forma explícita.
- Que las fórmulas extraídas se distingan de las fórmulas inferidas y de las convenciones externas al binario.
- Que los resultados y diagnósticos sean deterministas.

Añade pruebas de regresión únicamente para defectos reales y relevantes. No hagas refactorizaciones generales ni modifiques código ajeno a la tarea.

## 3. Diseñar un modelo mecánico de objetos

Examina los datos de Data Dragon y las fuentes ya utilizadas en el proyecto. Determina qué información está disponible, cuál falta y cómo se puede obtener de manera reproducible.

Propón e implementa un esquema versionado para representar, como mínimo:

- Identidad del objeto y versión del juego.
- Estadísticas planas y porcentuales.
- Penetración, letalidad, aceleración de habilidades, robo de vida y otros atributos cuando existan.
- Efectos pasivos y activos.
- Fórmulas de daño y curación.
- Condiciones de activación, objetivos, enfriamientos, acumulaciones y límites.
- Restricciones de compra, mapa y modo de juego cuando sean relevantes.
- Fuente, versión, procedencia, confianza y estado de verificación.
- Componentes y recetas, si son necesarios para evaluar builds.

No inventes fórmulas para completar campos. Distingue entre dato ausente, valor desconocido, efecto no modelado y valor numérico igual a cero.

No dupliques en JSON información que pueda derivarse sin ambigüedad de una fuente de datos versionada, salvo que exista una razón técnica documentada.

## 4. Alcance de implementación

Implementa el esquema, el validador y una pequeña selección representativa de objetos que permita demostrar el modelo. Escoge los objetos tras inspeccionar los datos disponibles; prioriza diversidad mecánica frente a cantidad.

Incluye pruebas para:

- Estadísticas y porcentajes.
- Efectos con condiciones.
- Fórmulas soportadas y no soportadas.
- Referencias inválidas.
- Versiones y procedencia.
- Ausencia de sustitución silenciosa por cero.
- Determinismo de la extracción y validación.

No afirmes que todos los objetos o efectos están cubiertos si solo has modelado una muestra.

## 5. Preparación del motor de daño

Define la interfaz que permitirá al futuro motor consumir los datos de campeones y objetos.

La interfaz deberá distinguir entre:
- Fórmulas evaluables.
- Fórmulas parcialmente evaluables.
- Efectos excluidos por falta de información.
- Resultados que no se pueden calcular con fiabilidad.

Documenta qué entradas necesita una futura evaluación de daño explosivo: campeón, nivel, rangos, estadísticas, objetos, runas, objetivo, resistencias, condiciones de impacto y rotación de habilidades.

No implementes todavía una búsqueda exhaustiva de builds ni una simulación temporal completa.

## 6. Organización y flujo Git

- Sigue las convenciones de `AGENTS.md`.
- Trabaja en una rama de tarea apropiada, creada desde la base correcta.
- Usa Conventional Commits en inglés, con mensajes de hasta 72 caracteres.
- Mantén los cambios limitados a esta tarea.
- Ejecuta las comprobaciones antes de cada commit.
- No hagas push.
- No integres cambios en `integration` ni `dev` sin autorización.
- No ejecutes operaciones destructivas.
- Si necesitas cambiar de rama y hay modificaciones locales, protégelas y verifica que no se pierda ningún trabajo.

## 7. Entrega

Actualiza la documentación necesaria y entrega:

1. Resultado de la auditoría del extractor, con defectos y evidencias.
2. Esquema de objetos y justificación de sus decisiones.
3. Objetos y efectos realmente modelados.
4. Inventario de efectos todavía no soportados.
5. Interfaz propuesta para el motor de daño.
6. Pruebas ejecutadas y resultados reales.
7. Archivos modificados, rama y commits creados.
8. Coste aproximado o consumo disponible, sin inventar métricas que la herramienta no proporcione.
9. Siguientes tareas priorizadas.

Si la auditoría encuentra un defecto que invalida la fiabilidad del extractor, prioriza corregirlo y demostrar la corrección antes de ampliar el modelo de objetos.

Criterio de éxito: un modelo de objetos pequeño pero verificable, conectado conceptualmente con el extractor y preparado para un motor determinista. La cobertura real y las limitaciones deben quedar explícitas.

### L2 — Ejecución y evidencia (2026-10-20)

**Base y protección.** La rama se creó desde `research/zaahen-formula-extraction` (`89e2dbe`), no desde `dev`, porque el extractor auditado todavía no está integrado. `dev` seguía en `f3e2948` y el árbol estaba limpio. No se descartó ni reorganizó trabajo existente.

**Línea base.** `pytest -q` 105, `pytest research -q` 82, Ruff limpio, `lol_knowledge validate` 181 archivos y salida 0. Ningún fallo de entorno.

**Auditoría.** Se corrigieron seis defectos reales con regresión: cero silencioso en breakpoints y cálculos vacíos; `TypeError`/`KeyError` en nodos malformados; dependencias filtradas entre evaluaciones; `unresolved` sin SHA-256 ni versión; factores sintéticos sin confianza ni procedencia. La política de defaults omitidos queda marcada como `inferred`. Detalle y líneas en `research/reports/agent-d-extractor-audit.md`; commit `61b1d8e`. `pytest research` pasó de 82 a 97.

**Modelo.** `lol-object-model/1` con identidad, estadísticas planas y porcentuales normalizadas, letalidad, penetraciones, aceleración, robo de vida, efectos pasivos/activos, fórmulas, condiciones, enfriamientos, acumulaciones, límites, disponibilidad, procedencia, confianza, recetas y componentes. El catálogo curado no repite lo derivable de Data Dragon y cita la descripción para cada dato de prosa.

**Muestra real.** 13 objetos, 28 estadísticas (7 declaradas desde prosa), 8 efectos: 3 `evaluable`, 4 `partially_evaluable`, 1 `excluded`. Objetos: 1036, 1031, 3067, 3134, 3135, 3089, 3031, 3153, 3036, 3047, 3157, 3075 y 6617. No se afirma cobertura del resto del catálogo.

**Interfaz.** `ChampionState`, `ItemSlot`, `RuneState`, `TargetProfile`, `ImpactConditions`, `RotationStep`, `DamageRequest` y `DamageOutcome` con cuatro estados (`evaluable`, `partially_evaluable`, `excluded`, `unreliable`). `validate_request` rechaza hojas incompletas, objetivos incoherentes, objetos duplicados y rotaciones vacías. No hay simulación.

**Validación ejecutada.** `pytest -q`: 171 pasan. `pytest research -q`: 97 pasan. `ruff check .`: limpio. `ruff format --check .`: 91 archivos formateados. `lol_knowledge validate`: 183 archivos, salida 0. `python -m lol_knowledge.objects --validate`: 1 catálogo válido. `--json` produjo dos veces el mismo SHA-256 (`ed1b0be7…`), 38 015 bytes.

**Git.** Rama `feat/object-model`. Commits: `dde181d` plan ODD, `61b1d8e` correcciones del extractor, `215e19c` modelo de objetos. Sin push, sin merge a `dev`/`integration`, sin operaciones destructivas.

**Coste.** La herramienta no expone tokens, CPU ni coste monetario; no se inventan. Métricas disponibles: 173 pruebas en 2.7 s, 183 archivos validados y el diff de la rama.

**Límites.** Muestra de 13 objetos; sin motor de daño, sin búsqueda de builds y sin simulación temporal. Ratios, curvas y enfriamientos no publicados se marcan como desconocidos o excluidos.
