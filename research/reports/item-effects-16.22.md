# Datos de efectos de objetos del cliente 16.22

- **Fecha de consulta:** 2026-11-16
- **Fuentes:** cliente local, `DATA/FINAL/Global.wad.client` → entrada `items` → `Items/<id>` (clase `ItemData`), y `DATA/FINAL/Localized/Global.es_ES.wad.client` (tablas RST v5).
- **Build:** `16.22.8348910+branch.releases-16-22.content.release` (`Game/content-metadata.json`). SHA-256 del bin de objetos: `06d06e2121f3cecd145e35781618a911881cc23d51fd0d53709d088a92a03000`; del WAD de textos: `395c78cee45cca06b747947f31b9ea95967127b854d3d14e85a1fca971cbc9fd`.
- **Método:** `python -m binmodel.item_effects` ([`../binmodel/item_effects.py`](../binmodel/item_effects.py)). Los nombres de las claves RST salen de `hashes.rst.xxh3.txt` de CommunityDragon/Data (GitHub), que solo convierte nombres en claves; ese archivo no se versiona. Los nombres de clases y campos de los cálculos están escritos en el código y solo se muestran si su FNV-1a coincide.
- **Resultado publicado:** [`../../lol-knowledge/derived/item-effects.json`](../../lol-knowledge/derived/item-effects.json), que `lol_knowledge validate` comprueba.
- **Etiqueta:** `Derivado`. No es una API oficial de Riot.

## Qué guarda cada objeto

| Campo | Origen | Para qué |
|---|---|---|
| `data_values` | `mDataValues` | Valores con nombre (`CritMax` 25). `null` si el objeto no tiene ninguno. |
| `data_values_without_amount` | `mDataValues` sin `mValue` | Nombres sin cantidad. No se rellenan con el valor por defecto de la clase. |
| `repeated_data_values` | `mDataValues` | Nombres repetidos con el mismo valor (`Cooldown` de 3142). Si el valor cambiara, el objeto sería un fallo. |
| `mode_overrides` | `DataValuesModeOverride` | Valores de otros modos: ARAM, KIWI (ARAM: Mayhem), URF, CHERRY (Arena) y siete claves sin nombre identificado. La Grieta usa los valores por defecto. |
| `effect_amounts` | `mEffectAmount` | Lista numerada antigua que los textos leen como `EffectNAmount`. |
| `calculations` | `mItemCalculations` | Árbol de cada cálculo (`CritPerStackCalc`). Las referencias a valores aparecen por su nombre. |
| `string_calculations` | `StringCalculations` | Variantes cuerpo a cuerpo / distancia / por defecto de un valor del texto. |
| `texts` | RST: `item_<id>_tooltip` y `item_<id>_active` | Plantillas del texto en es_ES, con `{{ … }}` expandido una vez. |
| `placeholders` | Marcadores `@Nombre@` de los textos | De dónde sale cada marcador, o `null` si no está en el registro del objeto. |

## Resultados (218 objetos comprables de la Grieta)

- **Fallos:** ninguno. Hay 10 registros del bin, de otra clase, que no se pueden decodificar; ninguno es un `Items/<id>` del catálogo.
- **Con valores:** 167 objetos tienen `data_values`; 93 tienen `effect_amounts`; 41, sobrescrituras por modo; 8, variantes cuerpo a cuerpo / distancia.
- **Cálculos:** 251 en 100 objetos. 100 se identifican por nombre porque un texto los usa; los demás quedan como hash. En los árboles quedan 72 hashes distintos sin nombre: clases, campos o referencias a valores de otros registros (por ejemplo, la clase `{e9a3c91d}`, que aparece con `mFormulaParts` y `mRangedMultiplier`).
- **Textos:** 179 objetos tienen al menos uno; 40 tienen un texto de activa. Los 39 restantes no tienen ni tooltip ni activa (componentes y objetos de estadísticas puras, como las Botas o la Espada larga).
- **Marcadores:** 162 objetos tienen alguno; en **149** se resuelven todos con su propio registro. Por tipo: 371 valores con nombre, 100 cálculos, 27 `EffectNAmount`, 10 variantes, 2 valores sin cantidad y 1 contador de partida (`@f1@`).
- **Marcadores sin resolver (27 en 13 objetos):** cinco parecen nombres de estadísticas del propio objeto (`FlatHPRegenMod` del Escudo de Doran, `MovementSpeed`, `SpeedBonus`, `HealShieldPower`, `SpellVamp`); varias activas leen sus valores de otro registro (Ídolo de Malignidad 3118, Impulso cósmico 4629, Tanque químico turbo 6664, el `Cooldown` de 2501 y `BindCooldown` de 3050); y tres valores no están en el registro (Espada de Doran: `HealMultiplier`, `HealingReduction`; Daga dentada: `Effect1Amount`; Carcaj del mediodía: `MinionDamage`).
- **Valores sin cantidad:** 22 objetos tienen alguno (por ejemplo, `AvatarMonsterDR` de los compañeros de la jungla). Ninguno se usa en un texto salvo 2 marcadores.

## Límites

- Los valores dicen **cuánto**; **cómo** se aplican está en los scripts del juego, que no se leen. Cada efecto del catálogo sigue necesitando un modelo curado. Este archivo es su fuente de cifras, no el modelo.
- Solo es_ES. Los textos de otros idiomas tienen los mismos marcadores.
- Las claves de modo sin nombre y los hashes de los árboles no se interpretan.
- Al cambiar de parche hay que regenerarlo desde el cliente; `validate` falla si su versión no coincide con la del snapshot.
