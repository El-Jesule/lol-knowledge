"""Turn a binary PROP bin into the JSON of CommunityDragon's ``.bin.json`` exports.

The extractor (``python -m binmodel``) reads those exports. When CommunityDragon
cannot be reached, this module produces the same shape from the bin of the
installed client, so a champion can be extracted for the client's own patch.

Names come from CommunityDragon's hash lists (``hashes.binentries.txt``,
``hashes.binfields.txt`` and ``hashes.bintypes.txt``) and from extra candidate
names (``--names``): the strings of the bin itself and, for calculation names,
the ``@placeholders@`` of the tooltips. A hash with no known name stays
``{xxxxxxxx}``, as in the exports; nothing is guessed. Floats keep their float32
value, written as the double that holds it (0.15000000596046448), like the
exports.

Usage::

    python -m binmodel.bin2json --wad "<Game>/DATA/FINAL/Champions/Ahri.wad.client" \\
        --entry data/characters/ahri/ahri.bin --hashes <dir with the hash lists> \\
        --names ahri-tooltips.json --output ahri.bin.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
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

HASH_LISTS = ("hashes.binentries.txt", "hashes.binfields.txt", "hashes.bintypes.txt")
PLACEHOLDER = re.compile(r"@(?:[A-Za-z0-9_.]+:)?([A-Za-z_][A-Za-z0-9_.]*)[^@]*@")
# Game mode keys of ``DataValuesModeOverride``, spelled as the exports spell them.
MODE_NAMES = ("CLASSIC", "ARAM", "cherry", "KIWI", "URF")


@dataclass(frozen=True)
class Names:
    """Known names by FNV-1a hash: fields and classes, entries, and extra candidates."""

    fields: Mapping[int, str]
    entries: Mapping[int, str]
    extra: Mapping[int, str]

    def field(self, value: int) -> str:
        return self.fields.get(value) or self.extra.get(value) or _hex(value)

    def entry(self, value: int) -> str:
        return self.entries.get(value) or self.extra.get(value) or _hex(value)

    def hashed(self, value: int) -> str:
        """A ``hash`` value: an entry, a field or class name, or a candidate."""
        return (
            self.entries.get(value)
            or self.extra.get(value)
            or self.fields.get(value)
            or _hex(value)
        )


def _hex(value: int) -> str:
    return f"{{{value:08x}}}"


def read_hash_list(path: Path) -> dict[int, str]:
    names: dict[int, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        value, _, name = line.partition(" ")
        if name:
            names[int(value, 16)] = name
    return names


def candidates(names: Iterable[str]) -> dict[int, str]:
    """Candidate names by hash; the first spelling of a name wins."""
    table: dict[int, str] = {}
    for name in names:
        table.setdefault(fnv1a32(name), name)
    return table


def strings_of(prop: PropFile) -> list[str]:
    """Every string value of the bin, in reading order."""
    found: list[str] = []

    def walk(value: Any) -> None:
        if isinstance(value, Value):
            if value.type is BinType.STRING:
                found.append(value.value)
        elif isinstance(value, ListValue):
            for item in value.items:
                walk(item)
        elif isinstance(value, ObjectValue):
            for item in value.fields.values():
                walk(item)
        elif isinstance(value, OptionValue):
            if value.item is not None:
                walk(value.item)
        elif isinstance(value, MapValue):
            for key, item in value.items:
                walk(key)
                walk(item)

    for entry in prop.entries.values():
        for item in entry.fields.values():
            walk(item)
    return found


def placeholders(texts: Iterable[str]) -> list[str]:
    """Names of the ``@Name@`` / ``@Name*100@`` placeholders of ``texts``."""
    return [match for text in texts for match in PLACEHOLDER.findall(text)]


def _value(value: Any, names: Names) -> Any:
    if isinstance(value, Value):
        if value.type is BinType.LINK:
            return names.entry(value.value)
        if value.type is BinType.HASH:
            return names.hashed(value.value)
        if value.type is BinType.FILE:
            return f"{{{value.value:016x}}}"
        if isinstance(value.value, tuple):
            if value.type is BinType.MTX44:
                rows = value.value
                return [list(rows[index : index + 4]) for index in range(0, 16, 4)]
            return list(value.value)
        return value.value
    if isinstance(value, ListValue):
        return [_value(item, names) for item in value.items]
    if isinstance(value, ObjectValue):
        if value.class_hash == 0:
            return None
        return _object(value.class_hash, value.fields, names)
    if isinstance(value, OptionValue):
        return None if value.item is None else _value(value.item, names)
    if isinstance(value, MapValue):
        result: dict[str, Any] = {}
        for key, item in value.items:
            if not isinstance(key, Value):
                raise PropError("composite map keys are not supported")
            rendered = _value(key, names)
            result[str(rendered)] = _value(item, names)
        return result
    raise PropError(f"unsupported value {value!r}")


def _object(class_hash: int, fields: Mapping[int, Any], names: Names) -> dict[str, Any]:
    body = {names.field(key): _value(item, names) for key, item in fields.items()}
    body["__type"] = names.field(class_hash)
    return body


def to_json(prop: PropFile, names: Names) -> dict[str, Any]:
    """The export-shaped document: one object per entry, keyed by its path."""
    document: dict[str, Any] = {
        names.entry(entry.path_hash): _object(entry.class_hash, entry.fields, names)
        for entry in prop.entries.values()
    }
    document["__linked"] = list(prop.linked)
    return document


def load_names(hash_dir: Path, extra: Iterable[str] = ()) -> Names:
    entries = read_hash_list(hash_dir / HASH_LISTS[0])
    fields = read_hash_list(hash_dir / HASH_LISTS[1])
    fields.update(read_hash_list(hash_dir / HASH_LISTS[2]))
    return Names(fields, entries, candidates([*extra, *MODE_NAMES]))


def _tooltip_texts(path: Path) -> list[str]:
    document = json.loads(path.read_text(encoding="utf-8"))
    strings = document.get("strings", document) if isinstance(document, dict) else {}
    return [text for text in strings.values() if isinstance(text, str)]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m binmodel.bin2json", description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--bin", type=Path, help="Binary PROP file.")
    source.add_argument("--wad", type=Path, help="WAD archive that contains --entry.")
    parser.add_argument("--entry", help="Path inside --wad, e.g. data/characters/x/x.bin.")
    parser.add_argument("--hashes", type=Path, required=True, help="Directory of hash lists.")
    parser.add_argument(
        "--names",
        type=Path,
        action="append",
        default=[],
        help="Tooltips JSON whose @placeholders@ name calculations (repeatable).",
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.wad is not None and not args.entry:
        parser.error("--wad requires --entry")
    try:
        data = read_entry(args.wad, args.entry) if args.wad is not None else args.bin.read_bytes()
        prop = parse_prop(data)
        texts = [text for path in args.names for text in _tooltip_texts(path)]
        names = load_names(args.hashes, [*strings_of(prop), *placeholders(texts)])
        document = to_json(prop, names)
    except (OSError, ValueError, WadError, PropError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    args.output.write_text(json.dumps(document, ensure_ascii=False) + "\n", encoding="utf-8")
    unresolved = len(re.findall(r'"\{[0-9a-f]{8}\}"', json.dumps(document)))
    print(f"entries: {len(document)}; unresolved names: {unresolved} -> {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
