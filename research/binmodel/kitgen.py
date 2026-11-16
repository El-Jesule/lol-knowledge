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


def tooltip_damage_type(tooltip: str, reference: str) -> str:
    """Damage type of the tag that wraps ``@reference@`` (or ``@reference*…@``)."""
    found = {
        DAMAGE_TAGS[tag]
        for tag, inner in TAG_PATTERN.findall(tooltip)
        if re.search(rf"@{re.escape(reference)}(?:[*][^@]*)?@", inner)
    }
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
            if node.get("multiplier") is not None:
                raise KitGenError(f"{self.slot}: game calculation multipliers are not translated")
            parts = node.get("parts") or []
            if not parts:
                raise KitGenError(f"{self.slot}: game calculation without parts")
            operands = [self.node(part, stack) for part in parts]
            return operands[0] if len(operands) == 1 else {"op": "add", "operands": operands}
        if kind == "number":
            return {"op": "constant", "value": _clean(node["value"])}
        if kind == "data_value":
            return self.data_value(str(node["name"]))
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

    def custom(self, formula: Any) -> Any:
        """Resolve ``{"op": "data_value", "name": …}`` placeholders in a curated formula."""
        if isinstance(formula, Mapping):
            if formula.get("op") == "data_value":
                return self.data_value(str(formula["name"]))
            return {key: self.custom(value) for key, value in formula.items()}
        if isinstance(formula, list):
            return [self.custom(item) for item in formula]
        return formula


def _clean(value: float) -> float | int:
    """Shortest decimal for float32 noise such as 0.20000000298023224."""
    for digits in range(0, 8):
        rounded = round(float(value), digits)
        if abs(rounded - value) <= 1e-6 * max(1.0, abs(value)):
            return int(rounded) if rounded == int(rounded) else rounded
    return float(value)


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
                damage_type = tooltip_damage_type(tooltip, reference)
                declared = part.get("damage_type")
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
        if "recast_window_seconds" in entry:
            abilities[slot]["recast_window_seconds"] = entry["recast_window_seconds"]
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
    args.output.write_text(json.dumps(kit, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"kit: {kit['champion']} ({len(kit['abilities'])} abilities) -> {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
