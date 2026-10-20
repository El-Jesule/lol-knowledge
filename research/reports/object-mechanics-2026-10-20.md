# Mecánicas de objetos — evidencia y plan de integración (2026-10-20)

- **Alcance:** las cinco mecánicas pendientes de la fase 5 (BotRK A/B, Lord Dominik, Zhonya, Malla de espinas), la ampliación selectiva del catálogo y la auditoría Git.
- **Snapshot:** `data/current`, parche `16.20.1`, locale `es_ES`, `items.json` SHA-256 `32ea85dfa5d2b35683f40ea325f544c906dc445f58b5fd53d8e98c75d2d3355b`, consultado el 2026-10-18.
- **Rama de trabajo:** `feat/object-mechanics-coverage`, creada desde `feat/object-model` (`f4f4919`). Sin commits, sin push, sin fusiones.
- **Estado:** las cinco mecánicas tienen conclusión. Cuatro son implementables; una (BotRK B) es parcialmente modelable porque la persistencia entre objetivos no está publicada.

## 1. Método y fuentes

Se contrastaron tres niveles:

1. **Dato oficial estructurado:** `data/current/items.json` (Data Dragon, Riot). Publica identidad, estadísticas planas/porcentuales, oro, mapas, recetas y la descripción localizada.
2. **Prosa oficial:** la misma descripción de Data Dragon. A veces publica la operación pero omite el número (por ejemplo, BotRK dice «un porcentaje»).
3. **Fuente secundaria:** LoL Wiki, contenido comunitario bajo CC BY-SA 3.0. Se consultó el wikitexto crudo (`?action=raw`) el 2026-10-20 para obtener fórmulas y valores que Data Dragon no publica. **No es una fuente oficial de Riot y no se presenta como tal.**

No se usó la instalación local del cliente para estas cinco mecánicas: el dato relevante está en definiciones de objeto, no en el bin de Zaahen ya estudiado. La instalación local existe (`D:\Games\Riot Games\League of Legends`), pero no se localizó un `items.bin.json` equivalente al export de CommunityDragon usado en la fase anterior; no se reimplementó un lector `PROP` de objetos en esta fase.

### 1.1 Corroboración de identidad y balance

La wiki y el snapshot coinciden en todos los valores estructurados de los objetos investigados. Esto no convierte la wiki en oficial, pero sí demuestra que describe el mismo estado de balance que `16.20.1`:

| Objeto | Data Dragon `16.20.1` | Wiki (2026-10-20) |
|---|---|---|
| BotRK `3153` | 40 AD, 25 % AS, 10 % LS, 3200 oro | 40 AD, 25 % AS, 10 % LS, 3200 oro |
| Lord Dominik `3036` | 35 AD, 25 % crítico, 3300 oro, 35 % penetración (prosa) | 35 AD, 25 % crítico, 3300 oro, 35 % penetración |
| Zhonya `3157` | 105 AP, 50 armadura, 3250 oro | 105 AP, 50 armadura, 3250 oro |
| Thornmail `3075` | 150 vida, 75 armadura, 2450 oro | 150 vida, 75 armadura, 2450 oro |
| Randuin `3143` | 350 vida, 75 armadura, 2700 oro | 350 vida, 75 armadura, 2700 oro |
| Botas de hechicero `3020` | 45 velocidad, 1100 oro, 12 penetración mágica (prosa) | 45 velocidad, 1100 oro, 12 penetración mágica |

**Discrepancia de numeración:** el snapshot se etiqueta `16.20.1`, mientras el historial de la wiki usa numeración `V25.x`/`V26.01`. No se observó una diferencia de estadísticas; se registra como discrepancia de numeración, no como evidencia de un build distinto.

## 2. BotRK A — daño de impacto

### Conclusión

El daño adicional al impactar es:

```
bonus_physical_damage = ratio(holder_range) * target_current_health
ratio(melee) = 9 %
ratio(ranged) = 6 %
cap = 100 flat against minions and monsters
```

