# Ataques básicos, daño al impactar y vida del objetivo en una rotación

- **Ámbito:** cómo convierte el motor un paso `attack` o `attack:crit` en partes de daño y cómo lleva la vida del objetivo de un paso a otro. Lo usa `python -m lol_knowledge rotation`.
- **Parche de referencia:** cliente 16.22 (2026-11-15).
- **Fecha de consulta:** 2026-11-15

## Fuentes

| Id | Fuente | Qué cubre | Naturaleza |
|---|---|---|---|
| A1 | LoL Wiki, `Attack_damage` (revisión 3959050), consultada el 2026-11-15 | El daño de ataque fija el daño físico sin modificar del ataque básico | Fuente comunitaria secundaria |
| A2 | LoL Wiki, `Blade_of_the_Ruined_King` (revisión 3688594), consultada el 2026-11-15 | El daño al impactar se aplica antes que el del ataque, así que Filo de la niebla usa la vida actual previa al ataque | Fuente comunitaria secundaria |
| A3 | LoL Wiki, artículo `Damage` (copia de `leagueoflegends.fandom.com`), consultada el 2026-11-15 | La mayoría de efectos al impactar no se ven afectados por el crítico | Fuente comunitaria secundaria |

## Partes de un paso de ataque (`Derivado`, fuente comunitaria)

1. **El ataque:** daño físico igual al daño de ataque total del atacante (A1). En `attack:crit`, multiplicado por el crítico ([`critical-strike.md`](critical-strike.md)).
2. **Daño al impactar de los objetos del atacante:** cada efecto `on_hit` evaluable del catálogo, con su tipo de daño. No se multiplica por el crítico (A3). Desde la versión 10 del catálogo hay seis (además del golpe de Hoja encantada de siete objetos, desde la 11): Filo de la niebla (Hoja del rey arruinado), Arco curvo, Final del ingenio, Diente de Nashor, Hoja de furia de Guinsoo y El final ([catálogo](../objects/README.md)).
3. **Hoja encantada:** si una habilidad cargó el ataque, se añade el golpe del objeto como otra parte al impactar ([`spellblade.md`](spellblade.md)). `attack:nospellblade` lo descarta.
4. **Cada N ataques y Vigor:** los efectos que cuentan ataques o salen con Vigor se añaden cuando toca ([`attack-counters.md`](attack-counters.md)).
5. **Ejecución:** con Recaudadora, si un campeón queda por debajo del 5 % tras el paso, se añade una parte `execute` con su vida restante ([`target-health.md`](target-health.md)).
6. **Quemaduras:** la primera habilidad que las inicia añade su daño completo como una parte `burn`, una vez por rotación ([`burns.md`](burns.md)).
7. Cada parte se mitiga por separado con la resistencia que le toca ([`damage-mitigation.md`](damage-mitigation.md)) y luego se le aplican los modificadores ([`damage-modifiers.md`](damage-modifiers.md)).

## Vida actual del objetivo

- La rotación empieza con la vida actual dada (por defecto, la máxima) y le resta el total de cada paso.
- Dentro de un paso, todas las partes leen la vida **del inicio del paso**. Para el daño al impactar coincide con A2: se calcula antes de que el ataque reste vida.
- La vida no baja de 0. El informe señala el primer paso que la deja en 0 y sigue sumando los pasos siguientes (daño sobrante).

## Datos que el motor nunca adivina

- **Cuerpo a cuerpo o a distancia:** Filo de la niebla cambia de 9 % a 6 % según el portador. Data Dragon no publica esa clasificación, así que se da con `--attacker-range melee|ranged`. Sin ella, el efecto se rechaza.
- **Tipo de objetivo:** el tope de 100 de Filo de la niebla solo vale contra súbditos y monstruos, y Verdugo de gigantes solo contra campeones. Un objetivo campeón (`--target-champion`) lo es; uno manual necesita `--target-kind`.
- **Vida adicional del objetivo:** Verdugo de gigantes la necesita. Con un objetivo manual se da con `--target-bonus-health`.
- **Objetos repetidos:** los efectos únicos de dos copias no están modelados; el motor rechaza la lista.

## Fuera de alcance

- **Ataques potenciados por habilidades** (por ejemplo, la Q de Zaahen): el kit modela el daño adicional de la habilidad y el informe recuerda que el ataque se suma aparte. Para incluirlo se escribe un paso `attack` junto a la habilidad. No consta si el ataque potenciado aplica los efectos al impactar como un ataque normal.
- **Tiempo:** el motor no simula enfriamientos, velocidad de ataque ni duraciones.
- **Efectos de objetos no evaluables o de otro tipo** (control de masas, curación, escudos, estadísticas porcentuales como la del Sombrero mortal de Rabadon): se listan en el informe como no aplicados. Si pueden cambiar el daño, el resultado queda `Pendiente de verificación`.
