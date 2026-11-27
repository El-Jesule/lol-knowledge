# Hoja de ruta post-v1.0: Pulido e Inteligencia del Motor (`v1.1`–`v1.6`) y Asistente de Selección de Campeones (`v2.0`)

- **Fecha de planificación:** 2026-11-27
- **Punto de partida:** `v1.0.0` (commit `bc431d0` en `dev`, parche `16.23.1` `Oficial` / cliente `16.23` `Derivado`).
- **Predecesor histórico:** [`roadmap.md`](roadmap.md) (fases 1 a 58 hasta el cierre de `v1.0.0`).
- **Estado:** Planificación aprobada; fases pendientes de implementación en orden estricto `v1.1` → `v1.6` → `v2.0`.

---

## 1. Visión estratégica y criterio de corte `1.X` vs `2.0` (`Recomendación`)

El desarrollo posterior a la `v1.0.0` se divide en dos etapas con responsabilidades claramente separadas:

1. **Serie `v1.1` a `v1.6` (`X = 6`) — Pulido, Velocidad, Modularidad e Inteligencia del Motor Determinista:**
   - **Objetivo:** convertir el motor local actual en una calculadora sub-milisegundo, modular, empíricamente contrastada e intrínsecamente inteligente al recomendar builds (valor esperado de crítico, identidad mecánica automática y frontera de Pareto), manteniendo **cero dependencias externas en runtime**, **cero acceso en vivo al cliente** y **aritmética exacta `Fraction`**.
   - **Por qué `X = 6`:** cada versión menor (`1.1` a `1.6`) ataca un único plano arquitectónico cohesivo con fronteras de archivos limpias y criterios de salida medibles. Juntar fases (por ejemplo, refactorizar módulos de 5.000 líneas a la vez que se cambia la matemática del crítico) multiplicaría el riesgo de regresiones; dividirlas más allá de `1.6` generaría entregas artificiales sin valor autónomo.
2. **Salto `v2.0` (`2.0.0`) — Asistente Determinista de Selección de Campeones (`Champ Select Assistant`):**
   - **Objetivo:** salto funcional diferenciado de producto. El sistema incorpora una base trazable de **Builds Estándar por `(campeón, rol)`**, un **Analizador Mecánico de Composición `5v5`** sobre los 5 kits rivales y tus aliados, y un **Conector Local LCU (`127.0.0.1`)** capaz de adaptar runas, fragmentos, hechizos de invocador y build completa en **`< 1 segundo`** dentro de la ventana real de `25–50 s` previa a entrar en partida.

```mermaid
flowchart LR
    V10["v1.0.0 (Actual)"] --> V11["v1.1 Rendimiento y Caché"]
    V11 --> V12["v1.2 Modularización y Mutación"]
    V12 --> V13["v1.3 Fidelidad de Combate y Crítico"]
    V13 --> V14["v1.4 Optimizador Inteligente y Pareto"]
    V14 --> V15["v1.5 Cobertura Plantel, Mascotas y Mapa"]
    V15 --> V16["v1.6 Verificación en Juego y Cierre 1.x"]
    V16 --> V20["v2.0 Asistente de Champ Select (5v5 + LCU)"]
```

---

## 2. Decisiones arquitectónicas incorporadas

Continuando la numeración de [`roadmap.md`](roadmap.md) §11 (`DEC-01` a `DEC-05`):

- **`DEC-06` (Aprobada el 2026-11-26 — Optimizador multiobjetivo e identidad en `v1.4`):**
  1. Ante objetivos temáticos o secundarios (ej. *«Zeri ADC full velocidad de movimiento»*), `optimize` utilizará **Frontera de Pareto (`Opción A`)**, descartando toda build matemáticamente dominada y devolviendo los escalones óptimos entre rendimiento de rol y objetivo secundario.
  2. El motor **deducirá automáticamente la identidad de combate del campeón** a partir de su `kit.json` y estadísticas del cliente (permitiendo sobreescritura explícita mediante `--profile`).
  3. Se ejecutará **primero la optimización de velocidad (`v1.1`)** antes de ampliar la búsqueda del optimizador (`v1.4`).