- Depende de la **vida actual** del objetivo, no de la máxima.
- El ratio depende de la clasificación **melee/ranged del portador**, no del tipo de objetivo.
- No hay mínimo publicado; el único límite publicado es el máximo de 100 contra súbditos y monstruos.
- No escala por nivel ni por campeón. ARAM usa 12 %/10 % y Arena 8 %/5 %; esos modos no se modelan.
- No se aplica a estructuras.
- Es daño físico adicional, se calcula al inicio del evento de daño, no dispara eventos on-hit y beneficia de robo de vida/omnivamp.

### Evidencia

- Data Dragon: «Los ataques infligen un porcentaje de la vida actual del objetivo como daño físico adicional al impactar». No publica el número.
- Wiki, `Blade_of_the_Ruined_King?action=raw`: «Basic attacks deal bonus physical damage on-hit equal to (Melee 9% / Ranged 6%) of the target's current health, with a maximum of 100 against minions and monsters.» Notas de la misma página: no aplica a estructuras; el daño se calcula al inicio del evento; no dispara on-hit; ARAM 12 %/10 %; Arena 8 %/5 %.
- Corroboración estructural: Data Dragon confirma «vida actual», «al impactar», «daño físico adicional» y los stats de identidad.

### Confianza

- Categoría y variables: **oficial** (Data Dragon).
- Ratio 9/6, cap 100 y modificadores de modo: **secundaria** (wiki), sin una segunda fuente independiente.
- No hay contradicción entre fuentes; hay una omisión oficial.

### Decisión

**Implementable.** Se modela con `by_holder_range` y `percent_of`; el cap queda como `limit` declarado. El motor debe aportar `ChampionState.attack_range`; si falta, el evaluador falla con `missing_holder_range`, no asume melee.

### Preguntas abiertas

- Redondeo/truncamiento exacto del daño (entero vs flotante) antes de mitigación.
- Interacción exacta con escudos y con daño que no llega a aplicarse; el dato de wiki describe el orden del evento, no una fórmula de motor.
- Modificadores de modo (ARAM/Arena) fuera del alcance del modelo actual.

## 3. BotRK B — acumulaciones y efecto de ataques

### Conclusión

- Se requieren **3 ataques básicos on-hit contra campeones**.
- Cada aplicación dura **6 s**; el máximo es **3 acumulaciones**.
- La tercera acumulación consume todas y ralentiza un **30 % durante 1 s**.
- El enfriamiento interno es **15 s**.
- Solo cuentan ataques básicos on-hit contra campeones; no habilidades, súbditos ni monstruos.
- No lo bloquea el escudo de hechizos.
- La persistencia de acumulaciones **entre objetivos distintos** no está publicada. No se afirma que sean por objetivo ni globales: queda como inferencia no verificada.

### Evidencia

- Data Dragon: «Atacar a un campeón tres veces lo ralentiza un 30% durante 1 s.» (3, 30 %, 1 s).
- Wiki: «Basic attacks on-hit against enemy champions apply a stack for 6 seconds, stacking up to 3 times. The third stack consumes them all to slow the target by 30% for 1 second (15 second cooldown).» Nota: no lo bloquea el escudo de hechizos.

### Confianza

- 3 impactos, 30 %, 1 s: **oficial** (Data Dragon).
- Ventana de 6 s, máximo 3 y enfriamiento 15 s: **secundaria**.
- Persistencia entre objetivos: **desconocida**.

### Decisión

**Parcialmente modelable.** La estructura y los valores conocidos se incorporan; `model_status` queda `partially_evaluable` y la nota declara la persistencia como no verificada. No se inventa un comportamiento por objetivo.

### Preguntas abiertas

- ¿Las acumulaciones viven en el objetivo o en el portador? La redacción «apply a stack» sugiere el objetivo, pero no se verificó en partida.
- ¿El enfriamiento empieza al consumir la tercera acumulación o al aplicarla?
- ¿Los ataques esquivados/bloqueados aplican acumulación? La descripción no lo aclara.

## 4. Lord Dominik — curva de daño adicional

### Conclusión

La curva completa es una rampa lineal con tope:

```
bonus_damage_percent = min(target_bonus_health / 100, 15)
```

