"""Compile a champion kit (``lol-champion-kit/1``) from a bin extraction and a curated spec.

The spec says *what* the kit contains (which cases each ability has and which
calculation feeds each damage part). The compiler fills in *the numbers* from
the bin extraction (``python -m binmodel --json``) and takes each part's damage
type from the client tooltip markup (``<physicalDamage>``, ``<magicDamage>``,
``<trueDamage>``). A declared damage type that disagrees with the tooltip, a
calculation node it cannot translate or a missing data value stops the
compilation: nothing is guessed.

Usage::

    python -m binmodel.kitgen --extract zaahen-extract.json \\
        --tooltips research/fixtures/zaahen_tooltips_es_es.json \\
        --spec research/kits/Zaahen.spec.json \\
        --output lol-knowledge/champions/Zaahen/kit.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

KIT_SCHEMA = "lol-champion-kit/1"
DAMAGE_TAGS = {"physicalDamage": "physical", "magicDamage": "magic", "trueDamage": "true"}
TAG_PATTERN = re.compile(r"<(physicalDamage|magicDamage|trueDamage)>(.*?)</\1>", re.DOTALL)
STAT_SCOPES = {
    "attack_damage": {"base", "bonus", "total"},
    "ability_power": {"total"},
    "health": {"base", "bonus", "total", "current", "max"},
    "armor": {"base", "bonus", "total"},
    "magic_resist": {"base", "bonus", "total"},
}


class KitGenError(Exception):
    """The kit cannot be compiled without guessing."""


def tooltip_damage_types(tooltip: str, reference: str) -> set[str]:
    """Damage types of the tags that wrap ``@reference@`` (or ``@reference*…@``)."""
    return {
        DAMAGE_TAGS[tag]
        for tag, inner in TAG_PATTERN.findall(tooltip)
        if re.search(rf"@{re.escape(reference)}(?:[*][^@]*)?@", inner)
    }


def tooltip_damage_type(tooltip: str, reference: str, declared: str | None = None) -> str:
    """The damage type of ``@reference@``: the one tag that wraps it, or ``declared``.

    A value shown under two tags (Ahri's Q: magic on the way out, true on the
    way back) needs a declared type, and the tooltip must show it under that tag.
    """
    found = tooltip_damage_types(tooltip, reference)
    if declared is not None and len(found) > 1:
        if declared not in found:
            raise KitGenError(
                f"declared {declared!r}, tooltip wraps @{reference}@ in {sorted(found)}"
            )
        return declared
    if len(found) != 1:
        raise KitGenError(
            f"tooltip wraps @{reference}@ in {sorted(found) or 'no'} damage tags; need exactly one"
        )
    return found.pop()


class _Ability:
    def __init__(self, record: Mapping[str, Any]) -> None:
        self.record = record
        self.slot = str(record["slot"])
        self.max_rank = int(record["level_count"])
        self.calculations = {item["name"]: item["tree"] for item in record.get("calculations", [])}
        self.data_values = {
            item["name"]: item
            for item in record.get("data_values", [])
            if item.get("mode", "base") == "base"
        }

    def data_value(self, name: str) -> dict[str, Any]:
        entry = self.data_values.get(name)
        ranks = entry.get("ranks") if entry else None
        if (
            not isinstance(ranks, Sequence)
            or len(ranks) != self.max_rank
            or not all(
                isinstance(value, (int, float)) and not isinstance(value, bool) for value in ranks
            )
        ):
            raise KitGenError(
                f"{self.slot}: data value {name!r} has no {self.max_rank} rank values"
            )
        values = [_clean(value) for value in ranks]
        if len(set(values)) == 1:
            return {"op": "constant", "value": values[0]}
        return {"op": "by_rank", "values": values}

    def calculation(self, name: str, stack: tuple[str, ...] = ()) -> dict[str, Any]:
        if name in stack:
            raise KitGenError(f"{self.slot}: calculation cycle {' -> '.join((*stack, name))}")
        tree = self.calculations.get(name)
        if tree is None:
            raise KitGenError(f"{self.slot}: no calculation named {name!r}")
        return self.node(tree, (*stack, name))

    def node(self, node: Mapping[str, Any], stack: tuple[str, ...]) -> dict[str, Any]:
        kind = node.get("kind")
        if kind == "game_calculation":
            parts = node.get("parts") or []
            if not parts:
                raise KitGenError(f"{self.slot}: game calculation without parts")
            operands = [self.node(part, stack) for part in parts]
            result = operands[0] if len(operands) == 1 else {"op": "add", "operands": operands}
            multiplier = node.get("multiplier")
            if multiplier is not None:
                return {"op": "mul", "operands": [result, self.node(multiplier, stack)]}
            return result
        if kind == "number":
            return {"op": "constant", "value": _clean(node["value"])}
        if kind == "data_value":
            return self.data_value(str(node["name"]))
        if kind == "sum":
            raw_ops = node.get("operands")
            if not isinstance(raw_ops, Sequence) or not raw_ops:
                raise KitGenError(f"{self.slot}: sum node without operands")
            operands = [self.node(part, stack) for part in raw_ops]
            return operands[0] if len(operands) == 1 else {"op": "add", "operands": operands}
        if kind == "product":
            raw_ops = node.get("operands")
            if not isinstance(raw_ops, Sequence) or not raw_ops:
                raise KitGenError(f"{self.slot}: product node without operands")
            operands = [self.node(part, stack) for part in raw_ops]
            return operands[0] if len(operands) == 1 else {"op": "mul", "operands": operands}
        if kind == "by_char_level_interpolation":
            if node.get("scale_by_stat_progression_multiplier"):
                raise KitGenError(
                    f"{self.slot}: stat-progression level interpolation is not translated"
                )
            start, end = node.get("start_value"), node.get("end_value")
            if not _is_num(start) or not _is_num(end):
                raise KitGenError(f"{self.slot}: level interpolation missing start/end values")
            return {"op": "linear_by_level", "min": _clean(start), "max": _clean(end)}
        if kind == "by_char_level_named_data_values_interpolation":
            if node.get("scale_by_stat_progression_multiplier"):
                raise KitGenError(
                    f"{self.slot}: stat-progression named level interpolation is not translated"
                )
            start = self.constant_data_value(str(node.get("start_data_value")))
            end = self.constant_data_value(str(node.get("end_data_value")))
            return {"op": "linear_by_level", "min": start, "max": end}
        if kind == "by_char_level_formula":
            raw_vals = node.get("values")
            if not isinstance(raw_vals, Sequence) or isinstance(raw_vals, (str, bytes)):
                raise KitGenError(f"{self.slot}: by_char_level_formula missing values")
            if len(raw_vals) >= 19:
                selected = raw_vals[1:19]
            elif len(raw_vals) == 18:
                selected = raw_vals
            else:
                raise KitGenError(
                    f"{self.slot}: by_char_level_formula needs 18 values, got {len(raw_vals)}"
                )
            if not all(_is_num(v) for v in selected):
                raise KitGenError(f"{self.slot}: by_char_level_formula has non-numeric values")
            return {"op": "by_level", "values": [_clean(v) for v in selected]}
        if kind == "by_char_level_breakpoints":
            return _breakpoints_formula(node, self.slot)
        if kind == "stat_scaled":
            stat = node.get("stat") or {}
            name, scope = stat.get("stat"), stat.get("formula")
            if not (
                stat.get("resolved")
                and stat.get("stat_confidence") == "corroborated"
                and stat.get("formula_confidence") == "corroborated"
            ):
                raise KitGenError(f"{self.slot}: stat {name}/{scope} is not corroborated")
            if scope not in STAT_SCOPES.get(name, set()):
                raise KitGenError(f"{self.slot}: stat {name}/{scope} has no kit equivalent")
            factor = self.node(node["factor"], stack)
            return {"op": "mul", "operands": [factor, {"op": "stat", "stat": name, "scope": scope}]}
        if kind == "modified":
            base = self.calculation(str(node["base_calculation"]), stack)
            return {"op": "mul", "operands": [base, self.node(node["multiplier"], stack)]}
        if kind == "calculation_reference":
            return self.calculation(str(node["key"]), stack)
        raise KitGenError(f"{self.slot}: calculation node {kind!r} is not translated")

    def constant_data_value(self, name: str) -> float | int:
        resolved = self.data_value(name)
        if resolved.get("op") != "constant":
            raise KitGenError(f"{self.slot}: data value {name!r} changes with the rank")
        return resolved["value"]

    def custom(self, formula: Any) -> Any:
        """Resolve ``{"op": "data_value", "name": …}`` placeholders in a curated formula."""
        if isinstance(formula, Mapping):
            if formula.get("op") == "data_value":
                return self.data_value(str(formula["name"]))
            return {key: self.custom(value) for key, value in formula.items()}
        if isinstance(formula, list):
            return [self.custom(item) for item in formula]
        return formula


def _is_num(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _clean(value: float) -> float | int:
    """Shortest decimal for float32 noise such as 0.20000000298023224."""
    for digits in range(0, 8):
        rounded = round(float(value), digits)
        if abs(rounded - value) <= 1e-6 * max(1.0, abs(value)):
            return int(rounded) if rounded == int(rounded) else rounded
    return float(value)


def _breakpoints_formula(node: Mapping[str, Any], slot: str) -> dict[str, Any]:
    """Expand ``ByCharLevelBreakpointsCalculationPart`` into an 18-level ``by_level`` table."""
    level1 = node.get("level1_value")
    if not _is_num(level1):
        raise KitGenError(f"{slot}: breakpoints node missing level1_value")
    initial_per = node.get("initial_bonus_per_level")
    rate = float(initial_per) if _is_num(initial_per) else 0.0
    raw_bps = node.get("breakpoints")
    if raw_bps is not None and not isinstance(raw_bps, Sequence):
        raise KitGenError(f"{slot}: breakpoints must be a list")
    by_level: dict[int, list[Mapping[str, Any]]] = {}
    for bp in raw_bps or ():
        if not isinstance(bp, Mapping) or not isinstance(bp.get("level"), int):
            raise KitGenError(f"{slot}: malformed breakpoint entry")
        by_level.setdefault(int(bp["level"]), []).append(bp)
    current = float(level1)
    values: list[float | int] = []
    for level in range(1, 19):
        if level > 1:
            current += rate
        for bp in by_level.get(level, ()):
            add_here = bp.get("additional_bonus_at_this_level")
            if _is_num(add_here):
                current += float(add_here)
            new_rate = bp.get("bonus_per_level_at_and_after")
            if _is_num(new_rate):
                rate = float(new_rate)
        values.append(_clean(current))
    return {"op": "by_level", "values": values}


def _scale_formula(formula: dict[str, Any], scale: float | int) -> dict[str, Any]:
    if formula.get("op") == "linear_by_level":
        return {
            "op": "linear_by_level",
            "min": _clean(formula["min"] * scale),
            "max": _clean(formula["max"] * scale),
        }
    if formula.get("op") == "constant":
        return {"op": "constant", "value": _clean(formula["value"] * scale)}
    return {"op": "mul", "operands": [formula, {"op": "constant", "value": _clean(scale)}]}


def _compile_formula_ref(
    ability: _Ability | None,
    entry: Mapping[str, Any],
    content_version: Any,
    context: str,
) -> tuple[dict[str, Any], str]:
    if "calculation" in entry:
        if ability is None:
            raise KitGenError(f"{context}: no bin data for this ability")
        ref = str(entry["calculation"])
        formula = ability.calculation(ref)
        source = f"{ability.record['path']}.mSpellCalculations.{ref} ({content_version})"
    elif "data_value" in entry:
        if ability is None:
            raise KitGenError(f"{context}: no bin data for this ability")
        ref = str(entry["data_value"])
        formula = ability.data_value(ref)
        source = f"{ability.record['path']}.DataValues.{ref} ({content_version})"
    elif "formula" in entry:
        formula = ability.custom(entry["formula"]) if ability is not None else entry["formula"]
        note = entry.get("source_note") or entry.get("source") or "curated formula"
        prefix = f"{ability.record['path']} · " if ability is not None else ""
        source = f"{prefix}{note} ({content_version})"
    else:
        raise KitGenError(f"{context}: needs 'calculation', 'data_value' or 'formula'")
    if "scale" in entry:
        scale = entry["scale"]
        if not _is_num(scale):
            raise KitGenError(f"{context}: scale must be numeric")
        formula = _scale_formula(formula, scale)
    if entry.get("source_note") and "formula" not in entry:
        source = f"{source}; {entry['source_note']}"
    return formula, source


def _compile_cost(
    ability: _Ability | None,
    cost_spec: Mapping[str, Any],
    content_version: Any,
    context: str,
) -> dict[str, Any]:
    formula, source = _compile_formula_ref(ability, cost_spec, content_version, f"{context}.cost")
    return {
        "resource": str(cost_spec["resource"]),
        "formula": formula,
        "label": str(cost_spec.get("label", "Derivado")),
        "source": source,
    }


def _compile_passive_effect(
    ability: _Ability | None,
    effect_spec: Mapping[str, Any],
    content_version: Any,
    context: str,
) -> dict[str, Any]:
    effect_ctx = f"{context}.passive_effects[{effect_spec.get('id')}]"
    formula, source = _compile_formula_ref(ability, effect_spec, content_version, effect_ctx)
    compiled: dict[str, Any] = {
        "id": str(effect_spec["id"]),
        "name": str(effect_spec["name"]),
        "kind": str(effect_spec["kind"]),
        "formula": formula,
        "label": str(effect_spec.get("label", "Derivado")),
        "source": source,
    }
    for key in ("stat", "mode", "trigger", "damage_type", "input_name", "condition"):
        if key in effect_spec:
            compiled[key] = effect_spec[key]
    for key in (
        "max_stacks",
        "max_stacks_multiplier",
        "duration_seconds",
        "cooldown_seconds",
        "every",
        "stacks_required",
    ):
        if key in effect_spec:
            compiled[key] = _setting(ability, effect_spec[key], f"{effect_ctx}.{key}")
    return compiled


def compile_kit(
    extract: Mapping[str, Any], tooltips: Mapping[str, str], spec: Mapping[str, Any]
) -> dict[str, Any]:
    by_slot = {str(item["slot"]): _Ability(item) for item in extract["abilities"]}
    content_version = extract.get("content_version")
    abilities: dict[str, Any] = {}
    for slot, entry in spec["abilities"].items():
        context = f"{spec['champion']} {slot}"
        ability = by_slot.get(slot)
        tooltip_key = entry.get("tooltip")
        tooltip = tooltips.get(tooltip_key, "") if tooltip_key else ""
        cases = []
        for case in entry.get("cases", []):
            parts = []
            for part in case["parts"]:
                if ability is None:
                    raise KitGenError(f"{context}: no bin data for this ability")
                if "calculation" in part:
                    reference = part["calculation"]
                    formula = ability.calculation(reference)
                    source = f"{ability.record['path']}.mSpellCalculations.{reference}"
                else:
                    reference = part["tooltip_reference"]
                    formula = ability.custom(part["formula"])
                    source = f"{ability.record['path']} · {part['source_note']}"
                if not tooltip:
                    raise KitGenError(f"{context}: tooltip {tooltip_key!r} not found")
                declared = part.get("damage_type")
                damage_type = tooltip_damage_type(tooltip, reference, declared)
                if declared is not None and declared != damage_type:
                    raise KitGenError(
                        f"{context}.{case['id']}: declared {declared!r}, "
                        f"tooltip says {damage_type!r}"
                    )
                parts.append(
                    {
                        "damage_type": damage_type,
                        "formula": formula,
                        "label": "Derivado",
                        "source": f"{source} ({content_version})",
                        "damage_type_source": f"{tooltip_key} <{_tag(damage_type)}>",
                    }
                )
            generated = {"id": case["id"], "name": case["name"], "parts": parts}
            if case.get("recast"):
                generated["recast"] = True
            if "cost" in case:
                generated["cost"] = _compile_cost(
                    ability, case["cost"], content_version, f"{context}.{case['id']}"
                )
            cases.append(generated)
        passive_stats = []
        for item in entry.get("passive_stats", []):
            if ability is None:
                raise KitGenError(f"{context}: no bin data for this ability")
            passive_stats.append(
                {
                    "stat": item["stat"],
                    "formula": ability.data_value(item["data_value"]),
                    "label": "Derivado",
                    "source": f"{ability.record['path']}.DataValues.{item['data_value']} "
                    f"({content_version})",
                    "condition": item["condition"],
                }
            )
        max_rank = ability.max_rank if ability is not None else int(entry["max_rank"])
        abilities[slot] = {
            "name": entry["name"],
            "max_rank": max_rank,
            "cases": cases,
            "passive_stats": passive_stats,
            "not_modelled": list(entry.get("not_modelled", [])),
        }
        if "cost" in entry:
            abilities[slot]["cost"] = _compile_cost(
                ability, entry["cost"], content_version, context
            )
        if entry.get("passive_effects"):
            abilities[slot]["passive_effects"] = [
                _compile_passive_effect(ability, effect_spec, content_version, context)
                for effect_spec in entry["passive_effects"]
            ]
        for key in ("recast_window_seconds", "max_recasts", "recast_interval_seconds"):
            if key in entry:
                abilities[slot][key] = _setting(ability, entry[key], f"{context}.{key}")
    return {
        "schema": KIT_SCHEMA,
        "champion": spec["champion"],
        "label": "Derivado",
        "game_version": spec["game_version"],
        "content_version": content_version,
        "verified_against": spec.get("verified_against"),
        "source": (
            "Árboles de cálculo del bin del cliente (python -m binmodel) y marcado de los "
            "tooltips del cliente; estructura de casos curada en research/kits/"
        ),
        "abilities": abilities,
    }


def _setting(ability: _Ability | None, value: Any, context: str) -> Any:
    """A literal, or ``{"data_value": name}`` read from the bin (a constant over ranks)."""
    if not isinstance(value, Mapping):
        return value
    if ability is None:
        raise KitGenError(f"{context}: no bin data for this ability")
    resolved = ability.data_value(str(value["data_value"]))
    if resolved.get("op") != "constant":
        raise KitGenError(f"{context}: {value['data_value']} changes with the rank")
    return resolved["value"]


def _tag(damage_type: str) -> str:
    return {value: key for key, value in DAMAGE_TAGS.items()}[damage_type]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m binmodel.kitgen", description=__doc__)
    parser.add_argument("--extract", type=Path, required=True)
    parser.add_argument("--tooltips", type=Path, required=True)
    parser.add_argument("--spec", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        extract = json.loads(args.extract.read_text(encoding="utf-8"))
        tooltips = json.loads(args.tooltips.read_text(encoding="utf-8"))
        tooltips = tooltips.get("strings", tooltips)
        spec = json.loads(args.spec.read_text(encoding="utf-8"))
        kit = compile_kit(extract, tooltips, spec)
    except (OSError, ValueError, KeyError, TypeError, KitGenError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(kit, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n"
    )
    print(f"kit: {kit['champion']} ({len(kit['abilities'])} abilities) -> {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
