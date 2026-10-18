# project-bootstrap — Fase 0

Objetivo: dejar el repositorio con reglas persistentes, estructura mínima y validaciones ejecutables antes de escribir lógica de negocio.

- Rama: `chore/project-bootstrap` (base: `dev`)
- Runner: pytest sobre `.venv` (Python 3.14)
- Estrategia de entrega: `single-pr` desactivada; commits de unidad de trabajo locales, sin push

## Specs

- **S1.** Las reglas del proyecto viven en `AGENTS.md`: flujo Git, Conventional Commits, comandos de validación, política de fuentes y seguridad.
- **S2.** Documentación en español; código, identificadores, tests y mensajes de commit en inglés.
- **S3.** Flujo Git: rama de tarea desde `dev`; `--no-ff` hacia `integration`; validación del conjunto integrado; `--ff-only` de `integration` a `dev`; conflictos solo en `integration`; sin push.
- **S4.** Validaciones obligatorias: `pytest`, `ruff check .`, `ruff format --check .`.
- **S5.** CLI mínima invocable: `python -m lol_knowledge version` y `--help`, con tests.
- **S6.** Entorno reproducible: `.venv` local ignorado; dependencias de desarrollo con versión exacta.
- **S7.** `.atl/` no se versiona: contiene rutas absolutas de la máquina.
- **S8.** Sin datos inventados y sin documentar comandos inexistentes.

## Tasks

- [ ] T1 — Reglas, README e higiene del repositorio (`AGENTS.md`, `README.md`, `.gitignore`). Spec: S1, S2, S3, S7, S8. Route: inline.
- [ ] T2 — Entorno y configuración de validaciones (`requirements-dev.txt`, `pyproject.toml`). Spec: S4, S6. Route: inline.
- [ ] T3 — CLI mínima y tests (`src/lol_knowledge/*`, `tests/test_cli.py`). Spec: S5. Route: inline.

## Log

- **L1.** El usuario aprueba el plan por fases presentado el 2026-10-18: «Apruebo el plan. Adelante». Decisiones aplicables a esta fase: ramas de tarea → `integration` (`--no-ff`) → `dev` (`--ff-only`); sin push; sin firma; pytest + ruff obligatorios; `AGENTS.md` como fuente de reglas; documentos de tareas compatibles con las herramientas instaladas (no hay SDD/OpenSpec, se usa ODD en `odd/tasks/`).
- **L2.** Verificado en solo lectura: ramas `main`, `dev`, `integration` (local y remoto) apuntan al mismo commit `5fd136e`; no existía `dev` local. Data Dragon responde y el parche más reciente es `16.20.1`. `.atl/skill-registry.md` contiene 10 rutas absolutas `C:\Users\Yisus\...`, por lo que se ignora.
- **L3.** Entorno: OpenCode 1.18.34, Gentle-AI 4.2.0, Python 3.14.7, Node 24.18.0. pytest y ruff no estaban instalados.
