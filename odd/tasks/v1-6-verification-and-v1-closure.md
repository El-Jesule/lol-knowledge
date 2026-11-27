# Fase `v1.6` — Verificación Empírica en Partida (`QA-01`), Auditoría Legal (`OP-05`) y Cierre de `v1.x`

- **Versión objetivo:** `1.6.0` *(última versión de la serie `1.x` antes del salto a `v2.0`)*
- **Estado:** Planificada — pendiente de implementación
- **Prerrequisitos:** `v1.5.0` completada e integrada en `dev`
- **Rama sugerida:** `chore/v1-6-verification-and-closure`
- **Hoja de ruta:** [`../roadmap-v2.md`](../roadmap-v2.md) (`QA-01`, `OP-05`, `MEC-12`, `MEC-14..16`, `MEC-19..20`, `RUN-03`, `OBJ-10..11`)
- **Modo de ejecución recomendado:** Mixto (sesión guiada de medición en Herramienta de Práctica + 2 pistas de agente: Pista A suite *golden* y ajustes de reglas; Pista B cierre documental/legal `OP-05` y auditoría integral de `1.6.0`).

---

## 1. Contexto y propósito del cierre `1.x`

Con las fases `v1.1`–`v1.5` completadas, el motor determinista tendrá velocidad sub-milisegundo, arquitectura modular, crítico esperado, identidad automática, frontera de Pareto y los `173/173` campeones cubiertos.

Para cerrar definitivamente la familia **`1.x`** antes de construir encima el asistente en vivo de Selección de Campeones (`v2.0`), `v1.6` resuelve los dos últimos pilares de rigor del proyecto:

1. **Contraste empírico en el cliente real (`QA-01`):** medir en la Herramienta de Práctica (*Practice Tool*) la lista acotada de interacciones que hoy degradan resultados a `Pendiente de verificación` por falta de confirmación directa en partida.
2. **Saneamiento jurídico y de redistribución (`OP-05`):** cerrar las cuatro cuestiones abiertas en [`research/evidence/usage-conditions.md`](../../research/evidence/usage-conditions.md) para que el repositorio pueda publicarse o compartirse sin ambigüedades legales.

---

## 2. Plan de implementación paso a paso

### Paso 1 — Protocolo y batería de mediciones en Herramienta de Práctica (`QA-01`)
1. Redactar `odd/procedures/practice-tool-verification.md` con una tabla reproducible de **12 experimentos rápidos en Herramienta de Práctica** (campeón, nivel, objetos exactos, muñeco de práctica con resistencias/vida conocidas y cifra exacta a observar en pantalla/registro de muerte) para resolver:
   - **`RUN-03`:** desempate `0 == 0` de fuerza adaptable en campeones con y sin `mAdaptiveForceToAbilityPowerWeight = 1` ([`runes.md`](../../lol-knowledge/mechanics/runes.md)).
   - **`MEC-14`:** apilado de múltiples fuentes de daño crítico adicional ([`critical-strike.md`](../../lol-knowledge/mechanics/critical-strike.md)).
   - **`MEC-15` y `MEC-16`:** curación en golpe letal con *overkill* y suma de robo de vida + omnivampirismo sobre la misma parte ([`life-steal-and-omnivamp.md`](../../lol-knowledge/mechanics/life-steal-and-omnivamp.md)).
   - **`MEC-19` y `MEC-20`:** recálculo del temporizador de ataque cuando sube la VA a mitad de animación y si el impacto que activa un efecto temporal (*Hoja encantada*, *Vigor*) ya recibe su propio bono ([`timeline.md`](../../lol-knowledge/mechanics/timeline.md)).
   - **`OBJ-10` y `OBJ-11`:** primer golpe luminoso/sombrío de *El final* (`3302`), renovación de acumulaciones de *Verdugo de krakens* (`6672`) y rampa lineal de *Verdugo de gigantes* (`3036`).
   - **`MEC-12`:** regla de redondeo visual mostrada por el cliente en números flotantes de daño/estadísticas (añadiendo opción de formato `--display-rounding game|exact`, manteniendo `exact` por defecto).
2. Guardar las mediciones verificadas (parche, fecha, escenario, valor observado en el juego, valor `exact` del motor) en `tests/fixtures/in_game_measurements.json` y crear `tests/test_in_game_golden.py`.
3. Promover en el motor de `Label.PENDING` a `Label.DERIVED` (con cita a `in_game_measurements.json`) únicamente aquellas interacciones confirmadas empíricamente; si alguna contradice la suposición previa, corregir la fórmula y documentar el hallazgo.

### Paso 2 — Cierre de condiciones de uso y redistribución (`OP-05`)
1. Auditar todos los archivos bajo `tests/fixtures/` y `research/fixtures/`:
   - Verificar que no exista ningún binario ni volcado íntegro del cliente (solo constantes numéricas mínimas o fixtures sintéticos para tests). Si algún recorte de `research/fixtures/` contiene estructura superflua del cliente, sustituirlo por datos mínimos o moverlo a regeneración local en `.cache/` documentada en `odd/procedures/patch-update.md`.
2. Actualizar [`research/evidence/usage-conditions.md`](../../research/evidence/usage-conditions.md) cerrando las 4 cuestiones pendientes (distinción entre datos numéricos factuales y texto creativo bajo CC BY-SA 3.0, atribución de CommunityDragon/Wiki y bloque de aviso legal de Riot Games en [`README.md`](../../README.md) y [`lol-knowledge/INDEX.md`](../../lol-knowledge/INDEX.md)).

### Paso 3 — Auditoría integral de cierre `v1.6.0` (Contrato, MCP y Rendimiento)
1. Ejecutar barrido automatizado sobre los `173` campeones en `stats`, `rotation`, `duel` y `optimize` verificando `0` excepciones inesperadas y tiempos objetivos (`< 5 ms` consultas individuales en caliente, `< 1.000 ms` optimización estándar de 6 huecos).
2. Actualizar [`README.md`](../../README.md), [`lol-knowledge/INDEX.md`](../../lol-knowledge/INDEX.md) y [`lol-knowledge/ai-layer.md`](../../lol-knowledge/ai-layer.md) al estado completo de `v1.6.0` y elevar `__version__` a `"1.6.0"`.

---

## 3. Validaciones obligatorias y criterios de salida (`Definición de terminado`)

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m pytest research/tests -q
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check .
.\.venv\Scripts\python.exe -m lol_knowledge validate
.\.venv\Scripts\python.exe research\tools\benchmark_engine.py
```

- [ ] `tests/test_in_game_golden.py` pasa al `100 %` contra las mediciones reales registradas.
- [ ] El empate de fuerza adaptable a nivel 1 sin objetos (`RUN-03`) ya no degrada innecesariamente páginas estándar de runas a `Pendiente de verificación` si queda confirmado en partida.
- [ ] Las 4 cuestiones de `usage-conditions.md` están cerradas y verificadas (`OP-05`).
- [ ] Integrado en `integration`, validado y promovido con `--ff-only` a `dev` como cierre oficial de la rama `1.x` (sin `push` salvo autorización expresa del usuario).
