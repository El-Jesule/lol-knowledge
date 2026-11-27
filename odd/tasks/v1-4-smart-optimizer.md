# Fase `v1.4` — Optimizador Inteligente: Identidad Automática, Restricciones y Frontera de Pareto

- **Versión objetivo:** `1.4.0`
- **Estado:** Planificada — pendiente de implementación
- **Prerrequisitos:** `v1.3.0` completada (`crit_mode="expected"` y kits `on_hit`/`can_crit` operativos)
- **Rama sugerida:** `feat/v1-4-smart-optimizer`
- **Hoja de ruta:** [`../roadmap-v2.md`](../roadmap-v2.md) (`DEC-06`, `OPT-06..09`)
- **Modo de ejecución recomendado:** Orchestrator en 2 pistas iniciales (`optimizer/identity.py` y `optimizer/pareto.py` + `subpool`), seguidas de integración única en `optimizer/search.py`, `cli.py`, `contract.py` y `mcp_server.py`.

---

## 1. Contexto y problema a resolver (`DEC-06`)

En `v1.0.0`, cuando un usuario o un LLM pide builds con requisitos mixtos o temáticos (ejemplo real: *«Zeri ADC full velocidad de movimiento»*), el optimizador falla por tres razones:

1. **Sin identidad de combate propia del campeón:** `default_champion_rotation` ([`search.py`](../../src/lol_knowledge/optimizer/search.py)) lanza una única secuencia corta `attack, R, attack, Q, attack, W, attack, E, attack` igual para un mago de ráfaga que para una tiradora de DPS sostenido como Zeri.
2. **Sin restricciones de estadísticas (`min_stats`) ni objetivos secundarios/Pareto:** no se puede pedir `move_speed` ni exigir `crit_chance >= 1.0`. Si se maximiza solo una estadística secundaria como velocidad de movimiento, los límites suaves (`415` y `490`, [`move-speed.md`](../../lol-knowledge/mechanics/move-speed.md)) hacen que objetos de tanque/utilidad regalen `1–3` puntos marginales de VM a costa de perder un `60–70 %` de DPS, cuando objetos de *Fervor* (*Bailarín espectral* `3046`, *Runaan* `3085`, *Cañón* `3094`) más *Filo infinito* (`3031`) logran prácticamente la misma velocidad efectiva con `100 %` de crítico y el triple de daño.
3. **Poda miope en `_select_subpool`:** la preselección evalúa 1 objeto aislado sobre inventario vacío; objetos sinérgicos sin DA propio (`3046` *Bailarín espectral*, `3094` *Cañón*) quedan fuera del top `16` antes del *beam search*.

En `DEC-06` se aprobaron dos principios rectores:
- **Deducción automática de la identidad del campeón** desde datos propios del repositorio (`kit.json` + `champion-records.json`).
- **Frontera de Pareto (`Opción A`)** para devolver builds no dominadas y descartar toda build subóptima.

---

## 2. Invariantes y restricciones innegociables

- **Cero *winrates* ni listas copiadas de webs externas** (`DEC-05` sigue vigente en toda la serie `1.x`): la identidad sale **100 % de fórmulas, enfriamientos, escalados y registros del cliente** (`Derivado` / `Calculado`).
- **Dominancia matemática estricta (`Fraction`):** una build $A$ domina a $B$ sobre los objetivos $(f_1, f_2)$ si $f_1(A) \ge f_1(B)$ y $f_2(A) \ge f_2(B)$ con al menos una desigualdad estricta (y a igualdad exacta de ambos, menor coste de oro). **Ninguna build dominada puede aparecer en `pareto_builds`.**
- **Separación intacta `OPT-03`:** la frontera de Pareto mantiene separadas `verified_pareto` (`Oficial`/`Derivado`) de `pending_pareto` (`Pendiente de verificación`).

---

## 3. Plan de implementación paso a paso

