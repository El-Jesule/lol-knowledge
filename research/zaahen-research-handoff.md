# Zaahen — documento de continuidad de la investigación

- **Parche objetivo:** 16.20.1 (Data Dragon) / contenido 16.20 (CommunityDragon)
- **Fecha de cierre de esta fase:** 2026-10-18
- **Rama:** `docs/zaahen-research-handoff` (base: `dev`)
- **Estado:** fase 3.5 cerrada. Hallazgos verificados integrados en la base de conocimiento; líneas abiertas declaradas en la sección J.

---

## A. Para qué sirve este documento

Este archivo existe para que **otro agente pueda continuar la investigación sin acceso a la conversación original**. Contiene:

1. Qué se intentó probar y qué se demostró, con la evidencia concreta (rutas, hashes, valores observados).
2. Qué quedó como **inferencia** (coherente con la evidencia, no demostrado).
3. Qué quedó **abierto**, con el punto exacto donde se detuvo.
4. Cómo reproducir cada pieza y qué límites de licencia aplican.

Regla de lectura: **una afirmación sin evidencia citada en este documento no debe reutilizarse como hecho**. Antes de escribir cualquier valor en `lol-knowledge/`, comprobar si está marcado como verificado, inferido o abierto.

---

## B. Objetivo y contexto

Objetivo de la investigación: disponer de datos numéricos de Zaahen lo bastante trazables como para **modelar y calcular builds orientadas a letalidad**, sin recurrir a fuentes comunitarias no verificables y sin inventar cifras.

Motivo: Data Dragon publica para Zaahen la estructura del kit (nombres, costes, enfriamientos, rangos y texto descriptivo) pero **no los valores numéricos de los efectos**: los tooltips usan marcadores con nombre (`initialdamage`, `healpercent`, `damageendcalc`, …) y `effectBurn` viene a `0`. Sin esos números, cualquier cálculo de daño sería una invención.

Por eso se exploraron tres vías alternativas:

| Vía | Qué aporta | Resultado |
|---|---|---|
| CommunityDragon (export del bin del cliente) | Valores numéricos por campo, con ruta exacta | 41 parámetros extraídos; 3 bloqueados por conflicto |
| Archivos del cliente (`*.wad.client`) | Cadenas localizadas, versiones históricas, semántica de campos | Cadenas localizadas extraídas; bindings históricos localizados |
| Wiki (tercero, CC BY-SA 3.0) | Valores de contraste | Usada solo como contraste, nunca como fuente oficial |

---

## C. Estado del repositorio y artefactos

### Qué se versiona

| Ruta | Contenido |
|---|---|
| `research/README.md` | Índice de navegación del directorio |
| `research/zaahen-research-handoff.md` | Este documento |
| `research/cdragon_zaahen/` | Prototipo Python (cliente, extracción, comparación, evidencia wiki, CLI) |
| `research/fixtures/` | Recortes mínimos de los datos usados (no el archivo original) |
| `research/evidence/usage-conditions.md` | Fuentes consultadas, lo que dicen y dudas abiertas |
| `research/tests/` | Suite offline del prototipo |
| `odd/tasks/zaahen-research-handoff.md` | Seguimiento de esta fase |

### Qué **no** se versiona

| Ruta | Motivo |
|---|---|
| `research/.cache/zaahen-16.20.bin.json` | Export original descargado; dudas sobre redistribución |
| `research/reports/*.json` | Informe generado; se regenera con la CLI |
| `research/**/__pycache__/` | Artefactos de ejecución |

### Independencia del producto

Nada en `src/lol_knowledge/`, `tests/` ni `data/current/` importa ni depende de `research/`. El prototipo se puede borrar (`Remove-Item -Recurse -Force research`) sin afectar a la CLI ni al snapshot.

### Archivos temporales

Las verificaciones de la fase anterior se ejecutaron con scripts sueltos en `%TEMP%` (`monster_versions.py`, `explore_wad.py`, `rst_probe*.py`). **Esos archivos no son durables ni se versionan**: si hace falta repetir esas comprobaciones, deben reescribirse partiendo de la sección F.

---

## D. Hallazgos verificados

Los tres hallazgos (H1, H2, H3) se etiquetan con su nivel real de demostración. **Ninguno se apoya en la wiki ni en CommunityDragon presentados como fuente oficial.**

### D.1 H1 — Identificación de la parte de interpolación por hash (verificado por cálculo)

