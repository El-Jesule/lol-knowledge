# Comando `rotation`: ataques, críticos y efectos de objeto — fase 14

- **Objetivo:** encadenar ataques básicos y habilidades contra un objetivo con los efectos de objeto que cambian el daño: daño al impactar (Filo de la niebla), aumentos (Verdugo de gigantes) y reducciones del objetivo (Placas, Adaptabilidad).
- **Rama:** `feat/rotations`, creada desde `dev` (`2ae3b0f`).
- **Entorno de ejecución:** shell Linux de Claude en el equipo del usuario, Python 3.14.10, `PYTHONPATH=src`. No se ha ejecutado con `.\.venv\Scripts\python.exe` en Windows.

## Reglas investigadas antes del código

- [`critical-strike.md`](../../lol-knowledge/mechanics/critical-strike.md): el crítico base es 200 % desde el parche 26.1 (notas oficiales) y el cliente 16.22 lo confirma (`critDamageMultiplier` = 2,0 en 172 campeones). La página de la wiki aún dice 175 %; la discrepancia queda registrada.
- [`damage-modifiers.md`](../../lol-knowledge/mechanics/damage-modifiers.md): los aumentos de daño infligido se suman entre sí (V26.09) y los de daño recibido se multiplican; todo multiplica con la resistencia.
- [`basic-attacks-and-on-hit.md`](../../lol-knowledge/mechanics/basic-attacks-and-on-hit.md): el daño al impactar se calcula con la vida previa al ataque y no critica.

## Decisiones

1. **Pasos explícitos, sin probabilidad.** `attack`, `attack:crit`, `SLOT` o `SLOT.caso`. Una habilidad con varios casos obliga a elegir uno; sumarlos sería sumar alternativas.
2. **La vida se lleva de un paso a otro.** Todas las partes de un paso leen la vida del inicio del paso. La vida no baja de 0 y el informe marca el primer paso letal.
3. **Nada se adivina.** Cuerpo a cuerpo o a distancia, tipo de objetivo manual y vida adicional se piden cuando un efecto los necesita; sin ellos, el comando falla con la opción que falta.
4. **Lo no aplicado se dice.** Efectos no evaluables o de otro tipo se listan; si pueden cambiar el daño (Rabadon), el resultado queda `Pendiente de verificación`.
5. **Etiquetas de la evidencia.** Un efecto con evidencia secundaria deja la parte en `Pendiente de verificación`. Desde la fase 15, Filo de la niebla está corroborado por el cliente y queda `Derivado` ([`item-client-evidence.md`](item-client-evidence.md)).
6. **Placas y daño al impactar:** no consta si se reduce; no se aplica y la parte queda pendiente con una nota.
7. **Objetos repetidos** se rechazan: los efectos únicos de varias copias no están modelados.

## Cambios de datos

- `critdamagemultiplier` añadido a [`champion-records.json`](../../lol-knowledge/derived/champion-records.json) con `research/binmodel/records.py`; los demás campos y los SHA-256 no cambian.
- Catálogo de objetos `catalog_version: 4`: Filo de la niebla declara `subject: target` en la vida actual. El evaluador compartido solo lee del objetivo con `subject: target`, así que sin el cambio la rotación habría leído la vida del atacante.
- `crit_damage_bonus` pasa a ser una estadística resuelta (aditiva, fracción); la probabilidad de crítico sigue pendiente.
- El objetivo de un escenario lleva su tipo, su vida adicional y sus objetos.

## Pruebas

39 pruebas nuevas en `tests/test_rotation.py`. 22 mutaciones deliberadas del motor: 21 eliminadas; la que sobrevive (pasar `crit` a las partes al impactar) es equivalente, porque la condición de crítico ya exige que la parte sea el ataque. La mutación que quitaba las etiquetas de penetración sobrevivió al principio y ahora tiene su prueba.

## Limitaciones

- Sin tiempo: ni enfriamientos, ni velocidad de ataque, ni duraciones.
- Los ataques potenciados por habilidades (Q de Zaahen) se escriben como la habilidad más un `attack`; no consta si aplican los efectos al impactar.
- Sin escudos, curación, reducciones planas de daño ni modificadores de estadística porcentual (Rabadon). Desde la fase 16 se informa la curación por robo de vida y omnivampirismo ([`attack-speed-and-vamp.md`](attack-speed-and-vamp.md)).
- Solo Zaahen tiene kit.
