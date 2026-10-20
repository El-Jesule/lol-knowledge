"""Command line entry point: ``python -m binmodel``."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

from .evaluate import FormulaError
from .extract import ExtractionError, extract_champion
from .registry import Registry
from .stats import champion_stats
from .traverse import TraversalError
from .validation import (
    evaluate_all_calculations,
    validate_ad_growth,
    validate_one_stack,
    validate_passive_percent,
)

DEFAULT_INPUT = Path("research/.cache/zaahen-16.20.bin.json")
DEFAULT_CONTENT_VERSION = "16.20.8248524+branch.releases-16-20.content.release"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="binmodel",
        description="Extract typed calculation trees from a decoded LoL bin JSON.",
    )
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, help="Write the full JSON extract here.")
    parser.add_argument("--schema", type=Path, help="Override the class registry path.")
    parser.add_argument("--source-url", default="")
    parser.add_argument("--game-version", default="16.20")
    parser.add_argument("--content-version", default=DEFAULT_CONTENT_VERSION)
    parser.add_argument("--retrieved-at", default="2026-10-20")
    parser.add_argument("--expect-sha256", help="Fail when the input hash does not match.")
    parser.add_argument("--json", action="store_true", help="Print the full JSON extract.")
    parser.add_argument("--validate", action="store_true", help="Include measurement validation.")
    parser.add_argument("--level", type=int)
    parser.add_argument("--rank", type=int)
    parser.add_argument("--bonus-ad", type=float)
    parser.add_argument("--self-check", action="store_true", help="Exit 1 on error diagnostics.")
    return parser


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _summary(extract, *, validation: dict[str, Any] | None, damage: dict[str, Any] | None) -> str:
    bot_unresolved = sum(
        len(item.bot_data.get("unresolved", [])) for item in extract.abilities if item.bot_data
    )
    bot_calculations = sum(
        len(item.bot_data.get("calculations", [])) for item in extract.abilities if item.bot_data
    )
    lines = [
        f"champion: {extract.champion['id']}",
        f"game version: {extract.game_version}",
        f"content version: {extract.content_version}",
        f"input sha256: {extract.source.get('input_sha256', '')}",
        f"artifact sha256: {extract.source.get('artifact_sha256', '')}",
        f"abilities: {len(extract.abilities)}",
        f"calculations: {sum(len(item.calculations) for item in extract.abilities)}",
        f"bot calculations: {bot_calculations}",
        f"data values: {sum(len(item.data_values) for item in extract.abilities)}",
        f"unresolved formula nodes: {len(extract.unresolved)}",
        f"unresolved BotData nodes: {bot_unresolved}",
        f"diagnostics: {len(extract.diagnostics)}",
    ]
    for ability in extract.abilities:
        lines.append(
            f"  {ability.slot:<7} {ability.path.rsplit('/', 1)[-1]:<24} "
            f"ranks={ability.level_count} calcs={len(ability.calculations)} "
            f"values={len(ability.data_values)}"
        )
    if validation and "ad" in validation:
        lines.append("")
        lines.append("AD growth:")
        for row in validation["ad"]["rows"]:
            lines.append(
                f"  level {row['level']:>2}: {row['computed']:.3f} -> {row['displayed']} "
                f"(observed {row['observed']}) {'ok' if row['match'] else 'MISMATCH'}"
            )
        lines.append("passive percent:")
        for row in validation["passive"]["rows"]:
            lines.append(
                f"  level {row['level']:>2}: {row['displayed_percent']:.1f}% "
                f"(observed {row['observed_percent']:.1f}%) "
                f"{'ok' if row['match'] else 'MISMATCH'}"
            )
        lines.append("one stack at 18:")
        for row in validation["one_stack"]["rows"]:
            lines.append(
                f"  {row['basis']}: +{row['bonus_ad']:.3f} -> {row['displayed_after']} "
                f"{'matches 146' if row['matches_146'] else ''}"
            )
    elif validation and validation.get("note"):
        lines.append("")
        lines.append(validation["note"])
    if damage:
        lines.append("")
        lines.append("damage at level/rank:")
        for key, value in damage.items():
            if "error" in value:
                lines.append(f"  {key}: unresolved ({value['code']})")
            else:
                lines.append(f"  {key}: {value['value']:.3f} (complete={value['complete']})")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        level = args.level if args.level is not None else 1
        rank = args.rank if args.rank is not None else 1
        bonus_ad = args.bonus_ad if args.bonus_ad is not None else 0.0
        if level < 1 or rank < 1:
            print("error: --level and --rank must be >= 1", file=sys.stderr)
            return 2
        document = _read_json(args.input)
        input_sha256 = _sha256(args.input)
        if args.expect_sha256 and input_sha256.lower() != args.expect_sha256.lower():
            print(
                f"error: sha256 mismatch: {input_sha256} != {args.expect_sha256}",
                file=sys.stderr,
            )
            return 2
        provenance = document.get("_provenance") if isinstance(document, dict) else None
        artifact_sha256 = (
            provenance.get("source_sha256") if isinstance(provenance, dict) else None
        ) or input_sha256
        source_url = args.source_url or (
            provenance.get("url") if isinstance(provenance, dict) else ""
        )
        content_version = args.content_version
        if isinstance(provenance, dict) and provenance.get("content_version"):
            content_version = str(provenance["content_version"])
        registry = Registry(args.schema) if args.schema else Registry()
        extract = extract_champion(
            document,
            source={
                "url": source_url,
                "input": str(args.input),
                "input_sha256": input_sha256,
                "artifact_sha256": artifact_sha256,
                "retrieved_at": args.retrieved_at,
            },
            registry=registry,
            game_version=args.game_version,
            content_version=content_version,
        )
        validation = None
        if args.validate:
            abilities = {item.ability_id: item for item in extract.abilities}
            passive = abilities.get("passive")
            has_percent = passive is not None and any(
                item.name == "PercentBonusADCalc" for item in passive.calculations
            )
            if extract.champion["id"] == "Zaahen" and has_percent:
                validation = {
                    "ad": validate_ad_growth(extract.champion["base_stats"]),
                    "passive": validate_passive_percent(passive),
                    "one_stack": validate_one_stack(extract.champion["base_stats"], passive),
                }
            else:
                validation = {
                    "champion": extract.champion["id"],
                    "note": "Measurement validation is Zaahen-specific; skipped.",
                }
        damage = None
        if args.level is not None or args.rank is not None or args.bonus_ad is not None:
            abilities = {item.ability_id: item for item in extract.abilities}
            stats = champion_stats(
                extract.champion["base_stats"],
                level,
                bonus_attack_damage=bonus_ad,
            )
            damage = evaluate_all_calculations(abilities, stats, level=level, rank=rank)
        payload = extract.to_dict()
        if validation is not None:
            payload["validation"] = validation
        if damage is not None:
            payload["damage"] = damage
        if args.output:
            args.output.write_text(
                json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
        if args.json:
            print(json.dumps(payload, indent=2, ensure_ascii=False))
        else:
            print(_summary(extract, validation=validation, damage=damage))
        if args.self_check and any(item.severity == "error" for item in extract.diagnostics):
            return 1
        return 0
    except (ExtractionError, FormulaError, TraversalError, OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
