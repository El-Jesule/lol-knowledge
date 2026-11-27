"""AST-based mutation testing tool for critical calculation modules (QA-02).

Copies the source package into isolated per-worker temporary workspaces so the
repository ``src/`` tree is never modified on disk, applies one atomic AST
mutation at a time, and runs each target's pytest suite with ``PYTHONPATH``
pointed at the temporary copy.
"""

from __future__ import annotations

import argparse
import ast
import concurrent.futures
import io
import json
import os
import queue
import shutil
import subprocess
import sys
import tempfile
import time
import tokenize
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SRC_ROOT = REPO_ROOT / "src"
DEFAULT_CI_SAMPLE_TOTAL = 24
DEFAULT_TIMEOUT = 15

_BINOP_SWAPS: dict[type[ast.operator], tuple[str, str]] = {
    ast.Add: ("+", "-"),
    ast.Sub: ("-", "+"),
    ast.Mult: ("*", "/"),
    ast.Div: ("/", "*"),
}

_CMPOP_SWAPS: dict[type[ast.cmpop], tuple[str, str]] = {
    ast.Lt: ("<", "<="),
    ast.LtE: ("<=", "<"),
    ast.Gt: (">", ">="),
    ast.GtE: (">=", ">"),
}


@dataclass(frozen=True)
class TargetSpec:
    """Configuration for a mutation-testing target."""

    name: str
    files: tuple[str, ...]
    tests: tuple[str, ...]
    min_score: float
    symbols: tuple[str, ...] | None = None


TARGETS: dict[str, TargetSpec] = {
    "damage": TargetSpec(
        name="damage",
        files=("src/lol_knowledge/damage/mitigation.py",),
        tests=("tests/test_damage_mitigation.py", "tests/test_mutation_hardening.py"),
        min_score=0.95,
    ),
    "survival": TargetSpec(
        name="survival",
        files=("src/lol_knowledge/survival.py",),
        tests=(
            "tests/test_survival.py",
            "tests/test_defense.py",
            "tests/test_mutation_hardening.py",
        ),
        min_score=0.95,
    ),
    "sheet": TargetSpec(
        name="sheet",
        files=("src/lol_knowledge/stats/sheet.py",),
        symbols=(
            "adaptive_stat",
            "StatValue",
            "_percent_amount",
            "_amplified",
            "_scaled_attack_speed",
            "_crit_chance_passive",
            "_apply_cassiopeia_move_speed_passive",
            "_resolve_move_speed",
            "_apply_ms_conversions",
        ),
        tests=(
            "tests/test_stats_sheet.py",
            "tests/test_stats_move_speed.py",
            "tests/test_stats_attack_speed.py",
            "tests/test_stats_crit_chance.py",
            "tests/test_stats_tenacity.py",
            "tests/test_stats_regeneration.py",
            "tests/test_stats_vamp.py",
            "tests/test_mutation_hardening.py",
        ),
        min_score=0.90,
    ),
    "tenacity": TargetSpec(
        name="tenacity",
        files=(
            "src/lol_knowledge/stats/registry.py",
            "src/lol_knowledge/stats/metrics.py",
        ),
        tests=(
            "tests/test_stats_registry.py",
            "tests/test_stats_metrics.py",
            "tests/test_stats_move_speed.py",
            "tests/test_stats_tenacity.py",
            "tests/test_mutation_hardening.py",
        ),
        min_score=0.85,
    ),
    "rotation": TargetSpec(
        name="rotation",
        files=("src/lol_knowledge/rotation/models.py",),
        tests=(
            "tests/test_rotation.py",
            "tests/test_rotation_timeline_windows.py",
            "tests/test_perf_memoization.py",
            "tests/test_mutation_hardening.py",
        ),
        min_score=0.85,
    ),
    "defense": TargetSpec(
        name="defense",
        files=("src/lol_knowledge/defense/cc_negations.py",),
        tests=(
            "tests/test_defense.py",
            "tests/test_duel.py",
            "tests/test_mutation_hardening.py",
        ),
        min_score=0.85,
    ),
}


