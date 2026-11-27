# Fase `v1.5` — Cobertura Completa de Plantel (`AoE`, Senna, Mascotas) y Contexto de Mapa

- **Versión objetivo:** `1.5.0`
- **Estado:** Planificada — pendiente de implementación
- **Prerrequisitos:** `v1.4.0` completada e integrada en `dev`
- **Rama sugerida:** `feat/v1-5-roster-and-map-context`
- **Hoja de ruta:** [`../roadmap-v2.md`](../roadmap-v2.md) (`DAT-03`, `DAT-04`, `MEC-17`, `MEC-32`, `CH-Z-02..04`, `CH-A-02`)
- **Modo de ejecución recomendado:** Ideal para **Orchestrator paralelo por lotes**: Lote 1 (`DAT-03`, `DAT-04` Senna y `MEC-32` buffs de mapa en código); Lotes 2–5 (división alfabética `A–D`, `E–K`, `L–R`, `S–Z` de `research/kits/*.spec.json` para `MEC-17` y mascotas, sin colisión de archivos); paso final único de compilación `kitgen` y validación.

---

## 1. Contexto y problema a resolver

Antes de que `v2.0` pueda evaluar cualquier sala real de Selección de Campeones (`5v5`, con `173` campeones posibles), quedan cuatro huecos de cobertura de datos en el plantel y en el mapa:

1. **Senna bloqueada a niveles `2–18` (`DAT-04`):** en [`README.md`](../../README.md) consta que Senna no tiene `attackdamageperlevel` en el bin (`0` en Data Dragon) porque su crecimiento procede de las almas de *Absolución*. Hoy pedir `stats`, `duel` u `optimize` con o contra Senna a nivel 11 deja su DA bloqueado salvo `--assume`.
2. **Semántica de área (`aoe` / `max_targets`) solo en 16 de 173 campeones (`MEC-17`):** solo `79` de los `968` casos de habilidad declaran `aoe` y `max_targets` (`CH-05`). Para evaluar *teamfights* (`--target-count 3..5`) en `v2.0` y aplicar el `33 %` de omnivampirismo en área, los `157` kits restantes deben tener su semántica multiobjetivo declarada.
3. **Campeones de mascotas / invocaciones de DPS:** en campeones como `Azir`, `Heimerdinger`, `Zyra`, `Yorick`, `Malzahar`, `Annie` (*Tibbers*), `Ivern` (*Daisy*) o `Naafiri`, parte sustancial de su daño sostenido proviene de ataques periódicos de mascotas hoy listados en `not_modelled`.
4. **Respaldo de maná/regeneraciones en el cliente (`DAT-03`) y Buffs Neutrales de la Grieta (`MEC-32`):** añadir `mp`, `mpperlevel`, `hpregen` y `mpregen` a [`champion-records.json`](../../lol-knowledge/derived/champion-records.json) (convirtiendo de `/s` del bin a `/5 s`), y modelar dragones, almas, Barón Nashor y mejoras roja/azul.

---

## 2. Invariantes y restricciones innegociables

- **Sin inventar almas ni objetivos:** en Senna (`mist_stacks`), si el usuario no pasa `--input mist_stacks=<N>`, `stats`/`ability`/`rotation` aplican `0` almas por defecto (`default: 0`, desbloqueando el DA base oficial `50` a todos los niveles con nota explícita de `mist_stacks=0`), mientras que `optimize` / perfiles pueden declarar explícitamente un supuesto estándar por nivel etiquetado según [`AGENTS.md`](../../AGENTS.md) §6, o evaluar con `--input mist_stacks`.
- **No tocar `data/current/` a mano:** toda actualización derivada pasa por `research/binmodel` y `validate`.

---

## 3. Plan de implementación paso a paso

