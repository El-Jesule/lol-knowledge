"""Load the versioned object catalog and build the canonical model."""

from __future__ import annotations

import copy
import html
import json
import math
import re
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .formula import classify_formula
from .schema import (
    CATALOG_RELATIVE_PATH,
    DDRAGON_STAT_MAP,
    ITEMS_FILENAME,
    MANIFEST_FILENAME,
    MODEL_KIND,
    OBJECT_SCHEMA_VERSION,
    OBJECTS_DIRNAME,
    SNAPSHOT_RELATIVE_PATH,
    STAT_ORDER,
)

_TAG_PATTERN = re.compile(r"<[^>]+>")
_STAT_INDEX = {stat: index for index, stat in enumerate(STAT_ORDER)}


class ObjectModelError(Exception):
    """The catalog cannot be turned into a model without guessing."""


@dataclass(frozen=True)
class Snapshot:
    """The parts of the Data Dragon snapshot the object model needs."""

    patch: str
    locale: str
    items: Mapping[str, Mapping[str, Any]]
    items_sha256: str


def description_text(source: str) -> str:
    """Turn a Data Dragon HTML description into normalized plain text."""
    return " ".join(html.unescape(_TAG_PATTERN.sub(" ", source)).split())


def load_snapshot(root: Path) -> Snapshot:
    """Read ``items.json`` and its manifest from ``data/current``."""
    current = root / SNAPSHOT_RELATIVE_PATH
    manifest_path = current / MANIFEST_FILENAME
    items_path = current / ITEMS_FILENAME
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        items = json.loads(items_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ObjectModelError(f"cannot read the Data Dragon snapshot: {exc}") from exc
    if not isinstance(manifest, Mapping) or not isinstance(items, Mapping):
        raise ObjectModelError("the snapshot manifest and items must be JSON objects")
    patch = manifest.get("patch")
    locale = manifest.get("locale")
    if not isinstance(patch, str) or not isinstance(locale, str):
        raise ObjectModelError("the snapshot manifest needs patch and locale")
    files = manifest.get("files")
    record = files.get(ITEMS_FILENAME) if isinstance(files, Mapping) else None
    items_sha256 = record.get("sha256") if isinstance(record, Mapping) else None
    if not isinstance(items_sha256, str):
        raise ObjectModelError("the snapshot manifest has no items.json sha256")
    return Snapshot(
        patch=patch,
        locale=locale,
        items=items,
        items_sha256=items_sha256,
    )


def load_catalog(root: Path) -> Mapping[str, Any]:
    """Read the curated catalog; validation is a separate step."""
    path = root / CATALOG_RELATIVE_PATH
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ObjectModelError(f"cannot read {CATALOG_RELATIVE_PATH.as_posix()}: {exc}") from exc
    if not isinstance(payload, Mapping):
        raise ObjectModelError("the object catalog must be a JSON object")
    return payload


def _id_key(value: Any) -> tuple[int, Any]:
    text = str(value)
    return (0, int(text)) if text.isdigit() else (1, text)


def _stat_sort_key(stat: Mapping[str, Any]) -> tuple[int, str, str]:
    source = stat.get("source") or {}
    return (
        _STAT_INDEX.get(str(stat.get("id")), len(_STAT_INDEX)),
        str(stat.get("kind")),
        str(source.get("kind")),
    )


def derive_stats(item: Mapping[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    stats: list[dict[str, Any]] = []
    unmapped: list[dict[str, Any]] = []
    raw_stats = item.get("stats")
    if not isinstance(raw_stats, Mapping):
        return stats, unmapped
    for key in sorted(raw_stats):
        raw_value = raw_stats[key]
        mapping = DDRAGON_STAT_MAP.get(key)
        if mapping is None:
            unmapped.append({"key": key, "value": raw_value})
            continue
        if (
            isinstance(raw_value, bool)
            or not isinstance(raw_value, (int, float))
            or not math.isfinite(raw_value)
        ):
            unmapped.append(
                {
                    "key": key,
                    "value": raw_value,
                    "reason": "non-numeric Data Dragon stat",
                }
            )
            continue
        stat_id, kind, factor = mapping
        value = float(raw_value) * factor
        if kind == "percent":
            value = round(value, 6)
        stats.append(
            {
                "id": stat_id,
                "kind": kind,
                "value": value,
                "raw_value": raw_value,
                "source": {"kind": "ddragon_stat", "key": key},
                "verification": "official_field",
            }
        )
    return stats, unmapped


def _overlay_stats(entry: Mapping[str, Any]) -> list[dict[str, Any]]:
    stats: list[dict[str, Any]] = []
    for raw in entry.get("stats") or []:
        stat = {
            "id": raw["id"],
            "kind": raw["kind"],
            "source": {
                "kind": "ddragon_description",
                "item_id": entry["id"],
                "quote": raw["quote"],
            },
            "verification": "description_quote_verified",
        }
        if "value" in raw:
            stat["value"] = float(raw["value"])
            stat["status"] = "declared"
        else:
            stat["value"] = None
            stat["status"] = raw.get("status", "unknown")
            stat["reason"] = raw["reason"]
        stats.append(stat)
    return stats


def _is_unknown_scalar(value: Any) -> bool:
    return isinstance(value, Mapping) and value.get("status") == "unknown"


def derived_effect_status(effect: Mapping[str, Any]) -> str:
    states = [
        classify_formula(component["formula"])
        for component in effect.get("components") or []
        if isinstance(component, Mapping) and "formula" in component
    ]
    unknown_scalar = any(
        _is_unknown_scalar(effect.get(key)) for key in ("cooldown_seconds", "duration_seconds")
    )
    stacks = effect.get("stacks")
    if isinstance(stacks, Mapping):
        unknown_scalar = unknown_scalar or _is_unknown_scalar(stacks.get("window_seconds"))
    if any(state == "excluded" for state in states):
        return "excluded"
    if unknown_scalar or any(state == "partially_evaluable" for state in states):
        return "partially_evaluable"
    return "evaluable"


def _build_effect(effect: Mapping[str, Any]) -> dict[str, Any]:
    built = copy.deepcopy(dict(effect))
    built["derived_status"] = derived_effect_status(effect)
    return built


def _build_object(entry: Mapping[str, Any], snapshot: Snapshot) -> dict[str, Any]:
    item_id = str(entry["id"])
    item = snapshot.items.get(item_id)
    if not isinstance(item, Mapping):
        raise ObjectModelError(f"item {item_id!r} is not in the snapshot")
    derived_stats, unmapped = derive_stats(item)
    stats = sorted([*derived_stats, *_overlay_stats(entry)], key=_stat_sort_key)
    effects = [_build_effect(effect) for effect in entry.get("effects") or []]

    raw_maps = item.get("maps")
    maps = (
        {
            str(key): bool(value)
            for key, value in sorted((raw_maps or {}).items(), key=lambda pair: _id_key(pair[0]))
        }
        if isinstance(raw_maps, Mapping)
        else {}
    )
    gold = item.get("gold") if isinstance(item.get("gold"), Mapping) else {}
    from_ids = item.get("from")
    from_counts = Counter(str(item_id) for item_id in from_ids or [])
    tags = item.get("tags")
    verification = (
        "description_quote_verified"
        if entry.get("stats") or entry.get("effects")
        else "official_field"
    )
    return {
        "id": item_id,
        "name": item.get("name"),
        "game_version": snapshot.patch,
        "verification": verification,
        "tags": sorted(tags) if isinstance(tags, list) else [],
        "stats": stats,
        "unmapped_source_stats": unmapped,
        "effects": effects,
        "gold": {
            "total": gold.get("total"),
            "base": gold.get("base"),
            "sell": gold.get("sell"),
        },
        "availability": {
            "purchasable": gold.get("purchasable"),
            "in_store": item.get("inStore"),
            "hide_from_all": item.get("hideFromAll"),
            "consumed": item.get("consumed"),
            "stacks": item.get("stacks"),
            "maps": maps,
            "map_ids": sorted(int(key) for key, value in maps.items() if value),
            "modes": {
                "status": "unknown",
                "reason": "Data Dragon does not encode game modes.",
            },
            "required_champion": item.get("requiredChampion"),
            "required_ally": item.get("requiredAlly"),
        },
        "recipe": {
            "builds_from": [
                {"id": key, "count": from_counts[key]} for key in sorted(from_counts, key=_id_key)
            ],
            "builds_into": [item_id for item_id in sorted(item.get("into") or [], key=_id_key)],
            "depth": item.get("depth"),
            "special_recipe": item.get("specialRecipe"),
        },
    }


def build_model(catalog: Mapping[str, Any], snapshot: Snapshot) -> dict[str, Any]:
    """Build the canonical model from an already validated catalog."""
    objects = [_build_object(entry, snapshot) for entry in catalog.get("objects") or []]
    objects.sort(key=lambda item: _id_key(item["id"]))
    return {
        "schema_version": OBJECT_SCHEMA_VERSION,
        "kind": MODEL_KIND,
        "catalog_version": catalog.get("catalog_version"),
        "game_version": snapshot.patch,
        "source": {
            "snapshot": SNAPSHOT_RELATIVE_PATH.as_posix(),
            "items_sha256": snapshot.items_sha256,
            "locale": snapshot.locale,
            "catalog": CATALOG_RELATIVE_PATH.as_posix(),
        },
        "objects": objects,
    }


def dump_model(model: Mapping[str, Any]) -> str:
    """Serialize the canonical model deterministically."""
    return json.dumps(model, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def load_model(root: Path) -> tuple[dict[str, Any], str]:
    """Load, validate and build the model. Returns ``(model, serialized)``."""
    from .validate import validate_catalog_document

    snapshot = load_snapshot(root)
    catalog = load_catalog(root)
    report = validate_catalog_document(catalog, snapshot)
    if report.violations:
        raise ObjectModelError(
            "the object catalog is invalid:\n"
            + "\n".join(f"{item.path}: {item.message}" for item in report.violations)
        )
    model = build_model(catalog, snapshot)
    return model, dump_model(model)


def catalog_directory(root: Path) -> Path:
    """Return the curated objects directory for a project root."""
    return root / "lol-knowledge" / OBJECTS_DIRNAME
