# zaahen-research-handoff — Fase 3.5 (cierre)

Objetivo: cerrar la fase de investigación de Zaahen integrando en la base de conocimiento solo los hallazgos verificados y útiles, y dejando un documento de continuidad autosuficiente para que otro agente pueda seguir sin esta conversación.

- Rama: `docs/zaahen-research-handoff` (base: `dev`)
- Runner: pytest sobre `.venv` (Python 3.14)
- Entrega: local. Sin push; la integración a `integration` y la promoción a `dev` requieren autorización expresa.

## Specs

- **S1.** Existe `research/zaahen-research-handoff.md`, en español, con secciones A–J, autosuficiente: un agente sin esta conversación puede continuar la investigación con él.
- **S2.** `research/README.md` funciona como índice de navegación del directorio y enlaza el handoff.
- **S3.** La base de conocimiento integra solo hallazgos verificados o útiles, con etiquetas `Oficial`/`Calculado`/`Recomendación`/`Pendiente de verificación`.
- **S4.** Ni la wiki ni CommunityDragon se presentan como fuente oficial de Riot. Se distingue explícitamente verificado / inferencia / abierto.
- **S5.** No se inventan cifras ni se sustituyen marcadores por valores deducidos.
- **S6.** Se registran los límites de licencia y de replicación (políticas de Riot, CommunityDragon sin licencia SPDX, wiki CC BY-SA 3.0).
- **S7.** Nada en `src/` ni `data/` depende del prototipo `research/`, ni de archivos temporales de `%TEMP%`. Las dependencias de archivos locales del cliente se documentan con su ruta y cómo recuperarlos.
- **S8.** Pasan: `pytest`, `ruff check .`, `ruff format --check .`, `python -m lol_knowledge validate` y los tests del prototipo (`PYTHONPATH=research pytest research -q`).
- **S9.** Los enlaces Markdown de `lol-knowledge/` existen y quedan dentro del repositorio; los números en code spans de `overview.md` y `abilities.md` existen en `data/current/champions/Zaahen.json`.
- **S10.** Commits convencionales en inglés, ≤72 caracteres, en la rama de tarea; sin push ni merge.

## Tasks

- [x] T1 — Rama de tarea y documento de seguimiento. Spec: S10. Route: inline. Evidencia: rama `docs/zaahen-research-handoff` creada desde `dev` sobre un árbol limpio (`?? research/` únicamente).
- [ ] T2 — `research/zaahen-research-handoff.md` con secciones A–J. Spec: S1, S4, S5, S6, S7. Route: inline.
- [ ] T3 — `research/README.md` como índice, enlazando el handoff. Spec: S2. Route: inline.
- [ ] T4 — Integración en la KB: `overview.md`, `abilities.md`, `build.md`, `sources.md`, `INDEX.md`. Spec: S3, S4, S5, S9. Route: inline.
- [ ] T5 — Ejecutar suite completa, Ruff (check y format), validador de la KB y tests del prototipo. Spec: S8. Route: inline.
- [ ] T6 — Commits por unidad coherente. Spec: S10. Route: inline.

## Log

- **L1.** Petición del usuario (reconstruida tras compactación de contexto; no es literal): cerrar la fase de investigación de Zaahen, integrar en la KB solo los hallazgos verificados y útiles, y documentar la investigación en `research/zaahen-research-handoff.md` (secciones A–J, español) más `research/README.md`, trabajando en rama de tarea con commits convencionales en inglés, sin push ni merge, con la suite completa, Ruff y el validador de la KB en verde.
- **L2.** Hallazgos previos de la investigación (fase ya cerrada técnicamente): H1 `fnv1a32("ByCharLevelNamedDataValuesInterpolationCalculationPart") = 0xee18a47b` (coincidencia por cálculo, ausente de los diccionarios publicados); H2 `MonsterDamagePercent` = 0.5/0.75/1.0/1.0 en 15.23/15.24/16.3/16.20 frente a 150 %/175 %/200 % de la wiki (`total = 1 + campo` es inferencia, no demostración); H3 ubicación y formato de las cadenas es_ES en `Global.es_ES.wad.client` (2 chunks RST v5, hash de índice = 32 bits bajos de XXH3-64 de la clave en minúsculas), con la asociación slot→cadena todavía abierta.
- **L3.** Verificación posterior a la compactación: la línea `except OSError, json.JSONDecodeError:` de `research/cdragon_zaahen/client.py` es válida en Python 3.14 (PEP 758, paréntesis opcionales en `except` múltiple). El defecto reportado era una falsa alarma: `py_compile` compila el archivo sin error. No se toca el código.
- **L4.** Riesgo detectado antes de escribir: `validate` cruza **todo** code span numérico de `overview.md` y `abilities.md` contra `data/current/champions/Zaahen.json`. Por eso las cifras de terceros (CommunityDragon, wiki) no pueden ir en code spans en esos dos archivos; se documentan en prosa o en `research/`.
- **L5.** Verificación de referencias externas con `HEAD` (2026-10-18): `https://github.com/LeagueToolkit/lol-meta-classes`, `https://github.com/CommunityDragon/Docs`, el JSON RCP de Zaahen en CommunityDragon, `https://docs.rs/cdragon-rst/latest/cdragon_rst/` y `https://communitydragon.org/` responden 200. La página de la wiki devuelve 403 a peticiones automatizadas: el contenido proviene de lectura manual previa y así se declara en el handoff.
- **L6.** Decisión de alcance: no se resuelve la asociación slot→cadena del índice RST en esta fase. El progreso del proyecto no depende de ello (la extracción de texto funciona leyendo el blob de cadenas y buscando literales). Queda como línea de investigación futura en el handoff.
- **L7.** Pendiente de evidencia: resultados de `pytest`, `ruff check`, `ruff format --check`, `lol_knowledge validate` y los tests del prototipo se anotan aquí cuando se ejecuten, con su salida observada.
