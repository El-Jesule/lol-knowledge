"""Generic discovery and traversal of champion spell calculation trees."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from .model import DataValue, Diagnostic
from .registry import Registry

SLOTS = ("Q", "W", "E", "R")


def json_pointer(path: str) -> str:
    """Build an RFC 6901 pointer from a slash-separated object path."""
    parts = [part.replace("~", "~0").replace("/", "~1") for part in path.split("/") if part]
    return "/" + "/".join(parts)


class TraversalError(Exception):
    """The source document does not have the expected shape."""


@dataclass
class TraversalContext:
    """State shared by the recursive traversal."""

    document: Mapping[str, Any]
    registry: Registry
    source_sha256: str
    content_version: str
    diagnostics: list[Diagnostic] = field(default_factory=list)
    unresolved: list[dict[str, Any]] = field(default_factory=list)
    spell_path: str = ""

    def pointer(self, path: str) -> str:
        return json_pointer(path)

    def provenance(self, json_pointer: str) -> dict[str, Any]:
        return {
            "source_path": self.spell_path,
            "json_pointer": json_pointer,
            "source_sha256": self.source_sha256,
            "content_version": self.content_version,
        }

    def diagnostic(
        self,
        severity: str,
        code: str,
        path: str,
        message: str,
        **data: Any,
    ) -> Diagnostic:
        item = Diagnostic(
            severity=severity,
            code=code,
            path=path,
            message=message,
            data=dict(data),
        )
        self.diagnostics.append(item)
        return item


def find_champion_root(document: Mapping[str, Any]) -> tuple[str, Mapping[str, Any]]:
    """Find the unique ``CharacterRecord`` in a champion bin export."""
    candidates: list[tuple[str, Mapping[str, Any]]] = []
    for path, node in document.items():
        if not isinstance(node, Mapping):
            continue
        if node.get("__type") == "CharacterRecord" or (
            "mCharacterName" in node and "baseDamageModifiable" in node
        ):
            candidates.append((path, node))
    if len(candidates) != 1:
        raise TraversalError(f"expected exactly one CharacterRecord, found {len(candidates)}")
    return candidates[0]


def _object(document: Mapping[str, Any], path: str) -> Mapping[str, Any]:
    node = document.get(path)
    if not isinstance(node, Mapping):
        raise TraversalError(f"missing object {path}")
    return node


def _number_list(value: Any, context: str) -> list[float] | None:
    if value is None:
        return None
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise TraversalError(f"{context} must be a list")
    result: list[float] = []
    for item in value:
        if isinstance(item, bool) or not isinstance(item, (int, float)):
            raise TraversalError(f"{context} contains a non-numeric value: {item!r}")
        result.append(float(item))
    return result


def ranked_values(
    raw: list[float] | None,
    level_count: int | None,
    context: str,
    diagnostics: list[Diagnostic],
) -> list[float] | None:
    """Select ranks 1..level_count from a bin array.

    Bin spell arrays reserve index 0 for rank 0. Rank 1 is ``raw[1]`` even when
    ``raw[0]`` is not zero (for example ``QCoeff`` starts at 0.15 and rank 1 is
    0.20, or ``EndDamage`` starts at 100 and rank 1 is 250). When an array has
    exactly ``level_count`` entries it is treated as already rank-aligned.
    Anything else is a diagnostic, not a guess.
    """
    if raw is None:
        return None
    if level_count is None:
        diagnostics.append(
            Diagnostic(
                "warning",
                "rank_count_unknown",
                context,
                "Cannot select ranks without a level count.",
            )
        )
        return None
    if level_count < 1:
        diagnostics.append(
            Diagnostic("error", "invalid_level_count", context, f"level_count={level_count}")
        )
        return None
    if level_count == 1 and len(raw) == 1:
        return list(raw)
    if len(raw) == level_count:
        diagnostics.append(
            Diagnostic(
                "warning",
                "ambiguous_rank_alignment",
                context,
                (
                    f"array length {len(raw)} equals level_count; cannot tell whether "
                    "index 0 is rank 0 or rank 1. Raw values are preserved."
                ),
            )
        )
        return None
    if len(raw) > level_count:
        return list(raw[1 : level_count + 1])
    diagnostics.append(
        Diagnostic(
            "error",
            "rank_array_too_short",
            context,
            f"array has {len(raw)} values for {level_count} ranks",
        )
    )
    return None


def tooltip_level_count(spell: Mapping[str, Any], path: str) -> int | None:
    """Read the rank count from the tooltip level-up list."""
    client = spell.get("mClientData")
    if not isinstance(client, Mapping):
        return None
    tooltip = client.get("mTooltipData")
    if not isinstance(tooltip, Mapping):
        return None
    lists = tooltip.get("mLists")
    if not isinstance(lists, Mapping):
        return None
    level_up = lists.get("LevelUp")
    if not isinstance(level_up, Mapping):
        return None
    value = level_up.get("levelCount")
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        return None
    return value


def discover_abilities(
    document: Mapping[str, Any],
    root: Mapping[str, Any],
    diagnostics: list[Diagnostic],
) -> list[dict[str, Any]]:
    """Return ordered passive/Q/W/E/R descriptors without champion-specific names."""
    spell_paths = root.get("spells")
    spell_paths = list(spell_paths) if isinstance(spell_paths, list) else []
    ability_paths = root.get("mAbilities")
    ability_paths = list(ability_paths) if isinstance(ability_paths, list) else []

    ability_by_root: dict[str, dict[str, Any]] = {}
    for path in ability_paths:
        node = document.get(path)
        if not isinstance(node, Mapping):
            continue
        root_spell = node.get("mRootSpell")
        if isinstance(root_spell, str):
            ability_by_root[root_spell] = {
                "ability_path": path,
                "children": list(node.get("mChildSpells") or []),
                "name": node.get("mName"),
            }

    described: list[dict[str, Any]] = []
    passive = root.get("mCharacterPassiveSpell")
    if isinstance(passive, str):
        described.append(
            {
                "slot": "P",
                "ability_id": "passive",
                "path": passive,
                "root_spell": passive,
                "ability_path": ability_by_root.get(passive, {}).get("ability_path"),
                "children": ability_by_root.get(passive, {}).get("children", []),
                "is_passive": True,
            }
        )
    else:
        diagnostics.append(
            Diagnostic(
                "warning",
                "passive_missing",
                "CharacterRecords/Root",
                "No mCharacterPassiveSpell found.",
            )
        )

    for index, path in enumerate(spell_paths[:4]):
        if not isinstance(path, str):
            continue
        slot = SLOTS[index]
        described.append(
            {
                "slot": slot,
                "ability_id": slot.lower(),
                "path": path,
                "root_spell": path,
                "ability_path": ability_by_root.get(path, {}).get("ability_path"),
                "children": ability_by_root.get(path, {}).get("children", []),
                "is_passive": False,
            }
        )
    if len(spell_paths) > 4:
        for index, path in enumerate(spell_paths[4:], start=5):
            if isinstance(path, str):
                described.append(
                    {
                        "slot": f"SPELL{index}",
                        "ability_id": f"spell{index}",
                        "path": path,
                        "root_spell": path,
                        "ability_path": ability_by_root.get(path, {}).get("ability_path"),
                        "children": ability_by_root.get(path, {}).get("children", []),
                        "is_passive": False,
                    }
                )
    return described


def extract_data_values(
    spell: Mapping[str, Any],
    *,
    spell_path: str,
    level_count: int | None,
    diagnostics: list[Diagnostic],
    mode: str = "base",
    entries: Sequence[Any] | None = None,
    source_sha256: str = "",
    content_version: str = "",
    source_path_prefix: str | None = None,
    pointer_prefix: str | None = None,
) -> list[DataValue]:
    """Extract named data values, preserving missing ones."""
    if entries is None:
        entries = spell.get("DataValues")
    if entries is None:
        return []
    if not isinstance(entries, Sequence) or isinstance(entries, (str, bytes)):
        raise TraversalError(f"{spell_path}.mSpell.DataValues must be a list")
    source_base = source_path_prefix or f"{spell_path}.mSpell.DataValues"
    pointer_base = pointer_prefix or json_pointer(f"{spell_path}/mSpell/DataValues")

    values: list[DataValue] = []
    for index, entry in enumerate(entries):
        if not isinstance(entry, Mapping) or not isinstance(entry.get("name"), str):
            diagnostics.append(
                Diagnostic(
                    "error",
                    "malformed_data_value",
                    f"{source_base}[{index}]",
                    "DataValue entry has no string name.",
                )
            )
            continue
        name = entry["name"]
        raw = _number_list(entry.get("values"), f"{source_base}[{name!r}].values")
        ranks = ranked_values(
            raw,
            level_count,
            f"{source_base}[{name!r}].values",
            diagnostics,
        )
        status = "source_explicit"
        notes = ""
        if raw is None:
            status = "unverified"
            notes = "DataValue has no values array; it is a reference only."
            diagnostics.append(
                Diagnostic(
                    "warning",
                    "missing_data_value_values",
                    f"{source_base}[{name!r}]",
                    f"DataValue {name!r} has no values.",
                    data={"name": name},
                )
            )
        elif ranks is None:
            status = "unverified"
            notes = "Rank selection failed; raw values are preserved."
        values.append(
            DataValue(
                name=name,
                source_path=f"{source_base}[{name!r}]",
                raw_values=raw,
                ranks=ranks,
                level_count=level_count,
                mode=mode,
                status=status,
                notes=notes,
                provenance={
                    "source_path": spell_path,
                    "json_pointer": f"{pointer_base}/{index}",
                    "source_sha256": source_sha256,
                    "content_version": content_version,
                },
            )
        )
    return values


def extract_mode_overrides(
    spell: Mapping[str, Any],
    *,
    spell_path: str,
    level_count: int | None,
    diagnostics: list[Diagnostic],
    source_sha256: str = "",
    content_version: str = "",
) -> list[DataValue]:
    """Extract ``DataValuesModeOverride`` without merging it into the base mode."""
    overrides = spell.get("DataValuesModeOverride")
    if not isinstance(overrides, Mapping):
        return []
    result: list[DataValue] = []
    for mode, payload in overrides.items():
        if not isinstance(payload, Mapping):
            continue
        entries = payload.get("SpellDataValues")
        if not isinstance(entries, Sequence) or isinstance(entries, (str, bytes)):
            continue
        result.extend(
            extract_data_values(
                spell,
                spell_path=spell_path,
                level_count=level_count,
                diagnostics=diagnostics,
                mode=str(mode),
                entries=entries,
                source_sha256=source_sha256,
                content_version=content_version,
                source_path_prefix=(
                    f"{spell_path}.mSpell.DataValuesModeOverride[{mode!r}].SpellDataValues"
                ),
                pointer_prefix=json_pointer(
                    f"{spell_path}/mSpell/DataValuesModeOverride/{mode}/SpellDataValues"
                ),
            )
        )
    return result


def _vector(
    spell: Mapping[str, Any],
    key: str,
    *,
    spell_path: str,
    level_count: int | None,
    diagnostics: list[Diagnostic],
    legacy_key: str | None = None,
) -> dict[str, Any] | None:
    value = spell.get(key)
    raw: list[float] | None = None
    if isinstance(value, Mapping):
        raw = _number_list(value.get("values"), f"{spell_path}.mSpell.{key}.values")
    elif value is not None:
        raw = _number_list(value, f"{spell_path}.mSpell.{key}")
    if raw is None and legacy_key:
        legacy = spell.get(legacy_key)
        if legacy is not None:
            raw = _number_list(legacy, f"{spell_path}.mSpell.{legacy_key}")
            if raw is not None:
                diagnostics.append(
                    Diagnostic(
                        "warning",
                        "vector_fallback",
                        f"{spell_path}.mSpell.{key}",
                        f"{key} missing; used legacy {legacy_key}.",
                    )
                )
    if raw is None:
        return None
    ranks = ranked_values(raw, level_count, f"{spell_path}.mSpell.{key}", diagnostics)
    result: dict[str, Any] = {
        "source_path": f"{spell_path}.mSpell.{key}",
        "raw_values": raw,
        "ranks": ranks,
        "level_count": level_count,
        "status": "source_explicit" if ranks is not None else "unverified",
    }
    if legacy_key and legacy_key in spell:
        legacy_raw = _number_list(spell.get(legacy_key), f"{spell_path}.mSpell.{legacy_key}")
        result["legacy"] = {
            "source_path": f"{spell_path}.mSpell.{legacy_key}",
            "raw_values": legacy_raw,
            "matches": legacy_raw == raw,
        }
    return result


def extract_cooldown(
    spell: Mapping[str, Any],
    *,
    spell_path: str,
    level_count: int | None,
    diagnostics: list[Diagnostic],
) -> dict[str, Any] | None:
    """Extract the effective cooldown and keep ``cooldownTime`` as diagnostics."""
    effective = spell.get("Cooldown")
    if isinstance(effective, Mapping):
        result = _vector(
            spell,
            "Cooldown",
            spell_path=spell_path,
            level_count=level_count,
            diagnostics=diagnostics,
            legacy_key="cooldownTime",
        )
        if result is not None:
            result["effective"] = True
        return result
    result = _vector(
        spell,
        "cooldownTime",
        spell_path=spell_path,
        level_count=level_count,
        diagnostics=diagnostics,
    )
    if result is not None:
        result["effective"] = True
        diagnostics.append(
            Diagnostic(
                "warning",
                "cooldown_fallback",
                f"{spell_path}.mSpell.Cooldown",
                "Cooldown object missing; used cooldownTime.",
            )
        )
    return result


def extract_tooltip(spell: Mapping[str, Any], spell_path: str) -> dict[str, Any]:
    """Extract the tooltip keys and level-up lists used for rank counts and labels."""
    client = spell.get("mClientData")
    if not isinstance(client, Mapping):
        return {}
    tooltip = client.get("mTooltipData")
    if not isinstance(tooltip, Mapping):
        return {}
    lists = tooltip.get("mLists")
    result: dict[str, Any] = {
        "object_name": tooltip.get("mObjectName"),
        "loc_keys": tooltip.get("mLocKeys"),
        "lists": {},
        "source_path": f"{spell_path}.mSpell.mClientData.mTooltipData",
    }
    if isinstance(lists, Mapping):
        for list_name, list_value in lists.items():
            if not isinstance(list_value, Mapping):
                continue
            elements = []
            for element in list_value.get("Elements") or []:
                if not isinstance(element, Mapping):
                    continue
                elements.append(
                    {
                        "type": element.get("type"),
                        "type_index": element.get("typeIndex"),
                        "name_override": element.get("nameOverride"),
                        "multiplier": element.get("multiplier"),
                        "style": element.get("Style"),
                    }
                )
            result["lists"][list_name] = {
                "level_count": list_value.get("levelCount"),
                "elements": elements,
            }
    return result


def _field_key(raw: Mapping[str, Any], hash_key: str) -> str:
    """Return the spelling used by the document for a hashed field."""
    for key in (f"{{{hash_key}}}", f"0x{hash_key}", hash_key):
        if key in raw:
            return key
    return f"{{{hash_key}}}"


def _field(raw: Mapping[str, Any], hash_key: str, default: Any = None) -> Any:
    """Read a hashed field that CDragon may spell with braces or a 0x prefix."""
    for key in (f"{{{hash_key}}}", f"0x{hash_key}", hash_key):
        if key in raw:
            return raw[key]
    return default


def _node_base(
    context: TraversalContext,
    raw: Mapping[str, Any],
    pointer: str,
) -> dict[str, Any]:
    return {
        "type": context.registry.describe_type(raw.get("__type")),
        "provenance": context.provenance(pointer),
    }


def _unresolved(
    context: TraversalContext,
    raw: Any,
    pointer: str,
    reason: str,
    **extra: Any,
) -> dict[str, Any]:
    node = {
        "kind": "unresolved",
        "reason": reason,
        "raw": raw,
    }
    if isinstance(raw, Mapping):
        node.update(_node_base(context, raw, pointer))
    else:
        node["type"] = None
        node["provenance"] = context.provenance(pointer)
    node.update(extra)
    context.unresolved.append(
        {
            "pointer": pointer,
            "source_path": context.spell_path,
            "reason": reason,
            "type": node.get("type"),
            "raw": raw if isinstance(raw, (str, int, float, bool)) else None,
        }
    )
    return node


def _stat_part(
    context: TraversalContext,
    raw: Mapping[str, Any],
    pointer: str,
) -> dict[str, Any]:
    from .stats import stat_ref

    stat = stat_ref(raw.get("mStat"), raw.get("mStatFormula"))
    if not stat["resolved"]:
        context.diagnostic(
            "warning",
            "unresolved_stat",
            pointer,
            f"Unresolved mStat/mStatFormula: {stat['mStat']}/{stat['mStatFormula']}",
            stat=stat,
        )
    node = _node_base(context, raw, pointer)
    node["kind"] = "stat_scaled"
    node["stat"] = stat
    return node


def parse_part(
    part: Any,
    *,
    context: TraversalContext,
    pointer: str,
) -> dict[str, Any]:
    """Parse one calculation part, preserving unknown structures."""
    if not isinstance(part, Mapping):
        return _unresolved(context, part, pointer, "part is not an object")
    type_value = part.get("__type")

    if type_value == "NamedDataValueCalculationPart":
        node = _node_base(context, part, pointer)
        node["kind"] = "data_value"
        node["name"] = part.get("mDataValue")
        return node

    if type_value == "NumberCalculationPart":
        node = _node_base(context, part, pointer)
        node["kind"] = "number"
        node["value"] = part.get("mNumber")
        return node

    if type_value == "EffectValueCalculationPart":
        node = _node_base(context, part, pointer)
        node["kind"] = "effect_value"
        node["effect_index"] = part.get("mEffectIndex")
        node["resolved"] = False
        context.unresolved.append(
            {
                "pointer": pointer,
                "source_path": context.spell_path,
                "reason": "effect value requires SpellEffectAmount data",
                "type": node.get("type"),
                "raw": None,
            }
        )
        return node

    if type_value == "StatByNamedDataValueCalculationPart":
        node = _stat_part(context, part, pointer)
        node["factor"] = {
            "kind": "data_value",
            "name": part.get("mDataValue"),
        }
        return node

    if type_value == "StatByCoefficientCalculationPart":
        node = _stat_part(context, part, pointer)
        node["factor"] = {
            "kind": "number",
            "value": part.get("mCoefficient"),
        }
        return node

    if type_value == "StatBySubPartCalculationPart":
        node = _stat_part(context, part, pointer)
        node["factor"] = parse_part(
            part.get("mSubpart"), context=context, pointer=f"{pointer}/mSubpart"
        )
        return node

    if type_value == "ProductOfSubPartsCalculationPart":
        node = _node_base(context, part, pointer)
        node["kind"] = "product"
        node["operands"] = [
            parse_part(part.get("mPart1"), context=context, pointer=f"{pointer}/mPart1"),
            parse_part(part.get("mPart2"), context=context, pointer=f"{pointer}/mPart2"),
        ]
        return node

    if type_value == "SumOfSubPartsCalculationPart":
        node = _node_base(context, part, pointer)
        node["kind"] = "sum"
        node["operands"] = [
            parse_part(item, context=context, pointer=f"{pointer}/mSubparts/{index}")
            for index, item in enumerate(part.get("mSubparts") or [])
        ]
        return node

    if type_value == "ByCharLevelBreakpointsCalculationPart":
        node = _node_base(context, part, pointer)
        node["kind"] = "by_char_level_breakpoints"
        node["level1_value"] = part.get("mLevel1Value")
        node["initial_bonus_per_level"] = part.get("mInitialBonusPerLevel", 0.0)
        node["breakpoints"] = [
            {
                "level": item.get("mLevel"),
                "additional_bonus_at_this_level": item.get("mAdditionalBonusAtThisLevel"),
                "bonus_per_level_at_and_after": item.get("mBonusPerLevelAtAndAfter", 0.0),
                "provenance": context.provenance(f"{pointer}/mBreakpoints/{index}"),
            }
            for index, item in enumerate(part.get("mBreakpoints") or [])
            if isinstance(item, Mapping)
        ]
        return node

    if type_value == "ByCharLevelFormulaCalculationPart":
        node = _node_base(context, part, pointer)
        node["kind"] = "by_char_level_formula"
        node["values"] = part.get("values") or part.get("mValues")
        return node

    if type_value == "ByCharLevelInterpolationCalculationPart":
        node = _node_base(context, part, pointer)
        node["kind"] = "by_char_level_interpolation"
        node["start_value"] = part.get("mStartValue")
        node["end_value"] = part.get("mEndValue")
        node["scale_by_stat_progression_multiplier"] = part.get(
            "mScaleByStatProgressionMultiplier", False
        )
        node["scale_past_default_max_level"] = part.get("mScalePastDefaultMaxLevel", True)
        return node

    if type_value == "GameCalculationModified":
        node = _node_base(context, part, pointer)
        node["kind"] = "modified"
        node["tooltip_only"] = part.get("tooltipOnly", False)
        node["base_calculation"] = part.get("mModifiedGameCalculation")
        multiplier = part.get("mMultiplier")
        node["multiplier"] = (
            parse_part(multiplier, context=context, pointer=f"{pointer}/mMultiplier")
            if isinstance(multiplier, Mapping)
            else None
        )
        return node

    if type_value == "{ee18a47b}":
        node = _node_base(context, part, pointer)
        node["kind"] = "by_char_level_named_data_values_interpolation"
        node["start_data_value"] = part.get("StartDataValue")
        node["end_data_value"] = part.get("EndDataValue")
        node["scale_past_default_max_level"] = _field(part, "32a393a", True)
        node["scale_by_stat_progression_multiplier"] = _field(part, "f4e470e6", False)
        return node

    if type_value == "{4ce08984}":
        node = _node_base(context, part, pointer)
        node["kind"] = "by_char_level_named_breakpoints"
        node["level1_data_value"] = _field(part, "91d404a5")
        node["bonus_per_level_data_value"] = _field(part, "bbd778a2")
        breakpoints_key = _field_key(part, "9823b29a")
        node["breakpoints"] = [
            {
                "level": item.get("level"),
                "additional_bonus_data_value": _field(item, "ae9b464d"),
                "bonus_per_level_at_and_after_data_value": _field(item, "b0d8b2ac"),
                "provenance": context.provenance(f"{pointer}/{breakpoints_key}/{index}"),
            }
            for index, item in enumerate(_field(part, "9823b29a") or [])
            if isinstance(item, Mapping)
        ]
        return node

    if type_value == "{f3cbe7b2}":
        node = _node_base(context, part, pointer)
        node["kind"] = "calculation_reference"
        node["key"] = part.get("mSpellCalculationKey")
        return node

    if type_value == "{ba007871}":
        node = _node_base(context, part, pointer)
        node["kind"] = "external_calculation_reference"
        node["source_object"] = part.get("SourceObject")
        node["key"] = part.get("CalculationKey")
        return node

    if type_value == "{9e9e2e5c}":
        node = _node_base(context, part, pointer)
        node["kind"] = "external_data_value"
        node["source_object"] = part.get("SourceObject")
        node["name"] = part.get("DataValue")
        return node

    if type_value == "{b09016f6}":
        node = _node_base(context, part, pointer)
        node["kind"] = "bot_effect"
        node["effect_tag"] = part.get("EffectTag")
        calculation = part.get("EffectCalculation")
        node["calculation"] = (
            parse_calculation(calculation, context=context, pointer=f"{pointer}/EffectCalculation")
            if isinstance(calculation, Mapping)
            else None
        )
        return node

    return _unresolved(
        context,
        part,
        pointer,
        "unknown calculation part type",
        type_hash=context.registry.describe_type(type_value).get("type_hash"),
    )


def parse_calculation(
    calculation: Mapping[str, Any],
    *,
    context: TraversalContext,
    pointer: str,
) -> dict[str, Any]:
    """Parse a ``GameCalculation`` or ``GameCalculationModified`` object."""
    type_value = calculation.get("__type")
    if type_value == "GameCalculation":
        node = _node_base(context, calculation, pointer)
        node["kind"] = "game_calculation"
        node["tooltip_only"] = calculation.get("tooltipOnly", False)
        node["display_as_percent"] = calculation.get("mDisplayAsPercent", False)
        node["precision"] = calculation.get("mPrecision")
        node["parts"] = [
            parse_part(item, context=context, pointer=f"{pointer}/mFormulaParts/{index}")
            for index, item in enumerate(calculation.get("mFormulaParts") or [])
        ]
        return node
    if type_value == "GameCalculationModified":
        return parse_part(calculation, context=context, pointer=pointer)
    if type_value == "GameCalculationConditional":
        node = _node_base(context, calculation, pointer)
        node["kind"] = "conditional"
        node["default_calculation"] = calculation.get("mDefaultGameCalculation")
        node["conditional_calculation"] = calculation.get("mConditionalGameCalculation")
        requirement = calculation.get("mConditionalCalculationRequirements")
        node["condition"] = (
            {
                "type": context.registry.describe_type(requirement.get("__type")),
                "raw": requirement,
            }
            if isinstance(requirement, Mapping)
            else None
        )
        node["tooltip_only"] = calculation.get("tooltipOnly", False)
        node["expanded_tooltip_display"] = calculation.get("mExpandedTooltipCalculationDisplay")
        return node
    return _unresolved(
        context,
        calculation,
        pointer,
        "unknown calculation type",
        type_hash=context.registry.describe_type(type_value).get("type_hash"),
    )


def extract_calculations(
    spell: Mapping[str, Any],
    *,
    spell_path: str,
    context: TraversalContext,
) -> list[Any]:
    """Parse every ``mSpellCalculations`` entry, preserving order."""
    from .model import Calculation

    calculations = spell.get("mSpellCalculations")
    if not isinstance(calculations, Mapping):
        return []
    result: list[Calculation] = []
    for name, calculation in calculations.items():
        if not isinstance(calculation, Mapping):
            context.diagnostic(
                "error",
                "malformed_calculation",
                f"{spell_path}.mSpell.mSpellCalculations[{name!r}]",
                "Calculation entry is not an object.",
            )
            continue
        pointer = f"{context.pointer(spell_path)}/mSpell/mSpellCalculations/{name}"
        tree = parse_calculation(calculation, context=context, pointer=pointer)
        status = "source_explicit"
        if tree.get("kind") == "unresolved":
            status = "unverified"
        result.append(
            Calculation(
                name=str(name),
                tree=tree,
                source_path=f"{spell_path}.mSpell.mSpellCalculations[{name!r}]",
                status=status,
            )
        )
    return result


def summarize_bot_data(
    node: Mapping[str, Any],
    *,
    spell_path: str,
    context: TraversalContext,
) -> dict[str, Any] | None:
    """Summarize BotData without pretending to understand every structure."""
    bot = node.get("BotData")
    if bot is None:
        return None
    type_counts: dict[str, int] = {}
    effects: list[dict[str, Any]] = []
    calculations: list[dict[str, Any]] = []
    references: list[dict[str, Any]] = []
    unresolved: list[dict[str, Any]] = []

    def walk(node: Any, pointer: str) -> None:
        if isinstance(node, Mapping):
            type_value = node.get("__type")
            if isinstance(type_value, str):
                type_counts[type_value] = type_counts.get(type_value, 0) + 1
                if type_value == "{b09016f6}":
                    parsed = parse_part(node, context=context, pointer=pointer)
                    effects.append(parsed)
                    return
                if type_value == "GameCalculation":
                    calculations.append(parse_calculation(node, context=context, pointer=pointer))
                    return
                if type_value in {"{f3cbe7b2}", "{ba007871}", "{9e9e2e5c}"}:
                    references.append(parse_part(node, context=context, pointer=pointer))
                    return
                known = {
                    "GameCalculation",
                    "GameCalculationModified",
                    "NamedDataValueCalculationPart",
                    "NumberCalculationPart",
                    "EffectValueCalculationPart",
                    "ProductOfSubPartsCalculationPart",
                    "StatBySubPartCalculationPart",
                    "SumOfSubPartsCalculationPart",
                    "StatByCoefficientCalculationPart",
                    "ByCharLevelBreakpointsCalculationPart",
                    "ByCharLevelInterpolationCalculationPart",
                }
                if type_value not in known:
                    unresolved.append(
                        {
                            "type": context.registry.describe_type(type_value),
                            "pointer": pointer,
                            "raw": node,
                        }
                    )
            for key, value in node.items():
                if key == "__type":
                    continue
                walk(value, f"{pointer}/{key}")
        elif isinstance(node, list):
            for index, value in enumerate(node):
                walk(value, f"{pointer}/{index}")

    walk(bot, f"{context.pointer(spell_path)}/BotData")
    return {
        "source_path": f"{spell_path}.BotData",
        "type_counts": dict(sorted(type_counts.items())),
        "effects": effects,
        "calculations": calculations,
        "references": references,
        "unresolved": unresolved,
    }