- **Hecho:** `fnv1a32("ByCharLevelNamedDataValuesInterpolationCalculationPart")` = `0xee18a47b`.
- **Algoritmo:** FNV-1a de 32 bits (offset `0x811C9DC5`, primo `0x01000193`) sobre el nombre en minúsculas. La variante se validó antes contra seis pares conocidos de nombre → hash del bin.
- **Evidencia:** en `research/fixtures/zaahen_spells_min.json` la parte de cálculo aparece referenciada por `{ee18a47b}`.
- **Alcance real de la prueba:** coincide **por cálculo** con el identificador observado. El nombre `ByCharLevelNamedDataValuesInterpolationCalculationPart` **no aparece** en los metadatos publicados (LeagueToolkit) ni en los diccionarios de CommunityDragon. Es decir: la coincidencia es fuerte, pero no es una equivalencia publicada por un tercero independiente.
- **Cómo repetirlo:**

```python
def fnv1a32(name: str) -> int:
    h = 0x811C9DC5
    for byte in name.lower().encode("utf-8"):
        h ^= byte
        h = (h * 0x01000193) & 0xFFFFFFFF
    return h


format(fnv1a32("ByCharLevelNamedDataValuesInterpolationCalculationPart"), "08x")  # 'ee18a47b'
```

- **Consecuencia práctica:** se puede tratar `{ee18a47b}` como esa parte de interpolación al analizar el bin, dejando constancia de que la etiqueta es una reconstrucción propia.

### D.2 H2 — Multiplicador de Q contra monstruos (valores y semántica verificados)

Valores observados en el campo `MonsterDamagePercent` del bin, por versión, **re-verificados el 2026-10-18** descargando cada export:

| Versión de contenido | Bin | Wiki (contraste) |
|---|---|---|
| 15.23 | `0.5` | 150 % |
| 15.24 | `0.75` | 175 % |
| 16.3 | `1.0` | 200 % |
| 16.20 | `1.0` | 200 % |

- **Verificado:** los cuatro valores del bin, uno por versión, en el mismo campo (7 entradas idénticas por versión). URLs: `https://raw.communitydragon.org/<versión>/game/data/characters/zaahen/zaahen.bin.json` para `15.23`, `15.24`, `16.3` y `16.20`. Los cuatro exports se descargaron de nuevo; no se reutilizaron cifras de la fase anterior.
- **Verificado también:** `Q1BaseDamage` no cambia entre versiones (`15 / 30 / 45 / 60 / 75` en los cuatro exports). El enfriamiento sí cambió: `cooldownTime` es `[9, 9, 8, 7, 6, 5, 7]` en 15.23 y `[10, 10, 9, 8, 7, 6, 5]` desde 15.24. En 15.23–16.3 **no existe** el campo `Cooldown`; solo `cooldownTime`. Eso confirma que el multiplicador es un campo independiente y no un efecto lateral del daño base.
- **Semántica verificada por el texto oficial del cliente:** la cadena `spell_zaahenq_tooltipextended` de `Global.es_ES.wad.client` dice literalmente: «Inflige un `@MonsterDamagePercent*100@%` de **daño adicional** a monstruos.» El campo es, por tanto, el porcentaje **adicional**, no el multiplicador total. Con `1.0` → +100 % adicional → 200 % del daño base. La cifra de la wiki (200 %) es coherente con esa lectura.
- **Límite que permanece:** no se ha medido en partida ni se ha leído el código consumidor; el total se deriva de la palabra «adicional» del texto oficial. **Prohibido** presentarlo como daño real de Q sin una medición o una fórmula oficial que lo confirme.


### D.3 H3 — Cadenas localizadas de Zaahen (ubicación, formato e índice verificados)

Resumen (detalle técnico completo en la sección F):

- Las cadenas localizadas de Zaahen **no** están en `Zaahen.es_ES.wad.client` (ese contenedor solo trae un activo `r3d2` y dos `BKHD` de audio).
- Están en `Global.es_ES.wad.client` (4 084 993 bytes), dentro de dos chunks en formato **RST v5**.
- **Resuelto:** la asociación ranura → cadena. La ranura de 8 bytes empaqueta un hash de **38 bits** en los bits bajos y el desplazamiento de la cadena en los bits altos: `clave = v & (2^38 - 1)`, `offset = v >> 38`. Verificado con `item_1001_name` → `Botas` y con los nueve nombres/tooltips de Zaahen.
- El segundo `uint32` que antes parecía un desplazamiento inválido es `(offset << 6) | (hash >> 32 & 0x3F)`; por eso no coincidía ni con la mitad alta del hash ni con un offset.


