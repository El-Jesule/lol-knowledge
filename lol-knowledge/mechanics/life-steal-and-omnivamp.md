# Robo de vida y omnivampirismo

- **Ámbito:** curación que obtiene el atacante con el daño que inflige, por robo de vida (`life_steal`) y omnivampirismo (`omnivamp`). La usa `python -m lol_knowledge rotation`, paso a paso y en total.
- **Parche de referencia:** Data Dragon 16.22.1 y cliente 16.22 (2026-11-15). El omnivampirismo funciona así desde el parche 26.1.
- **Fecha de consulta:** 2026-11-15

## Fuentes

| Id | Fuente | Qué cubre | Naturaleza |
|---|---|---|---|
| L1 | Notas oficiales del parche 26.1 (`leagueoflegends.com/en-sg/news/game-updates/patch-26-1-notes/`), sección «Omnivamp», consultadas el 2026-11-15 | El omnivampirismo pasa a «function fully as life steal» y «Now applies at 100% value, reduced to 33% value from pets, damage over time damage, and area effect spells against Minions»; Espada de Doran recibe 2,5 % de omnivampirismo | Oficial de Riot |
| L2 | LoL Fandom Wiki, `Lifesteal`, última edición indicada «June 11, 2023 - V13.11», consultada el 2026-11-15 (CC BY-SA) | Cura un porcentaje del daño básico infligido **tras la mitigación**; los ataques y algunos efectos al impactar o habilidades con la marca «applies life steal»; se suma entre sí; no se beneficia del poder de curación; Heridas graves lo reduce; no aplica contra estructuras | Fuente comunitaria secundaria |
| L3 | LoL Wiki, `Life_steal` (revisión 3415084), solo el extracto del buscador, consultado el 2026-11-15 | La curación usa el daño tras armadura, resistencia mágica y reducciones de daño | Fuente comunitaria secundaria |
| L4 | LoL Wiki, `Omnivamp`, solo el extracto del buscador (la página no se pudo abrir), consultado el 2026-11-15 | Cura un porcentaje del daño físico, mágico y verdadero tras la mitigación; se suma entre sí; no se beneficia del poder de curación ni del de escudos; no aplica a Prender ni a Castigo; historial: 33 % contra súbditos y monstruos con área, daño periódico y mascotas desde 26.1 | Fuente comunitaria secundaria |
| L5 | LoL Wiki, `Blade_of_the_Ruined_King` (revisión 3688594, del 13-03-2024), extracto del buscador, consultado el 2026-11-15 | «The bonus damage dealt by Mist's Edge benefits from life steal» | Fuente comunitaria secundaria |
| L6 | Data Dragon 16.22.1, `data/current/items.json` | Robo de vida en `stats.PercentLifeStealMod` (Hoja del rey arruinado: 10 %). El omnivampirismo («omnisucción») solo aparece en la descripción (Espada de Doran: 2,5 %) | Oficial de Riot |

## Regla (`Derivado`, L2 + L3 + L4; omnivampirismo corroborado por L1)

```text
curación de una parte = daño final de la parte × (robo de vida aplicable + omnivampirismo aplicable)
```

- **Daño final:** el daño de la parte tras la resistencia y las reducciones de daño (L2, L3: «post-mitigation»).
- **Apilamiento:** varias fuentes de robo de vida se **suman**; varias de omnivampirismo, también (L2, L4). No hay tope.
- **Robo de vida y omnivampirismo en la misma parte (`Pendiente de verificación`):** ninguna fuente dice de forma explícita cómo se combinan. L1 solo dice que el omnivampirismo funciona como el robo de vida; sumar ambos porcentajes es la lectura directa, no un hecho verificado.

### Qué daño cuenta (regla del juego)

- **Robo de vida:** el daño de los ataques básicos y, con la marca «applies life steal», el de algunos efectos al impactar y habilidades (L2). La mayoría de efectos al impactar de objetos la llevan, pero no todos (L2); Filo de la niebla de la Hoja del rey arruinado sí (L5).
- **Omnivampirismo:** todo el daño, físico, mágico y verdadero (L1, L4), salvo Prender y Castigo (L4).
- **Contra súbditos:** el omnivampirismo cura el 33 % con mascotas, daño periódico y hechizos en área (L1); L4 incluye también a los monstruos.
- **Estructuras:** el robo de vida no cura con el daño a estructuras (L2).