- **`DEC-07` (Aprobada el 2026-11-27 para `v2.0` — Builds estándar y conector de Selección de Campeones):**
  1. Se revisa `DEC-05` **exclusivamente a partir de `v2.0`** para admitir una capa separada de **Builds y Runas Estándar por `(campeón, rol)`**, etiquetada explícitamente como `Base recomendada` (nunca mezclada ni confundida con `Oficial`, `Derivado` o `Calculado`).
  2. **Prohibición estricta de scraping contrario a ToS ([`AGENTS.md`](../AGENTS.md) §10):** no se hará scraping con bots sobre `u.gg` ni portales con bloqueo anti-bot. Las fuentes autorizadas para poblar `standard-builds.json` en `v2.0` son: (a) los conjuntos recomendados por rol incluidos en los `.wad` del propio cliente de Riot (generados por Riot con telemetría real de cada parche), (b) agregación propia vía Riot API oficial (`match-v5`) si el usuario aporta clave de desarrollador aprobada, o (c) respaldo precalculado por el propio optimizador `v1.6`.
  3. **Cumplimiento estricto con Riot Games en `v2.0`:** el conector de Champ Select leerá únicamente `championId`, roles asignados y estado de fase en la LCU local (`127.0.0.1`). Queda **terminantemente prohibido en código** desanonimizar nombres de invocador ocultos en colas clasificatorias (*Lobby Revealer*), perfilar jugadores rivales o automatizar acciones de selección (*instalock*).

---

## 3. Mapa maestro de versiones y documentos de fase

Cada fase cuenta con su especificación detallada para agentes en `odd/tasks/`:

| Versión | Nombre de la fase | Documento de especificación | IDs de backlog cubiertos | Meta cuantitativa de cierre |
|---|---|---|---|---|
| **`v1.1.0`** | Rendimiento del Núcleo, Caché en RAM e Higiene | [`tasks/v1-1-engine-performance.md`](tasks/v1-1-engine-performance.md) | `PERF-01..04`, `FIX-01` (`Darius E`), `DOC-08` | `100 %` equivalencia `Fraction`; `>= 8×` mejora en `optimize`; MCP en caliente `< 5 ms` |
| **`v1.2.0`** | Modularización de Motores y Pruebas de Mutación | [`tasks/v1-2-engine-modularization.md`](tasks/v1-2-engine-modularization.md) | `QA-03`, `QA-02` | Ningún módulo de motor `> 1.500` líneas; `0` mutantes vivos en núcleo aritmético |
| **`v1.3.0`** | Fidelidad de Combate: Crítico Esperado, `On-Hit` y Duelos | [`tasks/v1-3-combat-fidelity.md`](tasks/v1-3-combat-fidelity.md) | `MEC-10`, `MEC-11`, `MEC-18` (canalizaciones), `MEC-22`, `MEC-24`, `MEC-25`, `MEC-29`, `OBJ-02` (Sterak), `OBJ-03`, `OBJ-04`, `OBJ-07`, `OBJ-09` | `crit_mode="expected"` exacto; `Zeri Q` y 16+ kits con `on_hit`/`can_crit`; *Zhonya* e interrupción de canalizaciones en `duel` |
| **`v1.4.0`** | Optimizador Inteligente: Identidad Automática y Pareto | [`tasks/v1-4-smart-optimizer.md`](tasks/v1-4-smart-optimizer.md) | `DEC-06`, `OPT-06` (identidad), `OPT-07` (`min_stats`), `OPT-08` (Pareto), `OPT-09` (subpool por familias) | `0` builds dominadas en Pareto; deducción determinista de perfil en los `173` kits |
| **`v1.5.0`** | Cobertura Total de Plantel (`AoE`, Senna, Mascotas) y Mapa | [`tasks/v1-5-roster-and-map-context.md`](tasks/v1-5-roster-and-map-context.md) | `DAT-03`, `DAT-04` (Senna), `MEC-17` (`173/173` AoE), `MEC-32` (dragones/Barón), `CH-Z-02..04`, `CH-A-02`, mascotas DPS | `173/173` campeones desbloqueados a nv. 1–18; `100 %` de casos con semántica `aoe` revisada |
| **`v1.6.0`** | Verificación Empírica en Partida, Licencias y Cierre `1.x` | [`tasks/v1-6-verification-and-v1-closure.md`](tasks/v1-6-verification-and-v1-closure.md) | `QA-01`, `OP-05`, `MEC-12`, `MEC-14..16`, `MEC-19..20`, `RUN-03` | Suite *golden* medida en cliente real; `usage-conditions.md` resuelto; `optimize` estándar `< 1 s` |
| **`v2.0.0`** | Asistente Determinista de Selección de Campeones (`5v5` + LCU) | [`tasks/v2-0-champ-select-assistant.md`](tasks/v2-0-champ-select-assistant.md) | `DEC-07`, `STD-01`, `DRAFT-01..03`, `LCU-01..02` | Adaptación completa de runas + hechizos + build vs 5 rivales en `< 500 ms` tras el último pick |

---

## 4. Trazabilidad de pendientes originales (`roadmap.md`) hacia `v1.1`–`v2.0`

Todo punto que permanecía `[ ]` en [`roadmap.md`](roadmap.md) queda asignado o acotado explícitamente:

