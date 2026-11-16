# Hoja encantada (Spellblade)

- **Ámbito:** el golpe potenciado que siete objetos dan al primer ataque básico tras usar una habilidad. Lo usa `python -m lol_knowledge rotation`.
- **Parche de referencia:** cliente 16.22 y Data Dragon 16.22.1.
- **Fecha de consulta:** 2026-11-16

## Fuentes

| Id | Fuente | Qué cubre | Naturaleza |
|---|---|---|---|
| S1 | Data Dragon 16.22.1, descripciones de 3057, 3078, 3100, 3508, 6662, 2510 y 3877 | «Tras usar una habilidad, tu siguiente ataque inflige daño … adicional al impactar»; ninguna da la cifra | Oficial de Riot |
| S2 | Cliente 16.22: [`../derived/item-effects.json`](../derived/item-effects.json), cálculo `SpellbladeDamage` y `SpellbladeCooldown` 1,5 de cada objeto | Fórmula de cada golpe | `Derivado` |
| S3 | LoL Wiki, `Named_item_effect`, `Lich_Bane` y `Dusk_and_Dawn` (revisión 4015331), extractos del buscador consultados el 2026-11-16 | Efecto único compartido (solo cuenta una vez entre todos los objetos que lo tienen); «Limited to 1 Spellblade item»; el daño aplica robo de vida; Amanecer y anochecer vuelve a aplicar los efectos al impactar | Fuente comunitaria secundaria |

## Cifras (S2; mStat 2 con mStatFormula 1 = daño de ataque base)

| Objeto | Daño del golpe | Otros efectos |
|---|---|---|
| Brillo (3057) | 100 % del DA base, físico | — |
| Fuerza de trinidad (3078) | 200 % del DA base, físico | ¡Adelante!: velocidad de movimiento al atacar (no se aplica) |
| Perdición del liche (3100) | 75 % del DA base + 45 % del AP, mágico | +50 % de velocidad de ataque para ese ataque (no cambia una rotación sin tiempo) |
| Segador de esencia (3508) | 125 % del DA base + 50 × probabilidad de crítico, físico | Devuelve maná: 50 % del daño (no se aplica: no hay maná) |
| Guantelete de hielo (6662) | 150 % del DA base, físico | Campo de escarcha que ralentiza 2 s (no se aplica) |
| Amanecer y anochecer (2510) | 75 % del DA base + 10 % del AP, mágico | Cura 10 % del AP + 3 % de la vida adicional (no se aplica); vuelve a aplicar los efectos al impactar (S3, sí se aplica) |
| Tonada sanguina (3877) | 100 % del DA base, físico | El campeón recibe un 8 % más de daño (5 % a distancia) durante 4 s (no se aplica) |

En Segador de esencia, `mStat 8` se toma como probabilidad de crítico, como dice el nombre del valor (`CritChanceMultiplier`); con 25 % de crítico suma 12,5.

## Regla del motor (`Calculado`; decisiones del usuario del 2026-11-16)

1. **Activación automática:** una habilidad carga el siguiente ataque básico. Varias habilidades seguidas cargan un solo ataque.
2. **`attack:nospellblade`:** ese ataque no se potencia y la carga se pierde (por ejemplo, si pasaron los 10 s o la recarga no estaba lista).
3. **Recarga:** sin línea de tiempo, la recarga de 1,5 s se supone siempre lista; con `--timeline` se respeta ([`timeline.md`](timeline.md)).
4. **Un solo objeto:** dos objetos con Hoja encantada en el atacante es un error (S3: «Limited to 1 Spellblade item»).
5. **El daño del golpe** es una parte más al impactar: no se multiplica por el crítico y aplica robo de vida (S3).
6. **Amanecer y anochecer:** los efectos al impactar de los objetos se aplican otra vez en ese ataque, con etiqueta `Pendiente de verificación` porque la fuente es secundaria y el texto en español está mal traducido. El propio daño de Hoja encantada no se repite (sin verificar).
7. **Tonada sanguina:** el 8 % / 5 % no se aplica; la rotación queda `Pendiente de verificación`.

## Fuera de alcance

- La recarga real, la ventana de 10 s y el orden en el tiempo.
- La curación, el maná, las ralentizaciones y la velocidad de movimiento de estos objetos.
- Los efectos al impactar de las habilidades del campeón (no hay ninguno modelado).
