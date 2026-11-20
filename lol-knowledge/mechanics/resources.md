# Recursos y costes de habilidades

- **Ámbito:** reserva de recursos del campeón (maná, energía, vida y recursos secundarios), costes de las habilidades (Q, W, E y R), regeneración pasiva en línea de tiempo y restauraciones por objetos y runas. Lo usan `python -m lol_knowledge stats` (`metrics.resource`, `metrics.ability_costs`) y `python -m lol_knowledge rotation`.
- **Parche de referencia:** Data Dragon `16.23.1` y cliente `16.23` (`16.23.8399929+branch.releases-16-23.content.release`).
- **Fecha de consulta:** 2026-11-20
- **Código:** [`src/lol_knowledge/resources.py`](../../src/lol_knowledge/resources.py), [`src/lol_knowledge/stats/metrics.py`](../../src/lol_knowledge/stats/metrics.py), [`src/lol_knowledge/kit/model.py`](../../src/lol_knowledge/kit/model.py) y [`src/lol_knowledge/rotation.py`](../../src/lol_knowledge/rotation.py).

## Fuentes

| Id | Fuente | Qué cubre | Naturaleza |
|---|---|---|---|
| C1 | Data Dragon `16.23.1`, `data/current/champions/<Id>.json`: `partype`, `stats.mp`, `stats.mpperlevel`, `stats.mpregen`, `stats.mpregenperlevel`, `spells[*].cost`, `spells[*].costType` | Tipo de recurso, reserva base y regeneración por cada 5 s de los 173 campeones; costes oficiales por rango de Q, W, E y R | `Oficial` de Riot |
| C2 | Cliente `16.23` ([`../derived/item-effects.json`](../derived/item-effects.json) → `items.3508`, [`../derived/runes.json`](../derived/runes.json) → `8009` y `8226`) | Devolución de maná de Segador de esencia (`TotalManaRefund = 0.5 × SpellbladeDamage`), tabla por nivel 1–18 de Claridad mental (`6..44`, `EnergyRestore = 6`, `PercentManaRestore = 0.15`, `CooldownDuration = 8`) y regeneración de Banda de maná (`1 %` del maná perdido cada `5 s`) | `Derivado` (datos del cliente, no API oficial) |
| C3 | Wiki oficial de League of Legends (`wiki.leagueoflegends.com`, consultada el 2026-11-20): `Champion_ability` (rev `4086204`), `Energy` (rev `4073066`), `Health` (rev `4073062`), `Presence_of_Mind` (rev `4062635`), `Template:Rune_data_Presence_of_Mind` (rev `3985219`), `Manaflow_Band` (rev `4058511`) y `Module:ItemData/data` (rev `4095269`) | Imposibilidad de lanzar con recurso insuficiente; energía fija sin crecimiento ni escalado por objetos de maná (`200`, `400` en Shen, `50/5 s = 10/s`); costes de vida incapaces de matar al lanzador (suelo `1` de vida); corroboración de la curva de Claridad mental (`× 0,8` a distancia, sustitución por Triunfo en campeones sin maná ni energía) y de Segador de esencia (`50 %` del daño previo a mitigación) | Fuente comunitaria secundaria (corrobora C1 y C2) |

## 1. Tipos de recurso en la hoja (`Oficial`, C1; `Derivado`, C3)

En Data Dragon `16.23.1`, los 173 campeones se clasifican en cuatro grupos en `champion_resource(sheet)`:

1. **Maná (`Maná` / `Mana`, 145 campeones):** reserva máxima de `sheet["mana"]` (base, crecimiento por nivel, objetos y Banda de maná) y regeneración de `sheet["mana_regen"]` (por cada 5 s; `/ 5` por segundo; [`regeneration.md`](regeneration.md)). Actúa como reserva de lanzamiento (`uses_casting_pool = true`).
2. **Energía (`Energía` / `Energy`, 6 campeones: Akali, Ambessa, Kennen, Lee Sin, Shen y Zed):** reserva fija `stats.mp` (`200`, salvo `400` en `data:champion:Shen`) y regeneración fija `stats.mpregen` (`50` cada 5 s = `10 / s`), sin crecimiento por nivel (`mpperlevel = 0`, `mpregenperlevel = 0`) e inmune a objetos de maná o regeneración de maná (C1 + C3). En la hoja, las estadísticas `mana` y `mana_regen` siguen bloqueadas para evitar que los objetos de maná se sumen a la energía; `metrics.resource` resuelve la reserva de energía como `Oficial`. Actúa como reserva de lanzamiento (`uses_casting_pool = true`).
3. **Sin reserva de lanzamiento (`Nada`, `""`, `Pozo sangriento` y recursos con `mp = 0`):** no existe reserva de maná ni energía (`uses_casting_pool = false`). Algunos de estos campeones pagan habilidades con vida (Dr. Mundo, Briar, Vladimir, Zac).
4. **Recursos secundarios propios (`Furia`, `Coraje`, `Flujo`, `Calor`, `Escudo`, `Ferocidad`, `Ráfaga carmesí` con `mp > 0`):** se muestra el tope oficial `stats.mp` (`Oficial`, C1), pero `uses_casting_pool = false` porque su generación y decaimiento dependen de cada kit individual.

