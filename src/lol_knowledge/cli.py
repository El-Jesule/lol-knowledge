"""Command line interface for the LoL-Knowledge tooling."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from fractions import Fraction
from pathlib import Path

from . import __version__
from .contract import execute_request
from .damage import DamageType, Modifiers, format_text, mitigate, to_dict, to_fraction
from .defense import evaluate_defense, hits_from_rotation, parse_incoming
from .defense_report import format_text as format_defense_text
from .defense_report import to_dict as defense_to_dict
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
from .mcp_server import MCPServer
from .objects.legality import ITEM_GROUPS_PATH, check_build, load_item_groups
from .optimizer import (
    OBJECTIVES,
    OptimizeConstraints,
    optimize_build,
)
from .optimizer import format_text as format_optimize_text
from .optimizer import to_dict as optimize_to_dict
from .passives import sheet_passive_effects
from .rotation import CritBase, evaluate_rotation, parse_steps
from .rotation_report import format_text as format_rotation_text
from .rotation_report import to_dict as rotation_to_dict
from .runes import (
    adaptive_stat,
    check_page,
    combat_rune_notes,
    load_runes,
    minor_rune_effects,
    needs_adaptive_stat,
    shard_contributions,
)
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
from .stats.sheet import MANA_RESOURCE
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
    _add_survive_parser(subparsers)
    _add_optimize_parser(subparsers)
    _add_contract_parser(subparsers)
    _add_mcp_parser(subparsers)

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
        "--input",
        action="append",
        default=[],
        metavar="NAME=VALUE",
        help="Scenario input for conditional or stacking runes (e.g. game_minutes=20).",
    )
    _add_build_option(stats)
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
    _add_build_option(ability)
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
    command.add_argument("--target-shield", help="Target shield amount (rotation).")
    command.add_argument(
        "--target-shield-type",
        choices=("normal", "physical", "magic"),
        default="normal",
        help="Target shield type: normal (all damage), physical or magic.",
    )
    command.add_argument(
        "--target-count",
        type=int,
        default=1,
        help=(
            "Number of enemy targets in range (default: 1). Area abilities hit all targets up to "
            "their max_targets cap; single-target abilities and basic attacks hit 1 target."
        ),
    )


def _add_build_option(command: argparse.ArgumentParser) -> None:
    command.add_argument(
        "--rune",
        action="append",
        default=[],
        metavar="ID",
        help=(
            "Tree rune of the page (repeat 6 times: keystone, 3 primary, 2 secondary); "
            "stat-sheet minor runes, combat minor runes and offensive keystones are applied "
            "(lol-knowledge/mechanics/runes.md)."
        ),
    )
    command.add_argument(
        "--shard",
        action="append",
        default=[],
        metavar="ID",
        help="Stat shard (repeat 3 times, in order: offense, flex, defense).",
    )
    command.add_argument(
        "--allow-illegal-build",
        action="store_true",
        help=(
            "Calculate even when the items cannot be held together (unique groups, boots, "
            "slots; lol-knowledge/mechanics/build-legality.md). The violations are printed."
        ),
    )


def _check_build(root: Path, item_ids: list[str], champion, *, allow: bool, who: str) -> None:
    """Refuse items one inventory cannot hold, unless ``allow``; notes go to stderr."""
    if not item_ids:
        return
    data = load_item_groups(root)
    if data is None:
        print(
            f"note: {who} build legality not checked: {ITEM_GROUPS_PATH.as_posix()} is missing",
            file=sys.stderr,
        )
        return
    report = check_build(item_ids, data, patch=champion.patch, champion=champion.id)
    for note in report.notes:
        print(f"note: {who} build: {note}", file=sys.stderr)
    if report.legal:
        return
    problems = "; ".join(violation.message for violation in report.violations)
    if not allow:
        raise StatsError(
            f"{who} build is not legal [{report.label}]: {problems} "
            "(--allow-illegal-build calculates it anyway)"
        )
    print(f"warning: {who} build is not legal [{report.label}]: {problems}", file=sys.stderr)


def _rune_ids(values: list[str], option: str) -> list[int]:
    try:
        return [int(value) for value in values]
    except ValueError as exc:
        raise StatsError(f"{option} expects numeric rune ids, got {values}") from exc


def _build_sheet(
    args,
    root: Path,
    champion,
    items,
    issues,
    assumptions,
    derived,
    extras=(),
    inputs=None,
    *,
    combat_context: str = "stats",
    kit=None,
):
    """The attacker's stat sheet, with champion passive and rune page if any."""
    passive = sheet_passive_effects(
        kit, args.level, inputs, include_stacking=combat_context != "rotation"
    )
    base_extras = (*extras, *passive.flats)
    runes, shards = _rune_ids(args.rune, "--rune"), _rune_ids(args.shard, "--shard")
    if not runes and not shards:
        return build_stat_sheet(
            champion,
            args.level,
            items,
            issues,
            assumptions,
            derived,
            base_extras,
            extra_amplifiers=passive.amplifiers,
            extra_notes=passive.notes,
        )
    data = load_runes(root)
    if data is None:
        raise StatsError("lol-knowledge/derived/runes.json is missing; runes cannot be used")
    report = check_page(runes, shards, data, patch=champion.patch)
    if report.label is Label.PENDING:
        print(
            f"note: runes are from client {data.game_version}, the snapshot is {champion.patch}",
            file=sys.stderr,
        )
    if not report.legal:
        problems = "; ".join(report.violations)
        if not args.allow_illegal_build:
            raise StatsError(
                f"rune page is not legal [{report.label}]: {problems} "
                "(--allow-illegal-build calculates it anyway)"
            )
        print(f"warning: rune page is not legal [{report.label}]: {problems}", file=sys.stderr)
    adaptive, label, note = None, Label.DERIVED, ""
    if needs_adaptive_stat(runes, shards, data):
        before = build_stat_sheet(champion, args.level, items, issues, assumptions, derived, extras)
        bonus_ad = sum(
            (
                part.value
                for part in before["attack_damage"].contributions
                if part.scope == "bonus" and not part.adaptive
            ),
            start=Fraction(0),
        )
        power = sum(
            (part.value for part in before["ability_power"].contributions if not part.adaptive),
            Fraction(0),
        )
        weight = derived.value(champion.id, "adaptiveforceapweight") if derived else None
        adaptive, label, note = adaptive_stat(bonus_ad, power, weight)
    flats, percents = shard_contributions(
        shards,
        data,
        level=args.level,
        patch=champion.patch,
        adaptive=adaptive,
        adaptive_label=label,
        adaptive_note=note,
    )
    if not items:
        has_boots: bool | None = False
    else:
        groups = load_item_groups(root)
        has_boots = None if groups is None else groups.has_boots([item.id for item in items])
    uses_mana = champion.resource == MANA_RESOURCE.get(champion.locale)
    rune_effects = minor_rune_effects(
        runes,
        data,
        level=args.level,
        patch=champion.patch,
        items=items,
        uses_mana=uses_mana,
        has_boots=has_boots,
        inputs=inputs,
        adaptive=adaptive,
        adaptive_label=label,
        adaptive_note=note,
    )
    extra_notes = [*passive.notes, *rune_effects.notes]
    pending = list(rune_effects.pending)
    if combat_context == "stats":
        extra_notes += combat_rune_notes(rune_effects.combat_runes, data, in_ability=False)
    elif combat_context == "ability":
        pending += combat_rune_notes(rune_effects.combat_runes, data, in_ability=True)
    return build_stat_sheet(
        champion,
        args.level,
        items,
        issues,
        assumptions,
        derived,
        (*base_extras, *flats, *rune_effects.flats),
        (*percents, *rune_effects.percents),
        pending,
        extra_amplifiers=(*passive.amplifiers, *rune_effects.amplifiers),
        extra_notes=extra_notes,
        move_speed_bonus_amp=rune_effects.move_speed_bonus_amp,
    )


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
    rotation.add_argument(
        "--attacker-resource",
        help="Attacker starting mana or energy (defaults to maximum resource).",
    )
    rotation.add_argument(
        "--allow-insufficient-resource",
        action="store_true",
        help=(
            "Calculate even when an ability costs more mana or energy than available "
            "(clamps to 0 and marks the step Pendiente de verificación)."
        ),
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
    _add_build_option(rotation)
    rotation.add_argument("--root", type=Path, default=Path("."))
    rotation.add_argument("--json", action="store_true", help="Print a JSON report.")


def _add_survive_parser(subparsers: argparse._SubParsersAction) -> None:
    survive = subparsers.add_parser(
        "survive",
        help="Reverse defense simulation: incoming damage, shields, flat reduction & time to die.",
        description=(
            "Evaluate how an analyzed defender survives either a manual sequence of incoming "
            "hits (--incoming) or an enemy champion's rotation (--enemy-champion + --steps), "
            "applying Bone Plating, Second Wind, Guardian, Sterak's Gage Lifeline and Thornmail "
            "(lol-knowledge/mechanics/survival.md)."
        ),
    )
    survive.add_argument("--champion", required=True, help="Defender champion, e.g. Zaahen.")
    survive.add_argument("--level", required=True, type=int, help="Defender level.")
    survive.add_argument("--item", action="append", default=[], metavar="ID")
    survive.add_argument("--defender-health", help="Defender starting health (defaults to max).")
    survive.add_argument("--defender-shield", help="Defender initial shield amount.")
    survive.add_argument(
        "--defender-shield-type",
        choices=("normal", "physical", "magic"),
        default="normal",
        help="Defender initial shield type: normal, physical or magic.",
    )
    survive.add_argument(
        "--incoming",
        help='Manual hits, e.g. "attack:400, attack:crit:600, magic:300, true:150, wait:1".',
    )
    survive.add_argument("--enemy-champion", help="Enemy attacker champion (requires kit).")
    survive.add_argument("--enemy-level", type=int, help="Enemy attacker level.")
    survive.add_argument("--enemy-item", action="append", default=[], metavar="ID")
    survive.add_argument(
        "--enemy-learned",
        action="append",
        default=[],
        metavar="SLOT=RANK",
        help="Enemy learned ability rank (repeat).",
    )
    survive.add_argument("--enemy-range", choices=("melee", "ranged"), help="Enemy range.")
    survive.add_argument("--steps", help="Enemy rotation steps (with --enemy-champion).")
    survive.add_argument(
        "--timeline", action="store_true", help="Simulate timestamps and durations."
    )
    survive.add_argument("--assume", action="append", default=[], metavar="FIELD=VALUE")
    survive.add_argument(
        "--input", action="append", default=[], metavar="NAME=VALUE", help="Scenario input."
    )
    _add_build_option(survive)
    survive.add_argument("--root", type=Path, default=Path("."))
    survive.add_argument("--json", action="store_true", help="Print a JSON report.")


def _add_optimize_parser(subparsers: argparse._SubParsersAction) -> None:
    opt = subparsers.add_parser(
        "optimize",
        help="Search legal builds optimizing a measurable combat or survival objective.",
        description=(
            "Pruned deterministic search over legal Summoner's Rift builds (OPT-01..OPT-03). "
            "Propagates weakest input labels and separates verified (Oficial/Derivado) builds "
            "from builds depending on Pendiente de verificación effects."
        ),
    )
    opt.add_argument("--champion", required=True, help="Champion id, e.g. Ahri or Garen.")
    opt.add_argument("--level", required=True, type=int, help="Champion level (1..18).")
    opt.add_argument(
        "--objective",
        required=True,
        choices=sorted(OBJECTIVES),
        help="Metric to maximize.",
    )
    opt.add_argument("--budget", type=int, help="Maximum total build gold.")
    opt.add_argument("--slots", type=int, default=6, help="Max item slots (1..6, default: 6).")
    opt.add_argument(
        "--require-item",
        action="append",
        default=[],
        metavar="ID",
        help="Item that must be included in every candidate build (repeat).",
    )
    opt.add_argument(
        "--forbid-item",
        action="append",
        default=[],
        metavar="ID",
        help="Item excluded from the candidate pool (repeat).",
    )
    opt.add_argument(
        "--require-boots",
        action="store_true",
        help="Require one pair of boots in every returned build.",
    )
    opt.add_argument(
        "--tier",
        choices=("completed", "all"),
        default="completed",
        help="Candidate tier: completed items + tier-2 boots (default) or all purchasable items.",
    )
    opt.add_argument(
        "--only-verified",
        action="store_true",
        help="Exclude items with pending effect review or excluded damage effects.",
    )
    opt.add_argument(
        "--use-item-actives",
        action="store_true",
        help="Automatically cast equipped items' evaluable combat actives during rotation scoring.",
    )
    opt.add_argument("--top", type=int, default=5, help="Builds to return per bucket (default: 5).")
    opt.add_argument(
        "--beam-width",
        type=int,
        default=12,
        help="Beam search width per slot (default: 12).",
    )
    opt.add_argument(
        "--pool-limit",
        type=int,
        default=16,
        help="Max non-boots items kept after marginal relevance pre-filter (default: 16).",
    )
    opt.add_argument(
        "--damage-mix",
        default="0.5",
        help="Physical damage weight (0..1) for effective_health_mixed (default: 0.5).",
    )
    # Rotation inputs (rotation_damage, dps, healing)
    opt.add_argument(
        "--steps", help="Rotation steps (for rotation_damage, dps, healing, or enemy)."
    )
    opt.add_argument(
        "--learned",
        action="append",
        default=[],
        metavar="SLOT=RANK",
        help="Learned ability rank (repeat).",
    )
    opt.add_argument(
        "--attacker-range",
        choices=("melee", "ranged"),
        help="Holder range (defaults from champion attackrange < 300 if omitted).",
    )
    opt.add_argument("--timeline", action="store_true", help="Simulate timestamps and durations.")
    _add_target_options(opt)
    # Defense inputs (time_to_die)
    opt.add_argument("--incoming", help='Manual incoming hits for time_to_die, e.g. "attack:500".')
    opt.add_argument("--enemy-champion", help="Enemy champion for time_to_die.")
    opt.add_argument("--enemy-level", type=int, help="Enemy champion level.")
    opt.add_argument("--enemy-item", action="append", default=[], metavar="ID")
    opt.add_argument("--enemy-learned", action="append", default=[], metavar="SLOT=RANK")
    opt.add_argument("--enemy-range", choices=("melee", "ranged"))
    opt.add_argument("--assume", action="append", default=[], metavar="FIELD=VALUE")
    opt.add_argument("--input", action="append", default=[], metavar="NAME=VALUE")
    _add_build_option(opt)
    opt.add_argument("--root", type=Path, default=Path("."))
    opt.add_argument("--json", action="store_true", help="Print a JSON report.")


def _add_contract_parser(subparsers: argparse._SubParsersAction) -> None:
    contract = subparsers.add_parser(
        "contract",
        help="Execute one versioned lol-knowledge-contract/1 JSON request (IA-01).",
    )
    contract.add_argument(
        "--input-file",
        type=Path,
        help="Path to a JSON request file (reads stdin when omitted).",
    )
    contract.add_argument("--root", type=Path, default=Path("."))


def _add_mcp_parser(subparsers: argparse._SubParsersAction) -> None:
    mcp = subparsers.add_parser(
        "mcp",
        help="Run the local MCP (Model Context Protocol) server over stdio (IA-04).",
    )
    mcp.add_argument("--root", type=Path, default=Path("."))


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
        "survive": _run_survive,
        "optimize": _run_optimize,
        "contract": _run_contract,
        "mcp": _run_mcp,
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
        _check_build(root, args.target_item, champion, allow=args.allow_illegal_build, who="target")
        current = _number(args.target_current_health, "--target-current-health")
        shield = _number(args.target_shield, "--target-shield")
        return target_from_sheet(
            sheet, current_health=current, shield=shield, shield_type=args.target_shield_type
        )
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
        shield=_number(args.target_shield, "--target-shield"),
        shield_type=args.target_shield_type,
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
        sheet = _build_sheet(
            args,
            root,
            champion,
            load_items(root, args.item),
            issues,
            assumptions,
            derived,
            passive_contributions(kit, ranks),
            inputs=inputs,
            combat_context="ability",
            kit=kit,
        )
        _check_build(root, args.item, champion, allow=args.allow_illegal_build, who="attacker")
        target = _ability_target(args, root, issues, derived)
        outcome = evaluate_ability(
            kit,
            sheet,
            slot,
            args.rank,
            target,
            case=args.case,
            inputs=inputs,
            target_count=args.target_count,
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
        sheet = _build_sheet(
            args,
            root,
            champion,
            load_items(root, args.item),
            issues,
            assumptions,
            derived,
            passive_contributions(kit, ranks),
            inputs=inputs,
            combat_context="rotation",
            kit=kit,
        )
        _check_build(root, args.item, champion, allow=args.allow_illegal_build, who="attacker")
        target = _ability_target(args, root, issues, derived)
        crit_base = _crit_base(champion.id, champion.patch, derived)
        rune_ids = _rune_ids(args.rune, "--rune")
        rune_data = load_runes(root) if rune_ids else None
        ap_weight = derived.value(champion.id, "adaptiveforceapweight") if derived else None
        start_resource = _number(args.attacker_resource, "--attacker-resource")
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
            runes=rune_ids,
            rune_data=rune_data,
            ap_weight=ap_weight,
            start_resource=start_resource,
            allow_insufficient_resource=args.allow_insufficient_resource,
            target_count=args.target_count,
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
        inputs = {
            key: _number(value, f"--input {key}")
            for key, value in _pairs(args.input, "--input").items()
        }
        champion = load_champion(root, args.champion)
        items = load_items(root, args.item)
        _check_build(root, args.item, champion, allow=args.allow_illegal_build, who="champion")
        issues = load_issues(root)
        derived = load_records(root)
        kit = load_kit(root, champion.id)
        sheet = _build_sheet(
            args, root, champion, items, issues, assumptions, derived, inputs=inputs, kit=kit
        )
    except (StatsError, KitError) as exc:
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


def _run_survive(args: argparse.Namespace) -> int:
    root: Path = args.root
    try:
        assumptions = _parse_assume(args.assume)
        inputs = {
            key: _number(value, f"--input {key}")
            for key, value in _pairs(args.input, "--input").items()
        }
        champion = load_champion(root, args.champion)
        items = load_items(root, args.item)
        _check_build(root, args.item, champion, allow=args.allow_illegal_build, who="defender")
        issues = load_issues(root)
        derived = load_records(root)
        defender_sheet = _build_sheet(
            args, root, champion, items, issues, assumptions, derived, inputs=inputs
        )
        runes = _rune_ids(args.rune, "--rune")
        rune_data = load_runes(root) if runes else None
        start_hp = _number(args.defender_health, "--defender-health")
        start_sh = _number(args.defender_shield, "--defender-shield") or Fraction(0)

        if bool(args.incoming) == bool(args.enemy_champion):
            raise StatsError("give either --incoming or --enemy-champion (with --steps), not both")
        if args.incoming:
            hits = parse_incoming(args.incoming)
            enemy_desc = "manual incoming hits"
        else:
            if args.enemy_level is None or not args.steps:
                raise StatsError("--enemy-champion requires --enemy-level and --steps")
            enemy_champ = load_champion(root, args.enemy_champion)
            enemy_kit = load_kit(root, enemy_champ.id)
            enemy_items = load_items(root, args.enemy_item)
            _check_build(
                root, args.enemy_item, enemy_champ, allow=args.allow_illegal_build, who="enemy"
            )
            enemy_ranks = _parse_ranks(args.enemy_learned)
            enemy_extras = passive_contributions(enemy_kit, enemy_ranks)
            enemy_sheet = build_stat_sheet(
                enemy_champ, args.enemy_level, enemy_items, issues, {}, derived, enemy_extras
            )
            crit_val = derived.value(enemy_champ.id, "critdamagemultiplier")
            crit_base = (
                None
                if crit_val is None
                else CritBase(
                    crit_val,
                    Label.DERIVED if derived.matches_patch(enemy_champ.patch) else Label.PENDING,
                    f"derived:{enemy_champ.id}.critdamagemultiplier ({derived.content_version})",
                )
            )
            rot = evaluate_rotation(
                enemy_kit,
                enemy_sheet,
                enemy_ranks,
                target_from_sheet(defender_sheet, current_health=start_hp),
                parse_steps(args.steps),
                crit_base,
                holder_range=args.enemy_range,
                inputs=inputs,
                timeline=args.timeline,
                ap_weight=derived.value(enemy_champ.id, "adaptiveforceapweight"),
            )
            hits = hits_from_rotation(rot)
            enemy_desc = (
                f"{enemy_champ.name} level {args.enemy_level} "
                f"({', '.join(args.enemy_item) or 'no items'}): {args.steps}"
            )
        outcome = evaluate_defense(
            defender_sheet,
            hits,
            enemy_description=enemy_desc,
            start_health=start_hp,
            start_shield=start_sh,
            shield_type=args.defender_shield_type,
            runes=runes,
            rune_data=rune_data,
            inputs=inputs,
            timeline=args.timeline,
        )
    except (StatsError, KitError, RotationError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except OSError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(defense_to_dict(outcome, defender_sheet), indent=2, ensure_ascii=False))
    else:
        print(format_defense_text(outcome, defender_sheet))
    return 0


def _run_optimize(args: argparse.Namespace) -> int:
    root: Path = args.root
    try:
        champion = load_champion(root, args.champion)
        issues = load_issues(root)
        derived = load_records(root)
        assumptions = _parse_assume(args.assume)
        inputs = {
            key: _number(value, f"--input {key}")
            for key, value in _pairs(args.input, "--input").items()
        }
        damage_mix = _number(args.damage_mix, "--damage-mix")
        assert damage_mix is not None
        constraints = OptimizeConstraints(
            budget=args.budget,
            slots=args.slots,
            required_items=tuple(args.require_item),
            forbidden_items=tuple(args.forbid_item),
            require_boots=args.require_boots,
            tier=args.tier,
            only_verified=args.only_verified,
            top=args.top,
            beam_width=args.beam_width,
            pool_limit=args.pool_limit,
            damage_mix_physical=damage_mix,
            use_item_actives=args.use_item_actives,
        )
        runes = _rune_ids(args.rune, "--rune")
        shards = _rune_ids(args.shard, "--shard")
        rune_data = load_runes(root) if (runes or shards) else None
        kit = load_kit(root, champion.id)
        ranks = _parse_ranks(args.learned)
        holder_range = args.attacker_range
        if holder_range is None:
            atk_range = champion.stats.get("attackrange")
            if atk_range is not None:
                holder_range = "melee" if atk_range < 300 else "ranged"

        target = None
        steps = ()
        crit_base = _crit_base(champion.id, champion.patch, derived)
        if args.objective in {"rotation_damage", "dps", "healing"}:
            if not args.steps:
                raise StatsError(f"--objective {args.objective} requires --steps")
            steps = parse_steps(args.steps)
            target = _ability_target(args, root, issues, derived)

        incoming_hits = ()
        incoming_hits_for_sheet = None
        if args.objective == "time_to_die":
            if bool(args.incoming) == bool(args.enemy_champion):
                raise StatsError(
                    "--objective time_to_die needs either --incoming or --enemy-champion"
                )
            if args.incoming:
                incoming_hits = parse_incoming(args.incoming)
            else:
                if args.enemy_level is None or not args.steps:
                    raise StatsError("--enemy-champion requires --enemy-level and --steps")
                enemy_champ = load_champion(root, args.enemy_champion)
                enemy_kit = load_kit(root, enemy_champ.id)
                if enemy_kit is None:
                    raise KitError(f"{enemy_champ.id} has no kit yet")
                enemy_items = load_items(root, args.enemy_item)
                enemy_ranks = _parse_ranks(args.enemy_learned)
                enemy_steps = parse_steps(args.steps)
                enemy_passive = sheet_passive_effects(
                    enemy_kit, args.enemy_level, inputs, include_stacking=False
                )
                enemy_sheet = build_stat_sheet(
                    enemy_champ,
                    args.enemy_level,
                    enemy_items,
                    issues,
                    assumptions,
                    derived,
                    (*passive_contributions(enemy_kit, enemy_ranks), *enemy_passive.flats),
                    extra_amplifiers=enemy_passive.amplifiers,
                    extra_notes=enemy_passive.notes,
                )
                enemy_crit = _crit_base(enemy_champ.id, enemy_champ.patch, derived)
                enemy_ap_w = (
                    derived.value(enemy_champ.id, "adaptiveforceapweight") if derived else None
                )
                enemy_range = args.enemy_range
                if enemy_range is None:
                    er = enemy_champ.stats.get("attackrange")
                    if er is not None:
                        enemy_range = "melee" if er < 300 else "ranged"

                def _enemy_hits(def_sheet):
                    rot = evaluate_rotation(
                        enemy_kit,
                        enemy_sheet,
                        enemy_ranks,
                        target_from_sheet(def_sheet),
                        enemy_steps,
                        enemy_crit,
                        holder_range=enemy_range,
                        inputs=inputs,
                        timeline=args.timeline,
                        ap_weight=enemy_ap_w,
                    )
                    return hits_from_rotation(rot)

                incoming_hits_for_sheet = _enemy_hits

        outcome = optimize_build(
            root,
            champion,
            args.level,
            args.objective,
            constraints=constraints,
            issues=issues,
            derived=derived,
            assumptions=assumptions,
            inputs=inputs,
            kit=kit,
            ranks=ranks,
            target=target,
            steps=steps,
            crit_base=crit_base,
            holder_range=holder_range,
            timeline=args.timeline,
            target_count=args.target_count,
            incoming_hits=incoming_hits,
            incoming_hits_for_sheet=incoming_hits_for_sheet,
            runes=runes,
            shards=shards,
            rune_data=rune_data,
        )
    except (StatsError, KitError, DamageInputError, RotationError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except OSError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(optimize_to_dict(outcome), indent=2, ensure_ascii=False))
    else:
        print(format_optimize_text(outcome))
    return 0


def _run_contract(args: argparse.Namespace) -> int:
    try:
        if args.input_file is not None:
            raw = args.input_file.read_text(encoding="utf-8")
        else:
            raw = sys.stdin.read()
        request = json.loads(raw)
    except (OSError, json.JSONDecodeError) as exc:
        envelope = {
            "schema": "lol-knowledge-contract/1",
            "ok": False,
            "operation": None,
            "error": {"code": "invalid_input", "message": f"cannot parse JSON request: {exc}"},
        }
        print(json.dumps(envelope, indent=2, ensure_ascii=False))
        return 2
    envelope = execute_request(request, args.root)
    print(json.dumps(envelope, indent=2, ensure_ascii=False))
    return 0 if envelope.get("ok") else 2


def _run_mcp(args: argparse.Namespace) -> int:
    if sys.stdin is sys.__stdin__ and hasattr(sys.stdin, "reconfigure"):
        sys.stdin.reconfigure(encoding="utf-8")
    logging.basicConfig(
        stream=sys.stderr, level=logging.WARNING, format="%(levelname)s %(message)s"
    )
    server = MCPServer(args.root)
    return server.serve_stdio()


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
