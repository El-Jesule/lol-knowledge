# Condiciones de uso — investigación (2026-10-18)

No es asesoramiento legal. Se registran las fuentes consultadas, lo que dicen y las dudas que quedan abiertas.

## Fuentes consultadas

| Fuente | URL | Qué se consultó |
|---|---|---|
| Riot — Legal Jibber Jabber | `https://www.riotgames.com/en/legal` | Licencia para proyectos comunitarios y uso de IP |
| Riot — General Policies | `https://developer.riotgames.com/policies/general` | Activos permitidos y requisitos de atribución |
| Riot — League of Legends API Policy | `https://developer.riotgames.com/docs/lol` | Datos estáticos y ejemplos de uso aprobado |
| Riot — Data Dragon | `https://developer.riotgames.com/docs/lol#data-dragon` | Fuente estática oficial |
| CommunityDragon | `https://communitydragon.org/` | Procedencia y declaración de política |
| CommunityDragon/Data | `https://github.com/CommunityDragon/Data` | Repositorio de datos adicionales; sin licencia SPDX declarada |
| LoL Wiki — Zaahen | `https://wiki.leagueoflegends.com/en-us/Zaahen?oldid=4050539` | Valores de contraste; licencia CC BY-SA 3.0 |

## Lo que dicen las fuentes

**Legal Jibber Jabber.** Concede una licencia «personal, non-exclusive, non-sublicenseable, non-transferable, revocable, limited» para usar, mostrar y crear obras derivadas de la IP de Riot, «strictly for noncommercial … community use», y reserva a Riot el derecho a revocar el permiso.

**General Policies.** Entre los activos que un producto puede usar figuran «Data Dragon» y la «Press Kit»; los logotipos y marcas deben limitarse a casos inevitables. Exige publicar el aviso de no afiliación.

**API Policy.** Solo se permite usar «Press Kit» y «Game-Specific static data» como activos de IP de Riot.

**CommunityDragon.** Declara: «created under Riot Games' "Legal Jibber Jabber" policy using assets owned by Riot Games. Riot Games does not endorse or sponsor this project.»

**CommunityDragon/Data.** Repositorio activo, sin licencia SPDX declarada (`license: null` en la API de GitHub). La ausencia de licencia no demuestra permiso ni prohibición.

**Wiki.** «Content on this site is licensed under CC BY-SA 3.0»; su API devolvió 403 en la consulta automatizada.

## Distinciones aplicadas en este prototipo

| Actividad | Decisión en este prototipo | Motivo |
|---|---|---|
| Consultar una fuente pública | Sí | Lectura de recursos públicamente accesibles |
| Guardar el archivo original localmente | Solo en `.cache/`, ignorado por Git | Evita redistribución; uso interno de investigación |
| Versionar el archivo original | **No** | Dudas materiales sobre redistribución de archivos del juego |
| Versionar valores derivados (recortes) | Sí, en `research/fixtures/` | Datos numéricos acotados y atribuidos; revisión legal pendiente |
| Publicar valores en la base de conocimiento | **No** | La Fase 3.5 no modifica `lol-knowledge/` ni `data/current` |
| Usar API key de Riot | **No** | No se demostró que resuelva el problema |

## Conclusión

El uso interno de investigación y la consulta de las fuentes no plantean una objeción evidente bajo la política de proyectos comunitarios no comerciales. La **redistribución de archivos originales del cliente no está autorizada de forma clara** y por eso no se versiona. La publicación de valores derivados es defendible como dato estático específico del juego dentro de la política de Riot, pero requiere atribución, aviso de no afiliación y una revisión jurídica antes de convertirse en parte permanente del producto.

## Cuestiones pendientes

1. Confirmar si los recortes de `fixtures/` cuentan como obra derivada redistribuible o si deben regenerarse localmente.
2. Confirmar si la licencia CC BY-SA 3.0 de la wiki impone obligaciones sobre valores numéricos factuales transcritos.
3. Confirmar la política de CommunityDragon sobre redistribución de sus exportaciones.
4. Documentar el aviso de no afiliación si algún día se publica el proyecto.
