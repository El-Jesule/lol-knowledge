# zaahen-derived-publication — Fase 3.6

Objetivo: publicar en `lol-knowledge/` los valores derivados de Zaahen aprobados por el usuario, con atribución, aviso de no afiliación y sin sustituir datos oficiales.

- Rama: `docs/zaahen-derived-values` (base: `dev`)
- Runner: pytest sobre `.venv` (Python 3.14)
- Entrega: local. Sin push; integración pendiente de autorización. La decisión de producto ya está aprobada.

## Specs

- **S1.** `AGENTS.md` define la etiqueta `Derivado` y sus reglas (build, ruta, método, sin archivos originales, sin code spans numéricos en `overview.md`/`abilities.md`).
- **S2.** `abilities.md` publica los valores derivados de pasiva, Q, W, E y R en texto plano, separados de los oficiales.
- **S3.** `sources.md` registra CommunityDragon como fuente derivada: URL, build `16.20.8248524`, `sha256`, método y límites; la wiki queda solo como contraste.
- **S4.** `README.md` y `lol-knowledge/INDEX.md` muestran el aviso de no afiliación.
- **S5.** Las discrepancias E.1 (crecimiento de AD) y E.2 (máximo de la pasiva) siguen como `Pendiente de verificación`; no se sustituye el dato oficial ni se fuerza coincidencia.
- **S6.** `build.md` usa los insumos derivados sin afirmar daño final ni una build cuantificada.
- **S7.** Pasan `pytest`, los tests del prototipo, `ruff check`, `ruff format --check` y `lol_knowledge validate`.
- **S8.** Commits convencionales en inglés, ≤72 caracteres, sin push ni merge.

## Tasks

- [x] T1 — Etiqueta `Derivado` y reglas en `AGENTS.md`. Spec: S1.
- [x] T2 — Valores derivados en `abilities.md`. Spec: S2.
- [x] T3 — Atribución y aviso legal en `sources.md`, `README.md` e `INDEX.md`. Spec: S3, S4.
- [x] T4 — `build.md` con insumos derivados y pendientes. Spec: S5, S6.
- [ ] T5 — Validaciones y commit en la rama. Spec: S7, S8.

## Log

- **L1.** El usuario aprueba la decisión de producto: «Lo apruebo», en respuesta a publicar valores derivados de CommunityDragon con atribución y aviso de no afiliación.
- **L2.** Base de la decisión: sección H del handoff. Se mantiene la prohibición de presentar wiki o CommunityDragon como fuente oficial, y la de versionar archivos originales del cliente.
- **L3.** Las cifras derivadas se escriben en texto plano para no romper la trazabilidad numérica de `validate`, que cruza los code spans de `overview.md`/`abilities.md` contra `data/current/champions/Zaahen.json`.
- **L4.** E.1 y E.2 no se resuelven: el dato oficial de Data Dragon no se sobrescribe y la discrepancia queda declarada.
