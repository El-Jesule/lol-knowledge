# Fase `v1.3` — Fidelidad de Combate y Optimización de Duelos (`PERF-05..06`, Crítico Esperado, `On-Hit` y Táctica)

- **Versión objetivo:** `1.3.0`
- **Estado:** Planificada — pendiente de implementación
- **Prerrequisitos:** `v1.2.0` completada e integrada en `dev`
- **Rama sugerida:** `feat/v1-3-combat-fidelity`
- **Hoja de ruta:** [`../roadmap-v2.md`](../roadmap-v2.md) (`MEC-10`, `MEC-11`, `MEC-18`, `MEC-22`, `MEC-24`, `MEC-25`, `MEC-29`, `OBJ-02`, `OBJ-03`, `OBJ-04`, `OBJ-07`, `OBJ-09`, `PERF-05`, `PERF-06`)
- **Modo de ejecución recomendado:** En 2 etapas: Etapa 1 secuencial o en sub-pistas disjuntas de motor (`rotation/`, `defense/`, `duel.py`, `kit/model.py`, `damage/mitigation.py`, incluyendo `PERF-05..06`); Etapa 2 paralelizable por lotes de kits en `research/kits/*.spec.json`.

---

## 1. Contexto y problemas a resolver

Para que el optimizador (`v1.4`) y el asistente de partida (`v2.0`) valoren con precisión real y baja latencia a tiradores (`Zeri`, `Ezreal`, `Samira`, `Miss Fortune`), luchadores de impacto (`Yasuo`, `Yone`, `Irelia`, `Gangplank`) y duelos con activas tácticas, `v1.3` cierra cuatro huecos mecánicos y los **dos cuellos de botella residuales de duelos** detectados al perfilar `v1.2.0`:

1. **Crítico todo-o-nada en `rotation` y `duel`:** hoy un paso `attack` nunca critica (`0 %` efectivo aunque tengas `100 %` `crit_chance`) y `attack:crit` critica siempre (`100 %` efectivo aunque solo lleves `25 %` `crit_chance`). Esto impide evaluar matemáticamente la curva real de probabilidad × daño crítico en builds de 1, 2, 3 y 4 objetos de crítico.
2. **Habilidades que cuentan como ataque o aplican `on-hit` / crítico (`MEC-24`, `MEC-25`):** en campeones como **Zeri (`Q.burst`)**, **Ezreal (`Q`)**, **Yasuo/Yone (`Q`)**, **Gangplank (`Q`)** o **Irelia (`Q`)**, su habilidad principal aplica efectos al impactar, *Hoja encantada* y/o impacto crítico. Hoy figuran en `not_modelled` como daño de habilidad plano.
3. **Mitigación, velocidad de ataque y aceleraciones secundarias pendientes (`MEC-10`, `MEC-11`, `MEC-22`, `MEC-29`):** suelo `0,2` y *debuffs* de VA, penetración de armadura adicional, reducciones en `ability` y aceleración de invocadores/objetos en todas las activas.
4. **Objetos y táctica en duelos (`OBJ-02`, `OBJ-03`, `OBJ-04`, `OBJ-07`, `OBJ-09`, `MEC-18`):** falta activar *Puñal de Statikk* (`3087`), el decaimiento de `4,5 s` de *Sterak* (`3053`), la activa de estasis de *Reloj de arena de Zhonya* (`3157`) y la **interrupción de canalizaciones por Hard CC / silencio** en [`duel.py`](../../src/lol_knowledge/duel.py).
5. **Cuellos de botella residuales en `duel` y sobrecarga de tipos en `v1.2.0` (`PERF-05`, `PERF-06` — `Calculado` con `cProfile` sobre commit `db24d6a`):**
   - Mientras `rotation` ya bajó a `~2,9 ms/estado` en `v1.2.0`, `optimize_duel` aún tarda `~38,3 ms/estado` (`4,83 s` para `126` estados; `17,26 s` y `16,06 M` de llamadas en `211` estados bajo `cProfile`):
     - [`snapshot_state`](../../src/lol_knowledge/defense/session.py) se invocó **`73.836` veces** (`1,67 s`) ejecutando 4 *list comprehensions* sobre `rt.cc_locks` y recalculando `_shield_total` (**`114.274` llamadas**, `0,54 s`) en cada consulta de reloj aunque no hayan cambiado vida, escudos ni controles de masas.
     - [`accrue_continuous`](../../src/lol_knowledge/defense/shields_heals.py) se invocó **`17.743` veces** (`1,87 s`) entrando al bucle `while t < until:`, creando listas `boundaries` y un *closure* `_regen_eff` incluso cuando el defensor **no tiene ningún *HoT*, regeneración reactiva ni sangrado activo**.
     - [`_accrue_both`](../../src/lol_knowledge/duel.py) construye `target_snapshot(until)` (**`17.749` llamadas**, `0,87 s`) en cada tic de ambos luchadores aunque `offense` no tenga quemaduras ni procs diferidos pendientes.
     - En rutas calientes transversales persisten **`962.606` llamadas a `_abc_instancecheck`** (`0,87 s`, por `isinstance(..., Fraction | Mapping | Sequence)` sobre ABCs virtuales) y **`871.246` a `Fraction.__new__`** (`1,37 s`, por instanciar `Fraction(0)`/`Fraction(1)` dentro de bucles en vez de constantes reutilizables).