### D.4 Prototipo CommunityDragon — resultados observados

Informe generado: `research/reports/zaahen-report.json` (no versionado; se regenera).

| Dato | Valor |
|---|---|
| `content_version` | `16.20.8248524+branch.releases-16-20.content.release` |
| `source_sha256` (export del bin) | `76e32de67667917769cc6022a818b13e5024ea521a23c70436dc48eea533ed0b` |
| `ddragon_patch` comparado | `16.20.1` |
| Parámetros extraídos | 41 |
| Comparaciones ejecutadas | 37 |
| Parámetros bloqueados | 3 (`champion.attack_damage_per_level`, `passive.ad_per_stack`, `q.monster_damage_multiplier`) |
| Cálculos | 1 (`r.damage_rank1_bonus_ad_100` = `250 + 2 * 100` = 450, estado `derived`) |
| Fórmulas reconocidas | 6, todas con estado `inferred` |

Puntos verificados que sí se pueden reutilizar:

1. **Enfriamientos efectivos:** tomados de `mSpell.Cooldown.values`. El campo `cooldownTime` se conserva solo como diagnóstico y no se compara. Con este criterio, **el enfriamiento de W queda resuelto**: coincide en bin, Data Dragon, RCP y wiki.
2. **Estadísticas del campeón:** leídas de `CharacterRecords/Root` (`baseDamageModifiable`, `damagePerLevelModifiable`, `hpPerLevelModifiable`, `armorPerLevelModifiable`, `baseMR`, `mrPerLevel`, `baseMoveSpeedModifiable`, `attackRangeModifiable`, `attackSpeedModifiable`).
3. **Cálculo de la R en rango 1 con 100 de bonus AD:** `250 + 2 × 100 = 450`. Marcado `derived` porque la equivalencia `mStat`/`mStatFormula` con «bonus AD» es una interpretación, no un enum documentado.
4. **Partes de cálculo con tipos desconocidos:** se rechazan como `unverified` en lugar de adivinar.
5. **Fallos de red o JSON inválido:** no tocan la caché ni los datos publicados.

### Estados del prototipo y su precedencia

`source_explicit` → `derived` → `inferred` → `corroborated` → `verified`, más `unverified` y `conflict`. Precedencia en caso de choque: `conflict` > `unverified` > `verified` > `corroborated` > `inferred` > `derived` > `source_explicit`.

`corroborated` exige coincidencia entre derivaciones del mismo origen (Data Dragon y CommunityDragon) o con una fuente secundaria. `verified` exige además coincidencia con Data Dragon del parche objetivo **y** con una fuente independiente.

---

## E. Discrepancias abiertas

Ninguna de estas se resolvió. **No deben usarse como datos** en cálculos ni en la base de conocimiento.

| # | Discrepancia | Evidencia | Estado |
|---|---|---|---|
| E.1 | Crecimiento de daño de ataque por nivel | Data Dragon publica `0`; el bin y la wiki dan `4.0` | Abierta. `validate` cruza los números oficiales contra el JSON, así que la cifra alternativa no puede ir en code span en `overview.md` |
| E.2 | AD por acumulación de la pasiva | Bin: `PBonusADMin = 0.015` y `PBonusADMax = 0.028` (valores float32 con ruido de representación en el export: `0.014999999664723873` y `0.02800000086426735`); el tooltip oficial del cliente usa `@PercentBonusADCalc@`, y ese cálculo parte de `PBonusADMin`/`PBonusADMax`; wiki: `2.95 %` con máximo `70.87 %` | Abierta solo en el máximo: el bin y el tooltip del cliente apuntan a `2.8 %`, y el historial de la wiki también documenta `2.8 %`; el `2.95 %` del resumen de la wiki no aparece en el bin. La curva exacta por nivel depende de la parte de interpolación `{ee18a47b}` y no se ha medido |
| E.3 | Enfriamiento: `cooldownTime` frente a `Cooldown.values` | Ambos campos existen y difieren; el segundo coincide con Data Dragon, RCP y wiki | Criterio adoptado (usar `Cooldown.values`), no equivalencia demostrada |
| E.4 | Multiplicador de Q contra monstruos | Ver D.2 | **Resuelta en semántica:** el texto oficial del cliente dice «daño adicional»; `1.0` = +100 % → 200 % total, coherente con la wiki. El prototipo todavía compara el campo bruto (`1.0`) contra el total (`2.0`) y por eso lo marca `conflict`: es una discrepancia de representación, no de valor. Pendiente corregir el prototipo |
| E.5 | Semántica de campos de interpolación | `mStat`/`mStatFormula` y las partes `ByCharLevel*` | Inferida por cálculo (H1) y por coherencia, no documentada |

