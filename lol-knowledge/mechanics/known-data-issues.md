# Defectos conocidos de los datos

- **Ámbito:** campos de las fuentes oficiales que se sabe que son incorrectos o incompletos y que bloquean un cálculo.
- **Registro legible por máquina:** [`../data-issues.json`](../data-issues.json). La hoja de estadísticas lo lee: un campo afectado bloquea la estadística en vez de producir un valor falso.

## Crecimiento de daño de ataque en Data Dragon 16.20.1 (`ddragon-attack-damage-growth`)

- **Hecho (`Oficial`):** `attackdamageperlevel` vale `0` para los 173 campeones de `data/current/` (comprobado el 2026-11-15).
- **Contraste (`Derivado`):** el bin del cliente de Zaahen da 4,0 (`damagePerLevelModifiable`). Ver la discrepancia E.1 del [documento de continuidad](../../research/zaahen-research-handoff.md).
- **Efecto:** el daño de ataque solo se calcula a nivel 1. A partir del nivel 2 la estadística queda bloqueada.
- **Cómo desbloquear un cálculo:** indicar el crecimiento con `--assume attackdamageperlevel=<valor>`. El aporte se marca `Pendiente de verificación` y esa etiqueta se propaga al resultado.
- **Estado:** abierto. Se cerrará cuando haya una fuente fiable del crecimiento por campeón.
