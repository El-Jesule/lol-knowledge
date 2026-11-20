"""Draft a champion kit spec (``research/kits/<Id>.spec.json``) and curation report (CH-02).

Reads a champion bin extraction (``python -m binmodel --json``), client tooltip
strings and (optionally) the Data Dragon champion JSON, then automatically:

- discovers tooltip keys and maps calculations to ``<physicalDamage>``,
  ``<magicDamage>`` and ``<trueDamage>`` markup;
- detects calculations wrapped in two or more damage tags (e.g. Ahri's Q) and
  emits separate draft cases with explicit ``damage_type`` declarations;
- detects damage-tagged ``@DataValue@`` references absent from
  ``mSpellCalculations`` (e.g. Zaahen's E ``PercentHPDamage``);
- detects recast windows, recast intervals, recast counts and recast pairs;
- detects stat scalings with omitted ``mStat`` (default ``0`` = AP) as well as
  uncorroborated stat/scope combinations and untranslatable calculation nodes;
- detects ``<healing>``/``<shield>`` references, passive-stat DataValue
  candidates and Data Dragon health-cost hints.

Usage::

    python -m binmodel.specdraft --extract extract.json --tooltips tooltips.json \\
        [--ddragon data/current/champions/Ahri.json] \\
        [--output research/kits/Ahri.draft.spec.json] [--review review.json]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from .kitgen import DAMAGE_TAGS, TAG_PATTERN, KitGenError, _Ability, tooltip_damage_types

HEAL_SHIELD_PATTERN = re.compile(r"<(healing|shield)>(.*?)</\1>", re.DOTALL)
REF_PATTERN = re.compile(r"@([A-Za-z0-9_]+)(?:[*][^@]*)?@")

RECAST_WINDOW_TOKENS = ("recastwindow", "recastduration", "recasttime", "secondcastwindow")
RECAST_INTERVAL_TOKENS = ("recastcooldown", "recastinterval", "recastdelay", "dashcooldown")
RECAST_COUNT_TOKENS = ("maxrecasts", "recastcount", "maxcasts")
RECAST_CALC_TOKENS = ("secondhit", "recast", "cast2", "secondcast")
PASSIVE_STAT_TOKENS = (
    "armorpen",
    "magicpen",
    "lethality",
    "percentbonusad",
    "maxstacks",
    "maxstacksmultiplier",
    "falloffduration",
    "lifesteal",
    "omnivamp",
    "critchance",
)
HEALTH_COST_KEYWORDS = ("vida", "health")


def _snake(name: str) -> str:
    s1 = re.sub(r"(.)([A-Z][a-z]+)", r"\1_\2", name)
    s2 = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", s1)
    cleaned = re.sub(r"[^a-z0-9]+", "_", s2.lower()).strip("_")
    return cleaned or "case"


def _tooltip_references(tooltip: str, pattern: re.Pattern[str]) -> dict[str, set[str]]:
    refs: dict[str, set[str]] = {}
    for tag, inner in pattern.findall(tooltip):
        for ref in REF_PATTERN.findall(inner):
            refs.setdefault(ref, set()).add(tag)
    return refs


def _find_tooltip_key(
    ability: Mapping[str, Any], tooltips: Mapping[str, str], champion_id: str
) -> str | None:
    tooltip_info = ability.get("tooltip") or {}
    loc_keys = tooltip_info.get("loc_keys")
    candidates: list[str] = []
    if isinstance(loc_keys, Mapping):
        for key in ("keyTooltip", "keyTooltipExtended", "keySummary"):
            val = loc_keys.get(key)
            if isinstance(val, str) and val.strip():
                candidates.append(val.strip().lower())
    obj_name = tooltip_info.get("object_name")
    if isinstance(obj_name, str) and obj_name.strip():
        low = obj_name.strip().lower()
        if ability.get("slot") == "P":
            candidates.extend(
                [
                    f"generatedtip_passive_{low}_tooltip",
                    f"buff_{low}_tooltip",
                    f"spell_{low}_tooltip",
                ]
            )
        else:
            candidates.extend([f"spell_{low}_tooltip", f"generatedtip_spell_{low}_tooltip"])
    if ability.get("slot") == "P":
        champ_low = champion_id.lower()
        candidates.extend(
            [
                f"generatedtip_passive_{champ_low}passive_tooltip",
                f"buff_{champ_low}p_tooltip",
            ]
        )
    for key in candidates:
        if key in tooltips and tooltips[key]:
            return key
    return None


def _walk_stat_nodes(
    node: Any,
    slot: str,
    calc_name: str,
    findings: list[dict[str, Any]],
) -> None:
    if not isinstance(node, Mapping):
        return
    if node.get("kind") == "stat_scaled":
        stat = node.get("stat") or {}
        if stat.get("mStat") == 0:
            findings.append(
                {
                    "slot": slot,
                    "kind": "omitted_mstat_default",
                    "reference": calc_name,
                    "message": (
                        f"{slot}.{calc_name}: scaling omits mStat (defaults to 0 = ability_power); "
                        "verify against tooltip"
                    ),
                    "details": {
                        "mStat": stat.get("mStat"),
                        "mStatFormula": stat.get("mStatFormula"),
                        "stat": stat.get("stat"),
                        "formula": stat.get("formula"),
                    },
                }
            )
        if not (
            stat.get("resolved")
            and stat.get("stat_confidence") == "corroborated"
            and stat.get("formula_confidence") == "corroborated"
        ):
            findings.append(
                {
                    "slot": slot,
                    "kind": "uncorroborated_stat",
                    "reference": calc_name,
                    "message": (
                        f"{slot}.{calc_name}: stat {stat.get('stat')}/{stat.get('formula')} "
                        f"is {stat.get('confidence')} (needs corroboration before kitgen)"
                    ),
                    "details": {
                        "mStat": stat.get("mStat"),
                        "mStatFormula": stat.get("mStatFormula"),
                        "stat": stat.get("stat"),
                        "formula": stat.get("formula"),
                        "confidence": stat.get("confidence"),
                    },
                }
            )
    for key in ("parts", "operands"):
        children = node.get(key)
        if isinstance(children, Sequence) and not isinstance(children, (str, bytes)):
            for child in children:
                _walk_stat_nodes(child, slot, calc_name, findings)
    for key in ("factor", "multiplier", "calculation"):
        if key in node:
            _walk_stat_nodes(node[key], slot, calc_name, findings)


def _is_constant_dv(ability: _Ability, name: str) -> bool:
    try:
        resolved = ability.data_value(name)
    except KitGenError:
        return False
    return resolved.get("op") == "constant"


def _detect_recast_settings(
    slot: str,
    ability_record: Mapping[str, Any],
    helper: _Ability,
    findings: list[dict[str, Any]],
) -> dict[str, Any]:
    settings: dict[str, Any] = {}
    for dv_name in helper.data_values:
        low = dv_name.lower()
        if any(token in low for token in RECAST_WINDOW_TOKENS) and _is_constant_dv(helper, dv_name):
            settings.setdefault("recast_window_seconds", {"data_value": dv_name})
            findings.append(
                {
                    "slot": slot,
                    "kind": "recast_detected",
                    "reference": dv_name,
                    "message": f"{slot}: detected recast window DataValue {dv_name!r}",
                    "details": {"setting": "recast_window_seconds", "data_value": dv_name},
                }
            )
        elif any(token in low for token in RECAST_INTERVAL_TOKENS) and _is_constant_dv(
            helper, dv_name
        ):
            settings.setdefault("recast_interval_seconds", {"data_value": dv_name})
            findings.append(
                {
                    "slot": slot,
                    "kind": "recast_detected",
                    "reference": dv_name,
                    "message": f"{slot}: detected recast interval DataValue {dv_name!r}",
                    "details": {"setting": "recast_interval_seconds", "data_value": dv_name},
                }
            )
        elif any(token in low for token in RECAST_COUNT_TOKENS) and _is_constant_dv(
            helper, dv_name
        ):
            val = helper.constant_data_value(dv_name)
            findings.append(
                {
                    "slot": slot,
                    "kind": "recast_detected",
                    "reference": dv_name,
                    "message": (
                        f"{slot}: detected cast/recast count DataValue {dv_name!r} = {val} "
                        "(check whether max_recasts = value - 1)"
                    ),
                    "details": {"setting": "max_recasts", "data_value": dv_name, "value": val},
                }
            )
    for child in ability_record.get("child_spells") or ():
        child_name = str(child.get("name", ""))
        low = child_name.lower()
        if any(token in low for token in ("recast", "two", "second", "2")):
            findings.append(
                {
                    "slot": slot,
                    "kind": "recast_detected",
                    "reference": child_name,
                    "message": f"{slot}: child spell {child_name!r} suggests a recast ability",
                    "details": {"child_spell": child_name},
                }
            )
    return settings


def _ddragon_spell_by_slot(ddragon: Mapping[str, Any] | None) -> dict[str, Mapping[str, Any]]:
    if not isinstance(ddragon, Mapping):
        return {}
    spells = ddragon.get("spells")
    if not isinstance(spells, Sequence) or isinstance(spells, (str, bytes)):
        return {}
    slots = ("Q", "W", "E", "R")
    return {
        slot: spell
        for slot, spell in zip(slots, spells, strict=False)
        if isinstance(spell, Mapping)
    }


def _display_name(
    slot: str,
    ability_record: Mapping[str, Any],
    tooltips: Mapping[str, str],
    ddragon: Mapping[str, Any] | None,
) -> str:
    if isinstance(ddragon, Mapping):
        if slot == "P" and isinstance(ddragon.get("passive"), Mapping):
            name = ddragon["passive"].get("name")
            if isinstance(name, str) and name.strip():
                return name.strip()
        dd_spell = _ddragon_spell_by_slot(ddragon).get(slot)
        if dd_spell and isinstance(dd_spell.get("name"), str) and dd_spell["name"].strip():
            return dd_spell["name"].strip()
    loc_keys = (ability_record.get("tooltip") or {}).get("loc_keys") or {}
    if isinstance(loc_keys, Mapping):
        key_name = loc_keys.get("keyName")
        if isinstance(key_name, str) and key_name.lower() in tooltips:
            return tooltips[key_name.lower()]
    return str(ability_record.get("name") or slot)


def draft_spec(
    extract: Mapping[str, Any],
    tooltips: Mapping[str, str],
    *,
    ddragon: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Generate a draft kit spec and structured curation findings for one champion."""
    champion_info = extract.get("champion") or {}
    champion_id = str(champion_info.get("id") or champion_info.get("name") or "Unknown")
    game_version = str(extract.get("game_version") or "16.23")
    dd_spells = _ddragon_spell_by_slot(ddragon)

    findings: list[dict[str, Any]] = []
    abilities_spec: dict[str, Any] = {}

    for record in extract.get("abilities") or ():
        slot = str(record["slot"])
        if slot not in {"P", "Q", "W", "E", "R"}:
            continue
        helper = _Ability(record)
        tooltip_key = _find_tooltip_key(record, tooltips, champion_id)
        tooltip = tooltips.get(tooltip_key, "") if tooltip_key else ""
        if tooltip_key is None:
            findings.append(
                {
                    "slot": slot,
                    "kind": "missing_tooltip",
                    "reference": str(record.get("name", slot)),
                    "message": f"{slot}: no matching tooltip key found in tooltip strings",
                    "details": {},
                }
            )

        # 1. Inspect every calculation for omitted mStat, uncorroborated stats & translatability.
        translatable: dict[str, bool] = {}
        for calc_entry in record.get("calculations") or ():
            calc_name = str(calc_entry["name"])
            _walk_stat_nodes(calc_entry.get("tree"), slot, calc_name, findings)
            try:
                helper.calculation(calc_name)
                translatable[calc_name] = True
            except KitGenError as exc:
                translatable[calc_name] = False
                findings.append(
                    {
                        "slot": slot,
                        "kind": "untranslatable_node",
                        "reference": calc_name,
                        "message": f"{slot}.{calc_name}: {exc}",
                        "details": {"error": str(exc)},
                    }
                )

        # 2. Discover damage-tagged calculations, dual damage types & damage-tagged DataValues.
        cases: list[dict[str, Any]] = []
        used_case_ids: set[str] = set()
        referenced_calcs: set[str] = set()
        recast_settings = _detect_recast_settings(slot, record, helper, findings)

        if tooltip:
            damage_refs = _tooltip_references(tooltip, TAG_PATTERN)
            for calc_name in helper.calculations:
                found_types = sorted(tooltip_damage_types(tooltip, calc_name))
                if not found_types:
                    continue
                referenced_calcs.add(calc_name)
                is_recast_calc = any(token in calc_name.lower() for token in RECAST_CALC_TOKENS)
                if is_recast_calc:
                    findings.append(
                        {
                            "slot": slot,
                            "kind": "recast_detected",
                            "reference": calc_name,
                            "message": (
                                f"{slot}.{calc_name}: name suggests a recast damage calculation"
                            ),
                            "details": {"calculation": calc_name},
                        }
                    )
                if len(found_types) > 1:
                    findings.append(
                        {
                            "slot": slot,
                            "kind": "dual_damage_type",
                            "reference": calc_name,
                            "message": (
                                f"{slot}.{calc_name}: wrapped in multiple damage tags "
                                f"{found_types}; declare damage_type per case"
                            ),
                            "details": {"damage_types": found_types},
                        }
                    )
                    for dtype in found_types:
                        case_id = _unique_id(f"{_snake(calc_name)}_{dtype}", used_case_ids)
                        case_entry: dict[str, Any] = {
                            "id": case_id,
                            "name": f"{calc_name} ({dtype})",
                            "parts": [{"calculation": calc_name, "damage_type": dtype}],
                        }
                        if is_recast_calc:
                            case_entry["recast"] = True
                        cases.append(case_entry)
                elif translatable.get(calc_name):
                    case_id = _unique_id(_snake(calc_name), used_case_ids)
                    case_entry = {
                        "id": case_id,
                        "name": calc_name,
                        "parts": [{"calculation": calc_name}],
                    }
                    if is_recast_calc:
                        case_entry["recast"] = True
                    cases.append(case_entry)

            # Tooltip damage references that point to DataValues instead of calculations
            for ref, raw_tags in sorted(damage_refs.items()):
                if ref in helper.calculations or ref not in helper.data_values:
                    continue
                dtypes = sorted(DAMAGE_TAGS[t] for t in raw_tags if t in DAMAGE_TAGS)
                findings.append(
                    {
                        "slot": slot,
                        "kind": "tooltip_data_value_damage",
                        "reference": ref,
                        "message": (
                            f"{slot}: @{ref}@ is a DataValue wrapped in damage tags {dtypes} "
                            "(not in mSpellCalculations; curate a tooltip_reference formula)"
                        ),
                        "details": {
                            "damage_types": dtypes,
                            "ranks": helper.data_values[ref].get("ranks"),
                        },
                    }
                )

            # Healing / shield calculations in tooltip
            hs_refs = _tooltip_references(tooltip, HEAL_SHIELD_PATTERN)
            for ref, raw_tags in sorted(hs_refs.items()):
                if ref in helper.calculations or ref in helper.data_values:
                    findings.append(
                        {
                            "slot": slot,
                            "kind": "healing_or_shield_calc",
                            "reference": ref,
                            "message": (
                                f"{slot}: @{ref}@ wrapped in {sorted(raw_tags)} "
                                f"(translatable={translatable.get(ref, ref in helper.data_values)})"
                            ),
                            "details": {
                                "tags": sorted(raw_tags),
                                "is_calculation": ref in helper.calculations,
                                "translatable": translatable.get(ref, ref in helper.data_values),
                            },
                        }
                    )

        # 3. Passive-stat DataValue candidates
        for dv_name in helper.data_values:
            low = dv_name.lower()
            if any(token in low for token in PASSIVE_STAT_TOKENS):
                findings.append(
                    {
                        "slot": slot,
                        "kind": "passive_stat_candidate",
                        "reference": dv_name,
                        "message": f"{slot}: DataValue {dv_name!r} may feed passive_stats/effects",
                        "details": {"ranks": helper.data_values[dv_name].get("ranks")},
                    }
                )

        # 4. Data Dragon health-cost hint
        dd_spell = dd_spells.get(slot)
        if dd_spell is not None:
            raw_costs = dd_spell.get("cost") or []
            cost_type = str(dd_spell.get("costType") or "")
            if all(v == 0 for v in raw_costs) and any(
                kw in cost_type.lower() for kw in HEALTH_COST_KEYWORDS
            ):
                findings.append(
                    {
                        "slot": slot,
                        "kind": "health_cost_needed",
                        "reference": str(dd_spell.get("id", slot)),
                        "message": (
                            f"{slot}: Data Dragon costType {cost_type!r} indicates a health cost "
                            "(add explicit cost spec)"
                        ),
                        "details": {"cost_type": cost_type},
                    }
                )

        not_modelled = [
            f"Cálculo sin caso curado: {name}"
            for name in helper.calculations
            if name not in referenced_calcs
        ]
        ability_entry: dict[str, Any] = {
            "name": _display_name(slot, record, tooltips, ddragon),
        }
        if slot == "P":
            ability_entry["max_rank"] = 1
        if tooltip_key:
            ability_entry["tooltip"] = tooltip_key
        if cases:
            ability_entry["cases"] = cases
        ability_entry.update(recast_settings)
        if not_modelled:
            ability_entry["not_modelled"] = not_modelled
        abilities_spec[slot] = ability_entry

    by_kind: dict[str, int] = {}
    for item in findings:
        by_kind[item["kind"]] = by_kind.get(item["kind"], 0) + 1

    return {
        "spec": {
            "champion": champion_id,
            "game_version": game_version,
            "abilities": abilities_spec,
        },
        "review": {
            "champion": champion_id,
            "summary": {
                "abilities": len(abilities_spec),
                "total_findings": len(findings),
                "by_kind": dict(sorted(by_kind.items())),
            },
            "findings": findings,
        },
    }