---

## F. Investigación de stringtables (detalle técnico)

Esta sección existe para que la línea abierta se pueda retomar sin repetir la exploración.

### F.1 Archivos del cliente relevantes

Raíz: `D:\Games\Riot Games\League of Legends\Game\`

| Archivo | Tamaño | Contenido observado |
|---|---|---|
| `DATA\FINAL\Champions\Zaahen.wad.client` | 27 863 976 B | Bin del campeón |
| `DATA\FINAL\Localized\Global.es_ES.wad.client` | 4 084 993 B | **Aquí están las cadenas es_ES** |
| `DATA\FINAL\Champions\Zaahen.es_ES.wad.client` | 8 200 249 B | Solo un activo `r3d2` y dos `BKHD` de audio: **sin texto** |
| `DATA\FINAL\Global.wad.client` | 1 014 829 144 B | Contenedor global |

Los cuatro tamaños se comprobaron sobre la instalación local el 2026-10-18.

Control de integridad realizado en la fase anterior: el bin del juego y el export de CommunityDragon coinciden byte a byte, con SHA-256 `7f1e936990c527d1cf457eea9d9327efaa743d6619436f0ccfc15e7e844078d1`.

### F.2 Formato observado (RST v5)

Dentro de `Global.es_ES.wad.client` hay **dos** chunks con texto, ambos con la misma estructura:

```text
[0..4)          magic: 52 53 54 05   ("RST" + versión 5)
[4..8)          uint32 little-endian: cantidad de ranuras (N)
[8..8+8N)       N ranuras de 8 bytes (índice)
[8+8N..)        blob de cadenas: UTF-8, separadas por NUL
```

Compresión: zstd (nivel 3), descomprimible con `compression.zstd` de la biblioteca estándar de Python 3.14.

| Chunk | N | Inicio del blob (`8+8N`) | Primera cadena |
|---|---|---|---|
| 0 | 136 473 | 1 091 792 | `Registro de progresión del Caos` |
| 1 | 111 615 | 892 928 | `Corona del Coloso` |

### F.3 Qué sí se verificó

- **Función de hash del índice:** `XXH3-64` de la clave en minúsculas, truncado a **38 bits**. El diccionario público `hashes.rst.xxh3.txt` da el hash completo; el índice usa `hash & (2^38 - 1)`.
  - `item_1001_name` → `Botas` (verificación independiente del campeón).
  - `spell_zaahenq_name`, `spell_zaahenp_name`, `spell_zaahenw_name`, `spell_zaahene_name`, `spell_zaahenr_name` → nombres en español.
  - `spell_zaahenq_tooltip`, `spell_zaahenq_tooltipextended`, `spell_zaahenw_tooltip`, `spell_zaahene_tooltip`, `spell_zaahenr_tooltip`, `spell_zaahenp_summary` → textos completos con marcadores `@...@`.
- **Discrepancia con `cdragon-rst` 0.2.0:** ese crate indica 39 bits para RST v5. En este archivo, 39 bits produce cadenas erróneas y 38 bits resuelve todos los pares comprobados. Se adopta 38 por evidencia empírica; queda anotado como posible diferencia de versión del formato.
- **Diccionarios útiles:** `https://raw.communitydragon.org/data/hashes/lol/hashes.rst.xxh3.txt` (147 656 líneas) contiene las claves de Zaahen. `hashes.rst.txt` y `hashes.rst.xxh64.txt` (108 709 líneas cada uno) **no** las contienen.
- **Claves ASCII en el chunk 1** (mayormente localización en inglés) y **valores en español en el chunk 0**.
- **Claves de Zaahen verificadas como presentes:** `Spell_ZaahenQ_Name`, `Spell_ZaahenQ_Summary`, `Spell_ZaahenQ_Tooltip`, `Spell_ZaahenQ_TooltipExtended`, `Spell_ZaahenP_Name`, `Spell_ZaahenP_Summary`, `Spell_ZaahenW_Tooltip`, `Spell_ZaahenE_Tooltip`, `Spell_ZaahenR_Tooltip`.
- **Valores en español verificados como presentes:** `Florescencia de la guerra`, `La guja de los Oscuros`, `Impulso áureo`, `Redención funesta`, `Hendidura del retorno`. Los valores contienen marcadores `@OtraClave@` que remiten a otras claves de la tabla.

