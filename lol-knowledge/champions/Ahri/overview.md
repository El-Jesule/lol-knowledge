# Ahri — La Mujer Zorro de nueve Colas

- **Parche:** 16.23.1 (datos oficiales); cliente 16.22 para los valores derivados, sin cambios en el cliente 16.23 ([revisión 16.23](../../../research/reports/client-16.23.md))
- **Fuente:** [`data/current/champions/Ahri.json`](../../../data/current/champions/Ahri.json) (Data Dragon, `es_ES`)
- **Fecha de consulta:** 2026-11-16
- **Limitación principal:** Data Dragon no publica los valores numéricos de las habilidades. Los valores derivados del bin del cliente, marcados `Derivado`, están en [`abilities.md`](abilities.md), con su trazabilidad en [`sources.md`](sources.md). El motor los usa a través de [`kit.json`](kit.json).

## Identidad (`Oficial`)

| Campo | Valor |
|---|---|
| Id | `Ahri` |
| Nombre | Ahri |
| Título | La Mujer Zorro de nueve Colas |
| Roles | Mage, Assassin |
| Recurso | Maná |

## Estadísticas base (`Oficial`)

| Estadística | Base | Crecimiento por nivel |
|---|---|---|
| Vida | `590` | `104` |
| Maná | `418` | `25` |
| Daño de ataque | `53` | `0` |
| Velocidad de ataque | `0.668` | `2.2` |
| Armadura | `21` | `4.2` |
| Resistencia mágica | `30` | `1.3` |
| Velocidad de movimiento | `330` | — |
| Alcance de ataque | `550` | — |
| Regeneración de vida | `2.5` | `0.6` |
| Regeneración de maná | `8` | `0.8` |

Como en Zaahen, Data Dragon publica `0` de crecimiento de daño de ataque; el registro del cliente da `3` y el ratio de velocidad de ataque `0,625` ([`../../derived/champion-records.json`](../../derived/champion-records.json), `Derivado`). La hoja de estadísticas usa el valor del cliente según [`../../mechanics/known-data-issues.md`](../../mechanics/known-data-issues.md).

## Lectura del kit (`Recomendación`)

Interpretación del texto oficial, no demostrada con estadísticas:

- **Daño mágico con una parte verdadera:** la vuelta del Orbe del engaño es daño verdadero, así que parte de su daño ignora la resistencia mágica.
- **Combo de control:** Hechizar prepara el resto; la propia Data Dragon recomienda abrir con él.
- **Movilidad repetida:** Impulso espiritual se usa hasta tres veces, y los derribos de campeones dan más usos.

## Advertencias de datos (`Pendiente de verificación`)

- El crecimiento de daño de ataque `0` de Data Dragon es un hueco de datos conocido; no se sobrescribe el valor oficial en esta ficha.
- Los escalados con poder de habilidad salen de partes del bin sin `mStat` (valor por defecto de la clase). Que ese valor sea poder de habilidad está corroborado ([`../../../research/reports/ahri-kit-16.22.md`](../../../research/reports/ahri-kit-16.22.md)), pero no es un dato publicado por Riot.