def _unique_id(base: str, used: set[str]) -> str:
    candidate = base
    suffix = 2
    while candidate in used:
        candidate = f"{base}_{suffix}"
        suffix += 1
    used.add(candidate)
    return candidate


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m binmodel.specdraft", description=__doc__)
    parser.add_argument("--extract", type=Path, required=True)
    parser.add_argument("--tooltips", type=Path, required=True)
    parser.add_argument("--ddragon", type=Path, default=None)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--review", type=Path, default=None)
    args = parser.parse_args(argv)
    try:
        extract = json.loads(args.extract.read_text(encoding="utf-8"))
        tooltips_raw = json.loads(args.tooltips.read_text(encoding="utf-8"))
        tooltips = tooltips_raw.get("strings", tooltips_raw)
        ddragon = (
            json.loads(args.ddragon.read_text(encoding="utf-8"))
            if args.ddragon is not None
            else None
        )
        result = draft_spec(extract, tooltips, ddragon=ddragon)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(result["spec"], indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
    if args.review is not None:
        args.review.parent.mkdir(parents=True, exist_ok=True)
        args.review.write_text(
            json.dumps(result["review"], indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
    if args.output is None and args.review is None:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        summary = result["review"]["summary"]
        print(
            f"specdraft: {result['review']['champion']} "
            f"({summary['abilities']} abilities, {summary['total_findings']} findings)"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
