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
    "input": {"op", "name", "default"},
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
        if "default" in formula and not _is_number(formula.get("default")):
            return ["input formula default must be a finite numeric value"]
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


@dataclass(frozen=True, slots=True)
class _Context:
    stats: Mapping[str, Any]
    target_stats: Mapping[str, Any] | None
    holder_range: str | None
    rank: int | None
    level: int | None
    inputs: Mapping[str, Any]


class CompiledFormula:
    """Pre-validated and compiled formula tree ready for repeated evaluation."""

    __slots__ = ("node", "ops")

    def __init__(self, node: Any, ops: frozenset[str]) -> None:
        self.node = node
        self.ops = ops


class _ConstNode:
    __slots__ = ("value",)

    def __init__(self, value: Fraction) -> None:
        self.value = value


class _StatNode:
    __slots__ = ("key", "target_label", "is_target", "raw")

    def __init__(self, key: str, target_label: str, is_target: bool, raw: Any) -> None:
        self.key = key
        self.target_label = target_label
        self.is_target = is_target
        self.raw = raw


class _PercentOfNode:
    __slots__ = ("key", "target_label", "is_target", "factor", "raw")

    def __init__(
        self, key: str, target_label: str, is_target: bool, factor: Fraction, raw: Any
    ) -> None:
        self.key = key
        self.target_label = target_label
        self.is_target = is_target
        self.factor = factor
        self.raw = raw


class _ByRankNode:
    __slots__ = ("values", "raw")

    def __init__(self, values: tuple[Fraction, ...], raw: Any) -> None:
        self.values = values
        self.raw = raw


class _ByLevelNode:
    __slots__ = ("values", "raw")

    def __init__(self, values: tuple[Fraction, ...], raw: Any) -> None:
        self.values = values
        self.raw = raw


class _LinearByLevelNode:
    __slots__ = ("low", "step", "raw")

    def __init__(self, low: Fraction, step: Fraction, raw: Any) -> None:
        self.low = low
        self.step = step
        self.raw = raw


class _InputNode:
    __slots__ = ("name", "dep", "has_default", "default_val", "raw")

    def __init__(
        self,
        name: str,
        dep: str,
        has_default: bool,
        default_val: Fraction | None,
        raw: Any,
    ) -> None:
        self.name = name
        self.dep = dep
        self.has_default = has_default
        self.default_val = default_val
        self.raw = raw


class _AggNode:
    __slots__ = ("op", "children")

    def __init__(self, op: str, children: tuple[Any, ...]) -> None:
        self.op = op
        self.children = children


class _ByRangeNode:
    __slots__ = ("melee", "ranged", "raw")

    def __init__(self, melee: Any, ranged: Any, raw: Any) -> None:
        self.melee = melee
        self.ranged = ranged
        self.raw = raw


class _ErrorNode:
    __slots__ = ("message", "code", "raw")

    def __init__(self, message: str, code: str, raw: Any) -> None:
        self.message = message
        self.code = code
        self.raw = raw


def _freeze_formula(node: Any) -> Any:
    """Return a hashable structural key for a formula tree without type collisions."""
    node_type = type(node)
    if node_type is dict:
        return tuple(sorted((k, _freeze_formula(v)) for k, v in node.items()))
    if node_type is list or node_type is tuple:
        return tuple(_freeze_formula(item) for item in node)
    if node_type in (str, int, float, Fraction, bool, type(None)):
        return (node_type, node)
    if isinstance(node, Mapping):
        return tuple(sorted((k, _freeze_formula(v)) for k, v in node.items()))
    if isinstance(node, Sequence) and not isinstance(node, (str, bytes, bytearray)):
        return tuple(_freeze_formula(item) for item in node)
    return (node_type, node)


def _compile_node(formula: Mapping[str, Any]) -> Any:
    operation = formula["op"]
    if operation == "constant":
        return _ConstNode(_exact(formula["value"]))
    if operation == "stat":
        key = _stat_key(str(formula["stat"]), str(formula["scope"]))
        return _StatNode(key, f"target:{key}", formula.get("subject") == "target", formula)
    if operation == "percent_of":
        key = _stat_key(str(formula["stat"]), str(formula["scope"]))
        factor = _exact(formula["percent"]) / 100
        return _PercentOfNode(
            key, f"target:{key}", formula.get("subject") == "target", factor, formula
        )
    if operation == "by_rank":
        return _ByRankNode(tuple(_exact(v) for v in formula["values"]), formula)
    if operation == "by_level":
        return _ByLevelNode(tuple(_exact(v) for v in formula["values"]), formula)
    if operation == "linear_by_level":
        low = _exact(formula["min"])
        step = (_exact(formula["max"]) - low) / 17
        return _LinearByLevelNode(low, step, formula)
    if operation == "input":
        name = str(formula["name"])
        has_default = "default" in formula
        default_val = _exact(formula["default"]) if has_default else None
        return _InputNode(name, f"input:{name}", has_default, default_val, formula)
    if operation in {"add", "mul", "min"}:
        children = tuple(_compile_node(operand) for operand in formula["operands"])
        return _AggNode(operation, children)
    if operation == "by_holder_range":
        return _ByRangeNode(
            _compile_node(formula["melee"]),
            _compile_node(formula["ranged"]),
            formula,
        )
    if operation == "unknown":
        return _ErrorNode(str(formula.get("reason") or "unknown input"), "unknown_input", formula)
    if operation == "unsupported":
        return _ErrorNode(
            str(formula.get("reason") or "unsupported mechanic"),
            "unsupported_formula",
            formula,
        )
    raise FormulaError(
        f"unsupported formula op {operation!r}", code="unsupported_operation", node=formula
    )


