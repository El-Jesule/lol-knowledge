# Fase `v1.3` — Fidelidad de Combate: Crítico Esperado, Habilidades `On-Hit` y Duelos Tácticos

- **Versión objetivo:** `1.3.0`
- **Estado:** Planificada — pendiente de implementación
- **Prerrequisitos:** `v1.2.0` completada e integrada en `dev`
- **Rama sugerida:** `feat/v1-3-combat-fidelity`
- **Hoja de ruta:** [`../roadmap-v2.md`](../roadmap-v2.md) (`MEC-10`, `MEC-11`, `MEC-18`, `MEC-22`, `MEC-24`, `MEC-25`, `MEC-29`, `OBJ-02`, `OBJ-03`, `OBJ-04`, `OBJ-07`, `OBJ-09`)
- **Modo de ejecución recomendado:** En 2 etapas: Etapa 1 secuencial (motor `rotation/`, `defense/`, `duel.py`, `kit/model.py`); Etapa 2 paralelizable por lotes de kits en `research/kits/*.spec.json`.

---

## 1. Contexto y problema a resolver

Para que el optimizador (`v1.4`) y el asistente de partida (`v2.0`) valoren con precisión real a tiradores (como Zeri, Ezreal, Samira, Miss Fortune), luchadores de impacto (`Yasuo`, `Yone`, `Irelia`, `Gangplank`) y duelos con activas tácticas, hay cuatro huecos mecánicos en `v1.0`–`v1.2`:

1. **Crítico todo-o-nada en `rotation` y `duel`:** hoy un paso `attack` nunca critica (`0 %` efectivo aunque tengas `100 %` `crit_chance`) y `attack:crit` critica siempre (`100 %` efectivo aunque solo lleves `25 %` `crit_chance`). Esto impide evaluar matemáticamente la curva real de probabilidad × daño crítico en builds de 1, 2, 3 y 4 objetos de crítico.
2. **Habilidades que cuentan como ataque o aplican `on-hit` / crítico (`MEC-24`, `MEC-25`):** en campeones como **Zeri (`Q.burst`)**, **Ezreal (`Q`)**, **Yasuo/Yone (`Q`)**, **Gangplank (`Q`)** o **Irelia (`Q`)**, su habilidad principal aplica efectos al impactar, *Hoja encantada* y/o impacto crítico. Hoy figuran en `not_modelled` como daño de habilidad plano.
3. **Mitigación, velocidad de ataque y aceleraciones secundarias pendientes (`MEC-10`, `MEC-11`, `MEC-22`, `MEC-29`):** suelo `0,2` y *debuffs* de VA, penetración de armadura adicional, reducciones en `ability` y aceleración de invocadores/objetos en todas las activas.
4. **Objetos y táctica en duelos (`OBJ-02`, `OBJ-03`, `OBJ-04`, `OBJ-07`, `OBJ-09`, `MEC-18`):** falta activar *Puñal de Statikk* (`3087`), el decaimiento de `4,5 s` de *Sterak* (`3053`), la activa de estasis de *Reloj de arena de Zhonya* (`3157`) y la **interrupción de canalizaciones por Hard CC / silencio** en `duel.py`.

---

## 2. Invariantes y restricciones innegociables

- **Retrocompatibilidad del modo explícito:** `rotation` y `duel` conservan `crit_mode="explicit"` como comportamiento por defecto en llamadas manuales de CLI para no alterar escenarios deterministas golpe a golpe ya escritos; `crit_mode="expected"` es opt-in en `rotation`/`duel` (`--crit-mode expected`) y pasa a ser el **modo por defecto en `optimize`** (con `--crit-mode explicit` disponible si se desea).
- **Aritmética exacta `Fraction`:** el valor esperado pondera exactamente con `p = sheet["crit_chance"].total()` en `Fraction`, sin `random` ni Monte Carlo.
- **Trazabilidad `Derivado`:** todo metadato añadido a un `kit.json` (`applies_on_hit`, `can_crit`, `channeling`) debe citar la ruta del `.bin` o tooltip localizado del cliente `16.23` (y corroboración documental cuando proceda).