## 2. Resolución del coste de una habilidad (`Calculado`)

Al lanzar una habilidad en `rotation`, `resolve_ability_cost` aplica este orden de prioridad:

1. **`case.cost` en `kit.json` (`Derivado` o `Oficial`):** fórmula explícita del caso (admite `mana`, `energy`, `health` o `none`, con cualquier operación de `ABILITY_OPS`, incluidas fracciones de `current_health` o `max_health`).
2. **Reactivación (`case.recast = true`):** coste `0` (`Derivado`), porque la reactivación pertenece al lanzamiento ya pagado (por ejemplo `Ahri` `R.recast` o `Zaahen` `Q.recast`).
3. **`ability.cost` en `kit.json`:** fórmula explícita de la habilidad (útil para campeones con coste de vida donde Data Dragon publica `cost: [0, ...]`).
4. **Coste oficial de Data Dragon (`Oficial`, C1):** `spells[slot].cost[rank - 1]` en el recurso del campeón (`mana` o `energy`).
5. **Aviso de coste de vida sin declarar (`Pendiente de verificación`):** si Data Dragon publica coste `0` pero `costType` contiene `"vida"` o `"health"` y el kit no declara `cost`, el paso se anota y queda `Pendiente de verificación` en lugar de fingir coste cero.

## 3. Reglas en `rotation` (`Calculado`, C1 + C2 + C3)

1. **Reserva inicial:** por defecto el campeón empieza al máximo (`maximum`). Puede ajustarse con `--attacker-resource <cantidad>` o con `--input attacker_resource_percent=<0..1>` (no ambos a la vez; fuera de `0..maximum` es error).
2. **Validación de coste (maná y energía):** si el coste supera el recurso disponible al llegar el paso, `rotation` rechaza el lanzamiento con error (C3: no se puede lanzar una habilidad sin el recurso requerido). La opción `--allow-insufficient-resource` permite calcular igualmente: deja la reserva en `0`, registra el índice del paso en `insufficient_steps` y marca el paso y el resultado como `Pendiente de verificación`.
3. **Costes de vida (`health`):** deducen vida del atacante (inicializando el seguimiento de vida al máximo si no se indicó `--input attacker_health_percent`). Según C3 (`Health` rev `4073062`), los costes de vida nunca pueden matar al lanzador: si la vida actual no supera el coste, el lanzamiento sigue permitido y deja al campeón en `1` de vida (`actual = max(0, vida_actual - 1)`).
4. **Regeneración pasiva (`--timeline`):** entre pasos y durante `wait:<segundos>` se acumula `regen_per_5s / 5 × Δt` de forma continua, con tope en `maximum`, **antes** de pagar el coste del paso siguiente. Sin `--timeline` no transcurre tiempo y la regeneración es `0`.
5. **Banda de maná (`8226` `ManaflowBand`, `Derivado`, C2 + C3):** en `--timeline` para campeones de maná, además de sus `+250` de maná máximo en la hoja, cada `5 s` (`t = 5, 10, 15…`) restaura el `1 %` del maná faltante en ese instante (`max_mana - mana_actual`).
6. **Segador de esencia (`data:item:3508`, `Derivado`, C2 + C3):** en el ataque potenciado por Hoja encantada, el componente `resource_restore` restaura maná igual al `50 %` del daño **previo a mitigación** de Hoja encantada (`62,5 % DA base + 25 × probabilidad de crítico`), con tope en el maná faltante (solo campeones de maná; [`spellblade.md`](spellblade.md)).
7. **Claridad mental (`8009` `PresenceOfMind`, `Derivado`, C2 + C3):** contra campeones enemigos (`--target-kind champion`):
   - **Al infligir daño** (enfriamiento `8 s` en `--timeline`; una vez sin línea de tiempo): restaura `6..44` de maná según la tabla por nivel 1–18 del cliente `16.23` (`[6, 6.8, 7.6, 8.4, 9.2, 10, 12, 14, 16, 18, 20, 23.2, 26.4, 29.6, 32.8, 36, 40, 44]`; `× 0,8` para campeones a distancia, requiere `--attacker-range`) o `6` de energía.
   - **Al derribar (`killed_target`):** restaura un `15 %` del maná o energía máximos (en el juego tiene un retardo de `1 s`, aplicado en el paso letal y anotado).
   - **Campeones sin maná ni energía:** no restaura recurso y se anota que el juego la sustituye por Triunfo (C3).

## Fuera de alcance / limitaciones

- Recursos secundarios específicos de cada campeón (Furia, Calor, Flujo, Ferocidad, Escudo, Coraje, Ráfaga carmesí) y habilidades con coste continuo (toggles como la R de Anivia o la E de Karthus).
- Excepciones de coste de vida que sí bloquean el lanzamiento (p. ej., Soraka W por debajo del 5 % de vida o Ivern P sin vida suficiente, C3).
- Mejoras externas de regeneración (Bendición azul / Emblema de perspicacia, fuente, frutos de miel) y restauraciones de energía propias de kits de campeón (p. ej., W de Akali, pasiva de Lee Sin o sombra de Zed, hasta contar con sus kits).
