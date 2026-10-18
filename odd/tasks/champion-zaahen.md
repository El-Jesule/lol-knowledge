# champion-zaahen — Fase 3

Objetivo: validar la arquitectura de conocimiento con un caso completo y honesto, separando dato oficial, cálculo e interpretación.

- Rama: `feat/champion-zaahen` (base: `dev`)
- Runner: pytest sobre `.venv` (Python 3.14)

## Specs

- **S1.** Documentación en `lol-knowledge/champions/Zaahen/`: `overview.md`, `abilities.md`, `build.md`, `sources.md`.
- **S2.** Cada sección con datos indica parche, fuente, fecha de consulta y limitación.
- **S3.** Estadísticas, costes, enfriamientos, rangos y texto de habilidades provienen de `data/current/champions/Zaahen.json`.
- **S4.** `build.md` separa cálculo determinista, criterio estratégico y datos pendientes.
- **S5.** Lo que Data Dragon no publica se declara como no disponible; no se sustituyen marcadores por ceros ni por valores deducidos.
- **S6.** `lol-knowledge/INDEX.md` enruta por intención y todos sus enlaces existen.
- **S7.** `validate` comprueba que los números oficiales citados en `overview.md` y `abilities.md` existan en el JSON del campeón.

## Tasks

- [ ] T1 — Validador: trazabilidad numérica de documentos de campeón y tests. Spec: S7. Route: inline.
- [ ] T2 — Documentos de Zaahen. Spec: S1–S6. Route: inline.
- [ ] T3 — Índice y README. Spec: S6. Route: inline.

## Log

- **L1.** El usuario aprueba la Fase 3 tras cerrar la Fase 2: «Adelante, implementa la Fase 3». Aprobado en la entrevista: empezar por Zaahen como primer caso completo y dejar estructura ampliable.
- **L2.** Hallazgo con datos reales: para Zaahen, `effectBurn` contiene `0` en todas las posiciones y los tooltips usan marcadores con nombre (`initialdamage`, `healpercent`, `damageendcalc`, etc.). No hay valores de daño ni escalado publicados. Se decide no sustituir nada y marcar como `Pendiente de verificación`.
- **L3.** Segundo hallazgo: `attackdamageperlevel` es `0`. Se documenta tal cual, sin interpretarlo como intencional.
- **L4.** Decisión: los valores oficiales se escriben en code spans y el validador los cruza contra el JSON. Es una regla pequeña y comprobable, documentada en `AGENTS.md`.