### Paso 1 — Desbloqueo de Senna (`DAT-04`) y respaldo completo en `champion-records.json` (`DAT-03`)
1. En `research/binmodel` y [`lol-knowledge/derived/champion-records.json`](../../lol-knowledge/derived/champion-records.json):
   - Extraer `base_mana`, `mana_per_level`, `base_hp_regen_per_5s`, `hp_regen_per_level_per_5s`, `base_mana_regen_per_5s` y `mana_regen_per_level_per_5s` de los 173 campeones del cliente `16.23` (`DAT-03`), con pruebas cruzadas frente a Data Dragon `16.23.1`.
   - Registrar para **Senna** su crecimiento nativo confirmado de `0` DA por nivel en [`lol-knowledge/data-issues.json`](../../lol-knowledge/data-issues.json) / `champion-records.json` (`Derivado`, corroborado por el diseño de *Absolución*: `0` crecimiento por nivel + `+0,75` DA por alma en `SennaPassive`), y verificar en [`Senna/kit.json`](../../lol-knowledge/champions/Senna/kit.json) los aportes pasivos por `--input mist_stacks` (DA adicional, alcance y probabilidad de crítico cada 20 acumulaciones, con conversión de exceso de crítico a robo de vida).

### Paso 2 — Cobertura `173/173` de `aoe`, `max_targets` y `secondary_damage_ratio` (`MEC-17`)
1. Ampliar [`research/binmodel/specdraft.py`](../../research/binmodel/specdraft.py) / script auditor en `research/tools/` para detectar automáticamente desde los `.bin` y tooltips de los 157 campeones restantes si cada caso de daño es `aoe: false` (objetivo único) o `aoe: true` (área / proyectil perforante / rebote con `max_targets` y `secondary_damage_ratio` cuando exista en `DataValues`).
2. Curar por lotes los `research/kits/<Id>.spec.json`, recompilar los 173 `kit.json` con `python -m binmodel.kitgen` y verificar que `--target-count 3` evalúa sin degradar innecesariamente a `Pendiente de verificación` por falta de metadato `aoe`.

### Paso 3 — Soporte declarativo de Mascotas e Invocaciones de DPS, más flecos de Zaahen y Ahri
1. Soportar casos/efectos periódicos de mascota en kits (`Azir W` soldados, `Heimerdinger Q` torretas, `Zyra` plantas, `Malzahar W` entes, `Yorick` caminantes/Dama, `Annie R` aura/golpes de Tibbers, `Ivern R` Daisy, `Shaco W` cajas, `Naafiri P` manada) parametrizados por número de impactos o duración en `--timeline`.
2. Cerrar los flecos verificables en el cliente `16.23` de Zaahen (`CH-Z-02..04`: bonificaciones contra monstruos, reducción de daño y curación de `R` si no están completas) y Ahri (`CH-A-02`: reactivaciones extra de `R` con `--input champion_takedowns`).

### Paso 4 — Buffs Neutrales de la Grieta (`MEC-32`, `src/lol_knowledge/map_buffs.py`)
1. Crear `src/lol_knowledge/map_buffs.py` con definiciones trazables (`Derivado` del cliente `16.23` + corroboración wiki en `lol-knowledge/mechanics/map-buffs.md`):
   - Acumulaciones de Dragones Elementales (`infernal`, `mountain`, `ocean`, `cloud`, `hextech`, `chemtech`: `0..4`), Almas de Dragón, Aspecto del Dragón (*Anciano*), Mano del Barón (*Barón Nashor*), Emblema de Perspicacia (*Mejora Azul*) y Emblema de Ceniza (*Mejora Roja*).
2. Exponer `--buff <id>[=<stacks>]` en `stats`, `ability`, `rotation`, `survive`, `duel` y `optimize`, más `buffs` en Contrato JSON y MCP. Elevar `__version__` a `"1.5.0"`.

---

## 4. Validaciones obligatorias y criterios de salida (`Definición de terminado`)

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m pytest research/tests -q
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check .
.\.venv\Scripts\python.exe -m lol_knowledge validate
```

- [ ] `stats`, `rotation`, `duel` y `optimize` funcionan para **los 173 campeones a nivel 11 y 16** (incluida **Senna**) sin ninguna estadística de combate bloqueada.
- [ ] `100 %` de los casos de habilidad en los `173` `kit.json` tienen `aoe` (`true` o `false`) explícito.
- [ ] Tests de `map_buffs.py` verificando amplificadores de Dragón Infernal/Montaña (interacción con Rabadon y Condicionamiento), quemadura verdadera de Mejora Roja/Anciano y aceleración de Mejora Azul/Hextech.
- [ ] Integrado en `integration`, validado y promovido con `--ff-only` a `dev` (sin `push`).
