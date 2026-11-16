# Efectos de daño de objetos — fase 24

- **Objetivo:** modelar los efectos de objeto que más influyen en el daño y que el motor ya sabe aplicar, con las cifras del cliente (`lol-knowledge/derived/item-effects.json`) cuando Data Dragon no las da.
- **Rama:** `feat/item-damage-effects`, creada desde `dev` (`8878d13`).
- **Entorno de ejecución:** shell Linux de Claude en el equipo del usuario, Python 3.14.8, `PYTHONPATH=src`. No se ha ejecutado con `.\.venv\Scripts\python.exe` en Windows.

## Alcance elegido

Los efectos que encajan en lo que el motor ya aplica (daño al impactar, estadísticas al máximo de acumulaciones y estadísticas siempre activas):

| Objeto | Efecto | Cifras |
|---|---|---|
| Sombrero mortal de Rabadon (3089) | +30 % de AP total, ahora aplicado por la hoja | Data Dragon |
| Arco curvo (1043) | 15 de daño físico al impactar | Data Dragon |
| Final del ingenio (3091) | 45 de daño mágico al impactar | Cliente |
| Diente de Nashor (3115) | 15 + 15 % de AP mágico al impactar | Cliente |
| Hoja de furia de Guinsoo (3124) | 30 mágico al impactar; +32 % de velocidad de ataque al máximo | Data Dragon |
| El final (3302) | 30 + 10 % de DA adicional + 10 % de AP mágico al impactar; 30 % de penetración al máximo | Cliente |

**Fuera de esta fase** (necesitan mecánicas nuevas en las rotaciones): Hoja encantada (Brillo, Fuerza de trinidad, Perdición del liche, Segador de esencia, Guantelete de hielo, Amanecer y anochecer, Tonada sanguina), cada tercer ataque (Verdugo de krakens, impactos fantasma de Guinsoo), daño en área (Huracán de Runaan), quemaduras y amplificadores por tiempo en combate.

## Decisiones

1. **Evidencia `derived`:** una cifra leída solo del cliente se etiqueta `Derivado`, como pide AGENTS.md (§6). Antes solo podía ser `secondary`, que se muestra como `Pendiente de verificación`, la etiqueta pensada para la wiki. Exige una fuente `client_data`.
2. **La hoja aplica los efectos `always` de estadísticas.** Rabadon deja de omitirse en las rotaciones. Un `percent` de `scope: total` amplifica el total de una estadística de cantidad al final; varios amplificadores se suman sobre el mismo total, sin componerse (hoy solo hay uno).
3. **El final:** la parte del ratio sin `mStat` se toma como AP. Lo respaldan el caso de Nashor (`NashorsAPValue`, también sin `mStat`) y un historial secundario de 26.15. Las resistencias de los ataques luminosos dependen del nivel; las fórmulas de objeto no tienen valores por nivel, así que se declaran y la hoja las deja `Pendiente de verificación`.
4. **Impactos fantasma de Guinsoo:** declarados como `excluded`; las rotaciones con Guinsoo quedan `Pendiente de verificación`.
5. **Catálogo `catalog_version: 10`.**

## Pruebas

- Nuevas o ampliadas: `tests/test_stats_item_scenarios.py` (amplificadores, efectos `always`, razones de la hoja, etiqueta `derived`), `tests/test_stats_real_items.py` (Rabadon, penetración de El final, velocidad de ataque de Guinsoo, daño al impactar de los cuatro objetos en una rotación, impactos fantasma), `tests/test_objects_validator.py` (evidencia `derived`) y `tests/test_rotation.py` (Rabadon lo aplica la hoja). Suite final: 808 pruebas, más 189 de `research/` (1 omitida, como antes).
- **Mutaciones deliberadas: 12; tres sobrevivieron al principio** (etiqueta del amplificador, amplificador en un escenario y la etiqueta `derived`, equivalente porque es también el valor por defecto) y ahora tienen prueba.

## Limitaciones

- Valores por nivel en fórmulas de objeto: no existen todavía (resistencias de El final).
- Las rotaciones no cuentan ataques ni tiempo: Hoja encantada, cada tercer ataque y Ráfaga siguen fuera.
- 152 objetos con efectos siguen `pending`.
