"""Command line interface for the LoL-Knowledge tooling."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from . import __version__
from .damage import DamageType, Modifiers, format_text, mitigate, to_dict
from .errors import DamageInputError, LolKnowledgeError, NetworkError, PayloadError
from .snapshot import build_snapshot
from .validate import validate_project

DEFAULT_DATA_DIR = "data"

LOGGER = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser with the commands available today."""
    parser = argparse.ArgumentParser(
        prog="lol_knowledge",
        description="LoL-Knowledge tooling: official-data ingestion, validation and calculations.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")

    subparsers = parser.add_subparsers(dest="command", metavar="<command>")
    subparsers.add_parser("version", help="Print the package version and exit.")

    update = subparsers.add_parser(
        "update",
        help="Download the Data Dragon snapshot into data/current.",
    )
    update.add_argument(
        "--patch",
        default="latest",
        help="Data Dragon patch such as 16.20.1. Defaults to the newest published one.",
    )
    update.add_argument(
        "--data-dir",
        type=Path,
        default=Path(DEFAULT_DATA_DIR),
        help="Directory that holds the current snapshot (default: data).",
    )

    validate = subparsers.add_parser(
        "validate",
        help="Validate the snapshot, the knowledge base and the object catalog.",
    )
    validate.add_argument(
        "--root",
        type=Path,
        default=Path("."),
        help="Project root to validate (default: current directory).",
    )

    _add_damage_parser(subparsers)

    return parser


def _add_damage_parser(subparsers: argparse._SubParsersAction) -> None:
    damage = subparsers.add_parser(
        "damage",
        help="Compute the post-mitigation damage of one damage instance.",
        description=(
            "Apply resistance reductions and penetrations in the game's order and "
            "mitigate one damage instance. Percentages are fractions (0.3 = 30 %). "
            "Repeat a modifier option once per independent source."
        ),
    )
    damage.add_argument("--raw", required=True, help="Raw (pre-mitigation) damage.")
    damage.add_argument(
        "--type",
        required=True,
        choices=[item.value for item in DamageType],
        help="Damage type.",
    )
    damage.add_argument(
        "--resistance",
        help="Target's armor (physical) or magic resistance (magic). Not used by true damage.",
    )
    for option, text in (
        ("--flat-reduction", "Flat resistance reduction on the target."),
        ("--percent-reduction", "Percent resistance reduction on the target."),
        ("--percent-penetration", "Attacker's percent penetration."),
        ("--flat-penetration", "Attacker's flat penetration (lethality for physical damage)."),
    ):
        damage.add_argument(option, action="append", default=[], metavar="VALUE", help=text)
    damage.add_argument("--json", action="store_true", help="Print a JSON report.")


def main(argv: list[str] | None = None) -> int:
    """Run the CLI and return the process exit code."""
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command is None:
        parser.print_help()
        return 0
    if args.command == "version":
        print(__version__)
        return 0

    handlers = {"update": _run_update, "validate": _run_validate, "damage": _run_damage}
    handler = handlers[args.command]
    return handler(args)


def _run_damage(args: argparse.Namespace) -> int:
    try:
        modifiers = Modifiers(
            flat_reduction=tuple(args.flat_reduction),
            percent_reduction=tuple(args.percent_reduction),
            percent_penetration=tuple(args.percent_penetration),
            flat_penetration=tuple(args.flat_penetration),
        )
        result = mitigate(args.raw, args.type, args.resistance, modifiers)
    except DamageInputError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(to_dict(result), indent=2, ensure_ascii=False))
    else:
        print(format_text(result))
    return 0


def _run_validate(args: argparse.Namespace) -> int:
    root: Path = args.root
    if not root.is_dir():
        print(f"error: {root} is not a directory", file=sys.stderr)
        return 2

    try:
        report = validate_project(root)
    except OSError as exc:
        # Application boundary: filesystem failures are reported, never swallowed.
        print(f"error: {exc}", file=sys.stderr)
        return 2

    for note in report.skipped:
        print(f"note: {note}", file=sys.stderr)
    for violation in report.violations:
        print(f"error: {violation}", file=sys.stderr)

    if report.violations:
        print(
            f"invalid: {len(report.violations)} violations in {report.checked_files} files",
            file=sys.stderr,
        )
        return 1

    print(f"valid: {report.checked_files} files checked")
    return 0


def _run_update(args: argparse.Namespace) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    try:
        result = build_snapshot(args.data_dir, patch=args.patch)
    except PayloadError as exc:
        # Downloaded data is untrusted input: exit 1 means the source content is unusable.
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except NetworkError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except LolKnowledgeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except OSError as exc:
        # Application boundary: filesystem failures are reported, never swallowed.
        print(f"error: {exc}", file=sys.stderr)
        return 2

    state = "updated" if result.changed else "unchanged"
    print(f"{state}: patch {result.patch} ({result.file_count} files) in {result.data_dir}")
    return 0
