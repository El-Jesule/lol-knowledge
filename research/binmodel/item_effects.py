"""Extract item effect data from the local client: values, calculations and texts.

For every requested item the client keeps, in the ``Items/<id>`` record of the
``items`` bin of ``DATA/FINAL/Global.wad.client``:

- ``mDataValues``: named values (``CritMax`` = 25) and their game-mode overrides;
- ``mEffectAmount``: an older numbered list that tooltips read as ``EffectNAmount``;
- ``mItemCalculations``: calculation trees that tooltips show (``@CritPerStackCalc@``);
- ``StringCalculations``: melee / ranged / default variants of a tooltip value.

The texts come from the localized RST string table
(``Localized/Global.<locale>.wad.client``): ``item_<id>_tooltip`` and, for items
that describe their active elsewhere, ``item_<id>_active`` and similar keys
(``TEXT_SUFFIXES``). RST keys are hashes; CommunityDragon's
``hashes.rst.xxh3.txt`` only turns names into keys.

Usage::

    python -m binmodel.item_effects --wad "<Game>/DATA/FINAL/Global.wad.client" \\
        --strings "<Game>/DATA/FINAL/Localized/Global.es_ES.wad.client" \\
        --rst-hashes hashes.rst.xxh3.txt --ids-from lol-knowledge/objects/catalog-stats.json \\
        --content-version <version> --retrieved-at 2026-11-16 --output item-effects.json

Nothing is filled in. A data value without ``mValue`` is listed, not given the
class default; hashes without a known name stay as ``{xxxxxxxx}``; the values
say how much, not how the game scripts apply them.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from tools.extract_rst import MAGIC, load_hash_table, parse_rst, read_wad_entries

from .hashes import fnv1a32
from .items import (
    DATA_VALUES,
    ITEM_CLASS,
    MODE_OVERRIDES,
    OVERRIDE_VALUES,
    VALUE_NAME,
    VALUE_VALUE,
    WAD_ENTRY,
    ItemError,
    _mode,
)
from .propbin import (
    BinType,
    ListValue,
    MapValue,
    ObjectValue,
    OptionValue,
    PropError,
    Value,
    parse_prop,
)
from .records import CONTENT_VERSION, f32_decimal
from .wad import WadError, read_entry

SCHEMA = "lol-derived-item-effects/1"
EFFECT_AMOUNT = fnv1a32("mEffectAmount")
CALCULATIONS = fnv1a32("mItemCalculations")
STRING_CALCULATIONS = fnv1a32("StringCalculations")
STRING_RESULTS = {"MeleeResult": "melee", "RangedResult": "ranged", "DefaultResult": "default"}
# Class and field names seen in the item calculation trees of 16.22. A name is
# only shown when its FNV-1a hash matches; anything else stays a hash.
KNOWN_NAMES = (
    "GameCalculation",
    "GameCalculationModified",
    "GameCalculationConditional",
    "NamedDataValueCalculationPart",
    "NumberCalculationPart",
    "StatByNamedDataValueCalculationPart",
    "StatByCoefficientCalculationPart",
    "StatBySubPartCalculationPart",
    "ByCharLevelBreakpointsCalculationPart",
    "ByCharLevelInterpolationCalculationPart",
    "ByItemEpicnessCountCalculationPart",
    "Breakpoint",
    "ProductOfSubPartsCalculationPart",
    "SumOfSubPartsCalculationPart",
    "ClampSubPartsCalculationPart",
    "BuffCounterByCoefficientCalculationPart",
    "BuffCounterByNamedDataValueCalculationPart",
    "AbilityResourceByCoefficientCalculationPart",
    "IsRangedCastRequirement",
    "HasAllSubRequirementsCastRequirement",
    "HasNNearbyVisibleUnitsRequirement",
    "SameTeamCastRequirement",
    "HasUnitTagsCastRequirement",
    "ObjectTags",
    "mFormulaParts",
    "mDataValue",
    "mNumber",
    "mStat",
    "mStatFormula",
    "mCoefficient",
    "mMultiplier",
    "mRangedMultiplier",
    "mPrecision",
    "mDisplayAsPercent",
    "mExpandedTooltipCalculationDisplay",
    "mSimpleTooltipCalculationDisplay",
    "mModifiedGameCalculation",
    "mConditionalGameCalculation",
    "mDefaultGameCalculation",
    "mConditionalCalculationRequirements",
    "mLevel",
    "mLevel1Value",
    "mBreakpoints",
    "mBonusPerLevelAtAndAfter",
    "mAdditionalBonusAtThisLevel",
    "mInitialBonusPerLevel",
    "mStartValue",
    "mEndValue",
    "mPart1",
    "mPart2",
    "mSubparts",
    "mSubpart",
    "mFloor",
    "mCeiling",
    "mBuffName",
    "mSpellCalculationKey",
    "mSubRequirements",
    "mInvertResult",
    "mUnitsRequirements",
    "mUnitTags",
    "mObjectTagList",
    "mRange",
    "epicness",
    "tooltipOnly",
    "DamageType",
    "MeleeResult",
    "RangedResult",
    "DefaultResult",
)
NAMES = {fnv1a32(text): text for text in KNOWN_NAMES}
HASH_TYPES = frozenset({BinType.HASH, BinType.LINK})
# Localized texts kept for each item: the shop tooltip and, for items that
# describe their active apart (Zhonya's Hourglass), the active. Other keys repeat
# them, carry in-game counters or keep text from older seasons.
TEXT_SUFFIXES = ("tooltip", "active")
# Placeholders the game fills during a match (``@f1@``: counters such as damage
# dealt) or from another record (``@spell.SummonerSmite:PetDPS@``).
RUNTIME_PLACEHOLDER = re.compile(r"[fF]\d+")
PLACEHOLDER = re.compile(r"@([^@]+)@")
TEMPLATE = re.compile(r"\{\{\s*([^}]+?)\s*\}\}")


def _hex(value: int) -> str:
    return f"{{{value:08x}}}"


def _values(node: Any, where: str) -> tuple[dict[str, float], list[str], list[str]]:
    """``(values, names without mValue, names repeated with the same value)``."""
    if not isinstance(node, ListValue):
        raise ItemError(f"{where}: data values are not a list")
    values: dict[str, float] = {}
    without: list[str] = []
    repeated: list[str] = []
    for entry in node.items:
        if not isinstance(entry, ObjectValue):
            raise ItemError(f"{where}: data value is not an object")
        name = entry.fields.get(VALUE_NAME)
        if not isinstance(name, Value) or not isinstance(name.value, str):
            raise ItemError(f"{where}: data value without a name")
        label = name.value
        raw = entry.fields.get(VALUE_VALUE)
        if raw is None:
            if label in values or label in without:
                raise ItemError(f"{where}: data value {label!r} is repeated")
            without.append(label)
            continue
        if not isinstance(raw, Value) or not isinstance(raw.value, float):
            raise ItemError(f"{where}.{label}: mValue is not a float")
        number = f32_decimal(raw.value)
        if label in without:
            raise ItemError(f"{where}: data value {label!r} is repeated")
        if label in values:
            if values[label] != number:
                raise ItemError(f"{where}: data value {label!r} is repeated with another value")
            repeated.append(label)
            continue
        values[label] = number
    return values, without, repeated


def _tree(node: Any, refs: Mapping[int, str]) -> Any:
    """A calculation tree as JSON: classes and fields by name when known."""
    if isinstance(node, ObjectValue):
        result: dict[str, Any] = {"class": NAMES.get(node.class_hash, _hex(node.class_hash))}
        for key, value in node.fields.items():
            result[NAMES.get(key, _hex(key))] = _tree(value, refs)
        return result
    if isinstance(node, ListValue):
        return [_tree(item, refs) for item in node.items]
    if isinstance(node, MapValue):
        return [[_tree(key, refs), _tree(value, refs)] for key, value in node.items]
    if isinstance(node, OptionValue):
        return None if node.item is None else _tree(node.item, refs)
    if isinstance(node, Value):
        if node.type in HASH_TYPES and isinstance(node.value, int):
            return refs.get(node.value, _hex(node.value))
        if isinstance(node.value, float):
            return f32_decimal(node.value)
        if isinstance(node.value, (bool, int, str)):
            return node.value
        if isinstance(node.value, tuple):
            return [f32_decimal(x) if isinstance(x, float) else x for x in node.value]
    raise ItemError(f"unsupported value in a calculation: {node!r}")


def placeholder_names(texts: Sequence[str]) -> list[str]:
    """Names of the ``@Name@`` / ``@Name*100@`` placeholders of ``texts``, sorted."""
    return sorted(
        {match.split("*")[0].strip() for text in texts for match in PLACEHOLDER.findall(text)}
    )


def _named(mapping_node: Any, candidates: Sequence[str], where: str) -> dict[str, Any]:
    if mapping_node is None:
        return {}
    if not isinstance(mapping_node, MapValue):
        raise ItemError(f"{where} is not a map")
    by_hash = {fnv1a32(name): name for name in candidates}
    result: dict[str, Any] = {}
    for key, value in mapping_node.items:
        if not isinstance(key, Value) or not isinstance(key.value, int):
            raise ItemError(f"{where}: key is not a hash")
        result[by_hash.get(key.value, _hex(key.value))] = value
    return result


def _item(entry: Any, item_id: str, texts: Mapping[str, str]) -> dict[str, Any]:
    where = f"Items/{item_id}"
    node = entry.fields.get(DATA_VALUES)
    values, without, repeated = (None, [], []) if node is None else _values(node, where)
    overrides: dict[str, dict[str, float]] = {}
    node = entry.fields.get(MODE_OVERRIDES)
    if node is not None:
        if not isinstance(node, MapValue):
            raise ItemError(f"{where}: DataValuesModeOverride is not a map")
        for key, value in node.items:
            if not isinstance(value, ObjectValue):
                raise ItemError(f"{where}: mode override is not an object")
            mode = _mode(key)
            mode_values, mode_without, _ = _values(
                value.fields.get(OVERRIDE_VALUES), f"{where}[{mode}]"
            )
            if mode_without:
                raise ItemError(f"{where}[{mode}]: override without mValue")
            overrides[mode] = mode_values
    amounts = entry.fields.get(EFFECT_AMOUNT)
    effect_amounts = None
    if amounts is not None:
        if not isinstance(amounts, ListValue) or not all(
            isinstance(item, Value) and isinstance(item.value, float) for item in amounts.items
        ):
            raise ItemError(f"{where}: mEffectAmount is not a list of floats")
        effect_amounts = [f32_decimal(item.value) for item in amounts.items]
    placeholders = placeholder_names(list(texts.values()))
    calculations = _named(
        entry.fields.get(CALCULATIONS), placeholders, f"{where}.mItemCalculations"
    )
    strings = _named(
        entry.fields.get(STRING_CALCULATIONS), placeholders, f"{where}.StringCalculations"
    )
    names = [*(values or {}), *without]
    refs = {fnv1a32(name): name for name in [*names, *calculations]}
    string_calculations: dict[str, dict[str, str]] = {}
    for label, node in strings.items():
        if not isinstance(node, ObjectValue):
            raise ItemError(f"{where}.StringCalculations.{label} is not an object")
        variants = {}
        for key, value in node.fields.items():
            field = STRING_RESULTS.get(NAMES.get(key, ""))
            if field is None or not isinstance(value, Value) or not isinstance(value.value, str):
                raise ItemError(f"{where}.StringCalculations.{label}: unexpected field")
            variants[field] = value.value
        string_calculations[label] = dict(sorted(variants.items()))
    kinds: dict[str, str | None] = {}
    numbered = {f"Effect{n}Amount" for n in range(1, len(effect_amounts or ()) + 1)}
    for name in placeholders:
        if name in (values or {}):
            kinds[name] = "data_value"
        elif name in without:
            kinds[name] = "data_value_without_amount"
        elif name in numbered:
            kinds[name] = "effect_amount"
        elif name in calculations:
            kinds[name] = "calculation"
        elif name in string_calculations:
            kinds[name] = "string_calculation"
        elif RUNTIME_PLACEHOLDER.fullmatch(name):
            kinds[name] = "runtime"
        elif name.startswith("spell."):
            kinds[name] = "other_record"
        else:
            kinds[name] = None
    result: dict[str, Any] = {
        "data_values": values,
        "mode_overrides": dict(sorted(overrides.items())),
        "effect_amounts": effect_amounts,
        "calculations": {label: _tree(node, refs) for label, node in sorted(calculations.items())},
        "string_calculations": dict(sorted(string_calculations.items())),
        "texts": dict(texts),
        "placeholders": kinds,
    }
    if without:
        result["data_values_without_amount"] = without
    if repeated:
        result["repeated_data_values"] = repeated
    return result


def extract_item_effects(
    bin_data: bytes, item_ids: Sequence[str], texts: Mapping[str, Mapping[str, str]]
) -> tuple[dict[str, Any], dict[str, str], tuple[int, ...]]:
    """Return ``(items, failures, skipped entry hashes)`` for ``item_ids``."""
    try:
        prop = parse_prop(bin_data, skip_unreadable=True)
    except PropError as exc:
        raise ItemError(f"bin: {exc}") from exc
    items: dict[str, Any] = {}
    failures: dict[str, str] = {}
    for item_id in item_ids:
        key = fnv1a32(f"Items/{item_id}")
        entry = prop.entries.get(key)
        if entry is None:
            failures[item_id] = "unreadable record" if key in prop.skipped else "no record"
            continue
        if entry.class_hash != ITEM_CLASS:
            failures[item_id] = f"record class 0x{entry.class_hash:08x} is not ItemData"
            continue
        try:
            items[item_id] = _item(entry, item_id, texts.get(item_id, {}))
        except ItemError as exc:
            failures[item_id] = str(exc)
    return items, failures, prop.skipped


def expand_templates(text: str, strings: Mapping[str, str]) -> str:
    """Replace each ``{{ Name }}`` once with its string; unknown templates stay."""
    return TEMPLATE.sub(lambda match: strings.get(match.group(1).lower(), match.group(0)), text)


def texts_from_strings(
    strings: Mapping[str, str], item_ids: Sequence[str]
) -> dict[str, dict[str, str]]:
    """The ``TEXT_SUFFIXES`` texts of each id that exist, templates expanded."""
    result: dict[str, dict[str, str]] = {}
    for item_id in item_ids:
        found = {}
        for suffix in TEXT_SUFFIXES:
            text = strings.get(f"item_{item_id}_{suffix}")
            if text is not None:
                found[suffix] = expand_templates(text, strings)
        result[item_id] = found
    return result


def load_strings(strings_wad: Path, rst_hashes: Path) -> dict[str, str]:
    """Every named RST string of the WAD, by lowercased name."""
    names = load_hash_table(rst_hashes)
    values: dict[int, str] = {}
    for _, data in read_wad_entries(strings_wad):
        if data.startswith(MAGIC):
            for key, text in parse_rst(data).items():
                values.setdefault(key, text)
    return {names[key].strip().lower(): text for key, text in values.items() if key in names}


def build_document(
    items: Mapping[str, Any],
    failures: Mapping[str, str],
    skipped: Sequence[int],
    *,
    bin_sha256: str,
    strings_sha256: str,
    locale: str,
    content_version: str,
    retrieved_at: str,
) -> dict[str, Any]:
    match = CONTENT_VERSION.fullmatch(content_version)
    if match is None:
        raise ItemError(f"content version {content_version!r} is not <major>.<minor>.<build>+…")
    return {
        "schema": SCHEMA,
        "label": "Derivado",
        "content_version": content_version,
        "game_version": f"{match.group(1)}.{match.group(2)}",
        "retrieved_at": retrieved_at,
        "locale": locale,
        "source": (
            "Cliente local: DATA/FINAL/Global.wad.client → items → Items/<id>; "
            f"DATA/FINAL/Localized/Global.{locale}.wad.client → item_<id>_<texto>"
        ),
        "bin_sha256": bin_sha256,
        "strings_sha256": strings_sha256,
        "method": (
            "research/binmodel/item_effects.py: lector PROP (registros ilegibles omitidos y "
            "listados); float32 escrito como el decimal más corto equivalente; claves RST "
            "con hashes.rst.xxh3.txt de CommunityDragon/Data; nombres de clases y campos de "
            "los cálculos solo cuando su FNV-1a coincide"
        ),
        "skipped_entries": [f"0x{value:08x}" for value in skipped],
        "items": dict(sorted(items.items(), key=lambda pair: int(pair[0]))),
        "failures": dict(sorted(failures.items())),
    }


def _ids_from(path: Path) -> list[str]:
    document = json.loads(path.read_text(encoding="utf-8"))
    objects = document.get("objects") if isinstance(document, Mapping) else None
    if not isinstance(objects, list):
        raise ItemError(f"{path}: no 'objects' list")
    return [str(entry["id"]) for entry in objects]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m binmodel.item_effects", description=__doc__)
    parser.add_argument("--wad", type=Path, required=True)
    parser.add_argument("--strings", type=Path, required=True)
    parser.add_argument("--rst-hashes", type=Path, required=True)
    parser.add_argument("--locale", default="es_ES")
    ids = parser.add_mutually_exclusive_group(required=True)
    ids.add_argument("--ids", nargs="+")
    ids.add_argument("--ids-from", type=Path)
    parser.add_argument("--content-version", required=True)
    parser.add_argument("--retrieved-at", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        item_ids = args.ids or _ids_from(args.ids_from)
        data = read_entry(args.wad, WAD_ENTRY)
        strings = load_strings(args.strings, args.rst_hashes)
        items, failures, skipped = extract_item_effects(
            data, item_ids, texts_from_strings(strings, item_ids)
        )
        document = build_document(
            items,
            failures,
            skipped,
            bin_sha256=hashlib.sha256(data).hexdigest(),
            strings_sha256=hashlib.sha256(args.strings.read_bytes()).hexdigest(),
            locale=args.locale,
            content_version=args.content_version,
            retrieved_at=args.retrieved_at,
        )
    except (ItemError, WadError, OSError, KeyError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    args.output.write_text(
        json.dumps(document, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(f"items: {len(items)}  failures: {len(failures)}  -> {args.output}")
    return 0 if not failures else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
