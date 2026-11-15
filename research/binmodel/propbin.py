"""Strict reader for binary ``PROP`` bin files (bin format version 1–3).

The reader returns a typed tree that keeps every field name, class and path as
its 32-bit FNV-1a hash. It never guesses: an unknown type, a truncated buffer or
an entry whose declared size does not match the parsed bytes raises
``PropError``.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any


class PropError(Exception):
    """The buffer is not a well-formed PROP bin."""


class BinType(IntEnum):
    NONE = 0x00
    BOOL = 0x01
    I8 = 0x02
    U8 = 0x03
    I16 = 0x04
    U16 = 0x05
    I32 = 0x06
    U32 = 0x07
    I64 = 0x08
    U64 = 0x09
    F32 = 0x0A
    VEC2 = 0x0B
    VEC3 = 0x0C
    VEC4 = 0x0D
    MTX44 = 0x0E
    RGBA = 0x0F
    STRING = 0x10
    HASH = 0x11
    FILE = 0x12
    LIST = 0x80
    LIST2 = 0x81
    POINTER = 0x82
    EMBED = 0x83
    LINK = 0x84
    OPTION = 0x85
    MAP = 0x86
    FLAG = 0x87


_FORMATS: dict[BinType, str] = {
    BinType.BOOL: "<?",
    BinType.I8: "<b",
    BinType.U8: "<B",
    BinType.I16: "<h",
    BinType.U16: "<H",
    BinType.I32: "<i",
    BinType.U32: "<I",
    BinType.I64: "<q",
    BinType.U64: "<Q",
    BinType.F32: "<f",
    BinType.VEC2: "<2f",
    BinType.VEC3: "<3f",
    BinType.VEC4: "<4f",
    BinType.MTX44: "<16f",
    BinType.RGBA: "<4B",
    BinType.HASH: "<I",
    BinType.FILE: "<Q",
    BinType.LINK: "<I",
    BinType.FLAG: "<?",
}

CONTAINERS = frozenset({BinType.LIST, BinType.LIST2})
OBJECTS = frozenset({BinType.POINTER, BinType.EMBED})


@dataclass(frozen=True)
class Value:
    """A primitive value. Vectors, matrices and colours are tuples."""

    type: BinType
    value: Any


@dataclass(frozen=True)
class ListValue:
    type: BinType
    item_type: BinType
    items: tuple[Any, ...]


@dataclass(frozen=True)
class ObjectValue:
    """A pointer or embed. ``class_hash == 0`` means a null pointer."""

    type: BinType
    class_hash: int
    fields: dict[int, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class OptionValue:
    item_type: BinType
    item: Any | None


@dataclass(frozen=True)
class MapValue:
    key_type: BinType
    value_type: BinType
    items: tuple[tuple[Any, Any], ...]


@dataclass(frozen=True)
class Entry:
    path_hash: int
    class_hash: int
    fields: dict[int, Any]


@dataclass(frozen=True)
class Patch:
    path_hash: int
    path: str
    value: Any


@dataclass(frozen=True)
class PropFile:
    version: int
    linked: tuple[str, ...]
    entries: dict[int, Entry]
    patches: tuple[Patch, ...] = ()
    is_patch: bool = False


class _Reader:
    def __init__(self, data: bytes) -> None:
        self.data = data
        self.pos = 0

    def take(self, fmt: str) -> Any:
        size = struct.calcsize(fmt)
        if self.pos + size > len(self.data):
            raise PropError(f"truncated at byte {self.pos}: need {size} bytes")
        values = struct.unpack_from(fmt, self.data, self.pos)
        self.pos += size
        return values[0] if len(values) == 1 else values

    def string(self) -> str:
        length = self.take("<H")
        end = self.pos + length
        if end > len(self.data):
            raise PropError(f"truncated string at byte {self.pos}")
        try:
            text = self.data[self.pos : end].decode("utf-8")
        except UnicodeDecodeError as exc:
            raise PropError(f"invalid UTF-8 string at byte {self.pos}") from exc
        self.pos = end
        return text

    def bin_type(self) -> BinType:
        raw = self.take("<B")
        try:
            return BinType(raw)
        except ValueError as exc:
            raise PropError(f"unknown bin type 0x{raw:02x} at byte {self.pos - 1}") from exc

    def expect_end(self, end: int, what: str) -> None:
        if self.pos != end:
            raise PropError(f"{what}: declared end {end}, parsed end {self.pos}")


def _value(reader: _Reader, kind: BinType) -> Any:
    if kind is BinType.NONE:
        return Value(kind, None)
    if kind in _FORMATS:
        return Value(kind, reader.take(_FORMATS[kind]))
    if kind is BinType.STRING:
        return Value(kind, reader.string())
    if kind in CONTAINERS:
        item_type = reader.bin_type()
        size = reader.take("<I")
        end = reader.pos + size
        count = reader.take("<I")
        items = tuple(_value(reader, item_type) for _ in range(count))
        reader.expect_end(end, "list")
        return ListValue(kind, item_type, items)
    if kind in OBJECTS:
        class_hash = reader.take("<I")
        if class_hash == 0:
            return ObjectValue(kind, 0)
        size = reader.take("<I")
        end = reader.pos + size
        count = reader.take("<H")
        fields = _fields(reader, count)
        reader.expect_end(end, f"object 0x{class_hash:08x}")
        return ObjectValue(kind, class_hash, fields)
    if kind is BinType.OPTION:
        item_type = reader.bin_type()
        count = reader.take("<B")
        if count > 1:
            raise PropError(f"option with {count} values at byte {reader.pos - 1}")
        return OptionValue(item_type, _value(reader, item_type) if count else None)
    if kind is BinType.MAP:
        key_type = reader.bin_type()
        value_type = reader.bin_type()
        size = reader.take("<I")
        end = reader.pos + size
        count = reader.take("<I")
        items = tuple((_value(reader, key_type), _value(reader, value_type)) for _ in range(count))
        reader.expect_end(end, "map")
        return MapValue(key_type, value_type, items)
    raise PropError(f"unhandled bin type {kind!r}")  # pragma: no cover - enum is exhaustive


def _fields(reader: _Reader, count: int) -> dict[int, Any]:
    fields: dict[int, Any] = {}
    for _ in range(count):
        name = reader.take("<I")
        if name in fields:
            raise PropError(f"duplicate field 0x{name:08x} at byte {reader.pos - 4}")
        fields[name] = _value(reader, reader.bin_type())
    return fields


def parse_prop(data: bytes) -> PropFile:
    """Parse a PROP (or PTCH-wrapped PROP) bin buffer."""
    reader = _Reader(data)
    is_patch = data[:4] == b"PTCH"
    if is_patch:
        reader.pos = 4
        reader.take("<Q")
    if reader.data[reader.pos : reader.pos + 4] != b"PROP":
        raise PropError("missing PROP magic")
    reader.pos += 4
    version = reader.take("<I")
    if version not in (1, 2, 3):
        raise PropError(f"unsupported PROP version {version}")
    linked: tuple[str, ...] = ()
    if version >= 2:
        linked = tuple(reader.string() for _ in range(reader.take("<I")))
    count = reader.take("<I")
    classes = [reader.take("<I") for _ in range(count)]
    entries: dict[int, Entry] = {}
    for class_hash in classes:
        size = reader.take("<I")
        end = reader.pos + size
        path_hash = reader.take("<I")
        fields = _fields(reader, reader.take("<H"))
        reader.expect_end(end, f"entry 0x{path_hash:08x}")
        if path_hash in entries:
            raise PropError(f"duplicate entry 0x{path_hash:08x}")
        entries[path_hash] = Entry(path_hash, class_hash, fields)
    patches: list[Patch] = []
    if is_patch and version >= 3:
        for _ in range(reader.take("<I")):
            path_hash = reader.take("<I")
            size = reader.take("<I")
            end = reader.pos + size
            kind = reader.bin_type()
            path = reader.string()
            patches.append(Patch(path_hash, path, _value(reader, kind)))
            reader.expect_end(end, f"patch 0x{path_hash:08x}")
    if reader.pos != len(data):
        raise PropError(f"{len(data) - reader.pos} trailing bytes after the last entry")
    return PropFile(version, linked, entries, tuple(patches), is_patch)
