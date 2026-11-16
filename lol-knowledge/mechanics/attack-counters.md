# Contadores de ataques y Vigor (Energized)

- **Ámbito:** efectos que saltan cada N ataques básicos y efectos de Vigor. Los usa `python -m lol_knowledge rotation`.
- **Parche de referencia:** cliente 16.22 y Data Dragon 16.22.1.
- **Fecha de consulta:** 2026-11-16

## Fuentes

| Id | Fuente | Qué cubre | Naturaleza |
|---|---|---|---|
| K1 | Data Dragon 16.22.1: «Cada tercer ataque…» (Verdugo de krakens, Guinsoo), «Cada quinto ataque…» (Rompecascos), «Tus ataques con vigor…» (Cañón de fuego rápido, Puñal de Statikk, Espada ciclovoltaica) | Qué ataque dispara cada efecto | Oficial de Riot |
| K2 | Cliente 16.22: [`../derived/item-effects.json`](../derived/item-effects.json) | Cifras: `AttackCount` 3 y `DamageAmount` de Kraken (150, +5 por nivel desde el 9; ×0,8 a distancia); `MaxStackDamage` de Rompecascos; `ChainDamage` de Statikk; 9 % / 7 % de vida actual y tope 200 de la Espada ciclovoltaica | `Derivado` |
| K3 | LoL Wiki, `Named_item_effect` (extracto del buscador, 2026-11-16) | Vigor: se acumula al moverse y atacar hasta un máximo; con el máximo, el siguiente ataque lo consume y gana un efecto al impactar | Fuente comunitaria secundaria |

## Regla del motor (`Calculado`; decisiones del usuario del 2026-11-16)

1. **Cada N ataques:** cada efecto cuenta los ataques básicos de la rotación **desde cero** y salta en el ataque N (el 3.º, el 6.º…). Las habilidades no cuentan. En el catálogo, un efecto `on_hit` u `on_attack` con `stacks.required` = N ≥ 2.
2. **Ventanas de tiempo:** las acumulaciones que caducan (4 s en Kraken, 10 s en Rompecascos) no se tienen en cuenta, porque las rotaciones no tienen tiempo.
3. **Vigor:** empieza **listo** (como si llegaras corriendo) y salta una vez, en el primer ataque. No se recarga dentro de la rotación: la recarga depende del movimiento, que no se modela.
4. **Galvanizado (Espada ciclovoltaica):** si una habilidad hace daño a un campeón antes del primer ataque, ella consume el Vigor.
5. **Varios objetos de Vigor:** se aplican todos, pero no está verificado si se acumulan, así que la rotación queda `Pendiente de verificación`.
6. **Impactos fantasma de Guinsoo:** cada tercer ataque repite los efectos al impactar de los objetos; se aplican porque la hoja ya supone Guinsoo con las acumulaciones al máximo.

## Objetos

| Objeto | Efecto | Estado |
|---|---|---|
| Verdugo de krakens (6672) | Cada tercer ataque: 150-200 físico según el nivel (×0,8 a distancia) | Aplicado, con el aumento por la vida que le falta al objetivo (hasta ×1,75) desde la fase 27 ([`target-health.md`](target-health.md)) |
| Hoja de furia de Guinsoo (3124) | Cada tercer ataque repite los efectos al impactar | Aplicado |
| Rompecascos (3181) | Cada quinto ataque contra campeones: 120 % del DA base + 5 % de la vida máxima (×0,7 a distancia) | Aplicado contra campeones; contra estructuras, no |
| Cañón de fuego rápido (3094) | Ataque con Vigor: 40 mágico | Aplicado |
| Espada ciclovoltaica (6699) | Ataque con Vigor: 9 % / 7 % de la vida actual del objetivo, físico (tope 200 contra súbditos y monstruos) | Aplicado; la letalidad de 4 s no |
| Puñal de Statikk (3087) | Ataque con Vigor: rayo de 60 mágico | No aplicado: no consta si el objetivo atacado lo recibe |

## Fuera de alcance

- La recarga del Vigor y cualquier ventana de tiempo.