@dataclass(frozen=True)
class Mutant:
    """One atomic source-level mutation."""

    file_rel: str
    lineno: int
    col_offset: int
    start_byte: int
    end_byte: int
    original: str
    mutated: str
    kind: str
    description: str

    def apply_bytes(self, source_bytes: bytes) -> bytes:
        return (
            source_bytes[: self.start_byte]
            + self.mutated.encode("utf-8")
            + source_bytes[self.end_byte :]
        )


@dataclass(frozen=True)
class MutantOutcome:
    """Execution result for one mutant."""

    mutant: Mutant
    status: str  # "killed", "survived", "timed_out"
    duration_s: float


@dataclass(frozen=True)
class TargetReport:
    """Aggregated mutation score for one target."""

    target: str
    files: tuple[str, ...]
    tests: tuple[str, ...]
    min_score: float
    total_generated: int
    evaluated: int
    killed: int
    timed_out: int
    survived: int
    score: float
    passed: bool
    survivors: tuple[dict[str, Any], ...]
    baseline_ok: bool = True


def _line_byte_starts(source_bytes: bytes) -> list[int]:
    starts: list[int] = [0]
    offset = 0
    for line in source_bytes.splitlines(keepends=True):
        offset += len(line)
        starts.append(offset)
    return starts


def _tokenize_ops(source_bytes: bytes, line_starts: list[int]) -> list[tuple[int, int, str]]:
    tokens: list[tuple[int, int, str]] = []
    for tok in tokenize.tokenize(io.BytesIO(source_bytes).readline):
        if tok.type != tokenize.OP:
            continue
        sline, scol = tok.start
        eline, ecol = tok.end
        if sline < 1 or sline > len(line_starts) - 1:
            continue
        line_str = tok.line
        b_start = line_starts[sline - 1] + len(line_str[:scol].encode("utf-8"))
        b_end = line_starts[eline - 1] + len(line_str[:ecol].encode("utf-8"))
        tokens.append((b_start, b_end, tok.string))
    return tokens


def _find_op_span(
    op_tokens: list[tuple[int, int, str]],
    left_end_byte: int,
    right_start_byte: int,
    expected_op: str,
) -> tuple[int, int] | None:
    for b_start, b_end, tok_str in op_tokens:
        if b_start >= left_end_byte and b_end <= right_start_byte and tok_str == expected_op:
            return b_start, b_end
    return None


def _is_structural_slice(node: ast.AST) -> bool:
    if isinstance(node, (ast.Constant, ast.Slice)):
        return True
    if isinstance(node, ast.Tuple):
        return all(_is_structural_slice(elt) for elt in node.elts)
    return False


