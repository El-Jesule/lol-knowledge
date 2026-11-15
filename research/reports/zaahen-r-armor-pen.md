# Zaahen — penetración de armadura de la R

- **Fecha de consulta:** 2026-11-15
- **Cliente local:** `16.22.8348910+branch.releases-16-22.content.release`
  - `zaahen.bin` (dentro de `Champions/Zaahen.wad.client`): SHA-256 `44e0d68c38fc1d715926a8d721d48321acc1b1ff08d844c9955e0fef6b70db75`
  - `Localized/Global.es_ES.wad.client`: SHA-256 `395c78cee45cca06b747947f31b9ea95967127b854d3d14e85a1fca971cbc9fd`
- **Nombres de campos y clases:** LeagueToolkit `lol-meta-classes` — `hashes/hashes.binfields.txt` y `hashes/hashes.bintypes.txt` (copias de las tablas de CommunityDragon del 2026-10-02) y los volcados de clases `dumps/16.22.8348910.json` (SHA-256 `a68527f7…`) y `dumps/16.20.8248524.json` (SHA-256 `ced98de5…`). Son fuentes de terceros, no de Riot.
- **Método:** `python -m binmodel.bindiff` y lectura del bin con `binmodel.propbin`; cadenas RST resueltas calculando XXH3-64 de cada clave truncado a 38 bits.

## Resumen

| Pregunta | Respuesta | Etiqueta |
|---|---|---|
| Valores por rango | 10 / 20 / 30 % (`ArmorPen` = `[0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6]`, índice 0 = rango 0). Sin cambios entre 16.20 y 16.22 | `Derivado` |
| Tipo | Penetración de armadura **porcentual** | `Derivado` (texto del cliente) |
| ¿Solo el golpe de la R o permanente? | **Pasiva** de la habilidad: el texto del cliente la separa de la parte «Activa» | `Derivado` (texto del cliente) |
| ¿Se pierde con la R en enfriamiento? | No, según los datos de 16.22 (`mRemoveWhenOnCooldown: false`) | `Derivado`; efecto no medido |
| ¿A qué daño se aplica? | Inferido: a todo el daño físico de Zaahen, por ser una estadística que «obtiene» | `Pendiente de verificación` |
| ¿Sobre armadura total o adicional? | El texto no dice «adicional». No hay dato del bin que lo decida | `Pendiente de verificación` |
| Orden respecto a reducciones, letalidad y otras fuentes de penetración | Regla general del motor de daño, no específica de Zaahen | `Pendiente de verificación` |

## Actualización 2026-11-15

El responsable del proyecto confirma tres cosas: la penetración es pasiva e independiente del enfriamiento; se aplica sobre la armadura total; y su orden es reducción plana → reducción porcentual → penetración porcentual → letalidad. La wiki `Armor_penetration` coincide en el orden y en la armadura total. Las filas «¿Se pierde…?», «¿Sobre armadura total…?» y «Orden…» de la tabla de arriba quedan resueltas; las reglas generales están en [`lol-knowledge/mechanics/damage-mitigation.md`](../../lol-knowledge/mechanics/damage-mitigation.md). Sigue sin medirse en partida dentro del repositorio.

## Evidencia

### 1. Texto del cliente 16.22 (`spell_zaahenr_tooltip`, es_ES)

> «Pasiva: Zaahen obtiene un `@ArmorPen*100@%` `%i:scaleAPen%` de penetración de armadura.»

El texto es idéntico al del fixture de 16.20 (`research/fixtures/zaahen_tooltips_es_es.json`). El icono `scaleAPen` es el de penetración porcentual. La parte de daño va después, bajo la etiqueta «Activa». La lista de subida de nivel muestra `ArmorPen1..3` como «Penetración de armadura» por rango.

### 2. Registro de la pasiva en el bin 16.22

`Characters/Zaahen/Spells/ZaahenRAbility/ZaahenR` → `mSpell.mSpellPassives` (hash `1632f6fc`), campo nuevo en 16.22:

```text
mSpellPassives: list[SpellPassiveData] = [
  SpellPassiveData {                                  # clase 0xd45ebe4a
    mBuff: link -> Characters/Zaahen/Spells/ZaahenRAbility/ZaahenRSpellPassive
    mRemoveWhenOnCooldown: false                      # 0x76b67bcc
    mDisplayFlags: 0                                  # 0x37a83601
  }
]
```

- La clase `SpellPassiveData` y el campo `SpellDataResource.mSpellPassives` ya existían en el volcado de 16.20. Lo nuevo es que la R de Zaahen los use. **No se sabe cómo se registraba la pasiva en 16.20**, porque esa versión no tiene este campo en los datos de Zaahen.
- Los campos de la clase que no aparecen en el bin (`RemoveOnPopCharacterData` y tres más sin nombre público) toman su valor por defecto. No se ha comprobado cuál es.

### 3. El efecto lo aplica un script

`ZaahenRSpellPassive` es un `SpellObject` con `mScriptName` y un `BuffData` **sin campos**. Ningún dato del bin enlaza ese buff con `ArmorPen`. Que el buff concede la penetración se infiere de tres cosas: el nombre, el texto «Pasiva» y que no haya otro candidato. No está demostrado.

## Protocolo de medición propuesto

Fórmula de mitigación del daño físico (regla general del juego, **no verificada en este informe**), sin letalidad ni reducciones y con armadura ≥ 0:

```text
daño = bruto × 100 / (100 + A × (1 − p))
⇒ A_ef = 100 × (bruto / daño − 1)
```

Herramienta de práctica, Zaahen sin objetos de penetración ni letalidad (y sin runas que la den), críticos imposibles:

1. **Armadura del objetivo:** a nivel 6, **antes** de subir la R, golpear con ataques básicos. Con el DA total del panel como `bruto`, `A = A_ef`.
2. **Rangos 1–3:** subir la R a nivel 6, 11 y 16, y medir de nuevo, siempre leyendo el DA total en ese momento. Cada medida da `p = 1 − A_ef / A`. Se espera 0,10 / 0,20 / 0,30.
3. **En enfriamiento:** lanzar la R y medir durante el enfriamiento. Si `p` no cambia, se confirma `mRemoveWhenOnCooldown: false`.
4. **Total frente a adicional:** contra un objetivo con armadura adicional conocida (por ejemplo, un bot en partida personalizada con un objeto de armadura), comparar con `A_total × (1 − p)` y con `A_base + A_adicional × (1 − p)`.

Límites: los números de daño son enteros, así que conviene un DA alto para reducir el error de redondeo. Si el muñeco de práctica tiene armadura 0, `p` no se puede medir con él y hay que usar un bot.