Equivale a **1 % por cada 100 de vida adicional**, máximo **15 % a 1500**. Es continua; no hay tabla de puntos ni interpolación entre umbrales. Se aplica solo a campeones enemigos. La vida adicional es la estadística del objetivo; no se recalcula después de otros modificadores dentro del modelo (el orden de aplicación del daño es responsabilidad del motor).

### Evidencia

- Data Dragon: «Infliges hasta un 15% de daño adicional a campeones, según su vida adicional. El máximo de daño adicional se alcanza con 1500 de vida adicional.» Publica los extremos, no la pendiente.
- Wiki, `Lord_Dominik%27s_Regards?action=raw`, V26.01: «1% per 100 bonus health, up to a maximum of 15% at 1500 bonus health.» La misma página lista la fórmula de la plantilla `0 to 15 for 16 | 0 to 1500` con `formula=1% per 100 bonus health`.
- Corroboración: el snapshot tiene 3300 oro, 35 AD, 25 % crítico y 35 % penetración, exactamente el estado V26.01.

### Confianza

- Extremos 15 %/1500 y condición «solo campeones»: **oficial** (Data Dragon).
- Pendiente 1 %/100: **secundaria**, coherente con los extremos y con la fórmula publicada por la wiki.
- No hay contradicción; la wiki completa lo que Data Dragon omite.

### Decisión

**Implementable.** Se modela con `min(percent_of(1 % de vida adicional), 15)`. Tests manuales en 0, 500, 750, 1000, 1499, 1500 y 5000.

### Preguntas abiertas

- Redondeo final del daño y orden respecto a otros modificadores (penetración, reducciones, crítico). El modelo expone el modificador; el motor decide el orden.
- ¿La vida adicional incluye modificadores temporales? La estadística del objetivo es la entrada; el modelo no distingue fuentes.

## 5. Zhonya — enfriamiento de la activa

### Conclusión

- Enfriamiento de la activa: **120 s**.
- Duración de la estasis: **2,5 s** (no confundir).
- Los activos de objeto se reducen con **aceleración de objetos** (por ejemplo, Perspicacia cósmica), no con aceleración de habilidades.
- No se encontró una variación por parche dentro del estado actual; el valor es estable desde V6.9.

### Evidencia

- Data Dragon: «Entras en estasis durante 2.5 s.» No publica enfriamiento.
- Wiki, `Zhonya%27s_Hourglass?action=raw`, historial V10.23 y V6.9: «Put yourself in stasis for 2.5 seconds ... (120 second cooldown)»; V6.9: «Active cooldown increased to 120 seconds from 90.»
- La página de notas describe la activa como auto-targeted, sin cast time; no se encontró una reducción por aceleración de habilidades.

### Confianza

- Duración 2,5 s: **oficial**.
- Enfriamiento 120 s: **secundaria**.
- Interacción con aceleración de objetos: **secundaria/documental**, no modelada como fórmula.

### Decisión

**Implementable como dato.** Se añade `cooldown_seconds: 120` y `model_status: evaluable`. La interacción con item haste queda documentada; el motor puede aplicar la reducción cuando modele esa estadística.

### Preguntas abiertas

- Fórmula exacta y tope de item haste en el parche actual.
- Cambios específicos de modo (Arena/URF) no investigados.

## 6. Malla de espinas — daño reflejado

### Conclusión

- Daño reflejado: **20 + 10 % de la armadura adicional del portador**, como daño **mágico** al atacante.
- Se activa al recibir un ataque básico/on-hit, aunque el daño se mitigue por completo con escudo o invulnerabilidad.
- No se activa si el ataque se esquiva, se bloquea o falla por ceguera.
- No es un proyectil; no lo bloquea el escudo de hechizos.
- El daño reactivo se mitiga con la RM del atacante.
- La reducción de armadura plana/porcentual afecta al ratio de armadura adicional; la penetración de armadura no.
- Aplica **40 % de Heridas graves durante 3 s** si el atacante es un campeón. Es un componente distinto del daño reflejado.
- No hay mínimo publicado.

### Evidencia