---

## 2. Invariantes y restricciones innegociables

- **Retrocompatibilidad del modo explícito e invarianza dorada:** `rotation` y `duel` conservan `crit_mode="explicit"` por defecto en llamadas manuales para que [`tests/test_performance_equivalence.py`](../../tests/test_performance_equivalence.py) siga pasando sin alterar los escenarios existentes (salvo cuando un kit concreto curado en el Paso 2 actualice explícitamente su caso documentado); `crit_mode="expected"` es opt-in en `rotation`/`duel` (`--crit-mode expected`) y pasa a ser el **modo por defecto en `optimize`**.
- **Aritmética exacta `Fraction` y cero dependencias externas:** el valor esperado y todas las optimizaciones `PERF-05..06` usan exclusivamente `fractions.Fraction` y biblioteca estándar ([`AGENTS.md`](../../AGENTS.md) §9), sin `float` intermedios, `random` ni Monte Carlo.
- **Trazabilidad `Derivado`:** todo metadato añadido a un `kit.json` (`applies_on_hit`, `can_crit`, `channel_duration`) debe citar la ruta del `.bin` o tooltip localizado del cliente `16.23`.

---

## 3. Plan de implementación paso a paso

### Paso 1 — Modo de valor esperado de crítico (`crit_mode="expected"`)
1. En [`src/lol_knowledge/rotation/`](../../src/lol_knowledge/rotation/__init__.py):
   - Añadir parámetro `crit_mode: str = "explicit"` (`"explicit" | "expected"`).
   - En `"expected"`, para todo ataque básico sin modificador explícito `:crit` (respetando la regla propia de Ashe que ya escala determinísticamente) y para toda habilidad con `can_crit=True`:
     - Si `p = crit_chance` es `0`, evaluar solo rama no crítica; si `p == 1`, evaluar rama `100 %` crítica.
     - Si `0 < p < 1`, calcular daño exacto ponderado $(1 - p) \cdot D_{\text{no\_crit}} + p \cdot D_{\text{crit}}$ (aplicando reducciones anti-crítico como *Presagio de Randuin* `3143` únicamente a la fracción crítica $p \cdot D_{\text{crit}}$ y reembolso esperado $1 + p$ segundos en *Yun Tal* `3032`).
   - Exponer `--crit-mode explicit|expected` en `rotation`, `duel` y `optimize` (por defecto `"expected"` en `optimize`), más `crit_mode` en Contrato JSON y MCP.

### Paso 2 — Esquema y motor para habilidades con `on-hit`, *Hoja encantada* y crítico (`MEC-24`, `MEC-25`)
1. En [`src/lol_knowledge/kit/model.py`](../../src/lol_knowledge/kit/model.py) y [`research/binmodel/kitgen.py`](../../research/binmodel/kitgen.py), ampliar `CaseSpec`:
   - `applies_on_hit: bool = False`
   - `on_hit_effectiveness: Fraction = Fraction(1)` (ej. factor exacto del bin en habilidades multimpacto como `Katarina R` / `Urgot W`).
   - `triggers_spellblade: bool = False` (consume/aplica *Hoja encantada* en el propio impacto de la habilidad, como `Ezreal Q`, `Gangplank Q`, `Zeri Q`).
   - `can_crit: bool = False` y `crit_bonus_multiplier: Fraction | None = None` (cuando el multiplicador crítico de la habilidad difiere del ataque estándar según el `.bin`, ej. `Yasuo Q`, `Yone Q`, `Samira Q`, `Garen E`).
   - `casts_at_attack_speed: bool = False` (para `Zeri Q`, cuyo intervalo entre lanzamientos en `--timeline` viene gobernado por `1 / attack_speed`).
