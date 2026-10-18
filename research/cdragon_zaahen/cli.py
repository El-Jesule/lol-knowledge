"""Command line entry point: ``python -m cdragon_zaahen``."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .client import SourceError, load_pinned
from .compare import Report, build_report
from .extract import ExtractionError

DEFAULT_CACHE = Path("research/.cache")
DEFAULT_DDRAGON = Path("data/current/champions/Zaahen.json")
DEFAULT_MANIFEST = Path("data/current/manifest.json")
DEFAULT_RCP = Path("research/fixtures/zaahen_rcp_min.json")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cdragon_zaahen",
        description="Extract and cross-check Zaahen spell values (prototype).",
    )
    parser.add_argument("--offline", action="store_true", help="Use the local cache only.")
    parser.add_argument("--json", action="store_true", help="Print the full report as JSON.")
    parser.add_argument("--check", action="store_true", help="Exit 1 when conflicts exist.")
    parser.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE)
    parser.add_argument("--ddragon", type=Path, default=DEFAULT_DDRAGON)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--rcp", type=Path, default=DEFAULT_RCP)
    return parser


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    try:
        source = load_pinned(args.cache_dir, offline=args.offline)
        ddragon = _read_json(args.ddragon)
        manifest = _read_json(args.manifest)
        rcp = _read_json(args.rcp)
        report = build_report(
            source.payload,
            url=source.url,
            content_version=source.content_version,
            sha256=source.sha256,
            ddragon=ddragon,
            rcp=rcp,
            ddragon_patch=str(manifest.get("patch")),
        )
    except (SourceError, ExtractionError, OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(report.to_dict(), indent=2, ensure_ascii=False))
    else:
        _print_summary(report, from_cache=source.from_cache)

    return 1 if args.check and report.conflicts else 0


def _print_summary(report: Report, *, from_cache: bool) -> None:
    print(f"source: {report.source_url}")
    print(f"content version: {report.content_version} (cache={from_cache})")
    print(f"sha256: {report.source_sha256}")
    print(f"Data Dragon patch: {report.ddragon_patch}")
    print(f"values extracted: {len(report.values)}")
    print()

    header = f"{'parameter':38} {'cdragon':22} {'ddragon':18} {'rcp':16} {'status'}"
    print(header)
    print("-" * len(header))
    for item in report.comparisons:
        print(
            f"{item.parameter:38} "
            f"{_format(item.cdragon):22} {_format(item.ddragon):18} "
            f"{_format(item.rcp):16} {item.status}"
        )

    print()
    for calculation in report.calculations:
        state = "blocked" if calculation.blocked else "open"
        print(
            f"calculation {calculation.name}: {calculation.expression} = "
            f"{calculation.result:g} [{calculation.status}, {state}]"
        )

    print()
    print(f"conflicts: {len(report.conflicts)}")
    for item in report.conflicts:
        print(f"  - {item.parameter}: {item.conclusion}")
        if item.missing_evidence:
            print(f"    missing: {item.missing_evidence}")
    if report.blocked:
        print("blocked parameters: " + ", ".join(report.blocked))


def _format(values: tuple[float, ...] | None) -> str:
    if values is None:
        return "-"
    return "/".join(f"{value:g}" for value in values)


if __name__ == "__main__":
    raise SystemExit(main())
