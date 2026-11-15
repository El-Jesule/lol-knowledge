"""Extract champion stat records from the local client's WAD archives.

For every champion in the Data Dragon index, this reads
``data/characters/<id>/<id>.bin`` from ``<Champions dir>/<Id>.wad.client`` and
the entry ``Characters/<Id>/CharacterRecords/Root``, and maps the stat fields
to Data Dragon names. Values are float32 in the bin; they are written as the
shortest decimal that round-trips to the same float32. A field absent from the
bin is reported as absent: its class default is not guessed.

Usage::

    python -m binmodel.records --wad-dir "<Game>/DATA/FINAL/Champions" \\
        --index data/current/champion-index.json \\
        --content-version 16.22.8348910+branch.releases-16-22.content.release \\
        --retrieved-at 2026-11-15 --output lol-knowledge/derived/champion-records.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import struct
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from .hashes import fnv1a32
from .propbin import BinType, ObjectValue, PropError, Value, parse_prop
from .wad import WadError, read_entry

SCHEMA = "lol-derived-champion-records/1"
CONTENT_VERSION = re.compile(r"(\d+)\.(\d+)\.\d+\+.+")
BASE_VALUE = fnv1a32("baseValue")

# Bin field name -> Data Dragon stats key. "attackspeedratio" and "critdamagemultiplier"
# have no Data Dragon twin.
FIELD_MAP: dict[str, str] = {
    "baseHPModifiable": "hp",
    "hpPerLevelModifiable": "hpperlevel",
    "baseDamageModifiable": "attackdamage",
    "damagePerLevelModifiable": "attackdamageperlevel",
    "baseArmorModifiable": "armor",
    "armorPerLevelModifiable": "armorperlevel",
    "baseMR": "spellblock",
    "mrPerLevel": "spellblockperlevel",
    "baseMoveSpeedModifiable": "movespeed",
    "attackRangeModifiable": "attackrange",
    "attackSpeedModifiable": "attackspeed",
    "attackSpeedRatioModifiable": "attackspeedratio",
    "attackSpeedPerLevelModifiable": "attackspeedperlevel",
    "critDamageMultiplier": "critdamagemultiplier",
}
FIELD_HASHES = {fnv1a32(name): name for name in FIELD_MAP}


class RecordError(Exception):
    """A champion record could not be read without guessing."""


def f32_decimal(value: float) -> float:
    """Shortest decimal that packs to the same float32 as ``value``."""
    bits = struct.pack("<f", value)
    for digits in range(0, 10):
        candidate = round(value, digits)
        if struct.pack("<f", candidate) == bits:
            return candidate
    return value  # pragma: no cover - 9 decimals always round-trip a float32


def _scalar(node: Any, name: str) -> float:
    if isinstance(node, Value) and node.type is BinType.F32:
        return node.value
    if isinstance(node, ObjectValue):
        inner = node.fields.get(BASE_VALUE)
        if isinstance(inner, Value) and inner.type is BinType.F32:
            return inner.value
        if inner is None and node.class_hash != 0:
            raise RecordError(f"{name}: object without baseValue")
    raise RecordError(f"{name}: unsupported value {type(node).__name__}")


def extract_record(bin_data: bytes, champion_id: str) -> tuple[dict[str, float], list[str]]:
    """Return ``(fields, absent)`` for one champion's ``CharacterRecords/Root``."""
    try:
        prop = parse_prop(bin_data)
    except PropError as exc:
        raise RecordError(f"bin: {exc}") from exc
    entry = prop.entries.get(fnv1a32(f"Characters/{champion_id}/CharacterRecords/Root"))
    if entry is None:
        raise RecordError("CharacterRecords/Root not found")
    fields: dict[str, float] = {}
    for hashed, name in FIELD_HASHES.items():
        node = entry.fields.get(hashed)
        if node is not None:
            fields[FIELD_MAP[name]] = f32_decimal(_scalar(node, name))
    absent = sorted(
        FIELD_MAP[name] for hashed, name in FIELD_HASHES.items() if hashed not in entry.fields
    )
    return dict(sorted(fields.items())), absent


def _wad_files(wad_dir: Path) -> dict[str, Path]:
    files: dict[str, Path] = {}
    for path in wad_dir.glob("*.wad.client"):
        stem = path.name[: -len(".wad.client")]
        if "." in stem:  # localized archives such as Zaahen.es_ES.wad.client
            continue
        files[stem.lower()] = path
    return files


def extract_all(
    wad_dir: Path, champion_ids: Sequence[str]
) -> tuple[dict[str, Any], dict[str, str]]:
    wads = _wad_files(wad_dir)
    champions: dict[str, Any] = {}
    failures: dict[str, str] = {}
    for champion_id in champion_ids:
        wad = wads.get(champion_id.lower())
        if wad is None:
            failures[champion_id] = "no WAD archive for this champion"
            continue
        entry = f"data/characters/{champion_id.lower()}/{champion_id.lower()}.bin"
        try:
            data = read_entry(wad, entry)
            fields, absent = extract_record(data, champion_id)
        except (WadError, RecordError, OSError) as exc:
            failures[champion_id] = str(exc)
            continue
        champions[champion_id] = {
            "wad": wad.name,
            "bin": entry,
            "bin_sha256": hashlib.sha256(data).hexdigest(),
            "fields": fields,
            "absent": absent,
        }
    return champions, failures


def build_document(
    champions: Mapping[str, Any],
    failures: Mapping[str, str],
    *,
    content_version: str,
    retrieved_at: str,
) -> dict[str, Any]:
    match = CONTENT_VERSION.fullmatch(content_version)
    if match is None:
        raise RecordError(f"content version {content_version!r} is not <major>.<minor>.<build>+…")
    return {
        "schema": SCHEMA,
        "label": "Derivado",
        "content_version": content_version,
        "game_version": f"{match.group(1)}.{match.group(2)}",
        "retrieved_at": retrieved_at,
        "source": (
            "Cliente local: DATA/FINAL/Champions/<Id>.wad.client → "
            "data/characters/<id>/<id>.bin → Characters/<Id>/CharacterRecords/Root"
        ),
        "method": (
            "research/binmodel/records.py: lector PROP estricto; float32 escrito como el "
            "decimal más corto equivalente; campos ausentes no se rellenan"
        ),
        "field_map": FIELD_MAP,
        "champions": dict(sorted(champions.items())),
        "failures": dict(sorted(failures.items())),
    }


def _index_ids(index: Any) -> list[str]:
    """Champion ids from the Data Dragon index; anything else is rejected."""
    if not isinstance(index, list) or not index:
        raise RecordError("the champion index must be a non-empty list")
    ids = []
    for entry in index:
        champion_id = entry.get("id") if isinstance(entry, Mapping) else None
        if not isinstance(champion_id, str) or not champion_id:
            raise RecordError("every index entry needs a string 'id'")
        ids.append(champion_id)
    return ids


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m binmodel.records", description=__doc__)
    parser.add_argument("--wad-dir", type=Path, required=True)
    parser.add_argument("--index", type=Path, required=True)
    parser.add_argument("--content-version", required=True)
    parser.add_argument("--retrieved-at", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        ids = _index_ids(json.loads(args.index.read_text(encoding="utf-8")))
        champions, failures = extract_all(args.wad_dir, ids)
        document = build_document(
            champions,
            failures,
            content_version=args.content_version,
            retrieved_at=args.retrieved_at,
        )
    except (OSError, ValueError, KeyError, TypeError, RecordError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(document, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(f"champions: {len(champions)}  failures: {len(failures)}  -> {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