2. En [`src/lol_knowledge/rotation/combat_steps.py`](../../src/lol_knowledge/rotation/combat_steps.py): cuando un `CaseSpec` declara estas banderas, emitir las partes `on_hit`, `spellblade`, contadores (`Kraken`, `Guinsoo`, `Terminus`) y escalado crítico correspondientes sin obligar al usuario a añadir un paso artificial `attack` detrás.
3. Curar y recompilar en `research/kits/*.spec.json` → `lol-knowledge/champions/<Id>/kit.json` al menos los **18 campeones prioritarios**: `Zeri`, `Ezreal`, `Gangplank`, `Yasuo`, `Yone`, `Irelia`, `Samira`, `MissFortune`, `Fiora`, `Warwick`, `Smolder`, `Fizz`, `Ekko`, `Senna`, `Viego`, `Belveth`, `Katarina` y `Garen` (`E` crítica).

### Paso 3 — Velocidad de ataque, mitigación y aceleraciones (`MEC-22`, `MEC-10`, `MEC-11`, `MEC-29`)
1. **`MEC-22` ([`attack-speed.md`](../../lol-knowledge/mechanics/attack-speed.md)):** aplicar suelo exacto `Fraction(1, 5)` (`0,2` ataques/s) en [`sheet.py`](../../src/lol_knowledge/stats/sheet.py) y soportar reducciones multiplicativas de VA entrantes/auras (*Corazón de hielo* `3110`, *Malla del guardián* `3082`, *Randuin* / habilidades como `Nasus W`, `Malphite E`) en `rotation`, `survive` y `duel`.
2. **`MEC-10` y `MEC-11` ([`damage-mitigation.md`](../../lol-knowledge/mechanics/damage-mitigation.md)):** añadir `--target-flat-reduction` / `--target-percent-reduction` en `ability`, y añadir `bonus_armor_penetration_percent` en `damage/` + `sheet.py` (compilando `Yasuo R` `50 %` pen. armadura adicional en impactos críticos).
3. **`MEC-29` y `OBJ-09`:** aplicar `summoner_spell_haste` (`8347` *Perspicacia cósmica*, `3158` *Botas jonias*) a enfriamientos de invocadores en `--timeline`/`duel` y `item_haste` a todas las activas de objeto restantes (*Zhonya*, *Randuin*, *QSS*, *Redención*, *Solari*).

### Paso 4 — *Statikk*, decaimiento de *Sterak*, *Zhonya* e interrupción de canalizaciones (`OBJ-02..04`, `OBJ-07`, `MEC-18`)
1. **Objetos (`catalog.json` + `rotation/` + `defense/`):**
   - Verificar/activar *Puñal de Statikk* (`3087`) como efecto `evaluable` (`OBJ-03`) y aceptar `--input energized_move_units_per_sec` opcional (`0` por defecto, documentando `OBJ-04`).
   - Modelar el decaimiento lineal continuo de `4,5 s` del escudo Salvavidas de *Calibrador de Sterak* (`3053`) en `--timeline` (`OBJ-02`).
   - Añadir ejecución de `item:3157` (*Reloj de arena de Zhonya*: `2,5 s` de estasis activa que niega daño entrante e impide actuar al propio lanzador) en `survive` y `duel` (`OBJ-07`, `OBJ-09`).
   - Aplicar el bono de velocidad de movimiento al impactar de *Fuerza de trinidad* (`3078`) en `--timeline` (`OBJ-07`).
2. **Interrupción de canalizaciones en [`duel.py`](../../src/lol_knowledge/duel.py) (`MEC-18` parcial):**
   - Añadir `channel_duration: Fraction | None = None` en efectos/casos canalizados (`MasterYi W`, `Katarina R`, `Malzahar R`, `Warwick R`, `Janna R`, `Fiddlesticks W`, `Briar E` cuando sea interrumpible).
   - En `duel.py`, si un campeón en canalización recibe un CC no bloqueado de `CC_BLOCKS_ABILITIES` (*stun*, *airborne*, *silence*, *suppression*, *fear*, *charm*, *polymorph*, *sleep*), truncar inmediatamente el resto de la canalización (*HoT*, reducción de daño o tics futuros de daño) y registrarlo en `DuelEvent.notes`.

### Paso 5 — Optimización de tics de Duelo/Defensa y rutas rápidas de `Fraction` (`PERF-05`, `PERF-06`)
Aprovechando que esta fase modifica [`duel.py`](../../src/lol_knowledge/duel.py), [`defense/`](../../src/lol_knowledge/defense/__init__.py), [`rotation/`](../../src/lol_knowledge/rotation/__init__.py) y [`damage/mitigation.py`](../../src/lol_knowledge/damage/mitigation.py):
1. **Caché invalidada de `DefenseState` y `_shield_total` (`PERF-05a`, en [`defense/session.py`](../../src/lol_knowledge/defense/session.py)):**
   - Mantener en `_DefenseRuntime` el último `DefenseState` y el próximo instante de vencimiento (`_state_valid_until: Fraction | None`) invalidándolos únicamente cuando muten `health`, `current_max_health`, `shields`, `cc_locks`, `ga_stasis_until`, `dynamic_grievous_until` o `steps`, o cuando `rt.clock` alcance `_state_valid_until`. Si `rt.cc_locks` está vacío, omitir las 4 *list comprehensions* de bloqueos.