_COMPILED_CACHE_MAXSIZE = 8192
_COMPILED_CACHE: dict[tuple[Any, frozenset[str]], Any] = {}


def _get_compiled(formula: Any, ops: frozenset[str]) -> Any:
    try:
        key = (_freeze_formula(formula), ops)
        compiled = _COMPILED_CACHE.get(key)
    except TypeError:
        issues = formula_issues(formula, ops=ops)
        if issues:
            raise FormulaError("; ".join(issues), code="malformed_formula", node=formula) from None
        return _compile_node(formula)
    if compiled is not None:
        return compiled
    issues = formula_issues(formula, ops=ops)
    if issues:
        raise FormulaError("; ".join(issues), code="malformed_formula", node=formula)
    compiled = _compile_node(formula)
    if len(_COMPILED_CACHE) >= _COMPILED_CACHE_MAXSIZE:
        _COMPILED_CACHE.pop(next(iter(_COMPILED_CACHE)))
    _COMPILED_CACHE[key] = compiled
    return compiled


def _read_stat_compiled(node: _StatNode | _PercentOfNode, ctx: _Context) -> tuple[Fraction, str]:
    if ctx.target_stats is not None and node.is_target:
        source = ctx.target_stats
        label = node.target_label
    else:
        source = ctx.stats
        label = node.key
    value = source.get(node.key)
    if type(value) is Fraction:
        return value, label
    if not _is_number(value):
        raise FormulaError(f"missing stat {label!r}", code="missing_stat", node=node.raw)
    return _exact(value), label


def _pick_compiled(
    values: tuple[Fraction, ...], index: int | None, what: str, raw: Any
) -> Fraction:
    if index is None:
        raise FormulaError(f"formula needs an explicit {what}", code=f"missing_{what}", node=raw)
    if isinstance(index, bool) or not isinstance(index, int) or not 1 <= index <= len(values):
        raise FormulaError(
            f"{what} {index!r} is outside 1..{len(values)}",
            code=f"{what}_out_of_range",
            node=raw,
        )
    return values[index - 1]


def _eval_compiled(node: Any, ctx: _Context) -> tuple[Fraction, list[str]]:
    ntype = type(node)
    if ntype is _ConstNode:
        return node.value, []
    if ntype is _StatNode:
        value, label = _read_stat_compiled(node, ctx)
        return value, [label]
    if ntype is _PercentOfNode:
        value, label = _read_stat_compiled(node, ctx)
        return value * node.factor, [label]
    if ntype is _ByRankNode:
        return _pick_compiled(node.values, ctx.rank, "rank", node.raw), ["rank"]
    if ntype is _ByLevelNode:
        return _pick_compiled(node.values, ctx.level, "level", node.raw), ["level"]
    if ntype is _LinearByLevelNode:
        if ctx.level is None:
            raise FormulaError(
                "formula needs an explicit level", code="missing_level", node=node.raw
            )
        if (
            isinstance(ctx.level, bool)
            or not isinstance(ctx.level, int)
            or not 1 <= ctx.level <= 18
        ):
            raise FormulaError(
                f"level {ctx.level!r} is outside 1..18",
                code="level_out_of_range",
                node=node.raw,
            )
        return node.low + node.step * (ctx.level - 1), ["level"]
    if ntype is _InputNode:
        value = ctx.inputs.get(node.name)
        if value is None:
            if node.has_default:
                assert node.default_val is not None
                return node.default_val, [node.dep]
            raise FormulaError(f"missing input {node.name!r}", code="missing_input", node=node.raw)
        if type(value) is Fraction:
            return value, [node.dep]
        if not _is_number(value):
            raise FormulaError(f"missing input {node.name!r}", code="missing_input", node=node.raw)
        return _exact(value), [node.dep]
    if ntype is _AggNode:
        dependencies: list[str] = []
        values: list[Fraction] = []
        for child_node in node.children:
            value, child = _eval_compiled(child_node, ctx)
            values.append(value)
            for item in child:
                if item not in dependencies:
                    dependencies.append(item)
        if node.op == "add":
            return sum(values, start=Fraction(0)), dependencies
        if node.op == "min":
            return min(values), dependencies
        return math.prod(values, start=Fraction(1)), dependencies
    if ntype is _ByRangeNode:
        if ctx.holder_range == "melee":
            branch = node.melee
        elif ctx.holder_range == "ranged":
            branch = node.ranged
        else:
            raise FormulaError(
                "by_holder_range needs an explicit melee or ranged holder",
                code="missing_holder_range",
                node=node.raw,
            )
        value, child = _eval_compiled(branch, ctx)
        return value, ["holder_range", *(item for item in child if item != "holder_range")]
    if ntype is _ErrorNode:
        raise FormulaError(node.message, code=node.code, node=node.raw)
    raise FormulaError(
        f"unsupported compiled node {ntype!r}", code="unsupported_operation", node=node
    )


def compile_formula(formula: Any, *, ops: frozenset[str] = OBJECT_OPS) -> CompiledFormula:
    """Validate and compile ``formula`` once for repeated evaluation under ``ops``."""
    if type(formula) is CompiledFormula and formula.ops == ops:
        return formula
    return CompiledFormula(_get_compiled(formula, ops), ops)


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
    compiled = (
        formula.node
        if (type(formula) is CompiledFormula and formula.ops == ops)
        else _get_compiled(formula, ops)
    )
    ctx = _Context(stats, target_stats, holder_range, rank, level, inputs or {})
    value, dependencies = _eval_compiled(compiled, ctx)
    return FormulaResult(value=float(value), dependencies=tuple(dependencies), exact=value)
