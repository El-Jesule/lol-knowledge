"""Extract the item groups that limit what a build may hold, from the local client.

Every ``Items/<id>`` record of the ``items`` bin (``DATA/FINAL/Global.wad.client``)
links to item groups (``mItemGroups``). An ``ItemGroup`` record says how many
items of the group one inventory may own (``mMaxGroupOwnable``) and, for
trinkets, which inventory slot they take (``mInventorySlotMin``/``Max``). Since
items became unique, each legendary item has a group of its own whose
``mItemGroupID`` is the item id; shared groups (boots, Last Whisper, Lifeline…)
cover several items.

Usage::

    python -m binmodel.item_groups --wad "<Game>/DATA/FINAL/Global.wad.client" \\
        --ids-from lol-knowledge/objects/catalog-stats.json \\
        --entry-names hashes.binentries.txt \\
        --content-version <version> --retrieved-at 2026-11-19 \\
        --output lol-knowledge/derived/item-groups.json

Nothing is filled in: a field absent from a record stays ``null`` (its class
default is not guessed), and a group whose path is not in the entry name list
keeps ``entry: null``. Groups are keyed by the hex FNV-1a hash of their path.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

from .hashes import fnv1a32
from .items import ITEM_CLASS, WAD_ENTRY, ItemError
from .propbin import BinType, ListValue, PropError, Value, parse_prop
from .records import CONTENT_VERSION
from .wad import WadError, read_entry

SCHEMA = "lol-derived-item-groups/1"
GROUP_CLASS = fnv1a32("ItemGroup")
ITEM_GROUPS = fnv1a32("mItemGroups")
MAX_STACK = fnv1a32("maxStack")
REQUIRED_CHAMPION = fnv1a32("mRequiredChampion")
GROUP_ID = fnv1a32("mItemGroupID")
GROUP_INTEGERS = {
    fnv1a32("mMaxGroupOwnable"): "max_ownable",
    fnv1a32("mInventorySlotMin"): "inventory_slot_min",
    fnv1a32("mInventorySlotMax"): "inventory_slot_max",
}
GROUP_PREFIX = "items/itemgroups/"
INTEGER_TYPES = frozenset(
    {BinType.I8, BinType.U8, BinType.I16, BinType.U16, BinType.I32, BinType.U32}
)


def _key(path_hash: int) -> str:
    return f"{path_hash:08x}"


def _integer(node: Any, where: str) -> int | None:
    if node is None:
        return None
    if not isinstance(node, Value) or node.type not in INTEGER_TYPES:
        raise ItemError(f"{where} is not an integer")
    return int(node.value)


def _string(node: Any, where: str) -> str | None:
    if node is None:
        return None
    if not isinstance(node, Value) or not isinstance(node.value, str):
        raise ItemError(f"{where} is not a string")
    return node.value


def _links(node: Any, where: str) -> list[int]:
    if not isinstance(node, ListValue) or not all(
        isinstance(link, Value) and link.type is BinType.LINK for link in node.items
    ):
        raise ItemError(f"{where} is not a list of links")
    return [int(link.value) for link in node.items]


def _group(entry: Any, names: Mapping[int, str], id_names: Mapping[int, str]) -> dict[str, Any]:
    where = f"group {_key(entry.path_hash)}"
    group_id = entry.fields.get(GROUP_ID)
    if not isinstance(group_id, Value) or not isinstance(group_id.value, int):
        raise ItemError(f"{where}: mItemGroupID is not a hash")
    record: dict[str, Any] = {
        "entry": names.get(entry.path_hash),
        "group_id": id_names.get(group_id.value, f"{{{group_id.value:08x}}}"),
    }
    for field, key in GROUP_INTEGERS.items():
        record[key] = _integer(entry.fields.get(field), f"{where}.{key}")
    return record


def extract_item_groups(
    bin_data: bytes, item_ids: Sequence[str], entry_names: Mapping[int, str] | None = None
) -> tuple[dict[str, Any], dict[str, Any], dict[str, str], tuple[int, ...]]:
    """Return ``(items, groups, failures, skipped entry hashes)`` for ``item_ids``."""
    try:
        prop = parse_prop(bin_data, skip_unreadable=True)
    except PropError as exc:
        raise ItemError(f"bin: {exc}") from exc
    names = dict(entry_names or {})
    # A group id is the hash of a name: the tail of the group's path, or an item id.
    id_names = {fnv1a32(item_id): item_id for item_id in item_ids}
    for name in names.values():
        id_names.setdefault(fnv1a32(name.rsplit("/", 1)[-1]), name.rsplit("/", 1)[-1])
    items: dict[str, Any] = {}
    groups: dict[str, Any] = {}
    failures: dict[str, str] = {}
    for item_id in item_ids:
        path_hash = fnv1a32(f"Items/{item_id}")
        entry = prop.entries.get(path_hash)
        if entry is None:
            failures[item_id] = "unreadable record" if path_hash in prop.skipped else "no record"
            continue
        if entry.class_hash != ITEM_CLASS:
            failures[item_id] = f"record class 0x{entry.class_hash:08x} is not ItemData"
            continue
        try:
            links = _links(entry.fields.get(ITEM_GROUPS), f"Items/{item_id}.mItemGroups")
            found: dict[str, Any] = {}
            for link in links:
                group = prop.entries.get(link)
                if group is None or group.class_hash != GROUP_CLASS:
                    raise ItemError(f"Items/{item_id}: group {_key(link)} is not a readable group")
                found[_key(link)] = _group(group, names, id_names)
            record = {
                "groups": [_key(link) for link in links],
                "max_stack": _integer(entry.fields.get(MAX_STACK), f"Items/{item_id}.maxStack"),
                "required_champion": _string(
                    entry.fields.get(REQUIRED_CHAMPION), f"Items/{item_id}.mRequiredChampion"
                ),
            }
        except ItemError as exc:
            failures[item_id] = str(exc)
            continue
        groups.update(found)
        items[item_id] = record
    return items, groups, failures, prop.skipped


def build_document(
    items: Mapping[str, Any],
    groups: Mapping[str, Any],
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
        "source": (
            "Cliente local: DATA/FINAL/Global.wad.client → items → Items/<id>.mItemGroups → "
            "ItemGroup (mMaxGroupOwnable, mInventorySlotMin, mInventorySlotMax)"
        ),
        "bin_sha256": bin_sha256,
        "method": (
            "research/binmodel/item_groups.py: lector PROP (registros ilegibles omitidos y "
            "listados); rutas de grupo con hashes.binentries.txt de CommunityDragon/Data; "
            "campos ausentes a null, sin valor por defecto"
        ),
        "skipped_entries": [f"0x{value:08x}" for value in skipped],
        "groups": dict(sorted(groups.items())),
        "items": dict(sorted(items.items(), key=lambda pair: int(pair[0]))),
        "failures": dict(sorted(failures.items())),
    }


def read_group_names(lines: Iterable[str]) -> dict[int, str]:
    """Item group paths of a ``hashes.binentries.txt`` list, by hash."""
    names: dict[int, str] = {}
    for line in lines:
        value, _, path = line.strip().partition(" ")
        if path.lower().startswith(GROUP_PREFIX):
            names[int(value, 16)] = path
    return names


def _ids_from(path: Path) -> list[str]:
    document = json.loads(path.read_text(encoding="utf-8"))
    objects = document.get("objects") if isinstance(document, Mapping) else None
    if not isinstance(objects, list):
        raise ItemError(f"{path}: no 'objects' list")
    return [str(entry["id"]) for entry in objects]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m binmodel.item_groups", description=__doc__)
    parser.add_argument("--wad", type=Path, required=True)
    ids = parser.add_mutually_exclusive_group(required=True)
    ids.add_argument("--ids", nargs="+")
    ids.add_argument("--ids-from", type=Path)
    parser.add_argument("--entry-names", type=Path, help="hashes.binentries.txt (optional).")
    parser.add_argument("--content-version", required=True)
    parser.add_argument("--retrieved-at", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        item_ids = args.ids or _ids_from(args.ids_from)
        names: dict[int, str] = {}
        if args.entry_names is not None:
            with args.entry_names.open(encoding="utf-8") as handle:
                names = read_group_names(handle)
        data = read_entry(args.wad, WAD_ENTRY)
        items, groups, failures, skipped = extract_item_groups(data, item_ids, names)
        document = build_document(
            items,
            groups,
            failures,
            skipped,
            bin_sha256=hashlib.sha256(data).hexdigest(),
            content_version=args.content_version,
            retrieved_at=args.retrieved_at,
        )
    except (ItemError, WadError, OSError, KeyError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    args.output.write_text(
        json.dumps(document, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(f"items: {len(items)}  groups: {len(groups)}  failures: {len(failures)} -> {args.output}")
    return 0 if not failures else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
