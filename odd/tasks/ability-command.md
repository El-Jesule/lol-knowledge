# Comando `ability`: hoja, habilidad y mitigación — fase 13

- **Objetivo:** calcular desde la terminal el daño de una habilidad contra un objetivo, encadenando lo que ya existía: hoja de estadísticas, kit de campeón y motor de mitigación.
- **Rama:** `feat/ability-command`, creada desde `dev` (`956396b`).
- **Entorno de ejecución:** shell Linux de Claude en el equipo del usuario, Python 3.14.10, `PYTHONPATH=src`. No se ha ejecutado con `.\.venv\Scripts\python.exe` en Windows.

## Decisiones

1. **Función pura + comando.** `src/lol_knowledge/scenario.py` evalúa sobre valores ya cargados; la CLI carga y formatea (`scenario_report.py`).
2. **Dos formas de objetivo, sin mezclarlas.** A mano (resistencias y vida como datos del escenario, que no debilitan la etiqueta) o como campeón resuelto con la misma hoja (su etiqueta cuenta).
3. **Cada parte se mitiga con su resistencia.** Físico: armadura con penetración de armadura y letalidad; mágico: RM con penetración mágica; verdadero: sin mitigar.
4. **Pasivas de habilidades aprendidas.** `--learned` añade las estadísticas pasivas del kit a la hoja; la habilidad lanzada cuenta como aprendida a su rango, y un rango contradictorio es error.
5. **La vida actual del objetivo** es su vida máxima salvo que se indique otra cosa; nunca se inventa una vida máxima.

## Pruebas

26 pruebas nuevas (escenario, CLI y subproceso). Ocho mutaciones deliberadas; la única que sobrevivió al principio (la etiqueta del objetivo no contaba en el resultado) tiene ahora su prueba.

## Limitaciones

- Un lanzamiento: sin rotaciones, tiempo, críticos ni efectos de objeto al impactar.
- No admite reducciones de resistencia del objetivo (el comando `damage` sí).
- Solo Zaahen tiene kit.