- **Calidad y Operativa:** `QA-01` → `v1.6`; `QA-02` y `QA-03` → `v1.2`; `OP-05` → `v1.6`.
- **Datos:** `DAT-03` y `DAT-04` → `v1.5`; `DAT-05` (parser multi-locale) y `DAT-07`/`DAT-08` (tipos residuales de WAD/CDragon) quedan como mantenimiento opcional `P3` en `research/` sin bloquear `v1.x` ni `v2.0` (documentados en `v1.6`).
- **Mecánicas:** `MEC-10`, `MEC-11`, `MEC-18` (interrupción de canalizaciones), `MEC-22`, `MEC-24`, `MEC-25`, `MEC-29` → `v1.3`; `MEC-17` y `MEC-32` → `v1.5`; `MEC-12`, `MEC-14`, `MEC-15`, `MEC-16`, `MEC-19`, `MEC-20` → medidos y cerrados en `v1.6`. Mecánicas espaciales 2D (`MEC-27` ralentizaciones con movimiento, proyectiles) se mantienen fuera del motor temporal discreto salvo su impacto en activadores (`target_impaired`) y auditoría de CC en `v2.0`.
- **Objetos y Campeones:** `OBJ-02` (decaimiento Sterak), `OBJ-03`, `OBJ-04`, `OBJ-07`, `OBJ-09` → `v1.3`; `OBJ-10`/`OBJ-11` → verificados en `v1.6`; `CH-Z-02..04` y `CH-A-02` → `v1.5`.

---

## 5. Protocolo de ejecución para Agentes y uso de Orchestrator (`Recomendación`)

Cada fase **debe** seguir íntegramente [`AGENTS.md`](../AGENTS.md):

1. Leer [`AGENTS.md`](../AGENTS.md), este archivo y el documento `odd/tasks/v1-X-*.md` correspondiente.
2. Ejecutar preflight Git (`git status -sb`, `git branch -vv`, `git log --oneline -5`) y crear rama de tarea desde `dev`.
3. **Regla crítica si se ejecuta con Orchestrator (múltiples subagentes):**
   - **Solo el agente coordinador (Orchestrator)** ejecuta operaciones de Git (`checkout`, `commit`, `merge --no-ff` en `integration`, `merge --ff-only` en `dev`). Ningún subagente trabajador cambia de rama por su cuenta.
   - **Partición estricta de archivos:** dos subagentes en paralelo **nunca** deben editar el mismo archivo en el mismo turno.
   - **Estrategia recomendada por fase:**
     - **`v1.1`:** **Secuencial (1 agente o cadena serie)**. Toca núcleos acoplados antes de modularizar (`sheet.py`, `rotation.py`, `catalog.py`, `search.py`).
     - **`v1.2`:** **Orchestrator en 2 pistas tras definir interfaces**: Pista A refactoriza `src/lol_knowledge/rotation/`, Pista B refactoriza `src/lol_knowledge/defense/`, Pista C escribe `research/tools/mutation_check.py`.
     - **`v1.3`:** **Orchestrator en 2 etapas**: Etapa 1 (secuencial) añade soporte en motor (`crit_mode`, `applies_on_hit`, `Zhonya`, canalizaciones); Etapa 2 (paralela por lotes de campeones) actualiza los `research/kits/<Id>.spec.json` y `tests/`.
     - **`v1.4`:** **Orchestrator moderado (2 pistas)**: Pista A (`optimizer/identity.py` + tests de perfil), Pista B (`optimizer/pareto.py` + `min_stats` + subpool), seguidas de integración en CLI/Contrato/MCP.
     - **`v1.5`:** **Ideal para Orchestrator masivo por lotes**: los 157 specs de campeones (`MEC-17` + mascotas) se dividen en 4–6 subagentes por rangos alfabéticos sin colisión de archivos, mientras otro subagente implementa `MEC-32` (buffs de mapa) y `DAT-04` (Senna).
     - **`v1.6`:** **Mixto**: checklist humano/asistido en Herramienta de Práctica (`QA-01`) + subagente de tests *golden* + subagente de auditoría documental/licencias (`OP-05`).
     - **`v2.0`:** **Ideal para Orchestrator en 4 paquetes independientes**: `src/lol_knowledge/standard/`, `src/lol_knowledge/draft/threat_model.py`, `src/lol_knowledge/draft/optimizer.py` y `src/lol_knowledge/lcu/`, con agente revisor de seguridad/políticas Riot al cierre.
4. Ejecutar siempre las cuatro validaciones obligatorias de [`AGENTS.md`](../AGENTS.md) §5 (más `pytest research/tests -q` si se toca `research/`) sobre la rama y de nuevo sobre `integration` antes de promover con `--ff-only` a `dev`.
5. Al cerrar cada versión, actualizar su `odd/tasks/v*-*.md` cambiando `Estado: Planificada` a `Estado: Completada` con las métricas reales medidas, actualizar `src/lol_knowledge/__init__.py` (`__version__`) y marcar la fila en este documento.
