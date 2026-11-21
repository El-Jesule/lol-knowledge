# Fase 56 — Cierre total del catálogo de objetos (`OBJ-01`, `218/218` completos)

- **Parche:** `16.23.1` (`data/current/manifest.json`)
- **Fuentes:** Data Dragon (`data/current/items.json`, `Oficial`), cliente `16.23.8399929` (`lol-knowledge/derived/item-effects.json`, `Derivado`) y `wiki.leagueoflegends.com` (`Module:ItemData/data` rev `4095269`, secundaria de corroboración).
- **Fecha:** 2026-11-21.
- **Estado:** completada (**100 % de los `218` objetos comprables de la Grieta en `effect_review: complete`**).

## Qué se implementó

1. **Cuatro nuevas capacidades del motor (`rotation.py`, `defense.py`, `stats/sheet.py`, `objects/schema.py`, `objects/validate.py`):**
   - **Reducción porcentual acumulable de resistencias (`shred_percent_effects`):** `3071` Cuchilla negra (`-6 %` armadura por paso físico contra campeón, hasta `5` cargas = `-30 %`, `6 s`) y `8010` Maldición sanguinolenta (`-7,5 %` RM por habilidad mágica contra campeón, hasta `4` cargas = `-30 %`, `6 s`), inyectadas en `Modifiers.percent_reduction` en orden exacto de mitigación.
   - **Procs diferidos por umbral de daño (`threshold_procs`):** `4646` Sobrecarga tormentosa (`>= 25 %` vida máx. del campeón en `2,5 s` → `125 + 10 % AP` daño mágico tras `2 s`, `30 s` CD; en `--timeline` se liquida a `t + 2 s`, sin `--timeline` se dispara al instante con nota explícita).
   - **Reducción de enfriamiento restante al atacar (`cooldown_refund`):** `6675` Filofugaz de Navori (`-15 %` del enfriamiento restante de Q/W/E por ataque básico en `--timeline`).
   - **Amplificador porcentual de curación y escudo recibidos (`mode: "percent"` en `healing`/`shield`) y escudos reactivos sin umbral en `defense.py`:** `3065` Rostro espiritual (`+25 %` a toda curación y escudo propio en `rotation` y `survive`), más escudos reactivos al recibir daño sin umbral del `30 %` para `2504` Rookern kaénico (`15 %` vida máx. mágico), `3173` Trituradoras encadenadas (`90..190 + 8 %` vida adicional mágico, `5 s`, `15 s` CD) y `3174` Avance blindado (`Placas -10 %` ataques + `90..190 + 8 %` vida adicional físico, `5 s`, `15 s` CD).
   - **`holder_range` en `_sheet_effects` (`stats/sheet.py`):** permite conversiones en hoja con rama cuerpo a cuerpo / distancia como `2517` Hambre insaciable (`5 + 13 %` / `5 + 10 %` DA adicional en velocidad de habilidades).
   - **Optimizador (`OPT-03`):** `_has_excluded_defensive_effect` en [`src/lol_knowledge/optimizer/search.py`](../../src/lol_knowledge/optimizer/search.py) mantiene honestamente como `Pendiente de verificación` las builds defensivas/EHP con pasivas defensivas excluidas (`6665` Jak'Sho, `4401` Fuerza de la naturaleza, `3082` Malla del guardián, `2525` Arnés de protoplasma, `6333` Baile de la muerte).

2. **Curación de los `99` objetos restantes (`lol-knowledge/objects/catalog.json`, `catalog_version: 24`):**
   - **19 objetos nuevos `evaluable`:** `1054`, `1056`, `1120`, `3070` (`Mano amiga`), `1083` (`Segar`), `3095` (`Navaja de asalto`), `3871` (`Perforaplanos de Zaz'Zak`), `2520` (`Quiebrabastiones`), `2517` (`Hambre insaciable`), `2526` (`Diadema susurrante`), `3083` (`Armadura de Warmog`), `3065` (`Rostro espiritual`), `2504` (`Rookern kaénico`), `3173` (`Trituradoras encadenadas`), `3174` (`Avance blindado`), `3071` (`Cuchilla negra`), `8010` (`Maldición sanguinolenta`), `4646` (`Sobrecarga tormentosa`) y `6675` (`Filofugaz de Navori`).
   - **80 objetos restantes revisados a `effect_review: complete`:** todos los objetos de utilidad pura/visión/CC/escudo de hechizos/limpieza/estasis/botas/pociones/trinkets/compañeros de jungla dejan de debilitar indebidamente rotaciones ofensivas, mientras que los objetos con activas o pasivas situacionales de daño/estadísticas (`4628` Precisión infalible, `2523` Óptica hextech, `3146` Sable-pistola, `3152` Cintomisil, `6610` Firmamento desgarrado, `1082`/`3041` Gloria, `6657` Vara de las edades, `6697` Soberbia, etc.) declaran explícitamente su componente `excluded` y mantienen `Pendiente de verificación`.
   - **Balance final:** `218/218` objetos en `effect_review: complete` (`0` pendientes; `174` entradas curadas en `catalog.json`; `166` objetos con `233` efectos totales: `109` `evaluable` y `124` `excluded`).

## Limitaciones declaradas

- Los `124` efectos marcados `excluded` corresponden a activas de objeto, efectos que dependen de aliados, visión, distancia exacta, derribos previos, consumibles (`OBJ-12`) o compañeros de jungla (fuera de alcance según `DEC-03`), y se documentan siempre con su cita y motivo.
- En `3083` Armadura de Warmog (`Vitalidad de Warmog`), `+12 %` se aplica sobre `bonus_health` (exacto en builds de solo objetos; no separa vida adicional procedente de runas o pasivas de campeón).
