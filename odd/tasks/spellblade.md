# Hoja encantada — fase 25

- **Objetivo:** que las rotaciones apliquen el golpe de Hoja encantada de los siete objetos que la tienen, con las cifras del cliente.
- **Rama:** `feat/spellblade`, creada desde `dev` (`1da5b62`).
- **Entorno de ejecución:** shell Linux de Claude en el equipo del usuario, Python 3.14.8, `PYTHONPATH=src`. No se ha ejecutado con `.\.venv\Scripts\python.exe` en Windows.

## Decisiones del usuario (2026-11-16)

1. **Activación automática:** el primer ataque tras cada habilidad se potencia, como máximo una vez por habilidad; `attack:nospellblade` lo evita. La recarga de 1,5 s se supone lista.
2. **Extras:** el doble impacto de Amanecer y anochecer se aplica; el +8 % / 5 % de 4 s de Tonada sanguina no, y la rotación queda `Pendiente de verificación`.

## Decisiones técnicas

- Disparador nuevo `spellblade` y componente `repeat_on_hit` en el catálogo (versión 11).
- Dos objetos con Hoja encantada son un error: la wiki indica «Limited to 1 Spellblade item».
- La repetición de Amanecer y anochecer repite los efectos al impactar de los objetos, no el propio golpe, y sus partes quedan `Pendiente de verificación` (fuente secundaria; el texto en español está mal traducido).
- **El final:** la wiki antigua de Fandom que citó el usuario da 30 fijo; las notas oficiales de 26.15 añadieron 10 % de DA adicional y 10 % de AP, igual que el cliente. Se añade la fuente `patch_notes` y Sombra pasa a `corroborated`.

## Pruebas

- Nueva: `tests/test_rotation_spellblade.py` (14: pasos, activación, descarte, crítico, objeto único, fórmulas de Perdición del liche, Segador de esencia y Amanecer y anochecer, Tonada sanguina y El final). Casos nuevos en `tests/test_objects_validator.py`. Suite final: 824 pruebas, más 189 de `research/` (1 omitida, como antes).
- **Mutaciones deliberadas: 10, todas eliminadas.**

## Limitaciones

- Sin tiempo: ni recarga real ni ventana de 10 s.
- Curación, maná, ralentizaciones y velocidad de movimiento de estos objetos: declarados, no aplicados.
