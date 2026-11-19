# Legalidad de la build — fase 36

- **Objetivo:** OBJ-13 de la [hoja de ruta](../roadmap.md): que el motor sepa si un conjunto de objetos cabe en un inventario, como requisito del optimizador.
- **Rama:** `feat/build-legality`, desde `dev`.
- **Entorno de validación:** shell Linux de Claude en el equipo del usuario, Python 3.14.10. No ejecutado en Windows.

## Decisiones

1. **Fuente: el cliente, no la wiki.** Los grupos (`ItemGroup`) y sus máximos están en el bin de objetos 16.23; cada legendario tiene un grupo propio de máximo 1. Así no hay que mantener a mano listas de exclusión. Solo el número de huecos (6) sale de la wiki, porque no está en ese bin.
2. **Los grupos cuentan pilas.** Deducido de Pociones (grupo de máximo 1, `maxStack` 5) y Centinelas de control (máximo 1, `maxStack` 2). Queda `Pendiente de verificación` hasta medirlo.
3. **Una build ilegal no se calcula por defecto** (código 2). `--allow-illegal-build` la calcula y avisa. `Recomendación`: un cálculo sobre una build imposible parecería un dato válido; el usuario puede pedirlo explícitamente.
4. **Lo desconocido no se rellena:** sin `maxStack` cada copia ocupa su hueco y se anota; sin datos de grupo es una violación.

## Cambios

- `research/binmodel/item_groups.py` y sus pruebas; paso nuevo en `research/tools/refresh_patch.py`.
- `lol-knowledge/derived/item-groups.json` (218 objetos, 159 grupos, cliente 16.23).
- `src/lol_knowledge/objects/legality.py`: validación del archivo y `check_build`.
- `validate` comprueba el archivo; `stats`, `ability` y `rotation` comprueban atacante y objetivo.
- Regla: [`lol-knowledge/mechanics/build-legality.md`](../../lol-knowledge/mechanics/build-legality.md).

## Limitaciones

- No modela el hueco extra de la misión de rol ni el orden de compra.
- Las variantes por modo de los grupos no se leen.
- La salida JSON todavía no incluye la comprobación; las violaciones y notas van a la salida de errores. Entrará en el contrato de IA-01.