### F.4 Índice RST: resuelto

La ranura de 8 bytes no son dos `uint32` independientes: es un `uint64` empaquetado.

```text
v      = (offset << 38) | (hash & 0x3FFFFFFFFF)
hash   = v & 0x3FFFFFFFFF
offset = v >> 38
```

- El segundo `uint32` que parecía inválido es `(offset << 6) | (hash >> 32 & 0x3F)`.
- `entry_data` empieza en `8 + 8N`; el offset es relativo a ese punto.
- Verificación: `item_1001_name` → `Botas`; los nueve nombres/tooltips de Zaahen se resuelven con el diccionario.
- Consecuencia: ya se pueden reconstruir tooltips completos y resolver los marcadores `@OtraClave@` recorriendo la tabla; no hace falta buscar literales en el blob.
- Límite: comprobado en `Global.es_ES.wad.client` de 16.20; si se reutiliza con otra locale o build, repetir la comprobación de bits.

---

## G. Qué falta para calcular builds de letalidad

Con lo verificado hasta ahora **no se puede** producir una build cuantificada. Requisitos mínimos, en orden de valor:

1. **Ratios y daño base publicados o medidos** de Q, W, E y R, con su tipo de daño (físico/mágico/verdadero).
2. **Penetración de armadura de la R**: tipo (porcentual plana o escalada) y valores por rango. El prototipo extrae `ArmorPen`, pero su comparación con la wiki no cierra la discrepancia.
3. **Multiplicador de Q contra monstruos** (E.4) si el objetivo incluye jungla u objetivos.
4. **Eficiencia de objetos** del parche 16.20.1: oro por punto de estadística y umbrales de penetración.
5. **Reglas de daño efectivo**: orden de aplicación de penetración y reducción, y cómo interactúan con la R.
6. **Datos de rendimiento** (win rate, pick rate) si la build debe justificarse estadísticamente. **No se consultó ninguna fuente comunitaria**: su acceso no se ha verificado contra sus condiciones de uso.

Además, dos bloqueos de datos afectan directamente a cualquier cálculo de daño de ataque: el crecimiento de AD (E.1) y el AD por acumulación de la pasiva (E.2).

---

## H. Licencias y límites de uso

Detalle completo en [`evidence/usage-conditions.md`](evidence/usage-conditions.md). Resumen:

| Fuente | Naturaleza | Límite registrado |
|---|---|---|
| Riot — Legal Jibber Jabber | Licencia para proyectos comunitarios | Uso «strictly for noncommercial … community use», revocable |
| Riot — General Policies / API Policy | Activos permitidos | Solo «Press Kit», «Data Dragon» y datos estáticos del juego; exige aviso de no afiliación |
| CommunityDragon | Proyecto comunitario bajo la política de Riot | Sin licencia SPDX declarada: la ausencia no demuestra permiso ni prohibición |
| LoL Wiki | Contenido de terceros | CC BY-SA 3.0; su API respondió 403 a la consulta automatizada, el contenido se transcribió a mano |

**Conclusión registrada:** el uso interno de investigación no presenta objeción evidente. La **redistribución de archivos originales del cliente no está autorizada de forma clara**, por eso el bin completo vive solo en `research/.cache/` (ignorado por Git). La publicación de valores derivados es defendible como dato estático del juego dentro de la política de Riot, pero exige atribución, aviso de no afiliación y revisión jurídica antes de volverse permanente.

**Prohibición explícita para el siguiente agente:** no presentar la wiki ni CommunityDragon como fuente oficial de Riot, y no copiar cifras de la wiki a `lol-knowledge/` como si fueran dato oficial.

---

## I. Reproducibilidad

### Prototipo CommunityDragon

```powershell
$env:PYTHONPATH="research"

# Descarga fijada a 16.20, verifica el JSON y rellena research/.cache
.\.venv\Scripts\python.exe -m cdragon_zaahen

# Solo caché, sin red
.\.venv\Scripts\python.exe -m cdragon_zaahen --offline

# Informe completo en JSON
.\.venv\Scripts\python.exe -m cdragon_zaahen --json

# Falla (exit 1) si hay conflictos
.\.venv\Scripts\python.exe -m cdragon_zaahen --offline --check
```

