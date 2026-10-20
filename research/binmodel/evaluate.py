"""Deterministic evaluation of typed calculation trees.

The evaluator is deliberately strict: an unresolved node, a missing data value
or an unknown stat raises ``FormulaError``. Partial results are returned only
when the caller asks for them and the missing references are listed.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from .model import OMITTED_FLOAT_DEFAULT_POLICY, Ability, DataValue
from .stats import stat_value


def _require_number(
    value: Any,
    *,
    code: str,
    message: str,
    node: Mapping[str, Any] | None = None,
) -> float:
    """Return a finite float or raise an explicit formula error."""
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise FormulaError(message, code=code, node=node)
    return float(value)


class FormulaError(Exception):
    """A formula cannot be evaluated without inventing data."""

    def __init__(
        self,
        message: str,
        *,
        code: str = "formula_error",
        missing: list[str] | None = None,
        node: Mapping[str, Any] | None = None,
        partial: float | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.missing = missing or []
        self.node = node
        self.partial = partial


@dataclass
class EvaluationContext:
    """Everything the evaluator may read."""

    abilities: Mapping[str, Ability]
    stats: Mapping[str, float]
    mode: str = "base"
    level: int = 1
    rank: int = 1
    stack: list[tuple[str, str]] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)

    def dependency(self, value: str) -> None:
        if value not in self.dependencies:
            self.dependencies.append(value)


@dataclass
class Evaluation:
    """One evaluated calculation."""

    value: float
    complete: bool
    missing: list[str]
    dependencies: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "value": self.value,
            "complete": self.complete,
            "missing": self.missing,
            "dependencies": self.dependencies,
        }


def build_context(
    abilities: Mapping[str, Ability],
    stats: Mapping[str, float],
    *,
    mode: str = "base",
) -> EvaluationContext:
    """Build an evaluation context from extracted abilities and a stat sheet."""
    return EvaluationContext(abilities=abilities, stats=stats, mode=mode)


def _ability(ctx: EvaluationContext, ability_id: str) -> Ability:
    ability = ctx.abilities.get(ability_id)
    if ability is None:
        raise FormulaError(f"unknown ability {ability_id!r}", code="unknown_ability")
    return ability


def _data_value(
    ability: Ability,
    name: str,
    ctx: EvaluationContext,
    *,
    rank: int | None = None,
    mode: str | None = None,
) -> float:
    selected_mode = mode or ctx.mode
    matches = [
        item
        for item in ability.data_values
        if item.name == name and item.mode in {selected_mode, "base"}
    ]
    if not matches:
        ctx.missing.append(f"{ability.ability_id}.{selected_mode}.{name}")
        raise FormulaError(
            f"missing data value {name!r} in {ability.ability_id}",
            code="missing_data_value",
            missing=[f"{ability.ability_id}.{selected_mode}.{name}"],
        )
    matches.sort(key=lambda item: item.mode != selected_mode)
    item: DataValue = matches[0]
    if item.ranks is None:
        ctx.missing.append(f"{ability.ability_id}.{selected_mode}.{name}")
        raise FormulaError(
            f"data value {name!r} in {ability.ability_id} has no selected ranks",
            code="data_value_without_ranks",
            missing=[f"{ability.ability_id}.{selected_mode}.{name}"],
        )
    index = (rank or ctx.rank) - 1
    if index < 0 or index >= len(item.ranks):
        raise FormulaError(
            f"rank {rank or ctx.rank} out of range for {name!r}",
            code="rank_out_of_range",
        )
    ctx.dependency(f"data_value:{ability.ability_id}.{name}")
    return item.ranks[index]


def _calculation(ability: Ability, name: str) -> dict[str, Any]:
    for calculation in ability.calculations:
        if calculation.name == name:
            return calculation.tree
    raise FormulaError(
        f"missing calculation {name!r} in {ability.ability_id}",
        code="missing_calculation",
    )


def _external_ability(ctx: EvaluationContext, source_object: str) -> Ability:
    for ability in ctx.abilities.values():
        if ability.path == source_object or ability.root_spell == source_object:
            return ability
    raise FormulaError(
        f"external source object {source_object!r} not extracted",
        code="missing_external_object",
    )


def _eval_calculation(
    tree: Mapping[str, Any],
    ability: Ability,
    ctx: EvaluationContext,
) -> float:
    return _eval_node(tree, ability, ctx)


def _eval_named(ability: Ability, name: str, ctx: EvaluationContext) -> float:
    """Evaluate a named calculation with cycle detection."""
    marker = (ability.ability_id, name)
    if marker in ctx.stack:
        chain = " -> ".join(f"{item[0]}.{item[1]}" for item in [*ctx.stack, marker])
        raise FormulaError(
            f"calculation cycle: {chain}",
            code="calculation_cycle",
        )
    ctx.stack.append(marker)
    try:
        return _eval_calculation(_calculation(ability, name), ability, ctx)
    finally:
        ctx.stack.pop()


def _eval_node(
    node: Mapping[str, Any],
    ability: Ability,
    ctx: EvaluationContext,
) -> float:
    kind = node.get("kind")
    if kind == "game_calculation":
        parts = node.get("parts")
        if not isinstance(parts, Sequence) or isinstance(parts, (str, bytes)):
            raise FormulaError(
                "game calculation has no formula parts",
                code="missing_formula_parts",
                node=node,
            )
        return sum((_eval_node(part, ability, ctx) for part in parts), 0.0)
    if kind == "number":
        return _require_number(
            node.get("value"),
            code="malformed_number",
            message="number calculation part has no finite value",
            node=node,
        )
    if kind == "data_value":
        return _data_value(ability, str(node["name"]), ctx)
    if kind == "stat_scaled":
        stat = node.get("stat") or {}
        if not stat.get("resolved"):
            raise FormulaError(
                f"unresolved stat {stat.get('mStat')}/{stat.get('mStatFormula')}",
                code="unresolved_stat",
                node=node,
            )
        try:
            base = stat_value(ctx.stats, stat["stat"], stat["formula"])
        except KeyError as exc:
            raise FormulaError(
                f"unsupported stat {stat.get('stat')!r}/{stat.get('formula')!r}",
                code="unsupported_stat",
                node=node,
            ) from exc
        ctx.dependency(f"stat:{stat['stat']}/{stat['formula']}")
        return base * _eval_node(node["factor"], ability, ctx)
    if kind == "product":
        operands = node.get("operands")
        if not isinstance(operands, Sequence) or isinstance(operands, (str, bytes)):
            raise FormulaError(
                "product has no operands",
                code="missing_formula_operands",
                node=node,
            )
        value = 1.0
        for operand in operands:
            value *= _eval_node(operand, ability, ctx)
        return value
    if kind == "sum":
        operands = node.get("operands")
        if not isinstance(operands, Sequence) or isinstance(operands, (str, bytes)):
            raise FormulaError(
                "sum has no operands",
                code="missing_formula_operands",
                node=node,
            )
        return sum((_eval_node(item, ability, ctx) for item in operands), 0.0)
    if kind == "by_char_level_breakpoints":
        return _eval_breakpoints(node, ctx)
    if kind == "by_char_level_formula":
        values = node.get("values")
        if not isinstance(values, Sequence) or isinstance(values, (str, bytes)):
            raise FormulaError(
                "by-char-level formula has no values",
                code="malformed_formula_values",
                node=node,
            )
        index = ctx.level - 1
        if index < 0 or index >= len(values):
            raise FormulaError(
                f"level {ctx.level} out of range for formula values",
                code="level_out_of_range",
            )
        return _require_number(
            values[index],
            code="malformed_formula_values",
            message="by-char-level formula value is not a finite number",
            node=node,
        )
    if kind == "by_char_level_interpolation":
        if node.get("scale_by_stat_progression_multiplier"):
            raise FormulaError(
                "scale_by_stat_progression_multiplier is not modelled",
                code="unsupported_interpolation_mode",
                node=node,
            )
        steps = _interpolation_steps(
            ctx.level, bool(node.get("scale_past_default_max_level", True))
        )
        start = _require_number(
            node.get("start_value"),
            code="malformed_interpolation",
            message="interpolation has no finite start value",
            node=node,
        )
        end = _require_number(
            node.get("end_value"),
            code="malformed_interpolation",
            message="interpolation has no finite end value",
            node=node,
        )
        return start + (end - start) * steps / 17.0
    if kind == "by_char_level_named_data_values_interpolation":
        start = _data_value(ability, str(node["start_data_value"]), ctx)
        end = _data_value(ability, str(node["end_data_value"]), ctx)
        steps = _interpolation_steps(
            ctx.level, bool(node.get("scale_past_default_max_level", True))
        )
        return start + (end - start) * steps / 17.0
    if kind == "by_char_level_named_breakpoints":
        return _eval_named_breakpoints(node, ability, ctx)
    if kind == "modified":
        base_name = node.get("base_calculation")
        if not isinstance(base_name, str):
            raise FormulaError("modified calculation has no base key", code="missing_base")
        multiplier = node.get("multiplier")
        if not isinstance(multiplier, Mapping):
            raise FormulaError("modified calculation has no multiplier", code="missing_multiplier")
        return _eval_named(ability, base_name, ctx) * _eval_node(multiplier, ability, ctx)
    if kind == "calculation_reference":
        key = node.get("key")
        if not isinstance(key, str):
            raise FormulaError("calculation reference has no key", code="missing_reference")
        return _eval_named(ability, key, ctx)
    if kind == "external_calculation_reference":
        source = node.get("source_object")
        key = node.get("key")
        if not isinstance(source, str) or not isinstance(key, str):
            raise FormulaError("external reference is incomplete", code="missing_reference")
        external = _external_ability(ctx, source)
        return _eval_named(external, key, ctx)
    if kind == "external_data_value":
        source = node.get("source_object")
        name = node.get("name")
        if not isinstance(source, str) or not isinstance(name, str):
            raise FormulaError("external data value is incomplete", code="missing_reference")
        external = _external_ability(ctx, source)
        return _data_value(external, name, ctx)
    if kind == "bot_effect":
        calculation = node.get("calculation")
        if not isinstance(calculation, Mapping):
            raise FormulaError("bot effect has no calculation", code="missing_calculation")
        return _eval_calculation(calculation, ability, ctx)
    if kind == "conditional":
        raise FormulaError(
            "conditional calculation requires game state (buff/stack condition)",
            code="conditional_requires_game_state",
            node=node,
        )
    if kind == "effect_value":
        raise FormulaError(
            "effect value requires SpellEffectAmount data",
            code="effect_value_unresolved",
            node=node,
        )
    if kind == "unresolved":
        raise FormulaError(
            f"unresolved node {node.get('type')}",
            code="unresolved_node",
            node=node,
        )
    raise FormulaError(f"unknown node kind {kind!r}", code="unknown_node_kind", node=node)


def _interpolation_steps(level: int, scale_past_max: bool) -> float:
    if level < 1:
        raise FormulaError("level must be >= 1", code="invalid_level")
    effective = level if scale_past_max or level <= 18 else 18
    return float(effective - 1)


def _breakpoint_field(
    record: Mapping[str, Any],
    key: str,
    *,
    path: str,
    node: Mapping[str, Any],
    ctx: EvaluationContext,
) -> float:
    """Read one breakpoint field without inventing a zero.

    Only fields that the extractor marked as absent under the declared
    ``OMITTED_FLOAT_DEFAULT_POLICY`` may fall back to the class default (0.0).
    """
    value = record.get(key)
    if value is None:
        absent = node.get("absent_fields") or []
        if node.get("default_policy") == OMITTED_FLOAT_DEFAULT_POLICY and path in absent:
            ctx.dependency(f"default:{path}")
            return 0.0
        raise FormulaError(
            f"breakpoint field {path} is absent and has no declared default",
            code="missing_breakpoint_field",
            node=node,
        )
    return _require_number(
        value,
        code="missing_breakpoint_field",
        message=f"breakpoint field {path} is not a finite number",
        node=node,
    )


def _eval_breakpoints(node: Mapping[str, Any], ctx: EvaluationContext) -> float:
    value = _breakpoint_field(node, "level1_value", path="level1_value", node=node, ctx=ctx)
    initial = _breakpoint_field(
        node, "initial_bonus_per_level", path="initial_bonus_per_level", node=node, ctx=ctx
    )
    value += initial * (ctx.level - 1)
    breakpoints = node.get("breakpoints")
    if not isinstance(breakpoints, Sequence) or isinstance(breakpoints, (str, bytes)):
        raise FormulaError(
            "breakpoint calculation has no breakpoint list",
            code="missing_breakpoint_field",
            node=node,
        )
    for index, breakpoint in enumerate(breakpoints):
        if not isinstance(breakpoint, Mapping):
            raise FormulaError(
                f"breakpoint {index} is not an object",
                code="missing_breakpoint_field",
                node=node,
            )
        level_value = _require_number(
            breakpoint.get("level"),
            code="missing_breakpoint_field",
            message=f"breakpoint {index} has no finite level",
            node=node,
        )
        level = int(level_value)
        if ctx.level >= level:
            value += _breakpoint_field(
                breakpoint,
                "additional_bonus_at_this_level",
                path=f"breakpoints[{index}].additional_bonus_at_this_level",
                node=node,
                ctx=ctx,
            )
        if ctx.level > level:
            value += _breakpoint_field(
                breakpoint,
                "bonus_per_level_at_and_after",
                path=f"breakpoints[{index}].bonus_per_level_at_and_after",
                node=node,
                ctx=ctx,
            )
    return value


def _eval_named_breakpoints(
    node: Mapping[str, Any],
    ability: Ability,
    ctx: EvaluationContext,
) -> float:
    missing: list[str] = []
    value = 0.0
    level1_name = node.get("level1_data_value")
    if isinstance(level1_name, str):
        try:
            value = _data_value(ability, level1_name, ctx, rank=1)
        except FormulaError as exc:
            missing.extend(exc.missing)
    bonus_name = node.get("bonus_per_level_data_value")
    if isinstance(bonus_name, str):
        try:
            value += _data_value(ability, bonus_name, ctx, rank=1) * (ctx.level - 1)
        except FormulaError as exc:
            missing.extend(exc.missing)
    for breakpoint in node.get("breakpoints") or []:
        level = int(breakpoint.get("level") or 0)
        additional_name = breakpoint.get("additional_bonus_data_value")
        if ctx.level >= level and isinstance(additional_name, str):
            try:
                value += _data_value(ability, additional_name, ctx, rank=1)
            except FormulaError as exc:
                missing.extend(exc.missing)
        bonus_after_name = breakpoint.get("bonus_per_level_at_and_after_data_value")
        if ctx.level > level and isinstance(bonus_after_name, str):
            try:
                value += _data_value(ability, bonus_after_name, ctx, rank=1) * (ctx.level - level)
            except FormulaError as exc:
                missing.extend(exc.missing)
    if missing:
        ctx.missing.extend(item for item in missing if item not in ctx.missing)
        raise FormulaError(
            "named breakpoint calculation is incomplete",
            code="incomplete_named_breakpoints",
            missing=missing,
            node=node,
            partial=value,
        )
    return value


def evaluate(
    ability: Ability,
    calculation_name: str,
    ctx: EvaluationContext,
    *,
    level: int | None = None,
    rank: int | None = None,
) -> Evaluation:
    """Evaluate one named calculation, reporting completeness explicitly."""
    if level is not None:
        ctx.level = level
    if rank is not None:
        ctx.rank = rank
    ctx.missing = []
    ctx.dependencies = []
    try:
        value = _eval_named(ability, calculation_name, ctx)
        return Evaluation(
            value=value,
            complete=True,
            missing=list(ctx.missing),
            dependencies=list(ctx.dependencies),
        )
    except FormulaError as exc:
        partial = exc.partial
        if partial is None:
            raise
        return Evaluation(
            value=float(partial),
            complete=False,
            missing=list(dict.fromkeys(exc.missing)),
            dependencies=list(ctx.dependencies),
        )
