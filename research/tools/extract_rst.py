"""Extract selected RST v5 strings from a League of Legends WAD.

The parser is read-only and does not need a WAD path dictionary: it scans the
decompressed entries for the ``RST\\x05`` magic. A CommunityDragon hash table is
needed only to turn the 38-bit keys into names.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import struct
import sys
from collections.abc import Iterator
from compression import zstd
from pathlib import Path
from typing import Any

MAGIC = b"RST\x05"
MASK = (1 << 38) - 1
DEFAULT_WAD = Path(
    r"D:\Games\Riot Games\League of Legends\Game\DATA\FINAL\Localized\Global.es_ES.wad.client"
)
DEFAULT_PREFIXES = (
    "spell_zaahen",
    "buff_zaahen",
    "generatedtip_spell_zaahen",
    "generatedtip_passive_zaahen",
    "generatedtip_buff_zaahen",
)


class WadError(Exception):
    """The WAD or RST structure is not the expected one."""


def read_wad_entries(path: Path) -> Iterator[tuple[int, bytes]]:
    """Yield ``(path_hash, data)`` for every decompressible WAD v3 entry."""
    blob = path.read_bytes()
    if len(blob) < 272 or blob[:2] != b"RW":
        raise WadError("not a WAD file")
    major = blob[2]
    if major != 3:
        raise WadError(f"unsupported WAD major version {major}")
    count = struct.unpack_from("<I", blob, 268)[0]
    for index in range(count):
        offset = 272 + index * 32
        path_hash, data_offset, compressed, uncompressed = struct.unpack_from("<QIII", blob, offset)
        flags = blob[offset + 20]
        data_type = flags & 0xF
        if compressed == 0 or data_offset + compressed > len(blob):
            continue
        raw = blob[data_offset : data_offset + compressed]
        try:
            if data_type == 0:
                data = raw
            elif data_type == 1:
                data = gzip.decompress(raw)
            elif data_type == 3:
                data = zstd.decompress(raw)
            else:
                continue
        except Exception:
            continue
        if len(data) != uncompressed:
            continue
        yield path_hash, data


def parse_rst(data: bytes) -> dict[int, str]:
    """Parse one RST v5 chunk into ``{38-bit hash: string}``."""
    if not data.startswith(MAGIC):
        raise WadError("missing RST v5 magic")
    if len(data) < 8:
        raise WadError("RST chunk is too short")
    count = struct.unpack_from("<I", data, 4)[0]
    blob_offset = 8 + 8 * count
    if blob_offset > len(data):
        raise WadError("RST slot table exceeds the chunk")
    result: dict[int, str] = {}
    for index in range(count):
        packed = struct.unpack_from("<Q", data, 8 + index * 8)[0]
        key = packed & MASK
        offset = packed >> 38
        start = blob_offset + offset
        if start >= len(data):
            continue
        end = data.find(b"\0", start)
        if end < 0:
            end = len(data)
        value = data[start:end].decode("utf-8", "replace")
        result.setdefault(key, value)
    return result


def load_hash_table(path: Path) -> dict[int, str]:
    """Load ``hashes.rst.xxh3.txt`` and truncate each hash to 38 bits."""
    table: dict[int, str] = {}
    with path.open(encoding="utf-8", errors="replace") as handle:
        for line in handle:
            parts = line.rstrip("\n").split(" ", 1)
            if len(parts) != 2:
                continue
            try:
                full = int(parts[0], 16)
            except ValueError:
                continue
            table.setdefault(full & MASK, parts[1])
    return table


def select(
    values: dict[int, str],
    names: dict[int, str],
    prefixes: tuple[str, ...],
) -> dict[str, str]:
    """Select strings whose resolved key starts with one of the prefixes."""
    selected: dict[str, str] = {}
    for key, name in names.items():
        if any(name.lower().startswith(prefix) for prefix in prefixes):
            selected[name] = values.get(key, "")
    return dict(sorted(selected.items()))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_fixture(
    wad: Path,
    hash_table: Path,
    *,
    prefixes: tuple[str, ...],
    retrieved_at: str,
) -> dict[str, Any]:
    hashes = load_hash_table(hash_table)
    all_strings: dict[int, str] = {}
    chunks = 0
    for _path_hash, data in read_wad_entries(wad):
        if not data.startswith(MAGIC):
            continue
        chunks += 1
        for key, value in parse_rst(data).items():
            all_strings.setdefault(key, value)
    resolved = {key: hashes[key] for key in all_strings if key in hashes}
    selected = select(all_strings, resolved, prefixes)
    missing = sum(1 for key in all_strings if key not in hashes)
    return {
        "_provenance": {
            "source": "local League of Legends client",
            "wad": wad.name,
            "wad_sha256": sha256(wad),
            "format": "RST v5",
            "hash_bits": 38,
            "rst_chunks": chunks,
            "resolved_strings": len(resolved),
            "unresolved_keys": missing,
            "retrieved_at": retrieved_at,
            "hash_table": hash_table.name,
            "selection_prefixes": list(prefixes),
            "note": (
                "Selected localized strings only. The full WAD and hash table are not versioned. "
                "Values keep the client's @Placeholder@ syntax."
            ),
        },
        "strings": selected,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wad", type=Path, default=DEFAULT_WAD)
    parser.add_argument("--hash-table", type=Path, required=True)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("research/fixtures/zaahen_tooltips_es_es.json"),
    )
    parser.add_argument("--retrieved-at", default="2026-10-20")
    parser.add_argument("--prefix", action="append", dest="prefixes")
    args = parser.parse_args(argv)
    prefixes = tuple(args.prefixes) if args.prefixes else DEFAULT_PREFIXES
    try:
        fixture = build_fixture(
            args.wad,
            args.hash_table,
            prefixes=prefixes,
            retrieved_at=args.retrieved_at,
        )
    except (OSError, WadError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    args.output.write_text(
        json.dumps(fixture, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"wrote {args.output} ({args.output.stat().st_size} bytes)")
    print(f"strings: {len(fixture['strings'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
