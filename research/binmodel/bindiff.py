"""Compare a binary PROP bin with a CommunityDragon ``.bin.json`` export.

Both trees are walked in parallel, guided by the binary types. Names in the JSON
export are hashed (FNV-1a for names, classes, paths and links; XXH64 for
``file`` fields) so they can be matched against the binary hashes. Floats are
compared after rounding to float32, so representation noise is not reported.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import struct
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .hashes import fnv1a32
from .propbin import (
    BinType,
    ListValue,
    MapValue,
    ObjectValue,
    OptionValue,
    PropError,
    PropFile,
    Value,
    parse_prop,
)
from .wad import WadError, read_entry
from .xxh64 import path_hash

FNV_TYPES = frozenset({BinType.HASH, BinType.LINK})
INT_TYPES = frozenset(
    {
        BinType.I8,
        BinType.U8,
        BinType.I16,
        BinType.U16,
        BinType.I32,
        BinType.U32,
        BinType.I64,
        BinType.U64,
    }
)
VECTOR_TYPES = frozenset({BinType.VEC2, BinType.VEC3, BinType.VEC4, BinType.MTX44})

CHANGED = "changed"
ADDED = "added"
REMOVED = "removed"
SHAPE = "shape"


@dataclass(frozen=True)
class Difference:
    path: str
    kind: str
    old: Any = None
    new: Any = None


def _hex_hash(text: str) -> int | None:
    if len(text) > 2 and text[0] == "{" and text[-1] == "}":
        try:
            return int(text[1:-1], 16)
        except ValueError:
            return None
    return None


def name_hash(text: str) -> int:
    """FNV-1a of a JSON name, or the raw value of a ``{hex}`` placeholder."""
    raw = _hex_hash(text)
    return fnv1a32(text) if raw is None else raw


def file_hash(text: str) -> int:
    raw = _hex_hash(text)
    return path_hash(text) if raw is None else raw


def _f32(value: float) -> float:
    return struct.unpack("<f", struct.pack("<f", value))[0]


def _flatten(value: Any) -> Any:
    if isinstance(value, list) and value and all(isinstance(row, list) for row in value):
        return [item for row in value for item in row]
    return value


def _same_float(a: float, b: Any) -> bool:
    if not isinstance(b, (int, float)) or isinstance(b, bool):
        return False
    a32, b32 = _f32(a), _f32(float(b))
    return a32 == b32 or (math.isnan(a32) and math.isnan(b32))


def _plain(value: Any) -> Any:
    """Render a binary value for reports."""
    if isinstance(value, Value):
        if isinstance(value.value, tuple):
            return [_plain(Value(BinType.F32, item)) for item in value.value]
        if value.type in FNV_TYPES:
            return f"{{{value.value:08x}}}"
        if value.type is BinType.FILE:
            return f"{{{value.value:016x}}}"
        if value.type is BinType.F32:
            return float(f"{_f32(value.value):.7g}")
        return value.value
    if isinstance(value, ListValue):
        return [_plain(item) for item in value.items]
    if isinstance(value, ObjectValue):
        if value.class_hash == 0:
            return None
        body = {f"{{{name:08x}}}": _plain(item) for name, item in value.fields.items()}
        return {"__type": f"{{{value.class_hash:08x}}}", **body}
    if isinstance(value, OptionValue):
        return None if value.item is None else _plain(value.item)
    if isinstance(value, MapValue):
        return {str(_plain(key)): _plain(item) for key, item in value.items}
    return value


class _Differ:
    def __init__(self) -> None:
        self.differences: list[Difference] = []

    def add(self, path: str, kind: str, old: Any = None, new: Any = None) -> None:
        self.differences.append(Difference(path, kind, old, new))

    def value(self, path: str, binary: Any, old: Any) -> None:
        if isinstance(binary, ObjectValue):
            self.obj(path, binary, old)
        elif isinstance(binary, ListValue):
            self.list(path, binary, old)
        elif isinstance(binary, OptionValue):
            if binary.item is None:
                if old is not None:
                    self.add(path, CHANGED, old, None)
            else:
                self.value(path, binary.item, old)
        elif isinstance(binary, MapValue):
            self.map(path, binary, old)
        else:
            self.scalar(path, binary, old)

    def scalar(self, path: str, binary: Value, old: Any) -> None:
        kind, new = binary.type, binary.value
        if kind is BinType.F32:
            same = _same_float(new, old)
        elif kind in VECTOR_TYPES:
            flat = _flatten(old)
            same = (
                isinstance(flat, list)
                and len(flat) == len(new)
                and all(_same_float(a, b) for a, b in zip(new, flat, strict=True))
            )
        elif kind is BinType.RGBA:
            same = isinstance(old, list) and tuple(old) == new
        elif kind in FNV_TYPES:
            same = (isinstance(old, str) and name_hash(old) == new) or old == new
        elif kind is BinType.FILE:
            same = (isinstance(old, str) and file_hash(old) == new) or old == new
        elif kind in (BinType.BOOL, BinType.FLAG):
            same = old is new
        else:
            same = old == new and type(old) is not bool
        if not same:
            self.add(path, CHANGED, old, _plain(binary))

    def list(self, path: str, binary: ListValue, old: Any) -> None:
        if not isinstance(old, list):
            self.add(path, SHAPE, old, _plain(binary))
            return
        if len(old) != len(binary.items):
            self.add(path, SHAPE, old, _plain(binary))
            return
        for index, (item, previous) in enumerate(zip(binary.items, old, strict=True)):
            self.value(f"{path}[{index}]", item, previous)

    def obj(self, path: str, binary: ObjectValue, old: Any) -> None:
        if binary.class_hash == 0:
            if old is not None:
                self.add(path, CHANGED, old, None)
            return
        if not isinstance(old, dict):
            self.add(path, SHAPE, old, _plain(binary))
            return
        old_type = old.get("__type")
        if isinstance(old_type, str) and name_hash(old_type) != binary.class_hash:
            self.add(f"{path}.__type", CHANGED, old_type, f"{{{binary.class_hash:08x}}}")
            return
        self.fields(path, binary.fields, old)

    def fields(self, path: str, fields: dict[int, Any], old: dict[str, Any]) -> None:
        named = {name_hash(key): key for key in old if not key.startswith("__")}
        for hashed, item in fields.items():
            key = named.get(hashed)
            if key is None:
                self.add(f"{path}.{{{hashed:08x}}}", ADDED, None, _plain(item))
            else:
                self.value(f"{path}.{key}", item, old[key])
        for hashed in named.keys() - fields.keys():
            key = named[hashed]
            self.add(f"{path}.{key}", REMOVED, old[key], None)

    def _map_key(self, key_type: BinType, key: str) -> Any:
        if key_type in FNV_TYPES:
            return name_hash(key)
        if key_type is BinType.FILE:
            return file_hash(key)
        if key_type in INT_TYPES:
            try:
                return int(key)
            except ValueError:
                return key
        return key

    def map(self, path: str, binary: MapValue, old: Any) -> None:
        if not isinstance(old, dict):
            self.add(path, SHAPE, old, _plain(binary))
            return
        previous = {self._map_key(binary.key_type, key): key for key in old}
        current: dict[Any, Any] = {}
        for key, item in binary.items:
            if not isinstance(key, Value):
                raise PropError(f"{path}: composite map keys are not supported")
            current[key.value] = (key, item)
        for raw_key, (key, item) in current.items():
            label = previous.get(raw_key, _plain(key))
            if raw_key in previous:
                self.value(f"{path}{{{label}}}", item, old[previous[raw_key]])
            else:
                self.add(f"{path}{{{label}}}", ADDED, None, _plain(item))
        for raw_key in previous.keys() - current.keys():
            label = previous[raw_key]
            self.add(f"{path}{{{label}}}", REMOVED, old[label], None)


def diff_prop(prop: PropFile, document: dict[str, Any]) -> list[Difference]:
    """Return the differences between a parsed bin and a JSON export.

    ``old`` holds the JSON (export) value and ``new`` the binary value.
    Top-level keys starting with ``__`` (export metadata) are ignored.
    """
    differ = _Differ()
    named = {name_hash(key): key for key in document if not key.startswith("__")}
    for hashed, entry in prop.entries.items():
        key = named.get(hashed)
        if key is None:
            differ.add(f"{{{hashed:08x}}}", ADDED, None, f"{{{entry.class_hash:08x}}}")
            continue
        binary = ObjectValue(BinType.EMBED, entry.class_hash, entry.fields)
        differ.obj(key, binary, document[key])
    for hashed in named.keys() - prop.entries.keys():
        differ.add(named[hashed], REMOVED, document[named[hashed]].get("__type"), None)
    return differ.differences


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m binmodel.bindiff",
        description="Compare a binary PROP bin with a CommunityDragon .bin.json export.",
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--bin", type=Path, help="Binary PROP file.")
    source.add_argument("--wad", type=Path, help="WAD archive that contains --entry.")
    parser.add_argument("--entry", help="Path inside --wad, e.g. data/characters/x/x.bin.")
    parser.add_argument("--against", type=Path, required=True, help="Reference .bin.json.")
    parser.add_argument("--json", action="store_true", help="Print a JSON report.")
    parser.add_argument("--check", action="store_true", help="Exit 1 when differences exist.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.wad is not None and not args.entry:
        parser.error("--wad requires --entry")
    try:
        if args.wad is not None:
            data = read_entry(args.wad, args.entry)
            source = {"wad": args.wad.name, "entry": args.entry}
        else:
            data = args.bin.read_bytes()
            source = {"bin": args.bin.name}
        reference = args.against.read_bytes()
        document = json.loads(reference.decode("utf-8"))
        if not isinstance(document, dict):
            raise ValueError("the reference export must be a JSON object")
        prop = parse_prop(data)
        differences = diff_prop(prop, document)
    except (OSError, ValueError, WadError, PropError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    report = {
        "source": {**source, "sha256": _sha256(data), "bytes": len(data)},
        "reference": {"file": args.against.name, "sha256": _sha256(reference)},
        "entries": len(prop.entries),
        "differences": [asdict(item) for item in differences],
    }
    if args.json:
        text = json.dumps(report, indent=2, ensure_ascii=False)
    else:
        lines = [
            f"source sha256: {report['source']['sha256']}",
            f"reference sha256: {report['reference']['sha256']}",
            f"entries: {report['entries']}",
            f"differences: {len(differences)}",
        ]
        for item in differences:
            lines.append(
                f"{item.kind}: {item.path}: "
                f"{json.dumps(item.old, ensure_ascii=False)} -> "
                f"{json.dumps(item.new, ensure_ascii=False)}"
            )
        text = "\n".join(lines)
    sys.stdout.buffer.write((text + "\n").encode("utf-8"))
    return 1 if args.check and differences else 0


if __name__ == "__main__":
    raise SystemExit(main())
