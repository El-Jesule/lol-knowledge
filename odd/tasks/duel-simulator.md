# Tarea: Simulador de duelo 1v1 determinista (`duel`)

- **Parche:** `16.23.1`
- **Fecha:** 2026-11-25
- **Estado:** Implementado y validado en local (sin `push`)

## Objetivo

Añadir un simulador determinista de duelo 1v1 acoplado sobre reloj discreto exacto (`Fraction`) que reutilice íntegramente `rotation.py` y `defense.py` sin duplicar fórmulas ni provocar doble conteo, expuesto de forma homogénea en CLI (`duel`), contrato JSON (`operation: "duel"`), servidor MCP (`lol_duel`) y optimizador de builds (`optimize --objective duel`).

## Alcance entregado

1. **Steppers incrementales en motores existentes:**
   - `DefenseState`, `DefenseSession` y `open_defense_session(...)` en `src/lol_knowledge/defense.py`, con bandera `resistances_already_live` en `IncomingHit` y activación causal inmediata de defensivos (`activate_ability_cast`, `activate_summoner`, `apply_self_survival`, `set_grievous_until`, `set_shield_reaver`).
   - `DuelStepResult`, `RotationSession` y `open_rotation_session(...)` en `src/lol_knowledge/rotation.py`, con `defer_survival`, `sync_context` (vida viva y estado `exhausted`), `notify_shield_granted` (Golpe de escudo) y resolución dinámica de objetos de Heridas graves.
2. **Motor de duelo y formateo:**
   - `src/lol_knowledge/duel.py`: `DuelFighterSpec`, `DuelEvent`, `FighterDuelSummary`, `DuelOutcome`, `evaluate_duel(...)`, modos `scripted_then_attack` / `strict_scripted` / `priority_loop`, desempates `simultaneous` / `a_first` / `b_first`, escalado proporcional de robo de vida / omnivampirismo / `damage_dealt_heal` tras DR y negaciones, reflejo de *Malla de espinas* y pausa de estasis de *Ángel de la guarda*.
   - `src/lol_knowledge/duel_report.py`: `format_text` y `to_dict`.
3. **Integración completa:**
   - `src/lol_knowledge/cli.py`: subcomando `duel` y objetivo `duel` en `optimize`.
   - `src/lol_knowledge/contract.py`: operación `duel` y objetivo `duel` en `optimize`.
   - `src/lol_knowledge/mcp_server.py`: herramienta `lol_duel` y soporte `duel` en `lol_optimize`.
   - `src/lol_knowledge/optimizer/`: objetivo `duel` en `models.py`, `search.py` y `report.py`.
4. **Pruebas y documentación:**
   - `tests/test_duel.py` (19 pruebas cubriendo simetría exacta, empates, modos, mecánicas acopladas y paridad CLI/contrato/MCP/optimizador).
   - `lol-knowledge/mechanics/duel.md`, actualización de `lol-knowledge/ai-layer.md` y `lol-knowledge/INDEX.md`.
