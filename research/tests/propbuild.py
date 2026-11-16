"""Tiny PROP and WAD encoders used to build synthetic test inputs."""

from __future__ import annotations

import struct
from compression import zstd

from binmodel.hashes import fnv1a32
from binmodel.propbin import BinType as T
from binmodel.xxh64 import path_hash

PRIM = {
    T.BOOL: "<?",
    T.U8: "<B",
    T.I32: "<i",
    T.U32: "<I",
    T.F32: "<f",
    T.VEC3: "<3f",
    T.MTX44: "<16f",
    T.RGBA: "<4B",
    T.HASH: "<I",
    T.FILE: "<Q",
    T.LINK: "<I",
    T.FLAG: "<?",
}


def prim(kind, value):
    return (kind, value)


def name(text: str) -> int:
    """FNV-1a of ``text``, or the raw value of a ``{hex}`` placeholder."""
    if text.startswith("{") and text.endswith("}"):
        return int(text[1:-1], 16)
    return fnv1a32(text)


def obj(class_name, fields, kind=T.EMBED):
    return (kind, (name(class_name), fields))


def null(kind=T.POINTER):
    return (kind, None)


def lst(item_type, items):
    return (T.LIST, (item_type, items))


def opt(item_type, item=None):
    return (T.OPTION, (item_type, item))


def mapping(key_type, value_type, items):
    return (T.MAP, (key_type, value_type, items))


def encode_value(node) -> bytes:
    kind, value = node
    if kind in PRIM:
        packed = value if isinstance(value, tuple) else (value,)
        return struct.pack(PRIM[kind], *packed)
    if kind is T.STRING:
        raw = value.encode("utf-8")
        return struct.pack("<H", len(raw)) + raw
    if kind is T.LIST:
        item_type, items = value
        body = struct.pack("<I", len(items)) + b"".join(encode_value(i) for i in items)
        return struct.pack("<BI", item_type, len(body)) + body
    if kind in (T.EMBED, T.POINTER):
        if value is None:
            return struct.pack("<I", 0)
        class_hash, fields = value
        body = struct.pack("<H", len(fields)) + encode_fields(fields)
        return struct.pack("<II", class_hash, len(body)) + body
    if kind is T.OPTION:
        item_type, item = value
        if item is None:
            return struct.pack("<BB", item_type, 0)
        return struct.pack("<BB", item_type, 1) + encode_value(item)
    if kind is T.MAP:
        key_type, value_type, items = value
        body = struct.pack("<I", len(items)) + b"".join(
            encode_value(k) + encode_value(v) for k, v in items
        )
        return struct.pack("<BBI", key_type, value_type, len(body)) + body
    raise ValueError(kind)


def encode_fields(fields) -> bytes:
    out = b""
    for field_name, node in fields.items():
        out += struct.pack("<IB", fnv1a32(field_name), node[0]) + encode_value(node)
    return out


def encode_prop(entries, *, version=3, linked=()) -> bytes:
    """``entries`` maps a path name to ``(class_name, fields)``."""
    out = b"PROP" + struct.pack("<I", version)
    if version >= 2:
        out += struct.pack("<I", len(linked))
        for item in linked:
            raw = item.encode("utf-8")
            out += struct.pack("<H", len(raw)) + raw
    out += struct.pack("<I", len(entries))
    out += b"".join(struct.pack("<I", name(cls)) for cls, _ in entries.values())
    for path, (_cls, fields) in entries.items():
        body = struct.pack("<IH", fnv1a32(path), len(fields)) + encode_fields(fields)
        out += struct.pack("<I", len(body)) + body
    return out


def encode_wad(files) -> bytes:
    """``files`` maps a path to ``(data_type, data)``; only types 0, 3 and 4 are built."""
    header = bytearray(b"RW" + bytes([3, 4]) + bytes(268 - 4))
    header += struct.pack("<I", len(files))
    table = bytearray()
    payload = bytearray()
    offset = 272 + 32 * len(files)
    for path, (data_type, data) in files.items():
        stored = zstd.compress(data) if data_type in (3, 4) else data
        table += struct.pack(
            "<QIII", path_hash(path), offset + len(payload), len(stored), len(data)
        )
        table += bytes([data_type, 0]) + struct.pack("<HQ", 0, 0)
        payload += stored
    return bytes(header + table + payload)
