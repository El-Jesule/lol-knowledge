# Velocidad de ataque, robo de vida y omnivampirismo — fase 16

- **Objetivo:** resolver en la hoja de estadísticas la velocidad de ataque, el robo de vida y el omnivampirismo, y añadir a `rotation` la curación por robo de vida y omnivampirismo de cada paso y en total.
- **Rama:** `feat/attack-speed-and-vamp`, creada desde `dev` (`8bef1ab`).
- **Entorno de ejecución:** shell Linux de Claude en el equipo del usuario, Python 3.14.8 (venv nuevo con `requirements-dev.txt`), `PYTHONPATH=src`. No se ha ejecutado con `.\.venv\Scripts\python.exe` en Windows.

## Reglas investigadas antes del código

- [`attack-speed.md`](../../lol-knowledge/mechanics/attack-speed.md): `min(base + ratio × adicional, 3,0)`. El tope 3,0 es oficial (notas 25.S1.3); la fórmula y el crecimiento vienen de la wiki (2024, desfasada en el tope) y el ratio, del cliente 16.22. Base y crecimiento del cliente coinciden con Data Dragon en los 173 campeones.
- [`life-steal-and-omnivamp.md`](../../lol-knowledge/mechanics/life-steal-and-omnivamp.md): curación sobre el daño tras la mitigación; las fuentes de cada uno se suman. El omnivampirismo funciona como el robo de vida desde 26.1 (notas oficiales), con un 33 % contra súbditos para mascotas, daño periódico y área.
- La wiki (`wiki.leagueoflegends.com`) no se pudo abrir desde el entorno; varias citas vienen del extracto del buscador y así se indica en cada fuente.

## Decisiones

1. **Dos estadísticas para la velocidad de ataque.** `attack_speed_bonus` (fracción aditiva: crecimiento, objetos, efectos) y `attack_speed` (ataques por segundo con `cap` 3). Los objetos declaran `attack_speed` en porcentaje, que es velocidad adicional; el registro lo encamina con `routes_to`. No se cambia el esquema del modelo de objetos.
2. **El ratio solo hace falta si hay velocidad adicional.** Sin registro del cliente, el nivel 1 sin objetos sigue siendo la base `Oficial`; con velocidad adicional, el total queda bloqueado con el motivo.
3. **Kits que cambian el tope** (Bel'Veth, Graves, Jhin, Sion, Zeri, según la wiki de 2024): velocidad `Pendiente de verificación` con nota.
4. **Daño al impactar y robo de vida (decisión del usuario):** campo nuevo `applies_life_steal` en los componentes de daño del catálogo, con su propia fuente. Filo de la niebla lo declara con la wiki (`secondary`). Sin declaración, no se aplica y la curación queda pendiente.
5. **Golpe letal con daño excesivo (decisión del usuario):** curación sobre el daño completo, pendiente con nota.
6. **Omnivampirismo de habilidades contra súbditos y monstruos (decisión del usuario):** al 100 % y pendiente. Sin `--target-kind`, una habilidad con omnivampirismo no se calcula.
7. **Fuentes de omnivampirismo (decisión del usuario):** solo el esquema (`omnivamp`, `kind: percent`, declarable desde la descripción). Ningún objeto del catálogo lo declara todavía.
8. **Robo de vida y omnivampirismo en la misma parte:** se suman y quedan pendientes; ninguna fuente lo dice de forma explícita.
9. **Habilidades y robo de vida:** no se aplica, porque el kit no declara la marca «applies life steal»; con robo de vida, la curación de esas partes queda pendiente.

## Cambios de datos

- Catálogo de objetos `catalog_version: 6`: `applies_life_steal` en Filo de la niebla.
- `omnivamp` pasa a ser estadística canónica del modelo de objetos.

## Pruebas

- Nuevas: `tests/test_stats_attack_speed.py` (21), `tests/test_stats_vamp.py` (7), `tests/test_rotation_healing.py` (25); y casos nuevos en `tests/test_cli_stats.py`, `tests/test_objects_validator.py` y `tests/test_objects_model.py`. Suite final: 600 pruebas, más 173 de `research/` (1 omitida, como antes).
- **Mutaciones deliberadas: 71, todas eliminadas al final.** Velocidad de ataque 23, robo de vida y omnivampirismo 6, catálogo 8, curación en rotaciones 34. Sobrevivieron al principio 5, y cada una tiene ahora su prueba: la etiqueta de la velocidad adicional no llegaba al total escalado; la etiqueta de la regla y la de la parte no llegaban a la curación; una declaración sin confianza conocida no quedaba pendiente; y el informe de texto no mostraba las notas de curación.

## Limitaciones

- Sin tiempo: la velocidad de ataque no cambia cuántos ataques caben en una rotación.
- Reducciones de velocidad de ataque, suelo de 0,2 y kits que cambian el tope o el ratio: no modelados.
- La curación no está limitada por la vida perdida del atacante, ni reducida por Heridas graves.
- La declaración de Filo de la niebla es secundaria y de 2024 (revisión de la wiki leída en el extracto del buscador).
- El tope del cliente no se ha localizado en los datos del juego: el valor 3,0 sale de las notas de parche.
