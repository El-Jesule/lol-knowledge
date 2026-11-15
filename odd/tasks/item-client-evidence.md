# Evidencia del cliente para los efectos de objeto — fase 15

- **Objetivo:** sustituir o corroborar con los datos del cliente 16.22 las cifras de objetos que solo venían de la wiki comunitaria, y revisar las notas de parche 26.21 y 26.22.
- **Rama:** `feat/item-client-evidence`, creada desde `dev` (`cd41aa7`).
- **Entorno de ejecución:** shell Linux de Claude en el equipo del usuario, Python 3.14.10. No se ha ejecutado con `.\.venv\Scripts\python.exe` en Windows.

## Decisiones

1. **Fuente:** la entrada `items` de `Global.wad.client`. Su ruta se resolvió con la lista de hashes de CommunityDragon, porque ningún nombre probado a mano coincidía.
2. **Lector tolerante solo cuando se pide.** `parse_prop(..., skip_unreadable=True)` omite los registros que no se pueden decodificar y los lista; el tamaño declarado debe caber en el búfer. Por defecto el lector sigue siendo estricto.
3. **Nuevo tipo de fuente `client_data`.** Puede ser `secondary` o `corroborated`, nunca `official`. Como el cliente guarda los porcentajes como fracciones (0,09), el validador acepta en sus citas el número multiplicado por 100. Solo para ese tipo.
4. **Subir la confianza solo cuando todas las cifras coinciden.** Filo de la niebla, Tiempo detenido, Espinas y Humildad pasan a `corroborated`. Verdugo de gigantes y Zarpazo sombrío siguen en `secondary`, porque la pendiente lineal y las 3 acumulaciones no están en los datos.
5. **Corrección:** Zarpazo sombrío ralentiza un 15 % con portadores a distancia, no un 30 %.

## Efecto en las rotaciones

El daño al impactar de Filo de la niebla pasa a `Derivado`. Verdugo de gigantes sigue dejando la parte en `Pendiente de verificación`.

## Pruebas

- `research/tests/test_binmodel_items.py`: extracción, sobrescrituras por modo, registros ausentes o mal formados, omisión de registros ilegibles y tamaño declarado fuera del búfer.
- `tests/test_objects_validator.py`: fracciones de `client_data`, solo para ese tipo, y nunca `official`.
- `tests/test_objects_model.py`: confianza de cada efecto y ralentización a distancia.

## Limitaciones

- El código que aplica los valores (scripts del juego) no se lee: la forma de la curva de Verdugo de gigantes sigue sin fuente oficial.
- Los 10 registros ilegibles del bin no son objetos del catálogo, pero su formato no está entendido.
