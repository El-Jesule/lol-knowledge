"""Pure-Python XXH64, used for WAD path hashes and bin ``file`` fields.

Implemented here to keep the research tooling on the standard library. The test
suite pins it against published vectors and against path hashes observed in the
local game client.
"""

from __future__ import annotations

import struct

_MASK = 0xFFFFFFFFFFFFFFFF
_P1 = 11400714785074694791
_P2 = 14029467366897019727
_P3 = 1609587929392839161
_P4 = 9650029242287828579
_P5 = 2870177450012600261


def _rotl(value: int, bits: int) -> int:
    return ((value << bits) | (value >> (64 - bits))) & _MASK


def _round(acc: int, lane: int) -> int:
    acc = (acc + lane * _P2) & _MASK
    return (_rotl(acc, 31) * _P1) & _MASK


def _merge(acc: int, value: int) -> int:
    acc ^= _round(0, value)
    return (acc * _P1 + _P4) & _MASK


def xxh64(data: bytes, seed: int = 0) -> int:
    """Return the 64-bit XXH64 digest of ``data``."""
    length = len(data)
    offset = 0
    if length >= 32:
        v1 = (seed + _P1 + _P2) & _MASK
        v2 = (seed + _P2) & _MASK
        v3 = seed & _MASK
        v4 = (seed - _P1) & _MASK
        limit = length - 32
        while offset <= limit:
            a, b, c, d = struct.unpack_from("<4Q", data, offset)
            v1, v2, v3, v4 = _round(v1, a), _round(v2, b), _round(v3, c), _round(v4, d)
            offset += 32
        acc = (_rotl(v1, 1) + _rotl(v2, 7) + _rotl(v3, 12) + _rotl(v4, 18)) & _MASK
        for value in (v1, v2, v3, v4):
            acc = _merge(acc, value)
    else:
        acc = (seed + _P5) & _MASK
    acc = (acc + length) & _MASK
    while offset + 8 <= length:
        (lane,) = struct.unpack_from("<Q", data, offset)
        acc ^= _round(0, lane)
        acc = (_rotl(acc, 27) * _P1 + _P4) & _MASK
        offset += 8
    if offset + 4 <= length:
        (lane,) = struct.unpack_from("<I", data, offset)
        acc ^= (lane * _P1) & _MASK
        acc = (_rotl(acc, 23) * _P2 + _P3) & _MASK
        offset += 4
    while offset < length:
        acc ^= (data[offset] * _P5) & _MASK
        acc = (_rotl(acc, 11) * _P1) & _MASK
        offset += 1
    acc ^= acc >> 33
    acc = (acc * _P2) & _MASK
    acc ^= acc >> 29
    acc = (acc * _P3) & _MASK
    acc ^= acc >> 32
    return acc


def path_hash(path: str) -> int:
    """Hash a game path the way WAD tables and bin ``file`` fields do."""
    return xxh64(path.lower().encode("utf-8"))