Suite offline del prototipo (sin red, con fixtures locales):

```powershell
$env:PYTHONPATH="research"
.\.venv\Scripts\python.exe -m pytest research -q
```

### Base de conocimiento y snapshot

```powershell
.\.venv\Scripts\python.exe -m lol_knowledge update --patch 16.20.1
.\.venv\Scripts\python.exe -m lol_knowledge validate
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check .
```

### Dependencias externas y locales

- **Red:** la CLI del prototipo funciona `--offline` con la caché; sin caché necesita descargar el export de 16.20. Los tests del prototipo **no** usan red.
- **Cliente local:** las comprobaciones de WAD (sección F) requieren la instalación local de League of Legends. **Si no está disponible en la máquina, esas comprobaciones no se pueden repetir**: hay que registrarlo como limitación en lugar de afirmar el resultado.
- **Archivos temporales:** los scripts `*_probe*.py` de la fase anterior estaban en `%TEMP%` y no se conservan. Decisión: no versionar scripts sueltos; si una comprobación merece repetirse, se reescribe desde la sección F.
- **Codificación en Windows:** la consola no es fiable para acentos. Usar `sys.stdout.reconfigure(encoding="utf-8")` o `PYTHONIOENCODING=utf-8` antes de imprimir texto con acentos.

---

## J. Próximos pasos y referencias

### Prioridad 1 — desbloquear el cálculo

1. Cerrar E.1 (crecimiento de AD: `0` frente a `4.0`) con una fuente oficial o medición propia.
2. Cerrar E.2 (AD por acumulación de la pasiva) contrastando la interpolación `PercentBonusADCalc` con una medición en partida; el bin y el tooltip del cliente apuntan a `2.8 %`, no a `2.95 %`.
3. Cerrar G.2 (tipo y valores de la penetración de la R) para poder modelar letalidad.

### Prioridad 2 — investigación técnica

4. Corregir en el prototipo la representación de `MonsterDamagePercent`: el campo es daño **adicional** (`1.0` = +100 % → 200 % total), no un multiplicador total. Hasta entonces, `q.monster_damage_multiplier` seguirá marcado `conflict` por una diferencia de representación ya explicada en D.2/E.4.
5. Confirmar si la etiqueta `ByCharLevelNamedDataValuesInterpolationCalculationPart` (H1) es correcta por una segunda vía independiente.

### Prioridad 3 — decisión de producto

6. Decidir si `lol-knowledge/` puede publicar valores derivados de CommunityDragon con la atribución y el aviso de no afiliación exigidos (sección H). Sin esa decisión, los hallazgos viven en `research/` y no en la base de conocimiento.

### Referencias externas

Verificadas con `HEAD` el 2026-10-18 (responden 200), salvo la wiki, que devuelve 403 a peticiones automatizadas:

| Referencia | URL | Para qué se usó |
|---|---|---|
| CommunityDragon | `https://communitydragon.org/` | Procedencia y declaración de política |
| CommunityDragon — Docs (formato bin) | `https://github.com/CommunityDragon/Docs` | Formato del archivo bin |
| CommunityDragon — diccionarios de hashes | `https://raw.communitydragon.org/data/hashes/lol/hashes.rst.xxh3.txt` | Resolver claves es_ES (H3) |
| Export RCP de Zaahen | `https://raw.communitydragon.org/16.20/plugins/rcp-be-lol-game-data/global/default/v1/champions/904.json` | Contraste de valores (fixture `zaahen_rcp_min.json`) |
| LeagueToolkit — metadatos de clases | `https://github.com/LeagueToolkit/lol-meta-classes` | Nombres de clases y campos del bin (H1) |
| `cdragon-rst` | `https://docs.rs/cdragon-rst/latest/cdragon_rst/` | Formato de stringtables RST |
| LoL Wiki — Zaahen | `https://wiki.leagueoflegends.com/en-us/Zaahen?oldid=4050539` | Contraste de valores (lectura manual, 2026-08-07 última edición) |

Las cifras de la wiki se transcribieron a mano en `research/cdragon_zaahen/wiki_evidence.py`, junto a la URL, la fecha de acceso y la licencia. Ese módulo existe **solo** para comparar; no es una fuente oficial.