### Paso 1 — Deducción determinista de Identidad y Rotación Canónica (`OPT-06`, `src/lol_knowledge/optimizer/identity.py`)
1. Definir perfiles mecánicos deterministas (`CombatProfile`):
   - `marksman_dps`: alcance `ranged` (o kits melee de crítico como `Yasuo`, `Yone`, `Tryndamere`, `MasterYi`, `Nilah`) con alto ratio de VA / conversión de VA o habilidad spameable con `can_crit` / `applies_on_hit` (`Zeri`, `Jhin`, `Ashe`, `Caitlyn`, `Jinx`, `Samira`, `Ezreal`, `Kog'Maw`, `Vayne`…). Objetivo primario natural: `dps` con `crit_mode="expected"` sobre ventana de `6–8 s` (lanzando esteroide `R`/`Q`/`W`/`E` al inicio + bucle realista de ataques y habilidad principal según enfriamiento efectivo).
   - `sustained_caster`: campeón de PH/maná con habilidad principal de enfriamiento base `<= 3,5 s` (`Cassiopeia E`, `Ryze E+Q`, `Karthus Q`, `Azir W`, `Gwen Q`, `Aurelion Sol Q`). Objetivo primario natural: `dps` en ventana de `6 s`.
   - `burst_combo`: campeón con daño concentrado en rotación completa `Q+W+E+R` de enfriamientos medios/altos (`Ahri`, `Lux`, `Syndra`, `Zed`, `Talon`, `LeBlanc`, `Annie`). Objetivo primario natural: `rotation_damage` (combo completo con ataques intercalados si usa *Hoja encantada* o pasiva post-habilidad).
   - `bruiser_duelist`: cuerpo a cuerpo con curación/escudos propios en kit o escalados mixtos vida+DA/PH (`Darius`, `Aatrox`, `Jax`, `Camille`, `Fiora`, `Irelia`, `Mordekaiser`, `Zaahen`). Objetivo primario natural: `duel` o equilibrio `dps` + `effective_health_mixed`.
   - `tank_frontline`: kits dominados por `cc_effects`, escalados por vida/armadura/RM y mitigaciones activas (`Ornn`, `Malphite`, `Leona`, `Sejuani`, `Sion`, `Rammus`, `Tahm Kench`). Objetivo primario natural: `effective_health_mixed` / `time_to_die`.
   - `enchanter_support`: kits con curaciones/escudos aliados y escalado `heal_and_shield_power` (`Lulu`, `Janna`, `Soraka`, `Milio`, `Nami`, `Sona`, `Yuumi`). Objetivo primario natural: `shield_and_heal_output` + `ability_haste`.
2. Exponer `infer_combat_profile(champion, kit, derived, ranks) -> InferredProfile` (declarando en `notes` qué rasgos del kit dispararon la clasificación) y permitir sobreescritura explícita `--profile <auto|marksman_dps|...>`.

### Paso 2 — Nuevos objetivos de estadística/soporte y restricciones `min_stats` / `max_stats` (`OPT-07`)
1. Añadir a `OBJECTIVES` en [`src/lol_knowledge/optimizer/models.py`](../../src/lol_knowledge/optimizer/models.py):
   - `move_speed`: velocidad de movimiento efectiva tras límites suaves (y pico temporal si se pasa `--timeline` con habilidades/activas).
   - `ability_haste`: aceleración de habilidades efectiva total.
   - `shield_and_heal_output`: suma exacta de curación directa + escudos otorgados en una rotación de habilidades aprendidas (escalados con PH, DA, vida y `heal_and_shield_power`).
2. Añadir a `OptimizeConstraints`:
   - `min_stats: Mapping[str, Fraction] = field(default_factory=dict)` (ej. `{"crit_chance": Fraction(1), "move_speed": Fraction(420)}`).
   - `max_stats: Mapping[str, Fraction] = field(default_factory=dict)`.
   - Validar en la hoja final de cada candidato completa (`depth == remaining_slots`) que cumple `min_stats`/`max_stats`, guiando además al *beam search* mediante penalización de distancia al umbral en profundidades intermedias `1..k-1` (para que a hueco 2 de 4 encamine hacia `100 %` de crítico aunque aún lleve `50 %`!).

