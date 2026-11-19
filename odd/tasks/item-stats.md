# Estadísticas de todos los objetos de la Grieta — fase 21

- **Objetivo:** tener las estadísticas de todos los objetos comprables de la Grieta del Invocador, para no depender de objetos sintéticos, y que las rotaciones no presenten como completo un objeto cuyos efectos no están modelados.
- **Ramas:** `feat/effect-review` y `feat/item-stats`, creadas desde `dev` (`f0179e8` y `a786e45`).
- **Entorno de ejecución:** shell Linux de Claude en el equipo del usuario, Python 3.14.8, `PYTHONPATH=src`. No se ha ejecutado con `.\.venv\Scripts\python.exe` en Windows.

## Datos de partida (Data Dragon 16.22.1)

- 863 objetos; 218 comprables en la Grieta con id de hasta 4 cifras (los demás son variantes de otros modos o no se compran).
- Todas las líneas del bloque `<stats>` de esos 218 encajan en 23 frases. 21 son estadísticas del motor; poder de curaciones y escudos (7 objetos) y oro cada 10 s (5) no lo son.
- En todas las líneas que Data Dragon también trae en `stats`, el número de la descripción coincide.
- 166 objetos tienen `<passive>` o `<active>`; los demás no tienen más texto que sus estadísticas.

## Decisiones

1. **Primero, la regla de las rotaciones** (`feat/effect-review`): el modelo conserva `effect_review` y una rotación con un objeto del atacante o del objetivo que no esté en `complete` queda `Pendiente de verificación` con una nota.
2. **Archivo generado aparte** (`catalog-stats.json`), elegido con el usuario: `catalog.json` se queda con los efectos y las revisiones curados a mano. `validate` regenera el archivo desde el snapshot y falla si no coincide o si un objeto curado declara a mano estadísticas que ya genera.
3. **Nuevo estado `pending`** para los objetos que solo tienen estadísticas generadas y efectos en la descripción.
4. **Un `0` de la descripción no es un cero real** (regla ya escrita del modelo): se guarda como desconocido y la hoja lo trata como aporte 0 `Pendiente de verificación`. Solo ocurre en Flechas de los Yun Tal.
5. **Líneas sin estadística del motor:** se guardan con el motivo (`unmodelled_stats`), no se descartan.
6. **Catálogo `catalog_version: 8`:** las estadísticas de la descripción de los objetos curados (3020, 3031, 3067, 3111, 3134, 3135, 6617) se movieron al archivo generado; eran idénticas.

## Pruebas

- Nuevas: `tests/test_objects_generate.py` (33: selección, frases, comprobación contra Data Dragon, ceros, errores, fusión, validación de frescura y CLI), `tests/test_stats_real_items.py` (8, con objetos reales: Bailarín espectral, Espada de Doran, Rostro espiritual, Canción de batalla de Shurelya, Botas del lanzahechizos, Yun Tal) y casos en `tests/test_rotation.py` y `tests/test_objects_validator.py`. Suite final: 730 pruebas, más 173 de `research/` (1 omitida, como antes).
- **Mutaciones deliberadas: 29, todas eliminadas** (4 de la regla de revisión y 25 del generador, la fusión y la validación). Dos sobrevivieron al principio en la regla de revisión (el modelo y la hoja descartaban un valor distinto de `complete` sin que ninguna prueba lo viera) y ahora tienen prueba.
- **Coste medido:** cargar el modelo pasa de 22 ms a 39 ms.

## Limitaciones

> **Nota (2026-11-19):** esta lista refleja el estado al cerrar la fase. Lo que sigue abierto, con su prioridad, está en la [hoja de ruta](../roadmap.md); lo resuelto después se marca abajo con la fase que lo resolvió.

- Solo el locale `es_ES`: con otro, el generador se niega en vez de adivinar las frases.
- Efectos: 16 objetos curados; 158 objetos con efectos en la descripción siguen `pending`.
- Variantes de otros modos y objetos no comprables (mejoras de Ornn, transformaciones): fuera.
