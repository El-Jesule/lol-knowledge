# Snapshot de Data Dragon 16.22.1 — fase 11

- **Objetivo:** alinear el snapshot oficial con el cliente instalado (16.22), para que los datos del cliente y los oficiales sean del mismo parche.
- **Rama:** `chore/snapshot-16-22`, creada desde `dev` (`cdbf78f`). El snapshot lo descargó el usuario en Windows (`lol_knowledge update --patch 16.22.1`), porque Data Dragon no es accesible desde el entorno de Claude.
- **Entorno de validación:** shell Linux de Claude en el equipo del usuario, Python 3.14.10, `PYTHONPATH=src`. No se ha ejecutado la suite con `.\.venv\Scripts\python.exe` en Windows.

## Qué cambió entre 16.20.1 y 16.22.1

- **27 campeones** con cambios en Data Dragon; en 9 solo cambian aspectos o textos. Cambios numéricos en Azir, Darius, Jinx, Kayle, Lee Sin, Locke, Mel, Wukong, Sion, Thresh, Viktor, Yuumi y Zaahen (Q: 8/7.5/7/6.5/6).
- **Objetos del catálogo:** ninguno cambia en estadísticas, oro, descripciones ni recetas.
- **`attackdamageperlevel`:** sigue a 0 en los 173 campeones.

## Lo que el validador no veía (y ahora ve)

1. **Un defecto de datos caducaba en silencio.** El defecto del DA estaba registrado solo para 16.20.1; con el snapshot 16.22.1 dejaba de aplicarse y Zaahen pasaba a tener 63 de DA a nivel 11, etiquetado `Oficial`. Ahora cada defecto lista los parches en los que se comprobó (`patches`, esquema `lol-data-issues/2`) y `validate` falla si el snapshot está en un parche no comprobado.
2. **Las secuencias por rango no se comprobaban.** `abilities.md` seguía diciendo `10/9/8/7/6` para la Q de Zaahen y `validate` lo daba por bueno, porque solo cruzaba números sueltos. Ahora cada secuencia `a/b/c` en code span de `overview.md` o `abilities.md` debe existir como lista en el JSON del campeón.

## Cambios

- `data/current/` → Data Dragon 16.22.1.
- Catálogo de objetos → `catalog_version: 3`, `game_version: 16.22.1`. La evidencia secundaria no se ha revisado contra las notas de parche 16.21–16.22.
- Base de conocimiento de Zaahen, índice, README y defectos conocidos → 16.22.1.
- El prototipo de la fase 3.5 compara el bin 16.20 con Data Dragon 16.20.1: sus pruebas usan ahora el fixture `research/fixtures/zaahen_ddragon_16.20.1.json` (copia exacta del snapshot anterior, SHA-256 `7f504475…`) en lugar de `data/current/`.
- La hoja de estadísticas da el DA del cliente como `Derivado` (antes `Pendiente de verificación`).

## Limitaciones

- El catálogo de objetos solo se ha contrastado con Data Dragon; los efectos con fuente secundaria podrían haber cambiado en 16.21–16.22 sin reflejo en las descripciones.
- Otros campeones con cambios en 16.22.1 no tienen documentación en la base de conocimiento, así que no hay nada más que actualizar.
