# Kits de campeón y evaluador de habilidades — fase 12

- **Objetivo:** pasar de «R rango 3» a una instancia de daño bruto con su tipo, lista para el motor de mitigación, sin reescribir fórmulas a mano.
- **Rama:** `feat/champion-kit`, creada desde `dev` (`be09733`).
- **Entorno de ejecución:** shell Linux de Claude en el equipo del usuario, Python 3.14.10, `PYTHONPATH=src`. No se ha ejecutado con `.\.venv\Scripts\python.exe` en Windows.

## Decisiones

1. **Un evaluador para objetos y habilidades.** El de `objects/formula.py` pasa a `src/lol_knowledge/formula/` y `objects` lo reexporta. Las constantes que compartían (`STAT_SCOPES`, `STAT_SCOPES_BY_STAT`…) también se mueven, para evitar un import circular. El modelo de objetos generado es idéntico byte a byte antes y después.
2. **Operaciones solo para kits:** `by_rank`, `by_level` e `input`. El catálogo de objetos las rechaza.
3. **Aritmética exacta** en el evaluador; `FormulaResult.value` sigue siendo `float` y `exact` da la fracción.
4. **Estadísticas del objetivo separadas** (`target_stats`) cuando se pasan; sin ellas, el comportamiento del catálogo no cambia.
5. **Casos y partes.** Un caso es una alternativa (tajo o borde de la E); una parte es un daño que ocurre junto a otros en el mismo caso.
6. **Especificación curada + números generados.** `research/kits/<Id>.spec.json` decide la estructura; `binmodel.kitgen` pone los números del bin y el tipo de daño del tooltip, y falla si lo declarado y el tooltip no coinciden.
7. **Pasivas de habilidad como aportes a la hoja** (`passive_contributions`): la penetración de la R entra como una fuente más y el motor la apila con las de los objetos.

## Verificación

- El kit de Zaahen reproduce los valores derivados que ya documentaba `abilities.md` por otra vía.
- Un ejemplo de punta a punta fijado en pruebas: Zaahen nivel 16 con Recuerdos de lord Dominik y R rango 3 → 620 de daño bruto; contra 150 de armadura la armadura efectiva es 68,25 (150 × 0,65 × 0,70).
- El kit publicado es exactamente la salida del compilador sobre el fixture del bin.
- 64 pruebas nuevas; 14 mutaciones deliberadas, de las que dos sobrevivieron al principio y destaparon huecos que ahora tienen prueba (la etiqueta de una estadística pendiente no se propagaba en ningún test; el rango no se comprobaba en habilidades sin valores por rango).

## Limitaciones

> **Nota (2026-11-19):** esta lista refleja el estado al cerrar la fase. Lo que sigue abierto, con su prioridad, está en la [hoja de ruta](../roadmap.md); lo resuelto después se marca abajo con la fase que lo resolvió.

- No hay comando que encadene hoja, habilidad y mitigación: es el siguiente paso.
- La pasiva de Zaahen no está modelada (curva de interpolación sin medir).
- No se modelan curaciones, escudos, bonificaciones contra monstruos ni condiciones de impacto.
- Solo existe el kit de Zaahen.