- Data Dragon: «Al recibir un ataque, inflige daño mágico al atacante y aplica un 40% de heridas durante 3 s si se trata de un campeón.» Confirma tipo, trigger y Heridas; omite la cantidad.
- Wiki, `Thornmail?action=raw`, V14.20: «Thorns base damage increased to 20 from 15.» y «Thorns bonus armor ratio reduced to 10% bonus armor from 15%.» Notas: daño reactivo, no proyectil, no bloqueado por spell shield, se activa aunque el daño se mitigue, no si se esquiva/bloquea/falla; Heridas a campeones; la reducción de armadura afecta al ratio, la penetración no.
- Corroboración: snapshot 150 vida / 75 armadura / 2450 oro, estado V14.20.

### Confianza

- Tipo mágico, trigger, Heridas 40 %/3 s, condición de campeón: **oficial**.
- 20 + 10 % armadura adicional: **secundaria**.
- Interacción con mitigaciones: **secundaria/documental**, no una fórmula de motor.

### Decisión

**Implementable.** Se modela con `add(constant 20, percent_of(10 % de armadura adicional))` y un componente de Heridas separado. El daño se marca como mágico y con condición `damage_source_is_attack`.

### Preguntas abiertas

- Redondeo del daño reactivo y orden exacto respecto a la RM del atacante.
- Interacción con armadura negativa (la wiki antigua la trataba como 0 para el ratio; no se verificó en el parche actual).
- Fuentes de daño distintas de ataques básicos/on-hit (la descripción actual no las incluye).

## 7. Ampliación del catálogo

Se añadieron dos objetos, además de completar los cinco existentes:

| Id | Objeto | Motivo | Evidencia |
|---|---|---|---|
| `3020` | Botas de hechicero | Penetración mágica **plana**, familia que el modelo no tenía; útil para comparar builds AP explosivas. | Data Dragon: «12 de penetración mágica»; stats/oro coinciden con la wiki. |
| `3143` | Presagio de Randuin | Reducción condicional de daño crítico (modificador de daño) y activo de área con enfriamiento; útil para supervivencia. | Data Dragon: «30% menos de daño de los impactos críticos» y «70% durante 2 s»; wiki: enfriamiento 90 s. |

Total: **15 objetos, 10 efectos**. No se declara cobertura completa de ninguna categoría.

### Objetos evaluados y no añadidos

- **Kraken Slayer `6672`:** la fórmula actual combina daño base por nivel, escalado por vida faltante y un multiplicador ranged; la plantilla de la wiki no permite fijar todos los puntos sin ambigüedad. Añadirlo habría requerido inventar una interpretación. Se deja fuera.
- **Luden's Companion `6655`:** requiere modelar 6 ecos, reparto al objetivo principal y daño de área; el esquema actual no tiene contador de cargas/ecos. Se deja fuera.
- **Eclipse `6692`:** el escudo y su ratio no se verificaron con suficiente precisión en esta fase. Se deja fuera.
- **Sterak's Gage `3053`:** el escudo depende de vida adicional y umbral; no se verificó la fórmula completa. Se deja fuera.

Estas ausencias son deliberadas: el objetivo es exactitud, no cobertura aparente.

## 8. Cambios de esquema y compatibilidad

Se mantiene `schema_version: 1` porque los cambios son aditivos; se sube `catalog_version` a `2`.

| Cambio | Motivación | Compatibilidad |
|---|---|---|
| `magic_penetration_flat` | Botas de hechicero declaran penetración mágica plana; el modelo solo tenía la porcentual. | Nueva estadística canónica; los documentos existentes no la usan. |
| `percent_of` | Expresar «10 % de armadura adicional» o «1 % de vida adicional» sin constantes decimales no citadas. | Nueva operación; las fórmulas existentes siguen válidas. |
| `min` | Tope de la rampa de Lord Dominik. | Nueva operación; validada con operandos no vacíos. |
| `by_holder_range` | BotRK depende de melee/ranged del portador. | Nueva operación; falla explícitamente si falta el rango. |
| `subject` en `stat`/`percent_of` | `bonus_health` es del objetivo en Lord Dominik, pero `bonus_armor` es del portador en Thornmail. El scope solo no basta. | Campo opcional; por defecto se conserva la inferencia anterior (`current`/`max` → objetivo; resto → campeón). |
| `sources` + `evidence_confidence` | Registrar cifras que no están en Data Dragon sin presentarlas como oficiales. | Campos opcionales; los efectos existentes no los necesitan. |
| `basis: external_evidence_explicit` | Declarar que la fórmula viene de evidencia externa y no de la prosa de Data Dragon. | Nuevo valor; exige al menos una fuente y fórmulas evaluables. |
| `verification: secondary_source_verified` | Resumen del objeto cuando algún efecto usa fuentes secundarias. | Nuevo valor; los objetos existentes conservan `description_quote_verified`. |
| `ChampionState.attack_range` | El motor necesita melee/ranged para BotRK. | Campo obligatorio del contrato; se actualizaron tests y documentación. |

