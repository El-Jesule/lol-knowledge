"""Extract item data values from the local client's item bin.

The client keeps every item in one PROP bin, the ``items`` entry of
``DATA/FINAL/Global.wad.client`` (path from CommunityDragon's
``hashes.game.txt``). Each ``Items/<id>`` record lists named data values
(``mDataValues``) and per-game-mode overrides (``DataValuesModeOverride``).
Summoner's Rift has no override, so it uses the defaults.

Usage::

    python -m binmodel.items --wad "<Game>/DATA/FINAL/Global.wad.client" \\
        --ids 3153 3036 --content-version <version> --retrieved-at 2026-11-15 \\
        --output items.json

Nothing is filled in: an id without a readable ``ItemData`` record is a
failure, and a record without ``mDataValues`` keeps ``data_values: null``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from .hashes import fnv1a32
from .propbin import ListValue, MapValue, ObjectValue, PropError, Value, parse_prop
from .records import CONTENT_VERSION, f32_decimal
from .wad import WadError, read_entry

SCHEMA = "lol-derived-item-data-values/1"
WAD_ENTRY = "items"
ITEM_CLASS = fnv1a32("ItemData")
DATA_VALUES = fnv1a32("mDataValues")
MODE_OVERRIDES = fnv1a32("DataValuesModeOverride")
OVERRIDE_VALUES = fnv1a32("DataValues")
VALUE_NAME = fnv1a32("mName")
VALUE_VALUE = fnv1a32("mValue")
# Game-mode keys whose names are known (FNV-1a of the lowercased name).
MODE_NAMES = {fnv1a32(name): name for name in ("ARAM", "KIWI", "CLASSIC", "CHERRY", "URF")}


class ItemError(Exception):
    """The item bin cannot be read without guessing."""


def _data_values(node: Any, where: str) -> dict[str, float]:
    if not isinstance(node, ListValue):
        raise ItemError(f"{where}: data values are not a list")
    values: dict[str, float] = {}
    for entry in node.items:
        if not isinstance(entry, ObjectValue):
            raise ItemError(f"{where}: data value is not an object")
        name = entry.fields.get(VALUE_NAME)
        value = entry.fields.get(VALUE_VALUE)
        if not isinstance(name, Value) or not isinstance(name.value, str):
            raise ItemError(f"{where}: data value without a name")
        if not isinstance(value, Value) or not isinstance(value.value, float):
            raise ItemError(f"{where}.{name.value}: data value without a float value")
        if name.value in values:
            raise ItemError(f"{where}: data value {name.value!r} is repeated")
        values[name.value] = f32_decimal(value.value)
    return values


def _mode(key: Any) -> str:
    if not isinstance(key, Value) or not isinstance(key.value, int):
        raise ItemError("mode override key is not a hash")
    return MODE_NAMES.get(key.value, f"{{{key.value:08x}}}")


def extract_items(
    bin_data: bytes, item_ids: Sequence[str]
) -> tuple[dict[str, Any], dict[str, str], tuple[int, ...]]:
    """Return ``(items, failures, skipped entry hashes)`` for ``item_ids``."""
    try:
        prop = parse_prop(bin_data, skip_unreadable=True)
    except PropError as exc:
        raise ItemError(f"bin: {exc}") from exc
    items: dict[str, Any] = {}
    failures: dict[str, str] = {}
    for item_id in item_ids:
        entry = prop.entries.get(fnv1a32(f"Items/{item_id}"))
        if entry is None:
            failures[item_id] = (
                "unreadable record" if fnv1a32(f"Items/{item_id}") in prop.skipped else "no record"
            )
            continue
        if entry.class_hash != ITEM_CLASS:
            failures[item_id] = f"record class 0x{entry.class_hash:08x} is not ItemData"
            continue
        try:
            # An item without data values (a basic component) has no mDataValues field.
            node = entry.fields.get(DATA_VALUES)
            values = None if node is None else _data_values(node, f"Items/{item_id}")
            overrides: dict[str, dict[str, float]] = {}
            node = entry.fields.get(MODE_OVERRIDES)
            if node is not None:
                if not isinstance(node, MapValue):
                    raise ItemError("DataValuesModeOverride is not a map")
                for key, value in node.items:
                    if not isinstance(value, ObjectValue):
                        raise ItemError("mode override is not an object")
                    mode = _mode(key)
                    overrides[mode] = _data_values(
                        value.fields.get(OVERRIDE_VALUES), f"Items/{item_id}[{mode}]"
                    )
        except ItemError as exc:
            failures[item_id] = str(exc)
            continue
        items[item_id] = {"data_values": values, "mode_overrides": dict(sorted(overrides.items()))}
    return items, failures, prop.skipped


def build_document(
    items: Mapping[str, Any],
    failures: Mapping[str, str],
    skipped: Sequence[int],
    *,
    bin_sha256: str,
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
        "source": "Cliente local: DATA/FINAL/Global.wad.client → items → Items/<id>",
        "bin_sha256": bin_sha256,
        "method": (
            "research/binmodel/items.py: lector PROP (registros ilegibles omitidos y "
            "listados); float32 escrito como el decimal más corto equivalente"
        ),
        "skipped_entries": [f"0x{value:08x}" for value in skipped],
        "items": dict(sorted(items.items(), key=lambda pair: int(pair[0]))),
        "failures": dict(sorted(failures.items())),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m binmodel.items", description=__doc__)
    parser.add_argument("--wad", type=Path, required=True)
    parser.add_argument("--ids", nargs="+", required=True)
    parser.add_argument("--content-version", required=True)
    parser.add_argument("--retrieved-at", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        data = read_entry(args.wad, WAD_ENTRY)
        items, failures, skipped = extract_items(data, args.ids)
        document = build_document(
            items,
            failures,
            skipped,
            bin_sha256=hashlib.sha256(data).hexdigest(),
            content_version=args.content_version,
            retrieved_at=args.retrieved_at,
        )
    except (ItemError, WadError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    args.output.write_text(
        json.dumps(document, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(f"items: {len(items)}  failures: {len(failures)}  -> {args.output}")
    return 0 if not failures else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
