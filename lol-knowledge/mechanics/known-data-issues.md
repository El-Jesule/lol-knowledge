# Defectos conocidos de los datos

- **Ámbito:** campos de las fuentes oficiales que se sabe que son incorrectos o incompletos y que bloquean un cálculo.
- **Registro legible por máquina:** [`../data-issues.json`](../data-issues.json). La hoja de estadísticas lo lee: un campo afectado bloquea la estadística en vez de producir un valor falso.

## Crecimiento de daño de ataque en Data Dragon 16.20.1 (`ddragon-attack-damage-growth`)

- **Hecho (`Oficial`):** `attackdamageperlevel` vale `0` para los 173 campeones de `data/current/` (comprobado el 2026-11-15).
- **Contraste (`Derivado`):** el bin del cliente trae el crecimiento real (`damagePerLevelModifiable`): 4,0 para Zaahen y entre 1,5 y 4,0 para el resto. Ver la discrepancia E.1 del [documento de continuidad](../../research/zaahen-research-handoff.md).
- **Sustitución (desde 2026-11-15):** la hoja de estadísticas usa [`../derived/champion-records.json`](../derived/champion-records.json), extraído del cliente 16.22 para los 173 campeones ([informe](../../research/reports/champion-records-16.22.md)).
  - Con el cliente y el snapshot en el mismo parche, el aporte es `Derivado`.
  - Hoy el cliente es 16.22 y el snapshot 16.20.1: el aporte es `Pendiente de verificación` y el informe lo indica.
  - Senna no trae el campo en el bin: su DA sigue bloqueado por encima del nivel 1.
- **Supuesto manual:** `--assume attackdamageperlevel=<valor>` tiene prioridad sobre la tabla y se marca `Pendiente de verificación`.
- **Cómo alinear los parches:** ejecutar `python -m lol_knowledge update` desde Windows, con red, y regenerar la tabla si el cliente cambia. Desde el entorno de Claude no se puede: Data Dragon no está en la lista de dominios permitidos.
- **Estado:** abierto. Data Dragon sigue publicando 0; la tabla derivada lo sustituye.