2. **Cortocircuito `O(1)` en `accrue_continuous` (`PERF-05b`, en [`defense/shields_heals.py`](../../src/lol_knowledge/defense/shields_heals.py)):**
   - Mover `_regen_eff` fuera del bucle `while` y añadir al inicio una guarda rápida `_has_active_continuous(rt, t)`: cuando no haya ningún efecto continuo activo (*Fuerzas renovadas*, *Protoplasma*, *Escudo de Doran*, *Warmog* armada, poción, sangrados de *Baile de la muerte*, *HoTs* activos, buffs de vida temporal ni decaimiento de *Sterak*), actualizar `rt.last_accrued = until` y retornar `([], ZERO, [], [], None)` en `O(1)`.
3. **Sincronización perezosa en `_accrue_both` (`PERF-05c`, en [`duel.py`](../../src/lol_knowledge/duel.py)):**
   - Añadir `RotationSession.has_pending_accruals(until: Fraction) -> bool` (comprobando `burning`, `_summoner_burns`, quemaduras/procs diferidos de runas, `delayed_item_procs`, procs periódicos de `item_combat` y regeneración de recursos relevante). Si un luchador no tiene devengos pendientes antes de `until`, omitir la construcción de `target_snapshot(until)` y `sync_context` en ese tic intermedio.
4. **Rutas rápidas de tipos concretos y constantes `Fraction` (`PERF-06`):**
   - Sustituir en los bucles calientes de `damage/mitigation.py`, `rotation/`, `defense/` y `duel.py` los `isinstance(x, Fraction)` / `isinstance(x, Mapping)` / `isinstance(x, Sequence)` por comprobaciones rápidas `type(x) is Fraction`, `type(x) is dict` y `type(x) in (tuple, list)` antes del fallback ABC.
   - Reutilizar constantes compartidas `ZERO = Fraction(0)`, `ONE = Fraction(1)`, `HUNDRED = Fraction(100)` en lugar de instanciar `Fraction(0)`/`Fraction(1)` dentro de bucles repetitivos, evitar `sum(..., start=Fraction(0))` sobre secuencias vacías o de 1 elemento, y precompilar las fórmulas de `PostMsEffect` en [`sheet.py`](../../src/lol_knowledge/stats/sheet.py).
5. Actualizar las reglas en `lol-knowledge/mechanics/` (`critical-strike.md`, `basic-attacks-and-on-hit.md`, `attack-speed.md`, `damage-mitigation.md`, `duel.md`) y elevar `__version__` a `"1.3.0"`.

---

## 4. Validaciones obligatorias y criterios de salida (`Definición de terminado`)

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m pytest research/tests -q
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check .
.\.venv\Scripts\python.exe -m lol_knowledge validate
.\.venv\Scripts\python.exe research\tools\benchmark_engine.py
.\.venv\Scripts\python.exe research\tools\mutation_check.py --ci-sample
```

- [ ] Test unitario exacto de `crit_mode="expected"` verificando linealidad con `crit_chance` (`0 %`, `25 %`, `50 %`, `75 %`, `100 %`), interacción con *Filo infinito* (`3031`) y reducción de *Randuin* (`3143`) solo sobre la porción crítica.
- [ ] Test de `Zeri Q` y `Ezreal Q` aplicando *Hoja encantada*, efectos `on-hit` y crítico esperado (en Zeri), eliminando la nota correspondiente de `not_modelled`.
- [ ] Test de `duel` donde un `stun` o `silence` corta `MasterYi W` / `Katarina R` a mitad de canalización, y test donde `item:3157` (*Zhonya*) esquiva una definitiva diferida o quemadura durante `2,5 s`.
- [ ] **Meta de rendimiento de duelos (`PERF-05..06` en `benchmark_engine.py`):** `duel_1v1` warm baja de `~28 ms` (`v1.2.0`) a **`<= 14 ms`** y `optimize_duel` (`126` estados) baja de `~4,8 s` (`~38 ms/state`) a **`<= 2,2 s` (`<= 18 ms/state`, `>= 2×` de mejora adicional)** con `0` regresiones de equivalencia en modo `explicit`.
- [ ] Integrado en `integration`, validado y promovido con `--ff-only` a `dev` (sin `push`).