class _MutantCollector(ast.NodeVisitor):
    """Collect atomic AST mutants while skipping annotations, docstrings, and pragmas."""

    def __init__(
        self,
        *,
        file_rel: str,
        source_text: str,
        source_bytes: bytes,
        symbols: frozenset[str] | None,
    ) -> None:
        self.file_rel = file_rel
        self.lines = source_text.splitlines()
        self.source_bytes = source_bytes
        self.line_starts = _line_byte_starts(source_bytes)
        self.op_tokens = _tokenize_ops(source_bytes, self.line_starts)
        self.symbols = symbols
        self._in_selected_symbol = symbols is None
        self.mutants: list[Mutant] = []

    def _byte_pos(self, lineno: int, col_offset: int) -> int:
        return self.line_starts[lineno - 1] + col_offset

    def _has_no_mutate(self, start_line: int, end_line: int | None) -> bool:
        stop = end_line if end_line is not None else start_line
        for ln in range(start_line, stop + 1):
            if 1 <= ln <= len(self.lines) and "# pragma: no mutate" in self.lines[ln - 1]:
                return True
        return False

    def visit_Module(self, node: ast.Module) -> None:
        for stmt in node.body:
            if self.symbols is None:
                self.visit(stmt)
                continue
            if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and (
                stmt.name in self.symbols
            ):
                prev = self._in_selected_symbol
                self._in_selected_symbol = True
                try:
                    self.visit(stmt)
                finally:
                    self._in_selected_symbol = prev

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        if not self._in_selected_symbol:
            return
        for dec in node.decorator_list:
            self.visit(dec)
        for default in node.args.defaults:
            self.visit(default)
        for default in node.args.kw_defaults:
            if default is not None:
                self.visit(default)
        for stmt in node.body:
            self.visit(stmt)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        if not self._in_selected_symbol:
            return
        for dec in node.decorator_list:
            self.visit(dec)
        for default in node.args.defaults:
            self.visit(default)
        for default in node.args.kw_defaults:
            if default is not None:
                self.visit(default)
        for stmt in node.body:
            self.visit(stmt)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        self.visit(node.target)
        if node.value is not None:
            self.visit(node.value)

    def visit_TypeAlias(self, node: ast.TypeAlias) -> None:
        return

    def visit_Expr(self, node: ast.Expr) -> None:
        if isinstance(node.value, ast.Constant):
            return
        self.visit(node.value)

    def visit_Subscript(self, node: ast.Subscript) -> None:
        self.visit(node.value)
        if not _is_structural_slice(node.slice):
            self.visit(node.slice)

    def visit_Dict(self, node: ast.Dict) -> None:
        for key in node.keys:
            if key is not None and not isinstance(key, ast.Constant):
                self.visit(key)
        for value in node.values:
            self.visit(value)

    def visit_BinOp(self, node: ast.BinOp) -> None:
        self.generic_visit(node)
        swap = _BINOP_SWAPS.get(type(node.op))
        if swap is None:
            return
        if self._has_no_mutate(node.lineno, node.end_lineno):
            return
        if node.left.end_lineno is None or node.left.end_col_offset is None:
            return
        left_end = self._byte_pos(node.left.end_lineno, node.left.end_col_offset)
        right_start = self._byte_pos(node.right.lineno, node.right.col_offset)
        orig_op, mut_op = swap
        span = _find_op_span(self.op_tokens, left_end, right_start, orig_op)
        if span is None:
            return
        self.mutants.append(
            Mutant(
                file_rel=self.file_rel,
                lineno=node.lineno,
                col_offset=node.col_offset,
                start_byte=span[0],
                end_byte=span[1],
                original=orig_op,
                mutated=mut_op,
                kind="binop",
                description=f"{orig_op} -> {mut_op}",
            )
        )

    def visit_Compare(self, node: ast.Compare) -> None:
        self.generic_visit(node)
        if len(node.ops) != 1 or len(node.comparators) != 1:
            return
        swap = _CMPOP_SWAPS.get(type(node.ops[0]))
        if swap is None:
            return
        if self._has_no_mutate(node.lineno, node.end_lineno):
            return
        if node.left.end_lineno is None or node.left.end_col_offset is None:
            return
        left_end = self._byte_pos(node.left.end_lineno, node.left.end_col_offset)
        right = node.comparators[0]
        right_start = self._byte_pos(right.lineno, right.col_offset)
        orig_op, mut_op = swap
        span = _find_op_span(self.op_tokens, left_end, right_start, orig_op)
        if span is None:
            return
        self.mutants.append(
            Mutant(
                file_rel=self.file_rel,
                lineno=node.lineno,
                col_offset=node.col_offset,
                start_byte=span[0],
                end_byte=span[1],
                original=orig_op,
                mutated=mut_op,
                kind="compare",
                description=f"{orig_op} -> {mut_op}",
            )
        )

    def visit_Constant(self, node: ast.Constant) -> None:
        if type(node.value) is not int or node.value not in (0, 1):
            return
        if self._has_no_mutate(node.lineno, node.end_lineno):
            return
        if node.end_lineno is None or node.end_col_offset is None:
            return
        b_start = self._byte_pos(node.lineno, node.col_offset)
        b_end = self._byte_pos(node.end_lineno, node.end_col_offset)
        orig = self.source_bytes[b_start:b_end].decode("utf-8")
        mutated = "1" if node.value == 0 else "0"
        self.mutants.append(
            Mutant(
                file_rel=self.file_rel,
                lineno=node.lineno,
                col_offset=node.col_offset,
                start_byte=b_start,
                end_byte=b_end,
                original=orig,
                mutated=mutated,
                kind="constant",
                description=f"{orig} -> {mutated}",
            )
        )


