"""Read one named entry from a WAD v3 archive (``*.wad.client``).

Entries are located by the XXH64 hash of their lowercased path. Only raw (0),
gzip (1) and single-frame zstd (3) entries are decoded. Satellite (2) and
sub-chunked zstd (4) entries raise ``WadError`` instead of being guessed.
"""

from __future__ import annotations

import gzip
import struct
import zlib
from compression import zstd
from dataclasses import dataclass
from pathlib import Path

from .xxh64 import path_hash

HEADER_SIZE = 272
ENTRY_SIZE = 32
COUNT_OFFSET = 268

RAW = 0
GZIP = 1
SATELLITE = 2
ZSTD = 3
ZSTD_MULTI = 4


class WadError(Exception):
    """The archive or the requested entry cannot be read safely."""


@dataclass(frozen=True)
class WadEntry:
    path_hash: int
    offset: int
    compressed_size: int
    size: int
    data_type: int


def read_table(blob: bytes) -> dict[int, WadEntry]:
    """Parse the WAD v3 table of contents from the start of the archive."""
    if len(blob) < HEADER_SIZE or blob[:2] != b"RW":
        raise WadError("not a WAD archive")
    if blob[2] != 3:
        raise WadError(f"unsupported WAD major version {blob[2]}")
    (count,) = struct.unpack_from("<I", blob, COUNT_OFFSET)
    if HEADER_SIZE + count * ENTRY_SIZE > len(blob):
        raise WadError("table of contents exceeds the file")
    table: dict[int, WadEntry] = {}
    for index in range(count):
        base = HEADER_SIZE + index * ENTRY_SIZE
        hashed, offset, compressed, size = struct.unpack_from("<QIII", blob, base)
        table[hashed] = WadEntry(hashed, offset, compressed, size, blob[base + 20] & 0x0F)
    return table


def _read_head(handle) -> bytes:
    """Read the header and the whole table of contents, nothing else."""
    head = handle.read(HEADER_SIZE)
    if len(head) < HEADER_SIZE:
        raise WadError("not a WAD archive")
    (count,) = struct.unpack_from("<I", head, COUNT_OFFSET)
    return head + handle.read(count * ENTRY_SIZE)


def _decode(raw: bytes, entry: WadEntry) -> bytes:
    if entry.data_type == RAW:
        return raw
    if entry.data_type == GZIP:
        return gzip.decompress(raw)
    if entry.data_type == ZSTD:
        return zstd.decompress(raw)
    raise WadError(f"entry type {entry.data_type} is not supported")


def read_entry(wad: Path, path: str) -> bytes:
    """Return the decoded bytes of ``path`` inside ``wad``.

    Only the table of contents and the requested entry are read from disk.
    """
    with wad.open("rb") as handle:
        table = read_table(_read_head(handle))
        entry = table.get(path_hash(path))
        if entry is None:
            raise WadError(f"{path} is not in {wad.name}")
        handle.seek(0, 2)
        if entry.offset + entry.compressed_size > handle.tell():
            raise WadError(f"{path}: data exceeds the archive")
        handle.seek(entry.offset)
        raw = handle.read(entry.compressed_size)
    try:
        data = _decode(raw, entry)
    except (OSError, EOFError, zlib.error, zstd.ZstdError) as exc:
        raise WadError(f"{path}: cannot decompress ({exc})") from exc
    if len(data) != entry.size:
        raise WadError(f"{path}: expected {entry.size} bytes, got {len(data)}")
    return data
