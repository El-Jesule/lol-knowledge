# Legalidad de una build

- **Ámbito:** qué conjuntos de objetos puede llevar a la vez un inventario de la Grieta del Invocador. Lo comprueban `stats`, `ability` y `rotation` antes de calcular, y lo necesitará el optimizador (OPT-02).
- **Parche de referencia:** cliente 16.23 y Data Dragon 16.23.1.
- **Fecha de consulta:** 2026-11-19
- **Código:** [`src/lol_knowledge/objects/legality.py`](../../src/lol_knowledge/objects/legality.py). Datos: [`../derived/item-groups.json`](../derived/item-groups.json), generado con `python -m binmodel.item_groups` ([`research/README.md`](../../research/README.md)).

## Fuentes

| Id | Fuente | Qué cubre | Naturaleza |
|---|---|---|---|
| L1 | Cliente 16.23 (`16.23.8399929+branch.releases-16-23.content.release`): `DATA/FINAL/Global.wad.client` → `items` → `Items/<id>.mItemGroups` y los registros `ItemGroup` (`mMaxGroupOwnable`, `mInventorySlotMin`, `mInventorySlotMax`); `maxStack` y `mRequiredChampion` de cada objeto | Grupos de cada objeto, cuántos objetos de un grupo caben a la vez, el hueco fijo de los abalorios, la acumulación y el campeón exigido | Datos del cliente, no una API oficial |
| L2 | League of Legends Wiki, «Items» (consultada el 2026-11-19) | El inventario tiene seis huecos por defecto y un séptimo para el abalorio; la misión de rol de bot o de apoyo da un hueco extra para un objeto concreto | Fuente comunitaria secundaria |
| L3 | Nombres de las rutas de grupo: `hashes.binentries.txt` de CommunityDragon/Data (GitHub) | `Items/ItemGroups/Boots`, `LastWhisper`, `LifelineItems`… Los grupos propios de cada objeto no tienen nombre en la lista; su `mItemGroupID` es el id del objeto | Lista comunitaria de hashes |

## Reglas (`Derivado`, L1, salvo donde se indica)

1. **Huecos.** Hay 6 huecos normales (`Pendiente de verificación`, L2: no está en el bin de objetos). Cada objeto ocupa un hueco; los iguales se apilan hasta su `maxStack` (5 Pociones de vida en un hueco).
2. **Abalorios.** Los objetos de un grupo con `mInventorySlotMin` = `mInventorySlotMax` solo van en ese hueco: el grupo `Trinket` fija el hueco 6, que no es uno de los 6 normales, y cabe un único abalorio.
3. **Límite por grupo.** Un inventario no puede tener más de `mMaxGroupOwnable` objetos de un grupo. Cuenta pilas, no unidades: el grupo `Potion` tiene máximo 1 y las Pociones de vida se apilan hasta 5, así que caben 5 Pociones de vida pero no una Poción de vida y una Poción reutilizable. Que el límite cuente pilas es una deducción de esos dos datos (`Pendiente de verificación` hasta medirlo en partida).
4. **Objeto único.** Cada objeto legendario tiene un grupo propio con máximo 1, así que no se puede repetir. Los componentes no tienen ese grupo y sí se repiten (dos Espadas largas).
5. **Campeón exigido.** Un objeto con `mRequiredChampion` solo vale para ese campeón (Lanza negra de Kalista, Figura de espantapájaros de Fiddlesticks). Si no se sabe quién lo lleva, la comprobación lo anota y no lo da por ilegal.
6. **Datos ausentes.** Un objeto sin `maxStack` en el bin no recibe el valor por defecto de la clase: cada copia cuenta en su propio hueco y el informe lo anota. Un objeto sin datos de grupo es una violación.
7. **Etiqueta.** Las violaciones son `Derivado` cuando los grupos son del mismo parche que el snapshot y `Pendiente de verificación` si no.

## Grupos compartidos con límite (cliente 16.23, objetos comprables de la Grieta)

| Grupo | Máximo | Objetos |
|---|---|---|
| `Boots` | 1 | Las 15 botas, de Botas (1001) a sus mejoras de nivel 3 |
| `LastWhisper` | 1 | Últimas palabras, Recordatorio letal, Recuerdos de lord Dominik, Cuchilla negra, El final, Rencor de Serylda |
| `LifelineItems` | 1 | Arnés de protoplasma, Bastón del arcángel, Calibrador de Sterak, Sorbemaleficios, Fauces de Malmortius, Arcoescudo inmortal |
| `TearItems` | 1 | Lágrima de la diosa, Bastón del arcángel, Manamune, Llegada del invierno, Diadema susurrante |
| `CleaveItems` | 1 | Tiamat, Hidra voraz, Hidra titánica, Hidra profana, Cortasendas |
| `VoidPen` | 1 | Joya de la plaga, Bastón del Vacío, Florescencia sepulcral, El final, Maldición sanguinolenta |
| `ImmolateItems` | 1 | Rescoldo de Bami, Égida de fuego solar, Fulgor vano |
| `Quicksilver` | 1 | Fajín de mercurio, Cimitarra mercurial |
| `EternityItems` | 1 | Catalizador de eones, Vara de las edades |
| `Glory` | 1 | Sello oscuro, Robaalmas de Mejai |
| `DoransItems` | 1 | Objetos de Doran, mascotas de jungla y objetos de apoyo |
| `GuardianItems` | 1 | Objetos del guardián |
| `Potion` | 1 (pilas) | Poción de vida, Poción reutilizable |
| `StopwatchGroup` | 1 | Brazalete de la buscadora y Brazalete quebrado |
| Sin nombre (`{57352a0f}`) | 1 | Brillo, Fuerza de trinidad, Perdición del liche, Segador de esencia, Guantelete de hielo, Amanecer y anochecer, Tonada sanguina: los objetos de Hoja encantada |
| Sin nombre (`{d52cd27b}`) | 1 | Chaleco de zarzas y Malla de espinas |
| Sin nombre (`{548f93b0}`) | 1 | Barrera frondosa, Velo del hada de la muerte, Filo de la noche |

La lista completa, con los grupos propios de cada objeto, está en `item-groups.json`.

## Lo que no se comprueba

- El hueco extra de la misión de rol (L2): el bin lo describe con `RoleQuestGroup` (huecos 8), pero ningún objeto comprable del catálogo pertenece a él.
- Orden de compra, oro y recetas: una build es un conjunto de objetos, no una secuencia (OPT-04).
- Modos de juego distintos de la Grieta: los grupos se leen sin sus variantes por modo.
- El significado del campo sin nombre `{dbc029fa}` de los grupos `Boots` y `WardPink`: se desconoce y no se usa.

## Uso

```powershell
# Dos pares de botas: código 2 con la violación
.\.venv\Scripts\python.exe -m lol_knowledge stats --champion Ahri --level 11 --item 3006 --item 3047

# Calcular igualmente: las violaciones salen como aviso
.\.venv\Scripts\python.exe -m lol_knowledge stats --champion Ahri --level 11 --item 3006 --item 3047 --allow-illegal-build
```

`ability` y `rotation` comprueban la build del atacante y, si el objetivo es un campeón, también la suya.
