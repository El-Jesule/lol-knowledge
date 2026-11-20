"""Deterministic evaluation of formula trees shared by items and champion kits.

Operations: ``constant``, ``stat``, ``percent_of``, ``add``, ``mul``, ``min``,
``by_holder_range``, ``unknown`` and ``unsupported`` (items and kits), plus
``by_rank``, ``by_level`` and ``input`` (kits only, see ``ABILITY_OPS``).

``unknown`` means the data is absent; ``unsupported`` means the mechanic is
not modelled. Neither is ever replaced by zero. A rank, level, holder range or
input that a formula needs must be given explicitly: a missing value is an
error, never a default. Arithmetic is exact (``fractions.Fraction``).
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from fractions import Fraction
from typing import Any

from .schema import (
    MAX_FORMULA_DEPTH,
    OBJECT_OPS,
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
    """One evaluated formula and what it read.

    ``value`` is the float of ``exact``; ``dependencies`` lists stat keys,
    ``holder_range``, ``rank``, ``level`` and ``input:<name>`` in reading order.
    """

    value: float
    dependencies: tuple[str, ...] = field(default_factory=tuple)
    exact: Fraction | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"value": self.value, "dependencies": list(self.dependencies)}


def _is_number(value: Any) -> bool:
    if isinstance(value, bool):
        return False
    if isinstance(value, Fraction):
        return True
    return isinstance(value, (int, float)) and math.isfinite(value)


def _exact(value: Any) -> Fraction:
    if isinstance(value, Fraction):
        return value
    if isinstance(value, float):
        return Fraction(repr(value))
    return Fraction(value)


_ALLOWED_FORMULA_KEYS = {
    "constant": {"op", "value"},
    "stat": {"op", "stat", "scope", "subject"},
    "percent_of": {"op", "stat", "scope", "subject", "percent"},
    "add": {"op", "operands"},
    "mul": {"op", "operands"},
    "min": {"op", "operands"},
    "by_holder_range": {"op", "melee", "ranged"},
    "by_rank": {"op", "values"},
    "by_level": {"op", "values"},
    "linear_by_level": {"op", "min", "max"},
    "input": {"op", "name"},
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


def _values_issues(operation: str, values: Any) -> list[str]:
    if (
        not isinstance(values, Sequence)
        or isinstance(values, (str, bytes))
        or not values
        or not all(_is_number(value) for value in values)
    ):
        return [f"{operation} formula needs a non-empty list of finite numbers"]
    return []


def _formula_issues(formula: Any, depth: int, ops: frozenset[str]) -> list[str]:
    if depth > MAX_FORMULA_DEPTH:
        return [f"formula is deeper than {MAX_FORMULA_DEPTH} levels"]
    if not isinstance(formula, Mapping):
        return ["formula must be an object"]
    operation = formula.get("op")
    if operation not in ops:
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
    if operation in {"by_rank", "by_level"}:
        return _values_issues(operation, formula.get("values"))
    if operation == "linear_by_level":
        problems = []
        if not _is_number(formula.get("min")):
            problems.append("linear_by_level formula needs a finite numeric 'min'")
        if not _is_number(formula.get("max")):
            problems.append("linear_by_level formula needs a finite numeric 'max'")
        return problems
    if operation == "input":
        name = formula.get("name")
        if not isinstance(name, str) or not name.strip():
            return ["input formula needs a non-empty name"]
        return []
    if operation == "by_holder_range":
        problems = []
        for branch in ("melee", "ranged"):
            if branch not in formula:
                problems.append(f"by_holder_range is missing the {branch!r} branch")
                continue
            problems.extend(
                f"{branch}: {message}"
                for message in _formula_issues(formula[branch], depth + 1, ops)
            )
        return problems
    if operation in {"add", "mul", "min"}:
        operands = formula.get("operands")
        if not isinstance(operands, Sequence) or isinstance(operands, (str, bytes)) or not operands:
            return [f"{operation} formula needs a non-empty operands list"]
        problems = []
        for index, operand in enumerate(operands):
            problems.extend(
                f"operands[{index}]: {message}"
                for message in _formula_issues(operand, depth + 1, ops)
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


def formula_issues(formula: Any, *, ops: frozenset[str] = OBJECT_OPS) -> list[str]:
    """Return structural problems; an empty list means the formula is valid for ``ops``."""
    return _formula_issues(formula, 0, ops)


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


@dataclass(frozen=True)
class _Context:
    stats: Mapping[str, Any]
    target_stats: Mapping[str, Any] | None
    holder_range: str | None
    rank: int | None
    level: int | None
    inputs: Mapping[str, Any]


def _read_stat(formula: Mapping[str, Any], ctx: _Context) -> tuple[Fraction, str]:
    key = _stat_key(str(formula["stat"]), str(formula["scope"]))
    source = ctx.stats
    label = key
    if ctx.target_stats is not None and formula.get("subject") == "target":
        source = ctx.target_stats
        label = f"target:{key}"
    value = source.get(key)
    if not _is_number(value):
        raise FormulaError(f"missing stat {label!r}", code="missing_stat", node=formula)
    return _exact(value), label


def _pick(values: Sequence[Any], index: int | None, what: str, formula: Any) -> Fraction:
    if index is None:
        raise FormulaError(
            f"formula needs an explicit {what}", code=f"missing_{what}", node=formula
        )
    if isinstance(index, bool) or not isinstance(index, int) or not 1 <= index <= len(values):
        raise FormulaError(
            f"{what} {index!r} is outside 1..{len(values)}",
            code=f"{what}_out_of_range",
            node=formula,
        )
    return _exact(values[index - 1])


def _evaluate(formula: Any, ctx: _Context, depth: int) -> tuple[Fraction, list[str]]:
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
                "constant formula has no finite value", code="malformed_formula", node=formula
            )
        return _exact(value), []
    if operation == "stat":
        if not isinstance(formula.get("stat"), str) or not isinstance(formula.get("scope"), str):
            raise FormulaError("stat formula is incomplete", code="malformed_formula", node=formula)
        value, label = _read_stat(formula, ctx)
        return value, [label]
    if operation == "percent_of":
        problems = _stat_issues(formula)
        percent = formula.get("percent")
        if problems or not _is_number(percent):
            raise FormulaError(
                "; ".join(problems) or "percent_of needs a finite percent",
                code="malformed_formula",
                node=formula,
            )
        value, label = _read_stat(formula, ctx)
        return value * _exact(percent) / 100, [label]
    if operation == "by_rank":
        return _pick(formula["values"], ctx.rank, "rank", formula), ["rank"]
    if operation == "by_level":
        return _pick(formula["values"], ctx.level, "level", formula), ["level"]
    if operation == "linear_by_level":
        if ctx.level is None:
            raise FormulaError(
                "formula needs an explicit level", code="missing_level", node=formula
            )
        if (
            isinstance(ctx.level, bool)
            or not isinstance(ctx.level, int)
            or not 1 <= ctx.level <= 18
        ):
            raise FormulaError(
                f"level {ctx.level!r} is outside 1..18",
                code="level_out_of_range",
                node=formula,
            )
        low, high = _exact(formula["min"]), _exact(formula["max"])
        return low + (high - low) * Fraction(ctx.level - 1, 17), ["level"]
    if operation == "input":
        name = formula.get("name")
        value = ctx.inputs.get(name)
        if not _is_number(value):
            raise FormulaError(f"missing input {name!r}", code="missing_input", node=formula)
        return _exact(value), [f"input:{name}"]
    if operation in {"add", "mul", "min"}:
        operands = formula.get("operands")
        if not isinstance(operands, Sequence) or isinstance(operands, (str, bytes)) or not operands:
            raise FormulaError(
                f"{operation} formula needs operands", code="malformed_formula", node=formula
            )
        dependencies: list[str] = []
        values: list[Fraction] = []
        for operand in operands:
            value, child = _evaluate(operand, ctx, depth + 1)
            values.append(value)
            dependencies.extend(item for item in child if item not in dependencies)
        if operation == "add":
            return sum(values, start=Fraction(0)), dependencies
        if operation == "min":
            return min(values), dependencies
        return math.prod(values, start=Fraction(1)), dependencies
    if operation == "by_holder_range":
        if ctx.holder_range not in {"melee", "ranged"}:
            raise FormulaError(
                "by_holder_range needs an explicit melee or ranged holder",
                code="missing_holder_range",
                node=formula,
            )
        branch = formula.get(ctx.holder_range)
        if not isinstance(branch, Mapping):
            raise FormulaError(
                f"by_holder_range has no {ctx.holder_range!r} branch",
                code="malformed_formula",
                node=formula,
            )
        value, child = _evaluate(branch, ctx, depth + 1)
        return value, ["holder_range", *[item for item in child if item != "holder_range"]]
    if operation == "unknown":
        raise FormulaError(
            str(formula.get("reason") or "unknown input"), code="unknown_input", node=formula
        )
    if operation == "unsupported":
        raise FormulaError(
            str(formula.get("reason") or "unsupported mechanic"),
            code="unsupported_formula",
            node=formula,
        )
    raise FormulaError(
        f"unsupported formula op {operation!r}", code="unsupported_operation", node=formula
    )


def evaluate_formula(
    formula: Any,
    stats: Mapping[str, Any],
    *,
    holder_range: str | None = None,
    rank: int | None = None,
    level: int | None = None,
    inputs: Mapping[str, Any] | None = None,
    target_stats: Mapping[str, Any] | None = None,
    ops: frozenset[str] = OBJECT_OPS,
) -> FormulaResult:
    """Evaluate one formula or raise an explicit :class:`FormulaError`.

    With ``target_stats``, stats whose ``subject`` is ``target`` are read from
    it; without it every stat is read from ``stats`` (item model behaviour).
    """
    issues = formula_issues(formula, ops=ops)
    if issues:
        raise FormulaError("; ".join(issues), code="malformed_formula", node=formula)
    ctx = _Context(stats, target_stats, holder_range, rank, level, inputs or {})
    value, dependencies = _evaluate(formula, ctx, 0)
    return FormulaResult(value=float(value), dependencies=tuple(dependencies), exact=value)