## Pendiente de verificación

- **Daño excesivo en el golpe letal:** si un golpe inflige más daño que la vida restante del objetivo, ninguna fuente consultada dice si la curación usa el daño completo o solo la vida que quedaba.

## Modificadores de la curación

- **Poder de curación y escudos:** no se aplica a ninguno de los dos (L2, L4; ver [`survival.md`](survival.md)).
- **Heridas graves:** reduce la curación en un `40 %` (`× 0,60`, no acumulable) tanto al declararse con `--input grievous_wounds=1` como automáticamente al atacar a un objetivo con Malla de espinas (`3075`, antes de la curación del propio ataque disparador; [`survival.md`](survival.md)).
- **Revitalizar (`8453`):** su `+5 %` de poder de curaciones y escudos no afecta a robo de vida ni omnivampirismo, pero su `+10 %` adicional por debajo del `40 %` de vida del atacante sí los multiplica ([`survival.md`](survival.md)).

## Cómo lo aplica `rotation`

La curación de cada parte es su daño final (tras la resistencia y los modificadores de daño infligido y recibido, el mismo que informa la rotación) por los porcentajes que se aplican. La etiqueta de la curación es como mucho `Derivado` (la regla viene de fuentes secundarias) y nunca más fuerte que la del daño de la parte ni la de los porcentajes.

| Parte de la rotación | Robo de vida | Omnivampirismo |
|---|---|---|
| Ataque básico (`attack`, `attack:crit`) | Sí | Sí |
| Daño al impactar de un objeto | Solo si el componente del catálogo declara `applies_life_steal` con `value: true`. Si no lo declara, no se aplica y la curación queda `Pendiente de verificación` con una nota | Sí |
| Habilidad | No: el kit no declara la marca «applies life steal». Con robo de vida, la curación queda `Pendiente de verificación` con una nota | Sí |

- **Etiqueta de `applies_life_steal`:** sigue a la confianza de su fuente. `secondary` deja la curación en `Pendiente de verificación`; Filo de la niebla la declara con L5, así que su curación queda pendiente.
- **Robo de vida y omnivampirismo en la misma parte:** se suman y la curación queda `Pendiente de verificación` con una nota.
- **Objetivo campeón:** todo al 100 %.
- **Súbdito o monstruo:** ataques y daño al impactar al 100 %. Las habilidades se curan al 100 % y quedan `Pendiente de verificación`, porque el kit no dice si son mascotas, daño periódico o área (L1: 33 % en esos casos). Sin `--target-kind`, una habilidad con omnivampirismo no se calcula.
- **Estructura:** sin curación, `Pendiente de verificación`.
- **Golpe letal con daño excesivo:** se usa el daño completo de cada parte y la curación de ese paso queda `Pendiente de verificación` con una nota. Un paso que deja la vida exactamente en 0 no es excesivo.
- **Tope por vida perdida:** si se indica `--input attacker_health_percent=<0..1>`, la rotación sigue la vida del atacante e informa también la curación efectiva acotada por vida perdida (`effective_healing`); sin ese parámetro, informa la curación generada sin acotar ([`survival.md`](survival.md)).

## Implementación (`Calculado`)

- `src/lol_knowledge/stats/registry.py` declara `life_steal` y `omnivamp` como fracciones aditivas con esta regla. La hoja de estadísticas suma sus aportes: el robo de vida viene de `PercentLifeStealMod` de Data Dragon; el omnivampirismo solo puede declararse en el [catálogo de objetos](../objects/catalog.json) con la cita de la descripción (`kind: percent`), porque Data Dragon no lo trae en `stats`. Desde 2026-11-16 lo declaran los objetos cuya descripción lo trae, por ejemplo la Espada de Doran (2,5 %), con el [archivo generado](../objects/catalog-stats.json).
- `src/lol_knowledge/rotation.py` calcula `Healing` por parte; `StepOutcome` y `RotationOutcome` la suman y marcan el golpe letal excesivo. `rotation_report.py` la muestra en texto y JSON.
- Pruebas: `tests/test_stats_vamp.py`, `tests/test_objects_validator.py` y `tests/test_rotation_healing.py`.