---

## 3. Plan de implementación paso a paso

### Paso 1 — Modo de valor esperado de crítico (`crit_mode="expected"`)
1. En `rotation/`:
   - Añadir parámetro `crit_mode: str = "explicit"` (`"explicit" | "expected"`).
   - En `"expected"`, para todo ataque básico sin modificador explícito `:crit` (respetando la regla propia de Ashe que ya escala determinísticamente) y para toda habilidad con `can_crit=True`:
     - Si `p = crit_chance` es `0`, evaluar solo rama no crítica; si `p == 1`, evaluar rama `100 %` crítica.
     - Si `0 < p < 1`, calcular daño exacto ponderado $(1 - p) \cdot D_{\text{no\_crit}} + p \cdot D_{\text{crit}}$ (aplicando reducciones anti-crítico como *Presagio de Randuin* `3143` únicamente a la fracción crítica $p \cdot D_{\text{crit}}$ y reembolso esperado $1 + p$ segundos en *Yun Tal* `3032`).
   - Exponer `--crit-mode explicit|expected` en `rotation`, `duel` y `optimize` (por defecto `"expected"` en `optimize`), más `crit_mode` en Contrato JSON y MCP.

### Paso 2 — Esquema y motor para habilidades con `on-hit`, *Hoja encantada* y crítico (`MEC-24`, `MEC-25`)
1. En [`src/lol_knowledge/kit/model.py`](../../src/lol_knowledge/kit/model.py) y [`research/binmodel/kitgen.py`](../../research/binmodel/kitgen.py), ampliar `CaseSpec`:
   - `applies_on_hit: bool = False`
   - `on_hit_effectiveness: Fraction = Fraction(1)` (ej. `Fraction(1, 4)` o factor exacto del bin en habilidades multimpacto como `Katarina R` / `Urgot W`).
   - `triggers_spellblade: bool = False` (consume/aplica *Hoja encantada* en el propio impacto de la habilidad, como `Ezreal Q`, `Gangplank Q`, `Zeri Q`).
   - `can_crit: bool = False` y `crit_bonus_multiplier: Fraction | None = None` (cuando el multiplicador crítico de la habilidad difiere del ataque estándar según el `.bin`, ej. `Yasuo Q`, `Yone Q`, `Samira Q`, `Garen E`).
   - `casts_at_attack_speed: bool = False` (para `Zeri Q`, cuyo intervalo entre lanzamientos en `--timeline` viene gobernado por `1 / attack_speed`).
2. En `rotation/combat_steps.py`: cuando un `CaseSpec` declara estas banderas, emitir las partes `on_hit`, `spellblade`, contadores (`Kraken`, `Guinsoo`, `Terminus`) y escalado crítico correspondientes sin obligar al usuario a añadir un paso artificial `attack` detrás.
3. Curar y recompilar en `research/kits/*.spec.json` → `lol-knowledge/champions/<Id>/kit.json` al menos los **18 campeones prioritarios**: `Zeri`, `Ezreal`, `Gangplank`, `Yasuo`, `Yone`, `Irelia`, `Samira`, `MissFortune`, `Fiora`, `Warwick`, `Smolder`, `Fizz`, `Ekko`, `Senna`, `Viego`, `Belveth`, `Katarina` y `Garen` (`E` crítica).

