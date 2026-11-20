"""Batch extraction, survey and compilation of champion kits from the installed client (CH-01).

Loads ``Global.es_ES.wad.client`` RST strings and CommunityDragon's hash lists
once, then extracts, drafts or compiles any number of champions in a few seconds.

Usage::

    PYTHONPATH=research python -m binmodel.batch_kits \\
        --game "<Game>" --hashes "<hashes>" --survey

    PYTHONPATH=research python -m binmodel.batch_kits \\
        --game "<Game>" --hashes "<hashes>" --compile Annie,Lux,Jax

    PYTHONPATH=research python -m binmodel.batch_kits \\
        --game "<Game>" --hashes "<hashes>" --compile-all [--check]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from tools import extract_rst

from . import bin2json, extract, kitgen, propbin, specdraft, wad

ROOT = Path(__file__).resolve().parents[2]
VERSION_PATTERN = re.compile(r"(\d+)\.(\d+)\.\d+\+.+")
HASH_LISTS = (
    "hashes.binentries.txt",
    "hashes.binfields.txt",
    "hashes.bintypes.txt",
    "hashes.rst.xxh3.txt",
)


class BatchKitError(Exception):
    """Client assets or champion bin cannot be read without guessing."""


@dataclass(frozen=True)
class ClientAssets:
    """Preloaded hash tables and localized strings shared across champions."""

    champions_dir: Path
    content_version: str
    game_version: str
    tooltips: dict[str, str]
    fields: dict[int, str]
    entries: dict[int, str]


def load_client_assets(game: Path, hashes: Path) -> ClientAssets:
    """Load content version, RST tooltips and bin hash lists once."""
    meta_path = game / "content-metadata.json"
    if not meta_path.is_file():
        raise BatchKitError(f"{meta_path} not found: --game must be the client's Game directory")
    content_version = json.loads(meta_path.read_text(encoding="utf-8")).get("version")
    match = VERSION_PATTERN.fullmatch(content_version) if isinstance(content_version, str) else None
    if match is None:
        raise BatchKitError(f"{meta_path}: unexpected version {content_version!r}")
    game_version = ".".join(match.groups())

    missing = [name for name in HASH_LISTS if not (hashes / name).is_file()]
    if missing:
        raise BatchKitError(f"hash lists missing in {hashes}: {missing}")

    final = game / "DATA" / "FINAL"
    strings_wad = final / "Localized" / "Global.es_ES.wad.client"
    if not strings_wad.is_file():
        raise BatchKitError(f"{strings_wad} not found")

    rst_values: dict[int, str] = {}
    for _, data in extract_rst.read_wad_entries(strings_wad):
        if data.startswith(extract_rst.MAGIC):
            rst_values.update(extract_rst.parse_rst(data))
    rst_names = extract_rst.load_hash_table(hashes / "hashes.rst.xxh3.txt")
    tooltips = {
        rst_names[key].lower(): text for key, text in rst_values.items() if key in rst_names
    }

    fields = bin2json.read_hash_list(hashes / "hashes.binfields.txt")
    fields.update(bin2json.read_hash_list(hashes / "hashes.bintypes.txt"))
    entries = bin2json.read_hash_list(hashes / "hashes.binentries.txt")

    return ClientAssets(
        champions_dir=final / "Champions",
        content_version=content_version,
        game_version=game_version,
        tooltips=tooltips,
        fields=fields,
        entries=entries,
    )


def champion_wad_path(champions_dir: Path, champion_id: str) -> Path:
    """Locate ``<ChampionId>.wad.client`` cleanly."""
    direct = champions_dir / f"{champion_id}.wad.client"
    if direct.is_file():
        return direct
    lower = f"{champion_id.lower()}.wad.client"
    for candidate in champions_dir.iterdir():
        if candidate.name.lower() == lower and candidate.is_file():
            return candidate
    raise BatchKitError(f"missing champion WAD for {champion_id!r} in {champions_dir}")


def extract_champion_from_client(
    champion_id: str, assets: ClientAssets
) -> tuple[dict[str, Any], dict[str, str], str]:
    """Extract one champion from its WAD using preloaded ``assets``."""
    lower = champion_id.lower()
    wad_path = champion_wad_path(assets.champions_dir, champion_id)
    entry_name = f"data/characters/{lower}/{lower}.bin"
    raw_bin = wad.read_entry(wad_path, entry_name)
    bin_sha256 = hashlib.sha256(raw_bin).hexdigest()
    prop = propbin.parse_prop(raw_bin)

    prefixes = (
        f"spell_{lower}",
        f"buff_{lower}",
        f"generatedtip_spell_{lower}",
        f"generatedtip_passive_{lower}",
        f"generatedtip_buff_{lower}",
    )
    champ_tooltips = {k: v for k, v in assets.tooltips.items() if k.startswith(prefixes)}
    bin_strings = bin2json.strings_of(prop)
    for text in bin_strings:
        key = text.lower()
        if key in assets.tooltips:
            champ_tooltips[key] = assets.tooltips[key]

    placeholder_names = bin2json.placeholders(champ_tooltips.values())
    extra = bin2json.candidates((*bin_strings, *placeholder_names, *bin2json.MODE_NAMES))
    names = bin2json.Names(fields=assets.fields, entries=assets.entries, extra=extra)
    bin_doc = bin2json.to_json(prop, names)

    extracted = extract.extract_champion(
        bin_doc,
        source={"artifact_sha256": bin_sha256, "source_file": entry_name},
        game_version=assets.game_version,
        content_version=assets.content_version,
    )
    return extracted.to_dict(), champ_tooltips, bin_sha256


def compile_champion_spec(
    champion_id: str,
    spec_path: Path,
    assets: ClientAssets,
    *,
    output_path: Path | None = None,
) -> tuple[dict[str, Any], str]:
    """Compile a curated ``research/kits/<Id>.spec.json`` against the client bin."""
    extract_doc, champ_tooltips, bin_sha256 = extract_champion_from_client(champion_id, assets)
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    kit_doc = kitgen.compile_kit(extract_doc, champ_tooltips, spec)
    if output_path is not None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(kit_doc, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
            newline="\n",
        )
    return kit_doc, bin_sha256


def survey_all(root: Path, assets: ClientAssets) -> dict[str, Any]:
    """Run ``extract -> specdraft -> kitgen -> parse_kit`` over every snapshot champion."""
    from lol_knowledge.kit.model import parse_kit

    index = json.loads((root / "data/current/champion-index.json").read_text(encoding="utf-8"))
    champion_ids = sorted(entry["id"] for entry in index)
    counts: Counter[str] = Counter()
    issue_counts: Counter[str] = Counter()
    details: dict[str, dict[str, Any]] = {}

    for champion_id in champion_ids:
        try:
            extract_doc, champ_tooltips, bin_sha256 = extract_champion_from_client(
                champion_id, assets
            )
        except Exception as exc:
            counts["extract_failed"] += 1
            details[champion_id] = {"status": "extract_failed", "error": str(exc)}
            continue

        dd_path = root / "data/current/champions" / f"{champion_id}.json"
        ddragon = json.loads(dd_path.read_text(encoding="utf-8")) if dd_path.is_file() else None
        try:
            drafted = specdraft.draft_spec(extract_doc, champ_tooltips, ddragon=ddragon)
            spec = drafted["spec"]
            findings = drafted["review"]["findings"]
            for finding in findings:
                issue_counts[finding["kind"]] += 1
            kit_doc = kitgen.compile_kit(extract_doc, champ_tooltips, spec)
            parse_kit(kit_doc)
        except Exception as exc:
            counts["compile_failed"] += 1
            details[champion_id] = {"status": "compile_failed", "error": str(exc)}
            continue

        slots_with_cases = [
            slot for slot in ("Q", "W", "E", "R") if spec["abilities"].get(slot, {}).get("cases")
        ]
        counts["compile_ok"] += 1
        details[champion_id] = {
            "status": "compile_ok",
            "bin_sha256": bin_sha256,
            "damage_slots": len(slots_with_cases),
            "findings": dict(sorted(Counter(f["kind"] for f in findings).items())),
        }

    return {
        "content_version": assets.content_version,
        "game_version": assets.game_version,
        "total_champions": len(champion_ids),
        "counts": dict(sorted(counts.items())),
        "issue_counts": dict(sorted(issue_counts.items())),
        "champions": details,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m binmodel.batch_kits", description=__doc__)
    parser.add_argument("--game", type=Path, required=True, help="Client Game directory.")
    parser.add_argument("--hashes", type=Path, required=True, help="CommunityDragon hash dir.")
    parser.add_argument("--root", type=Path, default=ROOT, help="Repository root.")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--survey", action="store_true", help="Survey all snapshot champions.")
    mode.add_argument("--compile", help="Comma-separated champion IDs to compile from specs.")
    mode.add_argument(
        "--compile-all", action="store_true", help="Compile every research/kits/*.spec.json."
    )
    parser.add_argument(
        "--check", action="store_true", help="Compile and validate without writing."
    )
    parser.add_argument("--output", type=Path, help="Optional JSON output path for --survey.")
    args = parser.parse_args(argv)

    try:
        assets = load_client_assets(args.game, args.hashes)
    except (BatchKitError, OSError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if args.survey:
        report = survey_all(args.root, assets)
        if args.output is not None:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(
                json.dumps(report, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
                newline="\n",
            )
        print(
            f"survey ({assets.content_version}): {report['total_champions']} champions -> "
            f"{report['counts']}"
        )
        return 0

    from lol_knowledge.kit.model import parse_kit

    kits_dir = args.root / "research" / "kits"
    if args.compile_all:
        spec_paths = sorted(kits_dir.glob("*.spec.json"))
    else:
        ids = [item.strip() for item in args.compile.split(",") if item.strip()]
        spec_paths = [kits_dir / f"{cid}.spec.json" for cid in ids]

    failures = 0
    for spec_path in spec_paths:
        if not spec_path.is_file():
            print(f"error: spec not found: {spec_path}", file=sys.stderr)
            failures += 1
            continue
        champion_id = spec_path.name.removesuffix(".spec.json")
        out_path = (
            None
            if args.check
            else args.root / "lol-knowledge" / "champions" / champion_id / "kit.json"
        )
        try:
            kit_doc, bin_sha = compile_champion_spec(
                champion_id, spec_path, assets, output_path=out_path
            )
            parse_kit(kit_doc)
            action = "checked" if args.check else "compiled"
            print(
                f"{action}: {champion_id} ({len(kit_doc['abilities'])} abilities, {bin_sha[:12]})"
            )
        except Exception as exc:
            print(f"error: {champion_id}: {exc}", file=sys.stderr)
            failures += 1
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
