# Pruebas de mutación deterministas (`QA-02`)

Procedimiento operativo para ejecutar y mantener la verificación por mutación sobre los módulos matemáticos críticos del motor usando [`research/tools/mutation_check.py`](../../research/tools/mutation_check.py).

## 1. Principio y aislamiento (`AGENTS.md` §8–§10)

- **Cero dependencias externas:** utiliza exclusivamente el módulo estándar `ast`, `tokenize`, `subprocess` y `pytest` sobre las suites locales existentes.
- **Aislamiento total del árbol de trabajo:** copia `src/lol_knowledge/` en un directorio temporal por trabajador y ejecuta `pytest` con `PYTHONPATH` apuntando a esa copia. El árbol `src/` del repositorio nunca se modifica en disco.
- **Mutaciones atómicas aplicadas:**
  - Operadores binarios (`BinOp`): `+` ↔ `-`, `*` ↔ `/`.
  - Comparadores simples (`Compare`): `<` ↔ `<=`, `>` ↔ `>=`.
  - Constantes enteras de borde (`Constant` con `type(v) is int`, excluyendo booleanos `True`/`False`): `0` ↔ `1`.
  - Se omiten docstrings, anotaciones de tipo, claves literales de diccionario, índices estructurales de subscript y líneas marcadas con `# pragma: no mutate`.

## 2. Objetivos y umbrales mínimos

| Objetivo (`--target`) | Archivos cubiertos | Umbral mínimo |
|---|---|---|
| `damage` | `src/lol_knowledge/damage/mitigation.py` | `>= 95 %` |
| `survival` | `src/lol_knowledge/survival.py` | `>= 95 %` |
| `sheet` | Núcleo de cálculo en `src/lol_knowledge/stats/sheet.py` | `>= 90 %` |
| `tenacity` | `src/lol_knowledge/stats/registry.py`, `src/lol_knowledge/stats/metrics.py` | `>= 85 %` |
| `rotation` | `src/lol_knowledge/rotation/models.py` | `>= 85 %` |
| `defense` | `src/lol_knowledge/defense/cc_negations.py` | `>= 85 %` |

## 3. Comandos habituales

```powershell
# Muestra determinista para validación rápida / CI (24 mutantes repartidos)
.\.venv\Scripts\python.exe research\tools\mutation_check.py --ci-sample

# Evaluación exhaustiva de un objetivo concreto
.\.venv\Scripts\python.exe research\tools\mutation_check.py --target damage
.\.venv\Scripts\python.exe research\tools\mutation_check.py --target survival
.\.venv\Scripts\python.exe research\tools\mutation_check.py --target sheet

# Listar objetivos, recuento de mutantes y suites asociadas sin ejecutar
.\.venv\Scripts\python.exe research\tools\mutation_check.py --list

# Salida en JSON
.\.venv\Scripts\python.exe research\tools\mutation_check.py --ci-sample --json
```

## 4. Criterio ante mutantes supervivientes

1. Inspeccionar la línea y el cambio reportados (`SURVIVED <archivo>:<línea>: <cambio>`).
2. Si el mutante cambia el comportamiento observable en casos límite, comparaciones de borde (`<` vs `<=`) o constantes (`0` vs `1`), añadir un test unitario específico en `tests/` (por ejemplo en [`tests/test_mutation_hardening.py`](../../tests/test_mutation_hardening.py)) que falle bajo el mutante y pase con el código correcto.
3. Solo se permite `# pragma: no mutate` cuando el mutante es **matemáticamente equivalente** en todo dominio posible (por ejemplo, una comprobación de ruta rápida cuya rama alternativa calcula exactamente el mismo resultado, nunca para ocultar cobertura faltante).
