# Kits de campeones: oleada 2 (`CH-01`) — fase 47

- **Objetivo:** ampliar la cobertura de `CH-01` con **45 nuevos campeones curados y validados** sobre el cliente `16.23` (`16.23.8406595+branch.releases-16-23.content.release`), pasando de **40 a 85 campeones con `kit.json`** (casi la mitad de los 173 del snapshot `16.23.1`).
- **Rama:** `feat/champion-kits-wave-2`, creada desde `dev` (`c0b7697`).

## Mejora de extractor/compilador

- `research/binmodel/bin2json.py` y `research/binmodel/kitgen.py`: soporte de marcadores de tooltip con prefijo de hechizo (`@spell.VexR:RDamageCalc@`), desbloqueando el nombrado de cálculos y la verificación de tipo de daño en definitiva de Vex y otros hechizos con referencias cruzadas.

## Cobertura de la oleada 2 (45 nuevos → 85 totales)

Todas las cifras y fórmulas proceden del cliente instalado `16.23` (`Derivado`, con `bin_sha256` registrado en cada `research/kits/<Id>.spec.json`) y los tipos de daño se contrastan con las etiquetas de los tooltips `es_ES`:

- **Top (11):** `Volibear`, `Sion`, `Poppy`, `Ornn`, `Kennen`, `Irelia`, `Kayle`, `Gwen`, `MonkeyKing` (Wukong), `Quinn`, `Vladimir`.
- **Jungla (10):** `XinZhao`, `Rengar`, `Skarner`, `Nunu`, `Fiddlesticks`, `Rammus`, `Gragas`, `Lillia`, `Ekko`, `LeeSin`.
- **Mid (13):** `Neeko`, `Cassiopeia`, `Fizz`, `Galio`, `Swain`, `Qiyana`, `Vex`, `Aurora`, `Velkoz`, `Talon`, `Sylas`, `Kassadin`, `Akali`.
- **Tirador (4):** `KogMaw`, `Tristana`, `Caitlyn`, `Samira`.
- **Apoyo (7):** `Maokai`, `Zyra`, `Seraphine`, `Rell`, `Rakan`, `Blitzcrank`, `TahmKench`.

Mecánicas destacadas incorporadas en esta oleada:

- **Coste de vida real desde el bin:** `Vladimir` E (`Mareas de sangre`, `cost.resource = "health"` con `ChargeHealthTooltip = 8 %` de vida máxima), aplicado en `rotation` respetando el suelo de `1` de vida (`MEC-01`).
- **Estadística pasiva de habilidad:** `KogMaw` Q (`attack_speed_bonus` `5..25 %` pasivo en la hoja).
- **Daño porcentual sobre vida máxima, actual y perdida del objetivo:** `Volibear` E, `Sion` P/W, `Poppy` Q, `Ornn` W (llamarada y Quebradizo), `Kayle` E (ejecución), `Gwen` P, `MonkeyKing` R, `XinZhao` R, `Skarner` P/Q, `Fiddlesticks` Q/W, `Gragas` W, `Lillia` P, `Ekko` W, `Galio` Q (tornado), `Qiyana` R, `Aurora` P, `KogMaw` W, `Maokai` Q, `Rell` E y `TahmKench` R.
- **Daño verdadero y dual:** `Lillia` Q borde exterior (mágico + verdadero), `Nunu` Q contra monstruos (`400..1200` verdadero), `Velkoz` P (`Deconstrucción orgánica`), `KogMaw` P (`Sorpresa de Icathia`).
- **Reactivaciones con ventana/intervalo del bin:** `MonkeyKing` R, `LeeSin` Q, `Swain` R, `Gwen` R, `Vex` R, `Aurora` Q, `Akali` E/R.

## Verificación y límites

- `tests/test_champion_kits.py` evalúa todas las habilidades, todos los casos y una rotación `--timeline` sobre los **85 kits publicados**, además de comprobaciones deterministas específicas de la oleada 2 (`Vladimir` coste de vida en E, `KogMaw` Q velocidad de ataque pasiva + W `%` vida máxima, `Lillia` Q mágico+verdadero, `Vex` R con reactivación, `Fiddlesticks` Q `%` vida actual, `Nunu` Q verdadero a monstruos, `Kayle` E ejecución por vida perdida).
- Quedan **88 campeones** pendientes para las siguientes oleadas de `CH-01`, además de los efectos no modelados declarados en `not_modelled` de cada kit y las reglas especiales de `CH-04`.
