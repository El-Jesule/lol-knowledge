"""Client data of item effects (``lol-knowledge/derived/item-effects.json``).

``research/binmodel/item_effects.py`` writes the file from the local client:
data values, calculation trees, melee/ranged variants and the localized texts
of every purchasable Summoner's Rift item. The CLI never reads the client; it
only checks that the published file is well formed, matches the snapshot patch
and covers the generated catalog (lol-knowledge/objects/README.md).
"""

from __future__ import annotations

import math
import re
from collections.abc import Collection, Mapping
from pathlib import Path
from typing import Any

ITEM_EFFECTS_PATH = Path("lol-knowledge") / "derived" / "item-effects.json"
SCHEMA = "lol-derived-item-effects/1"
REGENERATE = "regenerate it with python -m binmodel.item_effects (research/README.md)"
GAME_VERSION = re.compile(r"\d+\.\d+")
SHA256 = re.compile(r"[0-9a-f]{64}")
PLACEHOLDER = re.compile(r"@([^@]+)@")
PLACEHOLDER_KINDS = frozenset(
    {
        "data_value",
        "data_value_without_amount",
        "effect_amount",
        "calculation",
        "string_calculation",
        "runtime",
        "other_record",
    }
)
TEXT_SUFFIXES = frozenset({"tooltip", "active"})
STRING_VARIANTS = frozenset({"melee", "ranged", "default"})
ITEM_KEYS = frozenset(
    {
        "data_values",
        "mode_overrides",
        "effect_amounts",
        "calculations",
        "string_calculations",
        "texts",
        "placeholders",
    }
)
OPTIONAL_ITEM_KEYS = frozenset({"data_values_without_amount", "repeated_data_values"})
HEADER_STRINGS = ("content_version", "retrieved_at", "locale", "source", "method")
# Where each placeholder kind must be found in the item.
KIND_FIELDS = {
    "data_value": "data_values",
    "data_value_without_amount": "data_values_without_amount",
    "calculation": "calculations",
    "string_calculation": "string_calculations",
}


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _number_map(value: Any) -> bool:
    return isinstance(value, Mapping) and all(
        isinstance(key, str) and _is_number(number) for key, number in value.items()
    )


def _names(value: Any) -> bool:
    return isinstance(value, list) and all(isinstance(name, str) for name in value)


def _placeholders(texts: Mapping[str, Any]) -> set[str]:
    return {
        match.split("*")[0].strip()
        for text in texts.values()
        if isinstance(text, str)
        for match in PLACEHOLDER.findall(text)
    }


def _item_problems(item_id: str, item: Any) -> list[str]:
    where = f"items.{item_id}"
    if not isinstance(item, Mapping):
        return [f"{where} must be an object"]
    problems = []
    missing = ITEM_KEYS - set(item)
    unknown = set(item) - ITEM_KEYS - OPTIONAL_ITEM_KEYS
    if missing:
        problems.append(f"{where} lacks {sorted(missing)}")
    if unknown:
        problems.append(f"{where} has unknown keys {sorted(unknown)}")
    if missing:
        return problems
    values = item["data_values"]
    if values is not None and not _number_map(values):
        problems.append(f"{where}.data_values must map names to finite numbers or be null")
    overrides = item["mode_overrides"]
    if not isinstance(overrides, Mapping) or not all(
        _number_map(mode) for mode in overrides.values()
    ):
        problems.append(f"{where}.mode_overrides must map modes to data values")
    amounts = item["effect_amounts"]
    if amounts is not None and not (
        isinstance(amounts, list) and all(_is_number(number) for number in amounts)
    ):
        problems.append(f"{where}.effect_amounts must be a list of numbers or null")
    for key in OPTIONAL_ITEM_KEYS & set(item):
        if not _names(item[key]) or not item[key]:
            problems.append(f"{where}.{key} must be a non-empty list of names")
    if not isinstance(item["calculations"], Mapping):
        problems.append(f"{where}.calculations must be an object")
    strings = item["string_calculations"]
    if not isinstance(strings, Mapping) or not all(
        isinstance(variants, Mapping)
        and set(variants) <= STRING_VARIANTS
        and all(isinstance(text, str) for text in variants.values())
        for variants in strings.values()
    ):
        problems.append(f"{where}.string_calculations must map names to melee/ranged/default")
    texts = item["texts"]
    if not isinstance(texts, Mapping) or not all(
        suffix in TEXT_SUFFIXES and isinstance(text, str) for suffix, text in texts.items()
    ):
        problems.append(f"{where}.texts must map {sorted(TEXT_SUFFIXES)} to strings")
        return problems
    placeholders = item["placeholders"]
    if not isinstance(placeholders, Mapping) or not all(
        kind is None or kind in PLACEHOLDER_KINDS for kind in placeholders.values()
    ):
        problems.append(f"{where}.placeholders must map names to a known kind or null")
        return problems
    if set(placeholders) != _placeholders(texts):
        problems.append(f"{where}.placeholders do not match the placeholders of its texts")
    for name, kind in sorted(placeholders.items()):
        field = KIND_FIELDS.get(str(kind))
        container = item.get(field) if field else None
        if field is not None and (container is None or name not in container):
            problems.append(f"{where}.placeholders.{name}: {kind} not found in {field}")
        if kind == "effect_amount":
            match = re.fullmatch(r"Effect(\d+)Amount", name)
            if match is None or not amounts or not 1 <= int(match.group(1)) <= len(amounts):
                problems.append(f"{where}.placeholders.{name}: no such effect amount")
    return problems


def item_effects_problems(
    document: Any, *, patch: str | None = None, item_ids: Collection[str] | None = None
) -> list[str]:
    """Every reason why ``document`` is not a usable ``item-effects.json``."""
    if not isinstance(document, Mapping):
        return ["the document must be a JSON object"]
    problems = []
    if document.get("schema") != SCHEMA:
        problems.append(f"schema must be {SCHEMA!r}")
    if document.get("label") != "Derivado":
        problems.append("label must be 'Derivado'")
    for key in HEADER_STRINGS:
        if not isinstance(document.get(key), str) or not document[key]:
            problems.append(f"{key} must be a non-empty string")
    for key in ("bin_sha256", "strings_sha256"):
        if not isinstance(document.get(key), str) or not SHA256.fullmatch(document[key]):
            problems.append(f"{key} must be a SHA-256 hex digest")
    game_version = document.get("game_version")
    if not isinstance(game_version, str) or not GAME_VERSION.fullmatch(game_version):
        problems.append("game_version must be <major>.<minor>")
    elif patch is not None and not patch.startswith(f"{game_version}."):
        problems.append(f"client {game_version} data for snapshot {patch}; {REGENERATE}")
    items = document.get("items")
    failures = document.get("failures")
    if not isinstance(items, Mapping):
        return [*problems, "items must be an object"]
    if not isinstance(failures, Mapping) or not all(
        isinstance(reason, str) for reason in failures.values()
    ):
        return [*problems, "failures must map item ids to reasons"]
    for item_id, item in items.items():
        problems += _item_problems(str(item_id), item)
    if item_ids is not None:
        covered = set(items) | set(failures)
        missing = sorted(set(item_ids) - covered)
        extra = sorted(covered - set(item_ids))
        if missing:
            problems.append(f"items of the catalog without client data: {missing}; {REGENERATE}")
        if extra:
            problems.append(f"items that are not in the catalog: {extra}; {REGENERATE}")
    return problems
