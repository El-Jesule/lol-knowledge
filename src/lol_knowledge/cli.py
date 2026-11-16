"""Command line interface for the LoL-Knowledge tooling."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from . import __version__
from .damage import DamageType, Modifiers, format_text, mitigate, to_dict, to_fraction
from .errors import (
    DamageInputError,
    KitError,
    LolKnowledgeError,
    NetworkError,
    PayloadError,
    RotationError,
    StatsError,
)
from .kit import load_kit, passive_contributions
from .rotation import CritBase, evaluate_rotation, parse_steps
from .rotation_report import format_text as format_rotation_text
from .rotation_report import to_dict as rotation_to_dict
from .scenario import evaluate_ability, target_from_sheet, target_from_values
from .scenario_report import format_text as format_ability_text
from .scenario_report import to_dict as ability_to_dict
from .snapshot import build_snapshot
from .stats import (
    Label,
    build_stat_sheet,
    load_champion,
    load_issues,
    load_items,
    load_records,
)
from .stats import format_text as format_stats_text
from .stats import to_dict as stats_to_dict
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
    _add_stats_parser(subparsers)
    _add_ability_parser(subparsers)
    _add_rotation_parser(subparsers)

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


def _add_stats_parser(subparsers: argparse._SubParsersAction) -> None:
    stats = subparsers.add_parser(
        "stats",
        help="Resolve a champion's stat sheet and its metrics.",
        description=(
            "Resolve a champion's statistics at a level with curated items, then compute "
            "effective health and ability cooldowns. Statistics affected by a known data "
            "issue are blocked unless --assume gives the missing value."
        ),
    )
    stats.add_argument("--champion", required=True, help="Champion id or name, e.g. Zaahen.")
    stats.add_argument("--level", required=True, type=int, help="Champion level.")
    stats.add_argument(
        "--item", action="append", default=[], metavar="ID", help="Curated item id (repeat)."
    )
    stats.add_argument(
        "--assume",
        action="append",
        default=[],
        metavar="FIELD=VALUE",
        help="Value for a Data Dragon field with an open data issue (repeat).",
    )
    stats.add_argument(
        "--root", type=Path, default=Path("."), help="Project root (default: current directory)."
    )
    stats.add_argument("--json", action="store_true", help="Print a JSON report.")


def _add_ability_parser(subparsers: argparse._SubParsersAction) -> None:
    ability = subparsers.add_parser(
        "ability",
        help="Damage of a champion ability against a target, after mitigation.",
        description=(
            "Resolve the attacker's stat sheet (items, level and the passive stats of learned "
            "abilities), evaluate the ability from the champion kit and mitigate every damage "
            "part with the target's matching resistance and the attacker's penetration. The "
            "target is either given by hand (--target-armor, --target-mr) or another champion "
            "(--target-champion, --target-level)."
        ),
    )
    ability.add_argument("--champion", required=True, help="Attacker champion, e.g. Zaahen.")
    ability.add_argument("--level", required=True, type=int, help="Attacker level.")
    ability.add_argument("--ability", required=True, help="Ability slot: Q, W, E or R.")
    ability.add_argument("--rank", required=True, type=int, help="Rank of that ability.")
    ability.add_argument("--case", help="Only this damage case (for example edge).")
    ability.add_argument(
        "--learned",
        action="append",
        default=[],
        metavar="SLOT=RANK",
        help="Rank of another learned ability, for its passive stats (repeat).",
    )
    ability.add_argument("--item", action="append", default=[], metavar="ID")
    ability.add_argument("--assume", action="append", default=[], metavar="FIELD=VALUE")
    ability.add_argument(
        "--input", action="append", default=[], metavar="NAME=VALUE", help="Scenario input."
    )
    _add_target_options(ability)
    ability.add_argument("--root", type=Path, default=Path("."))
    ability.add_argument("--json", action="store_true", help="Print a JSON report.")


def _add_target_options(command: argparse.ArgumentParser) -> None:
    command.add_argument("--target-champion", help="Target champion.")
    command.add_argument("--target-level", type=int, help="Target champion level.")
    command.add_argument("--target-item", action="append", default=[], metavar="ID")
    command.add_argument("--target-armor", help="Target armor (manual target).")
    command.add_argument("--target-mr", help="Target magic resistance (manual target).")
    command.add_argument("--target-max-health", help="Target max health (manual target).")
    command.add_argument(
        "--target-bonus-health", help="Target bonus health (manual target), e.g. for Giant Slayer."
    )
    command.add_argument(
        "--target-kind",
        choices=("champion", "monster", "minion", "structure"),
        help="What the manual target is; effects that depend on it need it.",
    )
    command.add_argument("--target-current-health", help="Target current health.")


def _add_rotation_parser(subparsers: argparse._SubParsersAction) -> None:
    rotation = subparsers.add_parser(
        "rotation",
        help="Damage of a sequence of basic attacks and abilities, with item effects.",
        description=(
            "Evaluate the steps in order against one target: basic attacks (attack, "
            "attack:crit) with the on-hit damage of the attacker's items, and ability cases "
            "(Q, E.edge...). Every part is mitigated, then multiplied by the attacker's "
            "damage-dealt modifiers (Giant Slayer) and the target items' damage-taken "
            "modifiers. The target's current health is carried from step to step."
        ),
    )
    rotation.add_argument("--champion", required=True, help="Attacker champion, e.g. Zaahen.")
    rotation.add_argument("--level", required=True, type=int, help="Attacker level.")
    rotation.add_argument(
        "--steps",
        required=True,
        help=(
            'Steps in order, e.g. "attack, Q.first_hit, attack:crit, E.edge, R". '
            "After an ability, the next attack gets Spellblade; attack:nospellblade "
            "drops it."
        ),
    )
    rotation.add_argument(
        "--learned",
        action="append",
        default=[],
        metavar="SLOT=RANK",
        help="Rank of each learned ability (repeat); ability steps use it.",
    )
    rotation.add_argument(
        "--attacker-range",
        choices=("melee", "ranged"),
        help="The attacker's melee/ranged classification, for effects that branch on it.",
    )
    rotation.add_argument("--item", action="append", default=[], metavar="ID")
    rotation.add_argument(
        "--timeline",
        action="store_true",
        help=(
            "Give every step a time: attacks spaced by 1 / attack speed, cooldowns and recast "
            "windows enforced, wait:<seconds> steps allowed (lol-knowledge/mechanics/timeline.md)."
        ),
    )
    rotation.add_argument("--assume", action="append", default=[], metavar="FIELD=VALUE")
    rotation.add_argument(
        "--input", action="append", default=[], metavar="NAME=VALUE", help="Scenario input."
    )
    _add_target_options(rotation)
    rotation.add_argument("--root", type=Path, default=Path("."))
    rotation.add_argument("--json", action="store_true", help="Print a JSON report.")


def _pairs(values: list[str], option: str) -> dict[str, str]:
    parsed: dict[str, str] = {}
    for entry in values:
        key, separator, value = entry.partition("=")
        if not separator or not key.strip() or not value.strip():
            raise StatsError(f"{option} expects KEY=VALUE, got {entry!r}")
        if key.strip() in parsed:
            raise StatsError(f"{option} repeats {key.strip()!r}")
        parsed[key.strip()] = value.strip()
    return parsed


def _number(value: str | None, option: str):
    if value is None:
        return None
    try:
        return to_fraction(value, option)
    except DamageInputError as exc:
        raise StatsError(str(exc)) from exc


def _parse_ranks(values: list[str]) -> dict[str, int]:
    learned = {key.upper(): value for key, value in _pairs(values, "--learned").items()}
    ranks: dict[str, int] = {}
    for key, value in learned.items():
        try:
            ranks[key] = int(value)
        except ValueError as exc:
            raise StatsError(f"--learned {key}: rank must be an integer") from exc
    return ranks


def _parse_assume(values: list[str]) -> dict[str, str]:
    parsed: dict[str, str] = {}
    for entry in values:
        key, separator, value = entry.partition("=")
        if not separator or not key.strip() or not value.strip():
            raise StatsError(f"--assume expects FIELD=VALUE, got {entry!r}")
        if key.strip() in parsed:
            raise StatsError(f"--assume repeats {key.strip()!r}")
        parsed[key.strip()] = value.strip()
    return parsed


def _use_utf8_streams() -> None:
    """Write UTF-8 to the process's own stdout and stderr.

    On Windows a piped stream defaults to the ANSI code page (cp1252), which
    mangles accented text such as "Maná". Streams replaced by a caller (for
    example a test capture) are left alone.
    """
    for current, original in ((sys.stdout, sys.__stdout__), (sys.stderr, sys.__stderr__)):
        if current is original and hasattr(current, "reconfigure"):
            current.reconfigure(encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    """Run the CLI and return the process exit code."""
    _use_utf8_streams()
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command is None:
        parser.print_help()
        return 0
    if args.command == "version":
        print(__version__)
        return 0

    handlers = {
        "update": _run_update,
        "validate": _run_validate,
        "damage": _run_damage,
        "stats": _run_stats,
        "ability": _run_ability,
        "rotation": _run_rotation,
    }
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


def _ability_target(args: argparse.Namespace, root: Path, issues, derived):
    manual = [
        args.target_armor,
        args.target_mr,
        args.target_max_health,
        args.target_bonus_health,
        args.target_kind,
    ]
    if args.target_champion:
        if any(value is not None for value in manual):
            raise StatsError("give either --target-champion or manual target values, not both")
        if args.target_level is None:
            raise StatsError("--target-champion needs --target-level")
        champion = load_champion(root, args.target_champion)
        sheet = build_stat_sheet(
            champion, args.target_level, load_items(root, args.target_item), issues, {}, derived
        )
        current = _number(args.target_current_health, "--target-current-health")
        return target_from_sheet(sheet, current_health=current)
    if args.target_level is not None or args.target_item:
        raise StatsError("--target-level and --target-item need --target-champion")
    if args.target_armor is None or args.target_mr is None:
        raise StatsError("give --target-champion, or both --target-armor and --target-mr")
    return target_from_values(
        _number(args.target_armor, "--target-armor"),
        _number(args.target_mr, "--target-mr"),
        max_health=_number(args.target_max_health, "--target-max-health"),
        current_health=_number(args.target_current_health, "--target-current-health"),
        bonus_health=_number(args.target_bonus_health, "--target-bonus-health"),
        kind=args.target_kind,
    )


def _run_ability(args: argparse.Namespace) -> int:
    root: Path = args.root
    try:
        slot = args.ability.strip().upper()
        ranks = _parse_ranks(args.learned)
        if slot in ranks and ranks[slot] != args.rank:
            raise StatsError(f"--learned {slot}={ranks[slot]} contradicts --rank {args.rank}")
        ranks[slot] = args.rank
        assumptions = _parse_assume(args.assume)
        inputs = {
            key: _number(value, f"--input {key}")
            for key, value in _pairs(args.input, "--input").items()
        }
        champion = load_champion(root, args.champion)
        kit = load_kit(root, champion.id)
        if kit is None:
            raise KitError(
                f"{champion.id} has no kit yet (lol-knowledge/champions/{champion.id}/kit.json)"
            )
        issues = load_issues(root)
        derived = load_records(root)
        sheet = build_stat_sheet(
            champion,
            args.level,
            load_items(root, args.item),
            issues,
            assumptions,
            derived,
            passive_contributions(kit, ranks),
        )
        target = _ability_target(args, root, issues, derived)
        outcome = evaluate_ability(
            kit, sheet, slot, args.rank, target, case=args.case, inputs=inputs
        )
    except (StatsError, KitError, DamageInputError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except OSError as exc:
        # Application boundary: filesystem failures are reported, never swallowed.
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(ability_to_dict(outcome, sheet, target), indent=2, ensure_ascii=False))
    else:
        print(format_ability_text(outcome, sheet, target))
    return 0


def _crit_base(champion_id: str, patch: str, derived) -> CritBase | None:
    value = derived.value(champion_id, "critdamagemultiplier") if derived else None
    if value is None:
        return None
    label = Label.DERIVED if derived.matches_patch(patch) else Label.PENDING
    return CritBase(
        value,
        label,
        f"{derived.path} {champion_id}.critdamagemultiplier ({derived.content_version})",
    )


def _run_rotation(args: argparse.Namespace) -> int:
    root: Path = args.root
    try:
        steps = parse_steps(args.steps)
        ranks = _parse_ranks(args.learned)
        assumptions = _parse_assume(args.assume)
        inputs = {
            key: _number(value, f"--input {key}")
            for key, value in _pairs(args.input, "--input").items()
        }
        champion = load_champion(root, args.champion)
        kit = load_kit(root, champion.id)
        if kit is None:
            raise KitError(
                f"{champion.id} has no kit yet (lol-knowledge/champions/{champion.id}/kit.json)"
            )
        issues = load_issues(root)
        derived = load_records(root)
        sheet = build_stat_sheet(
            champion,
            args.level,
            load_items(root, args.item),
            issues,
            assumptions,
            derived,
            passive_contributions(kit, ranks),
        )
        target = _ability_target(args, root, issues, derived)
        crit_base = _crit_base(champion.id, champion.patch, derived)
        outcome = evaluate_rotation(
            kit,
            sheet,
            ranks,
            target,
            steps,
            crit_base,
            holder_range=args.attacker_range,
            inputs=inputs,
            timeline=args.timeline,
        )
    except (StatsError, KitError, DamageInputError, RotationError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except OSError as exc:
        # Application boundary: filesystem failures are reported, never swallowed.
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if args.json:
        report = rotation_to_dict(outcome, sheet, target, crit_base)
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print(format_rotation_text(outcome, sheet, target, crit_base))
    return 0


def _run_stats(args: argparse.Namespace) -> int:
    root: Path = args.root
    try:
        assumptions = _parse_assume(args.assume)
        champion = load_champion(root, args.champion)
        items = load_items(root, args.item)
        issues = load_issues(root)
        derived = load_records(root)
        sheet = build_stat_sheet(champion, args.level, items, issues, assumptions, derived)
    except StatsError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except OSError as exc:
        # Application boundary: filesystem failures are reported, never swallowed.
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(stats_to_dict(sheet), indent=2, ensure_ascii=False))
    else:
        print(format_stats_text(sheet))
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