Regla de validación nueva: **cada número de un efecto debe aparecer en la descripción de Data Dragon o en la cita de alguna fuente declarada**. Esto no convierte la wiki en oficial; impide números huérfanos y hace explícita la procedencia. La regla cubre constantes, duraciones, límites, enfriamientos, contadores y ventanas de acumulaciones.

Invariantes añadidas tras la verificación independiente:

- Una fuente `community_wiki` o `community_dragon` no puede marcarse `official`; `official` solo vale para la descripción de Data Dragon.
- `evidence_confidence: corroborated` exige al menos dos fuentes declaradas.
- Las claves desconocidas de una fórmula se rechazan (un `subjet` mal escrito no cae silenciosamente en la convención de campeón).
- `TargetProfile.bonus_health` es obligatorio: un cero implícito no puede activar la curva de Lord Dominik.

## 9. Auditoría Git

### Grafo observado (2026-10-20)

```
main 5fd136e ────────────────────────────── 34 commits por detrás de dev
dev  f3e2948 = integration (local)
  ├── research/zaahen-formula-extraction 89e2dbe   (+5)
  │     └── feat/object-model f4f4919             (+7)
  │           └── feat/object-mechanics-coverage f4f4919 + cambios sin confirmar
  └── origin/integration c4017ac (24 commits por detrás de integration local)
```

- `main` = `5fd136e` (primer commit), 34 commits por detrás de `dev`.
- `dev` = `integration` = `f3e2948`; `origin/dev` = `f3e2948`; sin divergencia local.
- `integration` local está **24 commits por delante** de `origin/integration` (`c4017ac`). No se hizo push; esa diferencia es preexistente y debe decidirse aparte.
- `research/zaahen-formula-extraction` = `89e2dbe`, 5 commits por delante de `dev`, ancestro de `feat/object-model`.
- `feat/object-model` = `f4f4919`, 12 commits por delante de `dev`, 7 por delante de `research`.
- `feat/object-mechanics-coverage` apunta a `f4f4919`; los cambios de esta fase están en el árbol de trabajo, **sin commit** por instrucción explícita.

### Dependencias

1. `feat/object-model` depende de `research/zaahen-formula-extraction`: la rama contiene los 5 commits de investigación y los 7 propios. El modelo de objetos usa el snapshot, no importa `research/`, pero la auditoría del extractor y sus correcciones forman parte de la misma entrega.
2. Esta fase depende de `feat/object-model`: el esquema, el catálogo y el validador viven allí.
3. `dev` e `integration` no tienen divergencia entre sí; no hay commits nuevos en `dev` después de `f3e2948`.
4. No se detectaron ramas locales con trabajo posterior a `dev` fuera de las tres anteriores. Las ramas `feat/*`, `fix/*`, `docs/*`, `chore/*` restantes ya están integradas en `dev` (son ancestros).

### Riesgo de conflicto

`feat/object-model` modifica archivos compartidos: `README.md`, `lol-knowledge/INDEX.md`, `research/README.md`, `src/lol_knowledge/cli.py` y `src/lol_knowledge/validate.py`. Como `dev` no avanzó desde `f3e2948`, no hay cambios concurrentes en esos archivos. El riesgo esperado es bajo, pero **no se ejecutó ninguna simulación de merge**; la ausencia de conflicto no se declara como hecho hasta que se haga la integración real.