def generate_mutants(
    source_path: Path,
    *,
    file_rel: str | None = None,
    symbols: tuple[str, ...] | None = None,
) -> list[Mutant]:
    """Generate all atomic AST mutants for ``source_path``."""
    source_bytes = source_path.read_bytes()
    source_text = source_bytes.decode("utf-8")
    tree = ast.parse(source_bytes, filename=str(source_path))
    rel = file_rel if file_rel is not None else source_path.as_posix()
    collector = _MutantCollector(
        file_rel=rel,
        source_text=source_text,
        source_bytes=source_bytes,
        symbols=frozenset(symbols) if symbols is not None else None,
    )
    collector.visit(tree)
    return collector.mutants


def strided_sample(mutants: list[Mutant], max_count: int) -> list[Mutant]:
    """Deterministically pick up to ``max_count`` evenly spaced mutants."""
    if max_count <= 0:
        return []
    total = len(mutants)
    if total <= max_count:
        return list(mutants)
    return [mutants[(i * total) // max_count] for i in range(max_count)]


def _existing_tests(repo_root: Path, tests: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(t for t in tests if (repo_root / t).is_file())


def _run_pytest_in_workspace(
    *,
    temp_src: Path,
    repo_root: Path,
    tests: tuple[str, ...],
    timeout: int,
) -> tuple[str, float]:
    env = os.environ.copy()
    prev_pp = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = f"{temp_src}{os.pathsep}{prev_pp}" if prev_pp else str(temp_src)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    cmd = [
        sys.executable,
        "-m",
        "pytest",
        *tests,
        "-q",
        "-x",
        "--no-header",
        "--tb=no",
        "-o",
        f"pythonpath={temp_src}",
    ]
    t0 = time.perf_counter()
    try:
        proc = subprocess.run(
            cmd,
            cwd=repo_root,
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return "timed_out", time.perf_counter() - t0
    elapsed = time.perf_counter() - t0
    return ("survived" if proc.returncode == 0 else "killed"), elapsed


def evaluate_mutants(
    mutants: list[Mutant],
    *,
    tests: tuple[str, ...],
    repo_root: Path = REPO_ROOT,
    src_root: Path = DEFAULT_SRC_ROOT,
    timeout: int = DEFAULT_TIMEOUT,
    workers: int = 1,
    verify_baseline: bool = True,
) -> tuple[bool, list[MutantOutcome]]:
    """Run ``mutants`` in isolated temp copies of ``src_root`` without touching ``src_root``."""
    if not mutants or not tests:
        return True, []
    worker_count = max(1, min(workers, len(mutants)))
    src_rel_base = src_root.relative_to(repo_root) if src_root.is_relative_to(repo_root) else None
    workspaces: list[tuple[tempfile.TemporaryDirectory[str], Path]] = []
    ws_queue: queue.Queue[Path] = queue.Queue()

    def _rel_inside_src(file_rel: str) -> Path:
        p = Path(file_rel)
        if src_rel_base is not None and p.is_relative_to(src_rel_base):
            return p.relative_to(src_rel_base)
        if p.parts and p.parts[0] == src_root.name:
            return Path(*p.parts[1:])
        return p

    try:
        for _ in range(worker_count):
            tmp_dir = tempfile.TemporaryDirectory(prefix="lol_mut_")
            tmp_src = Path(tmp_dir.name) / "src"
            shutil.copytree(src_root, tmp_src)
            workspaces.append((tmp_dir, tmp_src))
            ws_queue.put(tmp_src)

        if verify_baseline:
            base_ws = workspaces[0][1]
            base_status, _ = _run_pytest_in_workspace(
                temp_src=base_ws,
                repo_root=repo_root,
                tests=tests,
                timeout=max(timeout * 2, 30),
            )
            if base_status != "survived":
                return False, []

        def _eval_one(mutant: Mutant) -> MutantOutcome:
            ws = ws_queue.get()
            target_file = ws / _rel_inside_src(mutant.file_rel)
            orig_bytes = target_file.read_bytes()
            try:
                target_file.write_bytes(mutant.apply_bytes(orig_bytes))
                status, elapsed = _run_pytest_in_workspace(
                    temp_src=ws,
                    repo_root=repo_root,
                    tests=tests,
                    timeout=timeout,
                )
                return MutantOutcome(mutant=mutant, status=status, duration_s=elapsed)
            finally:
                target_file.write_bytes(orig_bytes)
                ws_queue.put(ws)

        if worker_count == 1:
            outcomes = [_eval_one(m) for m in mutants]
        else:
            with concurrent.futures.ThreadPoolExecutor(max_workers=worker_count) as pool:
                outcomes = list(pool.map(_eval_one, mutants))
        return True, outcomes
    finally:
        for tmp_dir, _ in workspaces:
            tmp_dir.cleanup()


def _select_targets(target_arg: str) -> list[TargetSpec]:
    if target_arg == "all":
        return list(TARGETS.values())
    names = [part.strip() for part in target_arg.split(",") if part.strip()]
    unknown = [name for name in names if name not in TARGETS]
    if unknown:
        valid = ", ".join(["all", *TARGETS])
        raise ValueError(f"unknown target(s): {', '.join(unknown)} (expected one of: {valid})")
    return [TARGETS[name] for name in names]


def _allocate_sample_counts(counts: list[int], total_budget: int) -> list[int]:
    if sum(counts) <= total_budget:
        return list(counts)
    n_targets = len(counts)
    if n_targets == 0:
        return []
    alloc = [0] * n_targets
    remaining = total_budget
    base = max(1, total_budget // n_targets)
    for idx, cnt in enumerate(counts):
        take = min(cnt, base, remaining)
        alloc[idx] = take
        remaining -= take
    idx = 0
    while remaining > 0 and any(alloc[i] < counts[i] for i in range(n_targets)):
        if alloc[idx] < counts[idx]:
            alloc[idx] += 1
            remaining -= 1
        idx = (idx + 1) % n_targets
    return alloc


def run_targets(
    target_arg: str = "all",
    *,
    ci_sample: bool = False,
    sample_size: int | None = None,
    timeout: int = DEFAULT_TIMEOUT,
    workers: int = 1,
    full_file: bool = False,
    repo_root: Path = REPO_ROOT,
) -> tuple[bool, list[TargetReport]]:
    """Run mutation checks across selected targets and return ``(all_passed, reports)``."""
    specs = _select_targets(target_arg)
    generated_per_target: list[list[Mutant]] = []
    tests_per_target: list[tuple[str, ...]] = []
    for spec in specs:
        syms = None if full_file else spec.symbols
        mutants: list[Mutant] = []
        for file_rel in spec.files:
            path = repo_root / file_rel
            if path.is_file():
                mutants.extend(generate_mutants(path, file_rel=file_rel, symbols=syms))
        generated_per_target.append(mutants)
        tests_per_target.append(_existing_tests(repo_root, spec.tests))

    budget: int | None = sample_size
    if ci_sample and budget is None:
        budget = DEFAULT_CI_SAMPLE_TOTAL
    if budget is not None:
        allocs = _allocate_sample_counts([len(m) for m in generated_per_target], budget)
    else:
        allocs = [len(m) for m in generated_per_target]

    reports: list[TargetReport] = []
    all_passed = True
    for spec, all_mutants, tests, take in zip(
        specs, generated_per_target, tests_per_target, allocs, strict=True
    ):
        chosen = strided_sample(all_mutants, take)
        baseline_ok, outcomes = evaluate_mutants(
            chosen,
            tests=tests,
            repo_root=repo_root,
            src_root=repo_root / "src",
            timeout=timeout,
            workers=workers,
            verify_baseline=True,
        )
        killed = sum(1 for o in outcomes if o.status == "killed")
        timed_out = sum(1 for o in outcomes if o.status == "timed_out")
        survived = sum(1 for o in outcomes if o.status == "survived")
        evaluated = len(outcomes)
        score = (killed + timed_out) / evaluated if evaluated > 0 else 0.0
        passed = baseline_ok and evaluated > 0 and score >= spec.min_score
        if not passed:
            all_passed = False
        survivors = tuple(
            {
                "file": o.mutant.file_rel,
                "line": o.mutant.lineno,
                "kind": o.mutant.kind,
                "change": o.mutant.description,
            }
            for o in outcomes
            if o.status == "survived"
        )
        reports.append(
            TargetReport(
                target=spec.name,
                files=spec.files,
                tests=tests,
                min_score=spec.min_score,
                total_generated=len(all_mutants),
                evaluated=evaluated,
                killed=killed,
                timed_out=timed_out,
                survived=survived,
                score=score,
                passed=passed,
                survivors=survivors,
                baseline_ok=baseline_ok,
            )
        )
    if sum(r.evaluated for r in reports) == 0:
        all_passed = False
    return all_passed, reports


def _build_parser() -> argparse.ArgumentParser:
    default_workers = min(4, os.cpu_count() or 1)
    parser = argparse.ArgumentParser(
        description="AST mutation checker for LoL-Knowledge calculation modules (QA-02)."
    )
    parser.add_argument(
        "--target",
        default="all",
        help="Target name, comma-separated target names, or 'all' (default: all).",
    )
    parser.add_argument(
        "--ci-sample",
        action="store_true",
        help=f"Run a deterministic strided sample (default {DEFAULT_CI_SAMPLE_TOTAL} mutants).",
    )
    parser.add_argument(
        "--sample-size",
        type=int,
        default=None,
        help="Override total deterministic sample size across selected targets.",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=DEFAULT_TIMEOUT,
        help=f"Per-mutant pytest timeout in seconds (default: {DEFAULT_TIMEOUT}).",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=default_workers,
        help=f"Parallel temp-workspace workers (default: {default_workers}).",
    )
    parser.add_argument(
        "--full-file",
        action="store_true",
        help="Mutate entire files even when a target defines a core symbol subset.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="as_json",
        help="Emit machine-readable JSON summary.",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        dest="list_targets",
        help="List available targets, existing test files, and mutant counts without executing.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        specs = _select_targets(args.target)
    except ValueError as exc:
        parser.error(str(exc))

    if args.list_targets:
        listing = []
        for spec in specs:
            syms = None if args.full_file else spec.symbols
            total = sum(
                len(generate_mutants(REPO_ROOT / f, file_rel=f, symbols=syms))
                for f in spec.files
                if (REPO_ROOT / f).is_file()
            )
            tests = _existing_tests(REPO_ROOT, spec.tests)
            listing.append(
                {
                    "target": spec.name,
                    "files": list(spec.files),
                    "tests": list(tests),
                    "min_score": spec.min_score,
                    "mutants": total,
                }
            )
        if args.as_json:
            print(json.dumps({"targets": listing}, indent=2))
        else:
            for item in listing:
                print(
                    f"{item['target']}: mutants={item['mutants']}, "
                    f"min_score={item['min_score']:.0%}, tests={len(item['tests'])}"
                )
        return 0

    all_passed, reports = run_targets(
        args.target,
        ci_sample=args.ci_sample,
        sample_size=args.sample_size,
        timeout=args.timeout,
        workers=args.workers,
        full_file=args.full_file,
    )
    total_eval = sum(r.evaluated for r in reports)
    total_killed = sum(r.killed + r.timed_out for r in reports)
    overall_score = total_killed / total_eval if total_eval else 0.0

    if args.as_json:
        payload = {
            "passed": all_passed,
            "total_evaluated": total_eval,
            "total_killed": total_killed,
            "overall_score": round(overall_score, 4),
            "targets": [asdict(r) for r in reports],
        }
        print(json.dumps(payload, indent=2))
    else:
        for r in reports:
            status = "PASS" if r.passed else "FAIL"
            base_note = "" if r.baseline_ok else " [BASELINE FAILED]"
            print(
                f"[{status}] {r.target}: {r.killed + r.timed_out}/{r.evaluated} "
                f"({r.score:.1%}, min {r.min_score:.0%}, generated={r.total_generated}, "
                f"timed_out={r.timed_out}, survived={r.survived}){base_note}"
            )
            for surv in r.survivors:
                print(
                    f"  SURVIVED {surv['file']}:{surv['line']} ({surv['kind']}): {surv['change']}"
                )
        print(f"Overall: {total_killed}/{total_eval} ({overall_score:.1%})")
    return 0 if all_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