### Paso 3 — Búsqueda Multiobjetivo y Frontera de Pareto (`OPT-08`, `src/lol_knowledge/optimizer/pareto.py`)
1. Añadir `--secondary-objective <objetivo>` (y modo automático `--pareto-with-identity`: cuando el usuario pide optimizar un atributo secundario como `move_speed` o `ability_haste` sin desactivar la identidad del campeón, el motor empareja automáticamente `(primary = move_speed, secondary = profile.primary_objective)`).
2. Implementar búsqueda multiobjetivo determinista:
   - Ejecutar barrido sobre pesos convexos exactos $\lambda \in \{0, \tfrac{1}{5}, \tfrac{2}{5}, \tfrac{3}{5}, \tfrac{4}{5}, 1\}$ normalizados por los techos individuales $(F_1^{\max}, F_2^{\max})$ + refinamiento local *1-swap* de dominancia de Pareto sobre el conjunto unido de candidatos evaluados (reutilizando la caché de `_BuildEvaluator` para no evaluar dos veces la misma tupla de objetos).
   - Filtrar el frente exacto no dominado y anotar los hasta 3 arquetipos clave de la curva:
     - `role_optimum` (máximo desempeño en la función principal del campeón).
     - `knee_balanced` (**recomendación principal**: punto de máxima curvatura / menor sacrificio marginal de rol por unidad ganada del objetivo temático).
     - `theme_maximum` (máximo absoluto del objetivo temático).

### Paso 4 — Subpool por familias sinérgicas (`OPT-09`)
- En `_select_subpool` ([`search.py`](../../src/lol_knowledge/optimizer/search.py)), garantizar cuotas mínimas por ejes sinérgicos además del top marginal de 1 objeto:
  - Top objetos con `crit_chance + attack_speed/move_speed` (*Bailarín espectral* `3046`, *Huracán de Runaan* `3085`, *Cañón de fuego rápido* `3094`, *Puñal de Statikk* `3087`, *Flechas de los Yun Tal* `3032`, *Segador de esencia* `3508`).
  - Amplificadores y penetraciones porcentuales (`3031`, `3089`, `3036`, `3033`, `3135`, `3137`, `4645`, `3124`).
  - Objetos que alimentan estadísticas convertidas por la pasiva del campeón activo (p. ej. objetos de máxima VA en Zeri, vida en Vladimir/Mundo/Pyke/Sett, maná en Ryze/Kassadin, armadura/RM en Rammus/Ornn/K'Sante).

### Paso 5 — Paridad en CLI, Contrato JSON, MCP (`lol_optimize`) y prompts
- Exponer `profile`, `crit_mode`, `min_stats`, `max_stats` y `secondary_objective` / `pareto_builds` en `cli.py`, `contract.py`, `mcp_server.py` y [`lol-knowledge/ai-layer.md`](../../lol-knowledge/ai-layer.md) (actualizando `SERVER_INSTRUCTIONS` y `translate_scenario` para que ante peticiones tipo *«Zeri ADC full velocidad de movimiento»* el LLM invoque directamente `objective="move_speed", secondary_objective="dps"` o `profile="marksman_dps"` en una sola llamada). Elevar `__version__` a `"1.4.0"`.

---

## 4. Validaciones obligatorias y criterios de salida (`Definición de terminado`)

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check .
.\.venv\Scripts\python.exe -m lol_knowledge validate
.\.venv\Scripts\python.exe research\tools\benchmark_engine.py
```

- [ ] **Test de aceptación «Caso Zeri ADC Velocidad de Movimiento»:** `optimize` para `Zeri` nv. 16 con `objective="move_speed"` y `secondary_objective="dps"` devuelve una frontera de Pareto libre de builds dominadas donde `knee_balanced` alcanza `75–100 %` de crítico (incluyendo objetos de *Fervor* como `3046` + multiplicador de crítico) y ninguna build con igual o menor VM y menor DPS aparece en el resultado.
- [ ] **Test de inferencia de identidad:** `infer_combat_profile` clasifica determinísticamente una muestra representativa de los 6 arquetipos (`Zeri`/`Jinx`, `Cassiopeia`/`Ryze`, `Ahri`/`Zed`, `Darius`/`Zaahen`, `Ornn`/`Malphite`, `Lulu`/`Soraka`).
- [ ] **Test de `min_stats`:** `--min-stat crit_chance=1` en 5 huecos devuelve únicamente builds con `100 %` exacto de probabilidad de crítico.
- [ ] Integrado en `integration`, validado y promovido con `--ff-only` a `dev` (sin `push`).
