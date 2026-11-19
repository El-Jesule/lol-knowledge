# Defectos conocidos de los datos

- **Ámbito:** campos de las fuentes oficiales que se sabe que son incorrectos o incompletos y que bloquean un cálculo.
- **Registro legible por máquina:** [`../data-issues.json`](../data-issues.json). La hoja de estadísticas lo lee: un campo afectado no se usa.
- **Cada defecto lista los parches en los que se ha comprobado.** Si el snapshot pasa a un parche que no está en la lista, `validate` falla hasta que alguien lo vuelva a comprobar y añada el parche, o lo marque resuelto. Así un defecto no caduca en silencio al cambiar de parche.

## Crecimiento de daño de ataque en Data Dragon (`ddragon-attack-damage-growth`)

- **Hecho (`Oficial`):** `attackdamageperlevel` vale `0` para los 173 campeones en Data Dragon 16.20.1, 16.22.1 y 16.23.1 (comprobado el 2026-11-15 en los dos primeros y el 2026-11-19 en 16.23.1).
- **Contraste (`Derivado`):** el bin del cliente trae el crecimiento real (`damagePerLevelModifiable`): 4,0 para Zaahen y entre 1,5 y 4,0 para el resto. Ver la discrepancia E.1 del [documento de continuidad](../../research/zaahen-research-handoff.md).
- **Sustitución (desde 2026-11-15):** la hoja de estadísticas usa [`../derived/champion-records.json`](../derived/champion-records.json), extraído del cliente para los 173 campeones (16.22: [informe](../../research/reports/champion-records-16.22.md); regenerado con el cliente 16.23 el 2026-11-19: [revisión](../../research/reports/client-16.23.md)).
  - Con el cliente y el snapshot en el mismo parche, el aporte es `Derivado`.
  - Hoy cliente y snapshot son 16.23 (registros regenerados el 2026-11-19): el aporte es `Derivado`.
  - Senna no trae el campo en el bin: su DA sigue bloqueado por encima del nivel 1.
- **Supuesto manual:** `--assume attackdamageperlevel=<valor>` tiene prioridad sobre la tabla y se marca `Pendiente de verificación`.
- **Cómo alinear los parches:** ejecutar `python -m lol_knowledge update --patch <parche>` desde Windows, con red, y regenerar la tabla con `binmodel.records` cuando cambie el cliente. Desde el entorno de Claude no se puede: Data Dragon no está en la lista de dominios permitidos.
- **Estado:** abierto. Data Dragon sigue publicando 0; la tabla derivada lo sustituye.
