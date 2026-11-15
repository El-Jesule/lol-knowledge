# Valores de datos de objetos del cliente 16.22

- **Fecha de consulta:** 2026-11-15
- **Fuente:** cliente local, `DATA/FINAL/Global.wad.client` → entrada `items` (ruta resuelta con `hashes.game.txt` de CommunityDragon: XXH64 `1d720f4f42640c18`) → `Items/<id>` de clase `ItemData`
- **Build:** `16.22.8348910+branch.releases-16-22.content.release` (de `Game/content-metadata.json`)
- **Método:** `python -m binmodel.items` (lector PROP de `binmodel.propbin`). Cada float32 se escribe como el decimal más corto que vuelve al mismo float32. Un registro sin `mDataValues` queda con `data_values: null`.
- **Resultado:** el comando escribe `item-data-values-16.22.json`, que no se versiona (`research/.gitignore` excluye los JSON de informes); este documento recoge sus valores. SHA-256 del bin: `06d06e2121f3cecd145e35781618a911881cc23d51fd0d53709d088a92a03000`. No se versiona ningún archivo del cliente.
- **Etiqueta:** `Derivado`. No es una API oficial de Riot.

## Por qué

Seis efectos del [catálogo de objetos](../../lol-knowledge/objects/catalog.json) se apoyaban solo en la wiki comunitaria (`evidence_confidence: secondary`). El cliente guarda los valores con los que se juega, así que es una segunda fuente independiente.

## Notas de parche 26.21 y 26.22

Las notas oficiales no tocan ninguno de los 15 objetos del catálogo. En 26.21 cambian Bastion Breaker, Dawncore, Gluttonous Greaves y Hubris; en 26.22, Doran's Bow y Overlord's Bloodmail (nombres en inglés, como en las notas consultadas). Fuente: `leagueoflegends.com/en-sg/news/game-updates/league-of-legends-patch-26-21-notes/` y `…-26-22-notes/`, consultadas el 2026-11-15.

## Lectura del bin

- 2826 registros. 10 registros de la clase `0xff9d3409` no se pueden decodificar (su primer campo declara el tipo `0x4d`, que el formato PROP conocido no tiene). Se omiten y se listan en el JSON. Ninguno es un `Items/<id>` del catálogo.
- **Sobrescrituras por modo** (`DataValuesModeOverride`): las claves son FNV-1a del nombre del modo. Se identifican `ARAM` y `KIWI` (ARAM: Mayhem); las demás quedan como hash. Ninguna es `CLASSIC`, así que en la Grieta del Invocador rigen los valores por defecto.

## Comparación con el catálogo

| Objeto | Efecto | Catálogo (wiki) | Cliente 16.22 (por defecto) | Resultado |
|---|---|---|---|---|
| 3153 Hoja del rey arruinado | Filo de la niebla | 9 % / 6 % de vida actual; tope 100 contra súbditos y monstruos | `MeleeValue` 0,09; `RangedValue` 0,06; `MonsterDamageCap` 100 | Coincide → `corroborated` |
| 3153 Hoja del rey arruinado | Zarpazo sombrío | Ralentización 30 %, 1 s; ventana 6 s; enfriamiento 15 s; 3 acumulaciones | `MoveSpeedMod` −0,3; `RangedMoveSpeedMod` −0,15; `MoveSpeedDuration` 1; `AttackCounterDuration` 6; `Cooldown` 15 | Coincide y **añade** 15 % para portadores a distancia. Las 3 acumulaciones no están en los datos → sigue `secondary` |
| 3036 Recuerdos de lord Dominik | Verdugo de gigantes | 1 % por cada 100 de vida adicional, tope 15 % a 1500 | `MaxBonusDamagePercent` 0,15; `MaxBonusHealth` 1500 | Tope y umbral coinciden. La pendiente lineal no está en los datos (la calcula el script del objeto) → sigue `secondary` |
| 3157 Reloj de arena de Zhonya | Tiempo detenido | Estasis 2,5 s; enfriamiento 120 s | `Duration` 2,5; `Cooldown` 120 | Coincide → `corroborated` |
| 3075 Malla de espinas | Espinas | 20 + 10 % de armadura adicional; heridas graves 40 %, 3 s | `BaseDamage` 20; `BonusArmorDamageRatio` 0,1; `GrievousAmount` 0,4; `GrievousDuration` 3 | Coincide → `corroborated` |
| 3143 Presagio de Randuin | Humildad | Ralentización 70 %, 2 s; enfriamiento 90 s | `SlowAmount` 0,7; `SlowDuration` 2; `Radius` 500; `Cooldown` 90 (ARAM 75, ARAM: Mayhem 60) | Coincide → `corroborated` |

Otros valores que confirman lo que ya decía Data Dragon: Adaptabilidad de Randuin (`PercentCritDamageReduction` 0,3), Obra mágica del Sombrero mortal de Rabadon (`APAmp` 0,3) y Gracia estelar de Renovación de piedra lunar (`ChainHeal` 0,3, `ChainShield` 0,35). Espada larga, Chaleco de cadenas, Gema avivadora, Filo infinito y Bastón del Vacío no tienen `mDataValues`.

## Límites

- Los nombres de los valores (`MeleeValue`, `MonsterDamageCap`…) dicen qué miden, pero el código que los aplica está en los scripts del juego, que no se leen aquí. Por ejemplo, que `MonsterDamageCap` también valga para súbditos viene de la wiki.
- Las sobrescrituras de modos sin nombre identificado no se interpretan.
