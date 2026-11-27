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
from .duel import (
    DEFAULT_DUEL_MAX_DURATION,
    DEFAULT_DUEL_MODE,
    DEFAULT_DUEL_TIE_BREAK,
    DEFAULT_PRIORITY_SLOTS,
    DUEL_MODES,
    DUEL_TIE_BREAKS,
    DuelFighterSpec,
    evaluate_duel,
)
from .duel_report import format_text as format_duel_text
from .duel_report import to_dict as duel_to_dict
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
from .loadout import assemble_stat_sheet, check_item_legality, resolve_crit_base
from .mcp_server import MCPServer
from .optimizer import (
    OBJECTIVES,
    OptimizeConstraints,
    optimize_build,
)
from .optimizer import format_text as format_optimize_text
from .optimizer import to_dict as optimize_to_dict
from .rotation import CritBase, evaluate_rotation, parse_steps
from .rotation_report import format_text as format_rotation_text
from .rotation_report import to_dict as rotation_to_dict
from .runes import load_runes
from .scenario import evaluate_ability, target_from_sheet, target_from_values
from .scenario_report import format_text as format_ability_text
from .scenario_report import to_dict as ability_to_dict
from .snapshot import build_snapshot
from .stats import format_text as format_stats_text
from .stats import (
    load_champion,
    load_issues,
    load_items,
    load_records,
)
from .stats import to_dict as stats_to_dict
from .summoners import load_summoner_spells
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
    _add_duel_parser(subparsers)
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
    command.add_argument(
        "--target-rune",
        action="append",
        default=[],
        metavar="ID",
        help="Target champion tree rune id (repeat; requires --target-champion).",
    )
    command.add_argument(
        "--target-shard",
        action="append",
        default=[],
        metavar="ID",
        help="Target champion stat shard id (repeat 3 times; requires --target-champion).",
    )
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
        "--summoner",
        action="append",
        default=[],
        metavar="SPELL",
        help=(
            "Equipped summoner spell (repeat up to 2 times, e.g. ignite, barrier, heal, "
            "exhaust, smite, ghost, cleanse, flash, teleport)."
        ),
    )
    command.add_argument(
        "--elixir",
        metavar="ELIXIR",
        help="Active elixir (max 1, 0 slots, 500 g): 2138/iron, 2139/sorcery, 2140/wrath.",
    )
    command.add_argument(
        "--ornn-item",
        metavar="ID",
        help="Single equipped completed non-boots item upgraded to Ornn Masterwork (DEC-03).",
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
    notes, warnings = check_item_legality(root, item_ids, champion, allow_illegal=allow, who=who)
    for note in notes:
        print(f"note: {note}", file=sys.stderr)
    for warning in warnings:
        print(f"warning: {warning}", file=sys.stderr)


def _rune_ids(values: list[str], option: str) -> list[int]:
    try:
        return [int(value) for value in values]
    except ValueError as exc:
        raise StatsError(f"{option} expects numeric rune ids, got {values}") from exc


def _build_sheet_with_runes(
    root: Path,
    champion,
    level: int,
    items,
    runes: list[int],
    shards: list[int],
    issues,
    assumptions,
    derived,
    *,
    extras=(),
    inputs=None,
    combat_context: str = "stats",
    kit=None,
    allow_illegal: bool = False,
    summoners=(),
    elixir: str | None = None,
    ornn_item: str | None = None,
):
    """Build a StatSheet for either attacker or target, with passive, runes and summoners."""
    res = assemble_stat_sheet(
        root,
        champion,
        level,
        items,
        runes,
        shards,
        issues,
        assumptions,
        derived,
        extras=extras,
        inputs=inputs,
        combat_context=combat_context,
        kit=kit,
        allow_illegal=allow_illegal,
        summoners=summoners,
        elixir=elixir,
        ornn_item=ornn_item,
    )
    for note in res.notes:
        print(f"note: {note}", file=sys.stderr)
    for warning in res.warnings:
        print(f"warning: {warning}", file=sys.stderr)
    return res.sheet


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
    """The attacker's stat sheet, with champion passive, rune page and summoners if any."""
    runes, shards = _rune_ids(args.rune, "--rune"), _rune_ids(args.shard, "--shard")
    return _build_sheet_with_runes(
        root,
        champion,
        args.level,
        items,
        runes,
        shards,
        issues,
        assumptions,
        derived,
        extras=extras,
        inputs=inputs,
        combat_context=combat_context,
        kit=kit,
        allow_illegal=args.allow_illegal_build,
        summoners=getattr(args, "summoner", []),
        elixir=getattr(args, "elixir", None),
        ornn_item=getattr(args, "ornn_item", None),
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
    rotation.add_argument(
        "--window",
        action="append",
        default=[],
        metavar="SECONDS",
        help="Report cumulative damage and DPS in [0, SECONDS] (repeat; requires --timeline).",
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
        "--learned",
        action="append",
        default=[],
        metavar="SLOT=RANK",
        help="Defender learned ability rank (repeat, e.g. W=5 R=3).",
    )
    survive.add_argument(
        "--defender-cast",
        action="append",
        default=[],
        metavar="SLOT[=RANK]",
        help="Defensive Q/W/E/R ability cast by the defender (repeat, e.g. W=5 or R=3).",
    )
    survive.add_argument(
        "--incoming",
        help='Manual hits, e.g. "attack:400, attack:crit:600, magic:300, true:150, wait:1".',
    )
    survive.add_argument("--enemy-champion", help="Enemy attacker champion (requires kit).")
    survive.add_argument("--enemy-level", type=int, help="Enemy attacker level.")
    survive.add_argument("--enemy-item", action="append", default=[], metavar="ID")
    survive.add_argument(
        "--enemy-rune",
        action="append",
        default=[],
        metavar="ID",
        help="Enemy attacker tree rune id (repeat; requires --enemy-champion).",
    )
    survive.add_argument(
        "--enemy-shard",
        action="append",
        default=[],
        metavar="ID",
        help="Enemy attacker stat shard id (repeat 3 times; requires --enemy-champion).",
    )
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


def _add_duel_fighter_options(parser: argparse.ArgumentParser, prefix: str, label: str) -> None:
    parser.add_argument(f"--{prefix}-champion", required=True, help=f"Fighter {label} champion id.")
    parser.add_argument(
        f"--{prefix}-level", required=True, type=int, help=f"Fighter {label} level."
    )
    parser.add_argument(f"--{prefix}-item", action="append", default=[], metavar="ID")
    parser.add_argument(f"--{prefix}-rune", action="append", default=[], metavar="ID")
    parser.add_argument(f"--{prefix}-shard", action="append", default=[], metavar="ID")
    parser.add_argument(f"--{prefix}-summoner", action="append", default=[], metavar="SPELL")
    parser.add_argument(f"--{prefix}-elixir", metavar="ELIXIR")
    parser.add_argument(f"--{prefix}-ornn-item", metavar="ID")
    parser.add_argument(f"--{prefix}-learned", action="append", default=[], metavar="SLOT=RANK")
    parser.add_argument(f"--{prefix}-steps", help=f"Fighter {label} scripted steps.")
    parser.add_argument(
        f"--{prefix}-priority",
        help="Comma-separated priority slots for priority_loop (default: R,Q,W,E).",
    )
    parser.add_argument(
        f"--{prefix}-range",
        choices=("melee", "ranged"),
        help=f"Fighter {label} melee/ranged classification.",
    )
    parser.add_argument(f"--{prefix}-health", help=f"Fighter {label} starting health.")
    parser.add_argument(f"--{prefix}-shield", help=f"Fighter {label} starting shield.")
    parser.add_argument(
        f"--{prefix}-shield-type",
        choices=("normal", "physical", "magic"),
        default="normal",
        help=f"Fighter {label} starting shield type.",
    )
    parser.add_argument(f"--{prefix}-resource", help=f"Fighter {label} starting mana/energy.")
    parser.add_argument(
        f"--{prefix}-input",
        action="append",
        default=[],
        metavar="NAME=VALUE",
        help=f"Fighter {label} scenario input.",
    )
    parser.add_argument(
        f"--{prefix}-assume",
        action="append",
        default=[],
        metavar="FIELD=VALUE",
        help=f"Fighter {label} stat assumption.",
    )


def _add_duel_parser(subparsers: argparse._SubParsersAction) -> None:
    duel = subparsers.add_parser(
        "duel",
        help="Deterministic coupled 1v1 duel simulation between two champions.",
        description=(
            "Simulate a coupled 1v1 duel over an exact Fraction timeline where both fighters "
            "exchange attacks, abilities, item actives, summoners, runes, passives, burns, "
            "heals, shields, damage reductions and defensive reactions."
        ),
    )
    _add_duel_fighter_options(duel, "a", "A")
    _add_duel_fighter_options(duel, "b", "B")
    duel.add_argument(
        "--mode",
        choices=sorted(DUEL_MODES),
        default=DEFAULT_DUEL_MODE,
        help="Action policy after scripted steps (default: scripted_then_attack).",
    )
    duel.add_argument(
        "--tie-break",
        choices=sorted(DUEL_TIE_BREAKS),
        default=DEFAULT_DUEL_TIE_BREAK,
        help="Resolution when A and B act at the exact same timestamp (default: simultaneous).",
    )
    duel.add_argument(
        "--max-duration",
        default=str(DEFAULT_DUEL_MAX_DURATION),
        help="Maximum simulated duel duration in seconds (default: 30).",
    )
    duel.add_argument(
        "--allow-insufficient-resource",
        action="store_true",
        help="Allow casts even when mana/energy is insufficient.",
    )
    duel.add_argument(
        "--allow-illegal-build",
        action="store_true",
        help="Calculate even if a build breaks item legality or rune-page rules.",
    )
    duel.add_argument("--root", type=Path, default=Path("."))
    duel.add_argument("--json", action="store_true", help="Print a JSON report.")


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
    opt.add_argument(
        "--ornn-upgrade",
        action="store_true",
        help="Upgrade the single best completed non-boots item via Ornn Masterwork (DEC-03).",
    )
    opt.add_argument(
        "--purchase-curve",
        action="store_true",
        help="Compute the optimal 1..k incremental purchase order for the top build (OPT-04).",
    )
    opt.add_argument(
        "--gold-checkpoints",
        help="Comma-separated gold milestones for partial-build power curve, e.g. 3500,7000,10500.",
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
    opt.add_argument(
        "--enemy-rune",
        action="append",
        default=[],
        metavar="ID",
        help="Enemy attacker tree rune id (repeat; requires --enemy-champion).",
    )
    opt.add_argument(
        "--enemy-shard",
        action="append",
        default=[],
        metavar="ID",
        help="Enemy attacker stat shard id (repeat 3 times; requires --enemy-champion).",
    )
    opt.add_argument("--enemy-learned", action="append", default=[], metavar="SLOT=RANK")
    opt.add_argument("--enemy-summoner", action="append", default=[], metavar="SPELL")
    opt.add_argument("--enemy-steps", help="Enemy fighter steps for --objective duel.")
    opt.add_argument("--enemy-priority", help="Enemy priority slots for --objective duel.")
    opt.add_argument("--enemy-range", choices=("melee", "ranged"))
    opt.add_argument(
        "--priority",
        help="Candidate priority slots for --objective duel with priority_loop (default: R,Q,W,E).",
    )
    opt.add_argument(
        "--duel-mode",
        choices=sorted(DUEL_MODES),
        default=DEFAULT_DUEL_MODE,
        help="Action policy for --objective duel (default: scripted_then_attack).",
    )
    opt.add_argument(
        "--duel-tie-break",
        choices=sorted(DUEL_TIE_BREAKS),
        default=DEFAULT_DUEL_TIE_BREAK,
        help="Tie-break rule for --objective duel (default: simultaneous).",
    )
    opt.add_argument(
        "--duel-max-duration",
        default=str(DEFAULT_DUEL_MAX_DURATION),
        help="Max duration in seconds for --objective duel (default: 30).",
    )
    opt.add_argument(
        "--defender-cast",
        action="append",
        default=[],
        metavar="SLOT[=RANK]",
        help="Defensive Q/W/E/R ability cast by the defender during time_to_die.",
    )
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
        "duel": _run_duel,
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


def _ability_target(args: argparse.Namespace, root: Path, issues, derived, inputs=None):
    manual = [
        args.target_armor,
        args.target_mr,
        args.target_max_health,
        args.target_bonus_health,
        args.target_kind,
    ]
    target_runes = _rune_ids(getattr(args, "target_rune", []), "--target-rune")
    target_shards = _rune_ids(getattr(args, "target_shard", []), "--target-shard")
    if args.target_champion:
        if any(value is not None for value in manual):
            raise StatsError("give either --target-champion or manual target values, not both")
        if args.target_level is None:
            raise StatsError("--target-champion needs --target-level")
        champion = load_champion(root, args.target_champion)
        target_items = load_items(root, args.target_item)
        target_kit = load_kit(root, champion.id)
        sheet = _build_sheet_with_runes(
            root,
            champion,
            args.target_level,
            target_items,
            target_runes,
            target_shards,
            issues,
            {},
            derived,
            inputs=inputs,
            combat_context="stats",
            kit=target_kit,
            allow_illegal=args.allow_illegal_build,
        )
        _check_build(root, args.target_item, champion, allow=args.allow_illegal_build, who="target")
        current = _number(args.target_current_health, "--target-current-health")
        shield = _number(args.target_shield, "--target-shield")
        return target_from_sheet(
            sheet,
            current_health=current,
            shield=shield,
            shield_type=args.target_shield_type,
            runes=target_runes,
        )
    if args.target_level is not None or args.target_item:
        raise StatsError("--target-level and --target-item need --target-champion")
    if target_runes or target_shards:
        raise StatsError("--target-rune and --target-shard need --target-champion")
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
        target = _ability_target(args, root, issues, derived, inputs=inputs)
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
    return resolve_crit_base(champion_id, patch, derived)


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
        target = _ability_target(args, root, issues, derived, inputs=inputs)
        crit_base = _crit_base(champion.id, champion.patch, derived)
        rune_ids = _rune_ids(args.rune, "--rune")
        rune_data = load_runes(root) if (rune_ids or target.runes) else None
        summoners = list(args.summoner)
        summoner_data = (
            load_summoner_spells(root)
            if (summoners or any(s.summoner_id is not None for s in steps))
            else None
        )
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
            summoners=summoners,
            summoner_data=summoner_data,
        )
        win_secs = [
            sec
            for raw in getattr(args, "window", [])
            if (sec := _number(raw, "--window")) is not None
        ]
        if win_secs and not args.timeline:
            raise RotationError("--window requires --timeline")
        for sec in win_secs:
            if sec <= 0:
                raise RotationError("--window must be positive")
    except (StatsError, KitError, DamageInputError, RotationError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except OSError as exc:
        # Application boundary: filesystem failures are reported, never swallowed.
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if args.json:
        report = rotation_to_dict(outcome, sheet, target, crit_base, windows=win_secs)
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print(format_rotation_text(outcome, sheet, target, crit_base, windows=win_secs))
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
        defender_kit = load_kit(root, champion.id)
        defender_sheet = _build_sheet(
            args,
            root,
            champion,
            items,
            issues,
            assumptions,
            derived,
            inputs=inputs,
            kit=defender_kit,
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
            if enemy_kit is None:
                raise KitError(f"{enemy_champ.id} has no kit yet")
            enemy_items = load_items(root, args.enemy_item)
            _check_build(
                root, args.enemy_item, enemy_champ, allow=args.allow_illegal_build, who="enemy"
            )
            enemy_ranks = _parse_ranks(args.enemy_learned)
            enemy_runes = _rune_ids(args.enemy_rune, "--enemy-rune")
            enemy_shards = _rune_ids(args.enemy_shard, "--enemy-shard")
            enemy_extras = passive_contributions(enemy_kit, enemy_ranks)
            enemy_sheet = _build_sheet_with_runes(
                root,
                enemy_champ,
                args.enemy_level,
                enemy_items,
                enemy_runes,
                enemy_shards,
                issues,
                {},
                derived,
                extras=enemy_extras,
                inputs=inputs,
                combat_context="rotation",
                kit=enemy_kit,
                allow_illegal=args.allow_illegal_build,
            )
            crit_base = _crit_base(enemy_champ.id, enemy_champ.patch, derived)
            enemy_rune_data = load_runes(root) if enemy_runes else None
            enemy_steps = parse_steps(args.steps)
            enemy_summoner_data = (
                load_summoner_spells(root)
                if any(s.summoner_id is not None for s in enemy_steps)
                else None
            )
            rot = evaluate_rotation(
                enemy_kit,
                enemy_sheet,
                enemy_ranks,
                target_from_sheet(defender_sheet, current_health=start_hp),
                enemy_steps,
                crit_base,
                holder_range=args.enemy_range,
                inputs=inputs,
                timeline=args.timeline,
                runes=enemy_runes,
                rune_data=enemy_rune_data,
                ap_weight=derived.value(enemy_champ.id, "adaptiveforceapweight")
                if derived
                else None,
                summoner_data=enemy_summoner_data,
            )
            hits = hits_from_rotation(rot)
            if any(it.id == "6695" for it in enemy_sheet.items) and "shield_reaver" not in inputs:
                inputs = {
                    **inputs,
                    "shield_reaver": Fraction(35, 100)
                    if args.enemy_range == "ranged"
                    else Fraction(50, 100),
                }
            enemy_desc = (
                f"{enemy_champ.name} level {args.enemy_level} "
                f"({', '.join(args.enemy_item) or 'no items'}): {args.steps}"
            )
        summoners = list(args.summoner)
        summoner_data = load_summoner_spells(root) if summoners else None
        defender_ranks = _parse_ranks(args.learned)
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
            kit=defender_kit,
            summoners=summoners,
            summoner_data=summoner_data,
            defender_casts=args.defender_cast,
            defender_ranks=defender_ranks,
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


def _parse_priority_str(raw: str | None) -> tuple[str, ...]:
    if not raw or not raw.strip():
        return DEFAULT_PRIORITY_SLOTS
    return tuple(tok.strip() for tok in raw.split(",") if tok.strip())


def _build_duel_fighter_cli(
    args: argparse.Namespace,
    prefix: str,
    root: Path,
    issues,
    derived,
) -> DuelFighterSpec:
    champ_name = getattr(args, f"{prefix}_champion")
    level = getattr(args, f"{prefix}_level")
    item_ids = list(getattr(args, f"{prefix}_item"))
    runes = _rune_ids(getattr(args, f"{prefix}_rune"), f"--{prefix}-rune")
    shards = _rune_ids(getattr(args, f"{prefix}_shard"), f"--{prefix}-shard")
    summoners = list(getattr(args, f"{prefix}_summoner"))
    ranks = _parse_ranks(getattr(args, f"{prefix}_learned"))
    steps_raw = getattr(args, f"{prefix}_steps")
    steps = parse_steps(steps_raw) if (steps_raw and steps_raw.strip()) else ()
    priority_slots = _parse_priority_str(getattr(args, f"{prefix}_priority"))
    inputs = {
        key: _number(value, f"--{prefix}-input {key}")
        for key, value in _pairs(getattr(args, f"{prefix}_input"), f"--{prefix}-input").items()
    }
    assumptions = _parse_assume(getattr(args, f"{prefix}_assume"))

    champion = load_champion(root, champ_name)
    kit = load_kit(root, champion.id)
    if kit is None:
        raise KitError(
            f"{champion.id} has no kit yet (lol-knowledge/champions/{champion.id}/kit.json)"
        )
    items = load_items(root, item_ids)
    _check_build(
        root, item_ids, champion, allow=args.allow_illegal_build, who=f"fighter {prefix.upper()}"
    )
    sheet = _build_sheet_with_runes(
        root,
        champion,
        level,
        items,
        runes,
        shards,
        issues,
        assumptions,
        derived,
        extras=passive_contributions(kit, ranks),
        inputs=inputs,
        combat_context="rotation",
        kit=kit,
        allow_illegal=args.allow_illegal_build,
        summoners=summoners,
        elixir=getattr(args, f"{prefix}_elixir", None),
        ornn_item=getattr(args, f"{prefix}_ornn_item", None),
    )
    holder_range = getattr(args, f"{prefix}_range")
    if holder_range is None:
        atk_range = champion.stats.get("attackrange")
        if atk_range is not None:
            holder_range = "melee" if atk_range < 300 else "ranged"
    rune_data = load_runes(root) if (runes or shards) else None
    summoner_data = (
        load_summoner_spells(root)
        if (summoners or any(s.summoner_id is not None for s in steps))
        else None
    )
    ap_weight = derived.value(champion.id, "adaptiveforceapweight") if derived else None
    return DuelFighterSpec(
        sheet=sheet,
        kit=kit,
        ranks=ranks,
        crit_base=_crit_base(champion.id, champion.patch, derived),
        steps=steps,
        priority_slots=priority_slots,
        holder_range=holder_range,
        start_health=_number(getattr(args, f"{prefix}_health"), f"--{prefix}-health"),
        start_shield=_number(getattr(args, f"{prefix}_shield"), f"--{prefix}-shield")
        or Fraction(0),
        shield_type=getattr(args, f"{prefix}_shield_type"),
        runes=runes,
        rune_data=rune_data,
        summoners=summoners,
        summoner_data=summoner_data,
        inputs=inputs,
        start_resource=_number(getattr(args, f"{prefix}_resource"), f"--{prefix}-resource"),
        allow_insufficient_resource=args.allow_insufficient_resource,
        ap_weight=ap_weight,
    )


def _run_duel(args: argparse.Namespace) -> int:
    root: Path = args.root
    try:
        issues = load_issues(root)
        derived = load_records(root)
        max_duration = _number(args.max_duration, "--max-duration")
        assert max_duration is not None
        fighter_a = _build_duel_fighter_cli(args, "a", root, issues, derived)
        fighter_b = _build_duel_fighter_cli(args, "b", root, issues, derived)
        outcome = evaluate_duel(
            fighter_a,
            fighter_b,
            mode=args.mode,
            tie_break=args.tie_break,
            max_duration=max_duration,
        )
    except (StatsError, KitError, DamageInputError, RotationError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except OSError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(duel_to_dict(outcome), indent=2, ensure_ascii=False))
    else:
        print(format_duel_text(outcome))
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
        gold_checkpoints: tuple[int, ...] = ()
        if args.gold_checkpoints:
            parsed_cps: list[int] = []
            for tok in args.gold_checkpoints.split(","):
                tok = tok.strip()
                if not tok:
                    continue
                try:
                    val_g = int(tok)
                except ValueError as exc:
                    raise StatsError(f"--gold-checkpoints expects integers, got {tok!r}") from exc
                if val_g <= 0:
                    raise StatsError("--gold-checkpoints values must be positive integers")
                parsed_cps.append(val_g)
            gold_checkpoints = tuple(parsed_cps)
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
            elixir=args.elixir,
            ornn_upgrade=args.ornn_upgrade,
            purchase_curve=args.purchase_curve,
            gold_checkpoints=gold_checkpoints,
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
            if args.steps:
                steps = parse_steps(args.steps)
            target = _ability_target(args, root, issues, derived, inputs=inputs)
            if rune_data is None and target.runes:
                rune_data = load_runes(root)

        incoming_hits = ()
        incoming_hits_for_sheet = None
        duel_enemy = None
        duel_max_duration = _number(args.duel_max_duration, "--duel-max-duration")
        assert duel_max_duration is not None
        duel_priority_slots = _parse_priority_str(args.priority)
        if args.objective == "duel":
            if not args.enemy_champion or args.enemy_level is None:
                raise StatsError("--objective duel requires --enemy-champion and --enemy-level")
            if args.steps:
                steps = parse_steps(args.steps)
            enemy_champ = load_champion(root, args.enemy_champion)
            enemy_kit = load_kit(root, enemy_champ.id)
            if enemy_kit is None:
                raise KitError(f"{enemy_champ.id} has no kit yet")
            enemy_items = load_items(root, args.enemy_item)
            _check_build(
                root, args.enemy_item, enemy_champ, allow=args.allow_illegal_build, who="enemy"
            )
            enemy_ranks = _parse_ranks(args.enemy_learned)
            enemy_runes = _rune_ids(args.enemy_rune, "--enemy-rune")
            enemy_shards = _rune_ids(args.enemy_shard, "--enemy-shard")
            enemy_summoners = list(args.enemy_summoner)
            enemy_steps = parse_steps(args.enemy_steps) if args.enemy_steps else ()
            enemy_sheet = _build_sheet_with_runes(
                root,
                enemy_champ,
                args.enemy_level,
                enemy_items,
                enemy_runes,
                enemy_shards,
                issues,
                assumptions,
                derived,
                extras=passive_contributions(enemy_kit, enemy_ranks),
                inputs=inputs,
                combat_context="rotation",
                kit=enemy_kit,
                allow_illegal=args.allow_illegal_build,
                summoners=enemy_summoners,
            )
            enemy_range = args.enemy_range
            if enemy_range is None:
                er = enemy_champ.stats.get("attackrange")
                if er is not None:
                    enemy_range = "melee" if er < 300 else "ranged"
            enemy_rune_data = load_runes(root) if (enemy_runes or enemy_shards) else None
            enemy_sdata = (
                load_summoner_spells(root)
                if (enemy_summoners or any(s.summoner_id is not None for s in enemy_steps))
                else None
            )
            enemy_ap_w = derived.value(enemy_champ.id, "adaptiveforceapweight") if derived else None
            duel_enemy = DuelFighterSpec(
                sheet=enemy_sheet,
                kit=enemy_kit,
                ranks=enemy_ranks,
                crit_base=_crit_base(enemy_champ.id, enemy_champ.patch, derived),
                steps=enemy_steps,
                priority_slots=_parse_priority_str(args.enemy_priority),
                holder_range=enemy_range,
                runes=enemy_runes,
                rune_data=enemy_rune_data,
                summoners=enemy_summoners,
                summoner_data=enemy_sdata,
                inputs=inputs,
                ap_weight=enemy_ap_w,
            )
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
                _check_build(
                    root, args.enemy_item, enemy_champ, allow=args.allow_illegal_build, who="enemy"
                )
                enemy_ranks = _parse_ranks(args.enemy_learned)
                enemy_runes = _rune_ids(args.enemy_rune, "--enemy-rune")
                enemy_shards = _rune_ids(args.enemy_shard, "--enemy-shard")
                enemy_steps = parse_steps(args.steps)
                enemy_sheet = _build_sheet_with_runes(
                    root,
                    enemy_champ,
                    args.enemy_level,
                    enemy_items,
                    enemy_runes,
                    enemy_shards,
                    issues,
                    assumptions,
                    derived,
                    extras=passive_contributions(enemy_kit, enemy_ranks),
                    inputs=inputs,
                    combat_context="rotation",
                    kit=enemy_kit,
                    allow_illegal=args.allow_illegal_build,
                )
                enemy_crit = _crit_base(enemy_champ.id, enemy_champ.patch, derived)
                enemy_rune_data = load_runes(root) if enemy_runes else None
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
                        runes=enemy_runes,
                        rune_data=enemy_rune_data,
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
            summoners=list(args.summoner),
            defender_casts=args.defender_cast,
            duel_enemy=duel_enemy,
            duel_mode=args.duel_mode,
            duel_tie_break=args.duel_tie_break,
            duel_max_duration=duel_max_duration,
            duel_priority_slots=duel_priority_slots,
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
