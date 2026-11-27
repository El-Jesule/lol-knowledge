"""Tests for the stdlib AST mutation-testing tool (``research/tools/mutation_check.py``)."""

from __future__ import annotations

import sys
from pathlib import Path

TOOLS_DIR = Path(__file__).resolve().parents[1] / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

import mutation_check as mc  # noqa: E402


def test_generate_mutants_operators_and_skips(tmp_path: Path) -> None:
    sample = tmp_path / "sample.py"
    sample.write_text(
        '''"""Module docstring should not mutate: 0 and 1."""

FLAG: bool = True
LIMIT: int = 1  # annotation value should still be skipped? No, AnnAssign value mutates, type skips.

def calc(x: int, limit: int = 0) -> int:
    """Function docstring with 0 and 1."""
    if x < 10 and not False:
        y = x + 1
    elif x >= 0:
        y = x * 2
    else:
        y = x - 0  # pragma: no mutate
    data = {"k0": 0, 1: y}
    return data["k0"] + y
''',
        encoding="utf-8",
    )

    mutants = mc.generate_mutants(sample, file_rel="sample.py")
    changes = {(m.lineno, m.kind, m.description) for m in mutants}

    # BinOp and Compare mutations are emitted.
    assert (8, "compare", "< -> <=") in changes
    assert (9, "binop", "+ -> -") in changes
    assert (10, "compare", ">= -> >") in changes
    assert (11, "binop", "* -> /") in changes
    # 0/1 constants mutate; booleans, docstrings, dict keys, slices, and pragmas do not.
    assert (6, "constant", "0 -> 1") in changes
    assert (9, "constant", "1 -> 0") in changes
    assert (10, "constant", "0 -> 1") in changes
    assert not any(m.lineno in (1, 7) for m in mutants)
    assert not any(m.lineno == 13 for m in mutants)
    assert not any(m.original in ("True", "False") for m in mutants)
    # Dict literal key `1` and subscript slice `"k0"` are structural and skipped; value `0` mutates.
    assert (14, "constant", "0 -> 1") in changes
    assert (14, "constant", "1 -> 0") not in changes


def test_strided_sample_and_budget_allocation() -> None:
    mutants = [mc.Mutant("a.py", i, 0, 0, 1, "0", "1", "constant", f"m{i}") for i in range(10)]
    assert mc.strided_sample(mutants, 0) == []
    assert mc.strided_sample(mutants, 20) == mutants
    sampled = mc.strided_sample(mutants, 4)
    assert [m.description for m in sampled] == ["m0", "m2", "m5", "m7"]
    assert mc.strided_sample(mutants, 4) == sampled

    assert mc._allocate_sample_counts([25, 42, 56], 24) == [8, 8, 8]
    assert mc._allocate_sample_counts([2, 10, 20], 24) == [2, 10, 12]


def test_evaluate_mutants_in_isolated_temp_workspace(tmp_path: Path) -> None:
    src_root = tmp_path / "src"
    pkg_dir = src_root / "mini_pkg"
    pkg_dir.mkdir(parents=True)
    (pkg_dir / "__init__.py").write_text("", encoding="utf-8")
    mod_path = pkg_dir / "math_ops.py"
    original_src = (
        "def add_positive(a: int, b: int) -> int:\n"
        "    if a > 0:\n"
        "        return a + b\n"
        "    return b\n"
    )
    mod_path.write_text(original_src, encoding="utf-8")

    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    test_file = tests_dir / "test_math_ops.py"
    test_file.write_text(
        "from mini_pkg.math_ops import add_positive\n\n"
        "def test_add_positive() -> None:\n"
        "    assert add_positive(1, 3) == 4\n"
        "    assert add_positive(0, 3) == 3\n",
        encoding="utf-8",
    )

    mutants = mc.generate_mutants(mod_path, file_rel="src/mini_pkg/math_ops.py")
    # Expect: `>` -> `>=` survives (a=0 -> 0+3 == 3), `0` -> `1` and `+` -> `-` are killed.
    baseline_ok, outcomes = mc.evaluate_mutants(
        mutants,
        tests=("tests/test_math_ops.py",),
        repo_root=tmp_path,
        src_root=src_root,
        timeout=15,
        workers=1,
        verify_baseline=True,
    )
    assert baseline_ok is True
    assert mod_path.read_text(encoding="utf-8") == original_src

    by_desc = {o.mutant.description: o.status for o in outcomes}
    assert by_desc["+ -> -"] == "killed"
    assert by_desc["0 -> 1"] == "killed"
    assert by_desc["> -> >="] == "survived"
