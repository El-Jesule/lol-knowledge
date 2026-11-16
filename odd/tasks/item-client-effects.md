# Datos de efectos de los objetos desde el cliente — fase 23

- **Objetivo:** tener, para los 218 objetos comprables de la Grieta, las cifras de sus efectos tal como las guarda el cliente, para curar efectos sin depender de la wiki ni de agregadores.
- **Rama:** `feat/item-client-effects`, creada desde `dev` (`d378610`).
- **Entorno de ejecución:** shell Linux de Claude en el equipo del usuario, Python 3.14.8, `PYTHONPATH=src` (y `research` para sus pruebas). No se ha ejecutado con `.\.venv\Scripts\python.exe` en Windows.

## Decisiones

1. **El lector del cliente se queda en `research/`**, como el de los registros de campeones (`champion-records.json`): `research/binmodel/item_effects.py` genera el archivo y `lol-knowledge/derived/item-effects.json` lo publica. La CLI no lee el cliente; solo valida el archivo. Esto cambia lo que se propuso en la conversación (llevar el lector a `src/`): seguir el patrón que ya existía evita meter la lectura de WAD en el código de ejecución y deja la regeneración en manos de quien tenga el juego instalado.
2. **Nada se rellena:** un valor sin `mValue` se lista aparte; un nombre repetido con el mismo valor se anota y con otro valor es un fallo; los hashes sin nombre se quedan como hash.
3. **Textos:** `item_<id>_tooltip` y `item_<id>_active`. Las demás claves repiten esos textos, llevan contadores de partida o conservan texto de temporadas anteriores (los objetos míticos), y añadían falsos marcadores sin resolver.
4. **Marcadores clasificados:** valor, valor sin cantidad, `EffectNAmount`, cálculo, variante, contador de partida (`@f1@`) u otro registro (`@spell.…@`); `null` si no se encuentra.
5. **`validate`:** forma del archivo, etiqueta `Derivado`, versión del cliente igual a la del snapshot (16.22 frente a 16.22.1) y cobertura exacta de los objetos de `catalog-stats.json`. Si el archivo no existe, se omite con aviso, como los registros de campeones.

## Pruebas

- Nuevas: `research/tests/test_binmodel_item_effects.py` (16, con bins, tablas RST y WAD sintéticos) y `tests/test_item_effects_data.py` (33: forma, versión, cobertura, coherencia de cada marcador y el archivo publicado), más dos casos en `tests/test_validate.py`. Suite final: 786 pruebas, más 189 de `research/` (1 omitida, como antes).
- **Mutaciones deliberadas: 21, todas eliminadas.** Dos sobrevivieron al principio (el límite de la lista `EffectNAmount` y que `validate` pase los ids del catálogo) y ahora tienen prueba.

## Resultado

218 objetos sin fallos; en 149 de los 162 objetos con marcadores, todos se resuelven con su propio registro. Detalle en [`research/reports/item-effects-16.22.md`](../../research/reports/item-effects-16.22.md).

## Limitaciones

- Las cifras no dicen cómo se aplican; cada efecto sigue necesitando un modelo curado.
- Varias activas leen sus valores de otro registro, que no se sigue.
- Hay que regenerarlo en cada parche desde el cliente.
