"""Deterministic evaluation of the object formula subset.

Supported operations: ``constant``, ``stat``, ``percent_of``, ``add``, ``mul``,
``min`` and ``by_holder_range``. ``unknown`` means the data is absent;
``unsupported`` means the mechanic is not modelled. Neither is ever replaced by
zero. ``by_holder_range`` needs an explicit ``melee``/``ranged`` holder; a
missing value is an error, not a default.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from .schema import (
    FORMULA_OPS,
    MAX_FORMULA_DEPTH,
    STAT_SCOPES,
    STAT_SCOPES_BY_STAT,
    STAT_SUBJECTS,
)


class FormulaError(Exception):
    """A formula cannot be evaluated without inventing data."""

    def __init__(self, message: str, *, code: str, node: Any = None) -> None:
        super().__init__(message)
        self.code = code
        self.node = node


@dataclass(frozen=True)
class FormulaResult:
    """One evaluated formula and the stats it read."""

    value: float
    dependencies: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return {"value": self.value, "dependencies": list(self.dependencies)}


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


_ALLOWED_FORMULA_KEYS = {
    "constant": {"op", "value"},
    "stat": {"op", "stat", "scope", "subject"},
    "percent_of": {"op", "stat", "scope", "subject", "percent"},
    "add": {"op", "operands"},
    "mul": {"op", "operands"},
    "min": {"op", "operands"},
    "by_holder_range": {"op", "melee", "ranged"},
    "unknown": {"op", "reason"},
    "unsupported": {"op", "reason", "needed"},
}


def _stat_issues(formula: Mapping[str, Any]) -> list[str]:
    stat = formula.get("stat")
    scope = formula.get("scope")
    problems: list[str] = []
    if stat not in STAT_SCOPES_BY_STAT:
        problems.append(f"unknown formula stat {stat!r}")
    if scope not in STAT_SCOPES:
        problems.append(f"unknown stat scope {scope!r}")
    if isinstance(stat, str) and scope in STAT_SCOPES:
        allowed = STAT_SCOPES_BY_STAT.get(stat)
        if allowed is not None and scope not in allowed:
            problems.append(f"stat {stat!r} does not support scope {scope!r}")
    subject = formula.get("subject")
    if subject is not None and subject not in STAT_SUBJECTS:
        problems.append(f"stat subject must be one of {sorted(STAT_SUBJECTS)}")
    return problems


def _formula_issues(formula: Any, depth: int) -> list[str]:
    if depth > MAX_FORMULA_DEPTH:
        return [f"formula is deeper than {MAX_FORMULA_DEPTH} levels"]
    if not isinstance(formula, Mapping):
        return ["formula must be an object"]
    operation = formula.get("op")
    if operation not in FORMULA_OPS:
        return [f"unsupported formula op {operation!r}"]
    unknown_keys = set(formula) - _ALLOWED_FORMULA_KEYS[operation]
    if unknown_keys:
        return [f"{operation} formula has unknown keys: {sorted(unknown_keys)}"]
    if operation == "constant":
        if not _is_number(formula.get("value")):
            return ["constant formula needs a finite numeric value"]
        return []
    if operation == "stat":
        return _stat_issues(formula)
    if operation == "percent_of":
        problems = _stat_issues(formula)
        if not _is_number(formula.get("percent")):
            problems.append("percent_of formula needs a finite numeric percent")
        return problems
    if operation == "by_holder_range":
        problems = []
        for branch in ("melee", "ranged"):
            if branch not in formula:
                problems.append(f"by_holder_range is missing the {branch!r} branch")
                continue
            problems.extend(
                f"{branch}: {message}" for message in _formula_issues(formula[branch], depth + 1)
            )
        return problems
    if operation in {"add", "mul", "min"}:
        operands = formula.get("operands")
        if not isinstance(operands, Sequence) or isinstance(operands, (str, bytes)) or not operands:
            return [f"{operation} formula needs a non-empty operands list"]
        problems = []
        for index, operand in enumerate(operands):
            problems.extend(
                f"operands[{index}]: {message}" for message in _formula_issues(operand, depth + 1)
            )
        return problems
    reason = formula.get("reason")
    problems = []
    if not isinstance(reason, str) or not reason.strip():
        problems.append(f"{operation} formula needs a non-empty reason")
    needed = formula.get("needed")
    if needed is not None and (
        not isinstance(needed, Sequence)
        or isinstance(needed, (str, bytes))
        or any(not isinstance(item, str) or not item for item in needed)
    ):
        problems.append(f"{operation}.needed must be a list of non-empty strings")
    return problems


def formula_issues(formula: Any) -> list[str]:
    """Return structural problems; an empty list means the formula is valid."""
    return _formula_issues(formula, 0)


def _walk_reasons(formula: Any) -> tuple[list[str], list[str]]:
    unknowns: list[str] = []
    unsupported: list[str] = []
    if not isinstance(formula, Mapping):
        return unknowns, unsupported
    operation = formula.get("op")
    if operation == "unknown":
        unknowns.append(str(formula.get("reason") or "unknown input"))
    elif operation == "unsupported":
        unsupported.append(str(formula.get("reason") or "unsupported mechanic"))
    elif operation in {"add", "mul", "min"}:
        operands = formula.get("operands")
        if isinstance(operands, Sequence) and not isinstance(operands, (str, bytes)):
            for operand in operands:
                child_unknowns, child_unsupported = _walk_reasons(operand)
                unknowns.extend(child_unknowns)
                unsupported.extend(child_unsupported)
    elif operation == "by_holder_range":
        for branch in ("melee", "ranged"):
            child_unknowns, child_unsupported = _walk_reasons(formula.get(branch))
            unknowns.extend(child_unknowns)
            unsupported.extend(child_unsupported)
    return unknowns, unsupported


def classify_formula(formula: Any) -> str:
    """Classify a formula as ``evaluable``, ``partially_evaluable`` or ``excluded``."""
    unknowns, unsupported = _walk_reasons(formula)
    if unsupported:
        return "excluded"
    if unknowns:
        return "partially_evaluable"
    return "evaluable"


def _stat_key(stat: str, scope: str) -> str:
    if scope == "total":
        return stat
    return f"{scope}_{stat}"


def _evaluate(
    formula: Any,
    stats: Mapping[str, float],
    depth: int,
    holder_range: str | None,
) -> tuple[float, list[str]]:
    if depth > MAX_FORMULA_DEPTH:
        raise FormulaError(
            f"formula is deeper than {MAX_FORMULA_DEPTH} levels",
            code="depth_exceeded",
            node=formula,
        )
    if not isinstance(formula, Mapping):
        raise FormulaError("formula must be an object", code="malformed_formula", node=formula)
    operation = formula.get("op")
    if operation == "constant":
        value = formula.get("value")
        if not _is_number(value):
            raise FormulaError(
                "constant formula has no finite value",
                code="malformed_formula",
                node=formula,
            )
        return float(value), []
    if operation == "stat":
        stat = formula.get("stat")
        scope = formula.get("scope")
        if not isinstance(stat, str) or not isinstance(scope, str):
            raise FormulaError("stat formula is incomplete", code="malformed_formula", node=formula)
        key = _stat_key(stat, scope)
        value = stats.get(key)
        if not _is_number(value):
            raise FormulaError(
                f"missing stat {key!r}",
                code="missing_stat",
                node=formula,
            )
        return float(value), [key]
    if operation == "percent_of":
        problems = _stat_issues(formula)
        percent = formula.get("percent")
        if problems or not _is_number(percent):
            raise FormulaError(
                "; ".join(problems) or "percent_of needs a finite percent",
                code="malformed_formula",
                node=formula,
            )
        key = _stat_key(str(formula["stat"]), str(formula["scope"]))
        value = stats.get(key)
        if not _is_number(value):
            raise FormulaError(f"missing stat {key!r}", code="missing_stat", node=formula)
        return float(value) * float(percent) / 100.0, [key]
    if operation in {"add", "mul", "min"}:
        operands = formula.get("operands")
        if not isinstance(operands, Sequence) or isinstance(operands, (str, bytes)) or not operands:
            raise FormulaError(
                f"{operation} formula needs operands",
                code="malformed_formula",
                node=formula,
            )
        dependencies: list[str] = []
        values: list[float] = []
        for operand in operands:
            value, child_dependencies = _evaluate(operand, stats, depth + 1, holder_range)
            values.append(value)
            dependencies.extend(item for item in child_dependencies if item not in dependencies)
        if operation == "add":
            return sum(values), dependencies
        if operation == "min":
            return min(values), dependencies
        product = 1.0
        for value in values:
            product *= value
        return product, dependencies
    if operation == "by_holder_range":
        if holder_range not in {"melee", "ranged"}:
            raise FormulaError(
                "by_holder_range needs an explicit melee or ranged holder",
                code="missing_holder_range",
                node=formula,
            )
        branch = formula.get(holder_range)
        if not isinstance(branch, Mapping):
            raise FormulaError(
                f"by_holder_range has no {holder_range!r} branch",
                code="malformed_formula",
                node=formula,
            )
        value, dependencies = _evaluate(branch, stats, depth + 1, holder_range)
        return value, ["holder_range", *[item for item in dependencies if item != "holder_range"]]
    if operation == "unknown":
        raise FormulaError(
            str(formula.get("reason") or "unknown input"),
            code="unknown_input",
            node=formula,
        )
    if operation == "unsupported":
        raise FormulaError(
            str(formula.get("reason") or "unsupported mechanic"),
            code="unsupported_formula",
            node=formula,
        )
    raise FormulaError(
        f"unsupported formula op {operation!r}",
        code="unsupported_operation",
        node=formula,
    )


def evaluate_formula(
    formula: Any,
    stats: Mapping[str, float],
    *,
    holder_range: str | None = None,
) -> FormulaResult:
    """Evaluate one formula or raise an explicit :class:`FormulaError`."""
    issues = formula_issues(formula)
    if issues:
        raise FormulaError("; ".join(issues), code="malformed_formula", node=formula)
    value, dependencies = _evaluate(formula, stats, 0, holder_range)
    return FormulaResult(value=value, dependencies=tuple(dependencies))
