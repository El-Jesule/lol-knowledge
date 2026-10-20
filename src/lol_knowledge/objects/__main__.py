"""Command line entry point: ``python -m lol_knowledge.objects``."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

from .catalog import ObjectModelError, load_model
from .validate import validate_object_catalog


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m lol_knowledge.objects",
        description="Inspect and validate the versioned League of Legends object model.",
    )
    parser.add_argument("--root", type=Path, default=Path("."), help="Project root (default: .)")
    parser.add_argument("--json", action="store_true", help="Print the canonical model as JSON.")
    parser.add_argument("--validate", action="store_true", help="Validate the curated catalog.")
    return parser


def _summary(model: dict[str, Any]) -> str:
    objects = model["objects"]
    effects = [effect for item in objects for effect in item["effects"]]
    status_counts: dict[str, int] = {}
    for effect in effects:
        status = effect["model_status"]
        status_counts[status] = status_counts.get(status, 0) + 1
    overlay_stats = sum(
        1
        for item in objects
        for stat in item["stats"]
        if stat["source"]["kind"] == "ddragon_description"
    )
    lines = [
        f"object model: lol-object-model/{model['schema_version']}",
        f"game version: {model['game_version']}",
        f"catalog version: {model['catalog_version']}",
        f"objects: {len(objects)}",
        f"stats: {sum(len(item['stats']) for item in objects)} ({overlay_stats} from descriptions)",
        f"effects: {len(effects)}",
    ]
    for status in ("evaluable", "partially_evaluable", "excluded"):
        lines.append(f"  {status}: {status_counts.get(status, 0)}")
    for item in objects:
        lines.append(
            f"  {item['id']:<6} {item['name']:<34} "
            f"stats={len(item['stats'])} effects={len(item['effects'])}"
        )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root: Path = args.root
    if not root.is_dir():
        print(f"error: {root} is not a directory", file=sys.stderr)
        return 2

    if args.validate:
        report = validate_object_catalog(root)
        for note in report.skipped:
            print(f"note: {note}", file=sys.stderr)
        for violation in report.violations:
            print(f"error: {violation}", file=sys.stderr)
        if report.violations:
            print(f"invalid: {len(report.violations)} object catalog violations", file=sys.stderr)
            return 1
        if not args.json:
            print(f"valid: {report.checked_files} object catalog files checked")
            return 0

    try:
        model, serialized = load_model(root)
    except (ObjectModelError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if args.json:
        sys.stdout.write(serialized)
    else:
        print(_summary(model))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