### Secuencia propuesta (no ejecutada)

1. Autorizar y confirmar los cambios de esta fase en commits coherentes sobre `feat/object-mechanics-coverage`.
2. Revisar el diff completo y ejecutar la suite sobre la rama.
3. `git checkout integration` (local, en `f3e2948`) y `git merge --no-ff research/zaahen-formula-extraction`.
4. Ejecutar la suite completa y el validador sobre `integration`.
5. `git merge --no-ff feat/object-model`; resolver conflictos conservando la intención de ambas partes.
6. Ejecutar de nuevo la suite completa y los validadores.
7. `git merge --no-ff feat/object-mechanics-coverage`; repetir las comprobaciones.
8. `git checkout dev` y `git merge --ff-only integration`. Si el fast-forward falla, volver a integrar `dev` en `integration` y repetir; no forzar.
9. No hacer push. La decisión de publicar `origin/integration` (24 commits por detrás) y `origin/dev` queda fuera de esta tarea.

**Prohibiciones respetadas:** no se fusionó, no se hizo rebase, no se movieron referencias, no se hizo push, no se borraron ramas ni commits, no se ejecutaron operaciones destructivas.

## 10. Pruebas y resultados reales

| Comprobación | Resultado |
|---|---|
| `pytest -q` | `214 passed in 4.18s` |
| `pytest research -q` | `97 passed in 0.73s` |
| `ruff check .` | `All checks passed!` |
| `ruff format --check .` | `94 files already formatted` |
| `lol_knowledge validate` | `valid: 183 files checked`, salida `0` |
| `python -m lol_knowledge.objects --validate` | `valid: 1 object catalog files checked`, salida `0` |
| Determinismo | 47 700 bytes; SHA-256 `45c42aae5dd7c51e2c91381ff6a52a5b26e24695fb97e9abd1420cc4acc0710b`; dos ejecuciones idénticas |

Pruebas nuevas: fórmulas manuales de Lord Dominik (0, 500, 750, 1000, 1499, 1500, 5000), BotRK melee/ranged y fallo por rango ausente, Thornmail 20/25/30 con 0/50/100 de armadura adicional, ausencia de estadísticas sin sustitución por cero, clasificación de ramas desconocidas/no soportadas, procedencia secundaria obligatoria, citas de fuente, número huérfano, `magic_penetration_flat`, `attack_range` y determinismo. El endurecimiento posterior a la verificación independiente añade pruebas de coherencia entre tipo y confianza de fuente, de `corroborated` con dos fuentes, de contadores de acumulaciones sin cita, de claves desconocidas en fórmulas y de `TargetProfile.bonus_health` obligatorio.

## 11. Limitaciones

- La wiki es una fuente secundaria; no se presenta como oficial. No se hizo una segunda verificación independiente con el cliente o con CommunityDragon para estas cinco mecánicas.
- No se ejecutaron mediciones en partida. Las pruebas son deterministas y offline; no sustituyen una verificación empírica.
- La persistencia de acumulaciones de BotRK entre objetivos sigue sin verificar.
- Los modificadores por modo (ARAM/Arena/URF) están documentados pero no modelados.
- El orden de aplicación de mitigaciones, penetraciones y modificadores es responsabilidad del futuro motor; el modelo expone fórmulas y condiciones, no un pipeline de daño.
- El catálogo cubre 15 objetos; no se declara completa ninguna categoría.
- La integración Git no se ejecutó; el plan es una propuesta condicionada a autorización.

## 12. Próximas tareas recomendadas

1. **Verificar empíricamente BotRK B** (persistencia entre objetivos y reinicio del enfriamiento) con una prueba controlada; es el único hueco mecánico que queda abierto en la muestra.
2. **Modelar el pipeline de daño** (orden de penetración, mitigación, modificadores y crítico) antes de añadir objetos cuya evaluación dependa de ese orden.
3. **Añadir un objeto de escudo con fórmula verificada** (por ejemplo, Sterak's Gage) cuando se haya confirmado su ratio, para cubrir la familia de escudos absolutos.
4. **Integrar las ramas** siguiendo la secuencia de la sección 9, con autorización y revisión por unidad.