### Paso 3 — Velocidad de ataque, mitigación y aceleraciones (`MEC-22`, `MEC-10`, `MEC-11`, `MEC-29`)
1. **`MEC-22` ([`attack-speed.md`](../../lol-knowledge/mechanics/attack-speed.md)):** aplicar suelo exacto `Fraction(1, 5)` (`0,2` ataques/s) en `sheet.py` y soportar reducciones multiplicativas de VA entrantes/auras (*Corazón de hielo* `3110`, *Malla del guardián* `3082`, *Randuin* / habilidades como `Nasus W`, `Malphite E`) en `rotation`, `survive` y `duel`.
2. **`MEC-10` y `MEC-11` ([`damage-mitigation.md`](../../lol-knowledge/mechanics/damage-mitigation.md)):** añadir `--target-flat-reduction` / `--target-percent-reduction` en `ability`, y añadir `bonus_armor_penetration_percent` en `damage/` + `sheet.py` (compilando `Yasuo R` `50 %` pen. armadura adicional en impactos críticos).
3. **`MEC-29` y `OBJ-09`:** aplicar `summoner_spell_haste` (`8347` *Perspicacia cósmica*, `3158` *Botas jonias*) a enfriamientos de invocadores en `--timeline`/`duel` y `item_haste` a todas las activas de objeto restantes (*Zhonya*, *Randuin*, *QSS*, *Redención*, *Solari*).

### Paso 4 — *Statikk*, decaimiento de *Sterak*, *Zhonya* e interrupción de canalizaciones (`OBJ-02..04`, `OBJ-07`, `MEC-18`)
1. **Objetos (`catalog.json` + `rotation/` + `defense/`):**
   - Activar *Puñal de Statikk* (`3087`) como efecto `evaluable` (`OBJ-03`) y aceptar `--input energized_move_units_per_sec` opcional (`0` por defecto, documentando `OBJ-04`).
   - Modelar el decaimiento lineal continuo de `4,5 s` del escudo Salvavidas de *Calibrador de Sterak* (`3053`) en `--timeline` (`OBJ-02`).
   - Añadir ejecución de `item:3157` (*Reloj de arena de Zhonya*: `2,5 s` de estasis activa que niega daño entrante e impide actuar al propio lanzador) en `survive` y `duel` (`OBJ-07`, `OBJ-09`).
   - Aplicar el bono de velocidad de movimiento al impactar de *Fuerza de trinidad* (`3078`) en `--timeline` (`OBJ-07`).
2. **Interrupción de canalizaciones en `duel.py` (`MEC-18` parcial):**
   - Añadir `channel_duration: Fraction | None = None` en efectos/casos canalizados (`MasterYi W`, `Katarina R`, `Malzahar R`, `Warwick R`, `Janna R`, `Fiddlesticks W`, `Briar E` cuando sea interrumpible).
   - En `duel.py`, si un campeón en canalización recibe un CC no bloqueado de `CC_BLOCKS_ABILITIES` (*stun*, *airborne*, *silence*, *suppression*, *fear*, *charm*, *polymorph*, *sleep*), truncar inmediatamente el resto de la canalización (*HoT*, reducción de daño o tics futuros de daño) y registrarlo en `DuelEvent.notes`.
3. Actualizar las reglas en `lol-knowledge/mechanics/` (`critical-strike.md`, `basic-attacks-and-on-hit.md`, `attack-speed.md`, `damage-mitigation.md`, `duel.md`) y elevar `__version__` a `"1.3.0"`.

---

## 4. Validaciones obligatorias y criterios de salida (`Definición de terminado`)

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m pytest research/tests -q
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check .
.\.venv\Scripts\python.exe -m lol_knowledge validate
```

- [ ] Test unitario exacto de `crit_mode="expected"` verificando linealidad con `crit_chance` (`0 %`, `25 %`, `50 %`, `75 %`, `100 %`), interacción con *Filo infinito* (`3031`) y reducción de *Randuin* (`3143`) solo sobre la porción crítica.
- [ ] Test de `Zeri Q` y `Ezreal Q` aplicando *Hoja encantada*, efectos `on-hit` y crítico esperado (en Zeri), eliminando la nota correspondiente de `not_modelled`.
- [ ] Test de `duel` donde un `stun` o `silence` corta `MasterYi W` / `Katarina R` a mitad de canalización, y test donde `item:3157` (*Zhonya*) esquiva una definitiva diferida o quemadura durante `2,5 s`.
- [ ] Integrado en `integration`, validado y promovido con `--ff-only` a `dev` (sin `push`).
