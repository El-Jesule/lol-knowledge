"""Runes: client data, rune page legality and stat shards (lol-knowledge/mechanics/runes.md).

``lol-knowledge/derived/runes.json`` is published by ``research/binmodel/perks.py``
from the client (``Derivado``): the five trees with their rows, the bonus rune per
secondary tree, the three shard rows and the values and texts of every rune. The
CLI never reads the client.

A page is a keystone and one rune from each other row of its tree, two runes from
different rows of an allowed secondary tree, and one shard per shard row.
Stat shards become stat sheet contributions; the effects of the other runes are not
modelled yet (RUN-04), so a page with them weakens what it touches.
"""

from __future__ import annotations

import json
import re
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass, field
from fractions import Fraction
from pathlib import Path
from typing import Any

from .damage import format_number
from .errors import StatsError
from .stats import ItemData, Label, StatAmplifier, weakest
from .stats.sheet import ADAPTIVE_AD_PER_AP, Contribution
from .stats.sheet import adaptive_stat as adaptive_stat

RUNES_PATH = Path("lol-knowledge") / "derived" / "runes.json"
SCHEMA = "lol-derived-runes/1"
RULES = "lol-knowledge/mechanics/runes.md"
REGENERATE = "regenerate it with python -m binmodel.perks (research/README.md)"
KEYSTONE_ROW = 0
GAME_VERSION = re.compile(r"\d+\.\d+")
SHA256 = re.compile(r"[0-9a-f]{64}")
HEADER_STRINGS = ("content_version", "retrieved_at", "locale", "source", "method")
PERK_KEYS = frozenset(
    {
        "key",
        "enabled",
        "stackable",
        "script",
        "effect_amounts",
        "mode_overrides",
        "calculations",
        "texts",
        "placeholders",
    }
)
# What each stat shard grants, by its client key: (stat, value name, unit). "percent"
# values are percentage points (10 = 10 %). The meaning comes from each shard's text.
SHARD_STATS = {
    "AttackSpeed": ("attack_speed_bonus", "StatGain", "percent"),
    "CDRScaling": ("ability_haste", "HasteGain", "flat"),
    "Health": ("health", "StatGain", "flat"),
    "Tenacity": ("tenacity", "StatGain", "percent"),
}
LEVELS = 18
BOUNTY_MAX_STACKS = 5  # five enemy champions on Summoner's Rift
ADAPTIVE_RUNE_KEYS = frozenset(
    {"Adaptive", "JackOfAllTrades", "AbsoluteFocus", "Waterwalking", "GatheringStorm"}
)
NON_COMBAT_MINOR_RUNES: Mapping[str, str] = {
    "SixthSense": "vision/wards only; no combat stats or damage",
    "GrislyMementos": "trinket haste only on Summoner's Rift (trinkets out of scope)",
    "DeepWard": "vision/wards only; no combat stats or damage",
    "TreasureHunter": "bonus gold only; no combat stats or damage",
    "RelentlessHunter": "out-of-combat movement speed only (lol-knowledge/mechanics/move-speed.md)",
    "HextechFlashtraption": "summoner spell replacement only; no combat stats or damage",
    "CashBack": "gold refund only; no combat stats or damage",
}
# Defensive runes evaluated during reverse survival simulations (defense.py / survive).
DEFENSE_RUNE_KEYS = frozenset({"BonePlating", "SecondWind", "Guardian"})
# Minor runes whose combat damage or damage modifiers are evaluated by rotations (rune_combat.py).
COMBAT_MINOR_RUNE_KEYS = frozenset(
    {
        "CoupDeGrace",
        "CutDown",
        "LastStand",
        "NullifyingOrb",
        "Scorch",
        "CheapShot",
        "SuddenImpact",
        "Demolish",
        "Revitalize",
        "ShieldBash",
        "TasteOfBlood",
        "AbsorbLife",
        "Triumph",
        "FontOfLife",
        "PresenceOfMind",
    }
)
# Keystones whose combat effects are evaluated by rotations (rune_keystones.py).
COMBAT_KEYSTONE_KEYS = frozenset(
    {
        "Electrocute",
        "DarkHarvest",
        "PressTheAttack",
        "Conqueror",
        "LethalTempo",
        "HailOfBlades",
        "SummonAery",
        "ArcaneComet",
        "DeathfireTouch",
        "FirstStrike",
        "GraspOfTheUndying",
    }
)
COMBAT_RUNE_KEYS = COMBAT_MINOR_RUNE_KEYS | COMBAT_KEYSTONE_KEYS


@dataclass(frozen=True)
class RuneEffects:
    """Stat-sheet contributions and notes produced by the tree runes of a page."""

    flats: tuple[tuple[str, Contribution], ...] = ()
    percents: tuple[tuple[str, Contribution], ...] = ()
    amplifiers: tuple[StatAmplifier, ...] = ()
    move_speed_bonus_amp: Contribution | None = None
    notes: tuple[str, ...] = ()
    pending: tuple[str, ...] = ()
    combat_runes: tuple[int, ...] = ()


@dataclass(frozen=True)
class Tree:
    id: int
    key: str
    name: str
    allowed_secondary: tuple[int, ...]
    rows: tuple[tuple[int, ...], ...]  # the keystone row first


@dataclass(frozen=True)
class Rune:
    id: int
    key: str
    name: str
    values: Mapping[str, Fraction]
    ranged_multipliers: Mapping[str, Fraction] = field(default_factory=dict)
    level_bounds: Mapping[str, tuple[Fraction, Fraction]] = field(default_factory=dict)
    level_tables: Mapping[str, tuple[Fraction, ...]] = field(default_factory=dict)


@dataclass(frozen=True)
class RuneData:
    path: str
    content_version: str
    game_version: str
    trees: Mapping[int, Tree]
    shard_rows: tuple[tuple[int, ...], ...]
    runes: Mapping[int, Rune]

    def matches_patch(self, patch: str) -> bool:
        return ".".join(patch.split(".")[:2]) == self.game_version

    def tree_of(self, rune_id: int) -> tuple[Tree, int] | None:
        """The tree and row index of a tree rune."""
        for tree in self.trees.values():
            for index, row in enumerate(tree.rows):
                if rune_id in row:
                    return tree, index
        return None


@dataclass(frozen=True)
class RunePage:
    primary: int
    secondary: int
    runes: tuple[int, ...]  # keystone, three primary runes, two secondary runes
    shards: tuple[int, ...]  # offense, flex, defense


@dataclass(frozen=True)
class PageReport:
    page: RunePage | None
    violations: tuple[str, ...]
    label: Label
    source: str

    @property
    def legal(self) -> bool:
        return not self.violations


def _ids(value: Any) -> bool:
    return isinstance(value, list) and all(
        isinstance(item, int) and not isinstance(item, bool) for item in value
    )


def _tree_problems(key: str, tree: Any, perks: Mapping[str, Any]) -> list[str]:
    where = f"styles.{key}"
    if not isinstance(tree, Mapping):
        return [f"{where} must be an object"]
    problems = []
    if not isinstance(tree.get("key"), str) or not isinstance(tree.get("name"), str):
        problems.append(f"{where}: key and name must be strings")
    if not _ids(tree.get("allowed_secondary")):
        problems.append(f"{where}.allowed_secondary must be a list of tree ids")
    slots = tree.get("slots")
    if not isinstance(slots, list) or not slots:
        return [*problems, f"{where}.slots must be a non-empty list"]
    for index, slot in enumerate(slots):
        if not isinstance(slot, Mapping) or not _ids(slot.get("perks")) or not slot["perks"]:
            problems.append(f"{where}.slots[{index}] must list rune ids")
            continue
        expected = KEYSTONE_ROW if index == 0 else 3
        if slot.get("type") != expected:
            problems.append(f"{where}.slots[{index}].type must be {expected}")
        missing = [str(rune) for rune in slot["perks"] if str(rune) not in perks]
        if missing:
            problems.append(f"{where}.slots[{index}]: runes without data {missing}")
    bonus = tree.get("secondary_bonus")
    if not isinstance(bonus, Mapping) or not all(str(rune) in perks for rune in bonus.values()):
        problems.append(f"{where}.secondary_bonus must map tree ids to runes with data")
    return problems


def runes_problems(document: Any, *, patch: str | None = None, official: Any = None) -> list[str]:
    """Every reason why ``document`` is not a usable ``runes.json``.

    With ``official`` (Data Dragon's ``runes.json``), the trees, rows and rune ids
    must be the same.
    """
    if not isinstance(document, Mapping):
        return ["the document must be a JSON object"]
    problems = []
    if document.get("schema") != SCHEMA:
        problems.append(f"schema must be {SCHEMA!r}")
    if document.get("label") != "Derivado":
        problems.append("label must be 'Derivado'")
    for key in HEADER_STRINGS:
        if not isinstance(document.get(key), str) or not document[key]:
            problems.append(f"{key} must be a non-empty string")
    for key in ("bin_sha256", "strings_sha256"):
        if not isinstance(document.get(key), str) or not SHA256.fullmatch(document[key]):
            problems.append(f"{key} must be a SHA-256 hex digest")
    game_version = document.get("game_version")
    if not isinstance(game_version, str) or not GAME_VERSION.fullmatch(game_version):
        problems.append("game_version must be <major>.<minor>")
    elif patch is not None and not patch.startswith(f"{game_version}."):
        problems.append(f"client {game_version} data for snapshot {patch}; {REGENERATE}")
    perks = document.get("perks")
    styles = document.get("styles")
    shards = document.get("shard_slots")
    if not isinstance(perks, Mapping) or not isinstance(styles, Mapping):
        return [*problems, "perks and styles must be objects"]
    for perk_id, perk in perks.items():
        if not isinstance(perk, Mapping) or set(perk) != PERK_KEYS:
            problems.append(f"perks.{perk_id} must have exactly {sorted(PERK_KEYS)}")
            continue
        values = perk["effect_amounts"]
        if not isinstance(values, Mapping) or not all(
            isinstance(number, (int, float)) and not isinstance(number, bool)
            for number in values.values()
        ):
            problems.append(f"perks.{perk_id}.effect_amounts must map names to numbers")
    for key, tree in styles.items():
        problems += _tree_problems(str(key), tree, perks)
    if (
        not isinstance(shards, list)
        or len(shards) != 3
        or not all(isinstance(row, Mapping) and _ids(row.get("perks")) for row in shards)
    ):
        problems.append("shard_slots must be three rows of rune ids")
    else:
        missing = [str(rune) for row in shards for rune in row["perks"] if str(rune) not in perks]
        if missing:
            problems.append(f"shard_slots: shards without data {missing}")
    if official is not None and not problems:
        published = {
            int(tree["id"]): [[rune["id"] for rune in slot["runes"]] for slot in tree["slots"]]
            for tree in official
        }
        client = {
            int(key): [slot["perks"] for slot in tree["slots"]] for key, tree in styles.items()
        }
        if published != client:
            problems.append(
                "trees, rows or rune ids differ from Data Dragon's runes.json; " + REGENERATE
            )
    return problems


def _parse_ranged_multipliers(calculations: Any) -> dict[str, Fraction]:
    if not isinstance(calculations, Mapping):
        return {}
    result: dict[str, Fraction] = {}
    for name, calc in calculations.items():
        if not isinstance(calc, Mapping):
            continue
        mult = calc.get("mRangedMultiplier")
        if (
            isinstance(mult, Mapping)
            and isinstance(mult.get("mNumber"), (int, float))
            and not isinstance(mult.get("mNumber"), bool)
        ):
            result[str(name)] = Fraction(str(mult["mNumber"]))
    return result


def _parse_level_bounds(calculations: Any) -> dict[str, tuple[Fraction, Fraction]]:
    if not isinstance(calculations, Mapping):
        return {}
    result: dict[str, tuple[Fraction, Fraction]] = {}
    for name, calc in calculations.items():
        if not isinstance(calc, Mapping):
            continue
        for part in calc.get("mFormulaParts") or ():
            if (
                isinstance(part, Mapping)
                and part.get("class") == "ByCharLevelInterpolationCalculationPart"
                and isinstance(part.get("mStartValue"), (int, float))
                and isinstance(part.get("mEndValue"), (int, float))
                and not isinstance(part.get("mStartValue"), bool)
                and not isinstance(part.get("mEndValue"), bool)
            ):
                result[str(name)] = (
                    Fraction(str(part["mStartValue"])),
                    Fraction(str(part["mEndValue"])),
                )
                break
    return result


def _parse_level_tables(calculations: Any) -> dict[str, tuple[Fraction, ...]]:
    """Parse per-level value tables (class ``{2421b258}``, values in ``{34474c3b}``)."""
    if not isinstance(calculations, Mapping):
        return {}
    result: dict[str, tuple[Fraction, ...]] = {}
    for name, calc in calculations.items():
        if not isinstance(calc, Mapping):
            continue
        for part in calc.get("mFormulaParts") or ():
            if not isinstance(part, Mapping):
                continue
            values = part.get("{34474c3b}")
            if (
                isinstance(values, list)
                and len(values) > LEVELS
                and all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in values)
            ):
                result[str(name)] = tuple(Fraction(str(v)) for v in values)
                break
    return result


def rune_level_bounds(rune: Rune, name: str) -> tuple[Fraction, Fraction]:
    if name not in rune.level_bounds:
        raise StatsError(f"rune {rune.id} {rune.key}: client data has no level bounds {name}")
    return rune.level_bounds[name]


def rune_level_table(rune: Rune, name: str, level: int) -> Fraction:
    """1-indexed level value from a client per-level breakpoint table (levels 1..18)."""
    if name not in rune.level_tables:
        raise StatsError(f"rune {rune.id} {rune.key}: client data has no level table {name}")
    table = rune.level_tables[name]
    if not 1 <= level < len(table):
        raise StatsError(f"rune {rune.id} {rune.key}: level {level} out of table bounds")
    return table[level]


def rune_ranged_multiplier(rune: Rune, name: str) -> Fraction:
    if name not in rune.ranged_multipliers:
        raise StatsError(f"rune {rune.id} {rune.key}: client data has no ranged multiplier {name}")
    return rune.ranged_multipliers[name]


def parse_runes(document: Any, path: str = RUNES_PATH.as_posix()) -> RuneData:
    problems = runes_problems(document)
    if problems:
        raise StatsError(f"{path}: {problems[0]}")
    trees = {
        int(key): Tree(
            int(key),
            tree["key"],
            tree["name"],
            tuple(tree["allowed_secondary"]),
            tuple(tuple(slot["perks"]) for slot in tree["slots"]),
        )
        for key, tree in document["styles"].items()
    }
    runes = {
        int(perk_id): Rune(
            int(perk_id),
            perk["key"],
            perk["texts"].get("name", perk["key"]),
            {name: Fraction(str(value)) for name, value in perk["effect_amounts"].items()},
            _parse_ranged_multipliers(perk.get("calculations")),
            _parse_level_bounds(perk.get("calculations")),
            _parse_level_tables(perk.get("calculations")),
        )
        for perk_id, perk in document["perks"].items()
    }
    shard_rows = tuple(tuple(row["perks"]) for row in document["shard_slots"])
    return RuneData(
        path, document["content_version"], document["game_version"], trees, shard_rows, runes
    )


def load_runes(root: Path) -> RuneData | None:
    """The published rune data, or ``None`` when the project has none."""
    path = root / RUNES_PATH
    if not path.is_file():
        return None
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise StatsError(f"{RUNES_PATH.as_posix()}: unreadable: {exc}") from exc
    return parse_runes(document)


def _tree_part(data: RuneData, runes: Sequence[int], violations: list[str]) -> tuple[int, int]:
    """Check the six tree runes; return ``(primary, secondary)`` tree ids (0 if unknown)."""
    if len(runes) != 6:
        violations.append(
            f"a page has 6 tree runes (a keystone, 3 primary, 2 secondary); got {len(runes)}"
        )
    placed: dict[int, tuple[Tree, int]] = {}
    for rune in runes:
        found = data.tree_of(rune)
        if found is None:
            violations.append(f"{rune} is not a tree rune")
        elif rune in placed:
            violations.append(f"{rune} is repeated")
        else:
            placed[rune] = found
    keystones = [rune for rune, (_, row) in placed.items() if row == KEYSTONE_ROW]
    if len(keystones) != 1:
        violations.append(f"a page has exactly one keystone; got {keystones}")
        return 0, 0
    primary = placed[keystones[0]][0]
    primary_rows = sorted(row for rune, (tree, row) in placed.items() if tree.id == primary.id)
    if primary_rows != list(range(len(primary.rows))):
        violations.append(
            f"the primary tree {primary.key} needs one rune from each row; "
            f"rows used: {primary_rows}"
        )
    others = {tree.id for rune, (tree, _) in placed.items() if tree.id != primary.id}
    if len(others) != 1:
        violations.append(
            f"the two secondary runes must come from one other tree; trees: {sorted(others)}"
        )
        return primary.id, 0
    secondary = data.trees[others.pop()]
    if secondary.id not in primary.allowed_secondary:
        violations.append(f"{secondary.key} cannot be the secondary tree of {primary.key}")
    rows = [row for rune, (tree, row) in placed.items() if tree.id == secondary.id]
    if len(rows) != 2 or len(set(rows)) != 2:
        violations.append(
            f"the secondary tree {secondary.key} gives 2 runes from different rows; rows: {rows}"
        )
    return primary.id, secondary.id


def check_page(
    runes: Sequence[int], shards: Sequence[int], data: RuneData, *, patch: str
) -> PageReport:
    """Whether ``runes`` and ``shards`` (offense, flex, defense) form a legal page."""
    violations: list[str] = []
    primary, secondary = _tree_part(data, runes, violations)
    if len(shards) != len(data.shard_rows):
        violations.append(
            f"a page has {len(data.shard_rows)} shards, one per row; got {len(shards)}"
        )
    for index, (shard, row) in enumerate(zip(shards, data.shard_rows, strict=False)):
        if shard not in row:
            violations.append(f"shard {shard} is not in shard row {index + 1} {list(row)}")
    page = RunePage(primary, secondary, tuple(runes), tuple(shards))
    label = Label.DERIVED if data.matches_patch(patch) else Label.PENDING
    return PageReport(
        page, tuple(violations), label, f"{data.path} ({data.content_version}); rule: {RULES}"
    )


def rune_value(rune: Rune, name: str) -> Fraction:
    try:
        return rune.values[name]
    except KeyError as exc:
        raise StatsError(f"rune {rune.id} {rune.key}: no client value {name!r}") from exc


_value = rune_value


def shard_contributions(
    shards: Sequence[int],
    data: RuneData,
    *,
    level: int,
    patch: str,
    adaptive: str | None = None,
    adaptive_label: Label = Label.DERIVED,
    adaptive_note: str = "",
) -> tuple[list[tuple[str, Contribution]], list[tuple[str, Contribution]]]:
    """``(flat contributions, percentage contributions)`` the shards give at ``level``.

    ``adaptive`` is ``"attack_damage"`` or ``"ability_power"`` for adaptive shards
    (``adaptive_stat`` chooses it); a page with adaptive shards needs it.
    """
    base = Label.DERIVED if data.matches_patch(patch) else Label.PENDING
    flats: list[tuple[str, Contribution]] = []
    percents: list[tuple[str, Contribution]] = []
    for shard in shards:
        rune = data.runes.get(shard)
        if rune is None:
            raise StatsError(f"shard {shard} has no client data")
        source = f"rune:{shard} {rune.key} ({data.content_version})"
        if rune.key in SHARD_STATS:
            stat, name, unit = SHARD_STATS[rune.key]
            value = _value(rune, name)
            note, group = "", None
            if rune.key == "Tenacity":
                note, group = "group A (tenacity.md); its slow resist is not modelled", "A"
            flats.append(
                (
                    stat,
                    Contribution(
                        value / 100 if unit == "percent" else value,
                        "bonus",
                        source,
                        base,
                        note,
                        tenacity_group=group,
                    ),
                )
            )
        elif rune.key == "MovementSpeed":
            value = _value(rune, "StatGain1") / 100
            percents.append(("move_speed", Contribution(value, "bonus", source, base)))
        elif rune.key == "HealthScaling":
            low, high = _value(rune, "StatGainMin"), _value(rune, "StatGainMax")
            value = low + (high - low) * (level - 1) / (LEVELS - 1)
            note = f"{low}–{high} by level, linear 10/level ({RULES})"
            flats.append(("health", Contribution(value, "bonus", source, base, note)))
        elif rune.key == "Adaptive":
            if adaptive not in ("attack_damage", "ability_power"):
                raise StatsError(
                    "adaptive shards need the adaptive stat (attack_damage or ability_power)"
                )
            name = "StatGain1" if adaptive == "attack_damage" else "StatGain2"
            label = Label.PENDING if Label.PENDING in (adaptive_label, base) else base
            flats.append(
                (
                    adaptive,
                    Contribution(
                        _value(rune, name), "bonus", source, label, adaptive_note, adaptive=True
                    ),
                )
            )
        else:
            raise StatsError(f"shard {shard} {rune.key} has no stat rule ({RULES})")
    return flats, percents


def tree_rune_notes(runes: Collection[int], data: RuneData) -> list[str]:
    """One note per tree rune: their effects are not modelled yet."""
    notes = []
    for rune_id in runes:
        rune = data.runes.get(rune_id)
        name = rune.name if rune else str(rune_id)
        notes.append(f"rune {rune_id} {name}: effects not modelled (RUN-04)")
    return notes


def needs_adaptive_stat(runes: Sequence[int], shards: Sequence[int], data: RuneData) -> bool:
    """Whether any rune or shard on the page grants adaptive force."""
    for rune_id in (*runes, *shards):
        rune = data.runes.get(rune_id)
        if rune is not None and rune.key in ADAPTIVE_RUNE_KEYS:
            return True
    return False


def combat_rune_notes(
    runes: Sequence[int], data: RuneData, *, in_ability: bool = False
) -> list[str]:
    """Notes explaining combat runes in commands that do not evaluate them."""
    tail = (
        "combat effect (applied in rotation, not in ability)"
        if in_ability
        else ("combat effect (applied in rotation)")
    )
    notes = []
    for rune_id in runes:
        rune = data.runes.get(rune_id)
        name = rune.name if rune else str(rune_id)
        notes.append(f"rune {rune_id} {name}: {tail}")
    return notes


def int_input(
    inputs: Mapping[str, Fraction],
    name: str,
    *,
    minimum: int = 0,
    maximum: int | None = None,
) -> int | None:
    if name not in inputs:
        return None
    raw = inputs[name]
    if raw.denominator != 1:
        raise StatsError(f"input {name}: must be an integer, got {format_number(raw)}")
    value = int(raw)
    if value < minimum or (maximum is not None and value > maximum):
        bound = f"between {minimum} and {maximum}" if maximum is not None else f">= {minimum}"
        raise StatsError(f"input {name}: must be {bound}, got {value}")
    return value


_int_input = int_input


def _nonneg_input(inputs: Mapping[str, Fraction], name: str) -> Fraction | None:
    if name not in inputs:
        return None
    value = inputs[name]
    if value < 0:
        raise StatsError(f"input {name}: must not be negative, got {format_number(value)}")
    return value


def fraction_input(inputs: Mapping[str, Fraction], name: str) -> Fraction | None:
    if name not in inputs:
        return None
    value = inputs[name]
    if not 0 <= value <= 1:
        raise StatsError(f"input {name}: must be between 0 and 1, got {format_number(value)}")
    return value


_fraction_input = fraction_input


def linear_by_level(low: Fraction, high: Fraction, level: int) -> Fraction:
    return low + (high - low) * (level - 1) / (LEVELS - 1)


_linear_by_level = linear_by_level


def _adaptive_contribution(
    ap_amount: Fraction,
    source: str,
    base_label: Label,
    note: str,
    *,
    adaptive: str | None,
    adaptive_label: Label,
    adaptive_note: str,
) -> tuple[str, Contribution]:
    if adaptive not in ("attack_damage", "ability_power"):
        raise StatsError("adaptive runes need the adaptive stat (attack_damage or ability_power)")
    value = ap_amount if adaptive == "ability_power" else ap_amount * ADAPTIVE_AD_PER_AP
    label = weakest((base_label, adaptive_label))
    full_note = f"{note}; {adaptive_note}" if (note and adaptive_note) else (note or adaptive_note)
    return adaptive, Contribution(value, "bonus", source, label, full_note)


def _jack_distinct_stats(items: Sequence[ItemData]) -> tuple[int, bool]:
    """Count distinct non-zero item stats for Jack of All Trades; flag unknown item stats."""
    distinct: set[tuple[str, str]] = set()
    has_unknown = False
    for item in items:
        for entry in item.stats:
            if entry.value > 0:
                distinct.add((entry.stat, entry.kind))
            elif entry.value == 0 and entry.label is Label.PENDING:
                has_unknown = True
        for reason in item.unmodelled_stats:
            if "heal and shield power" in reason.lower():
                distinct.add(("heal_shield_power", "percent"))
    return len(distinct), has_unknown


def _apply_legend(
    rune: Rune,
    source: str,
    base: Label,
    inputs: Mapping[str, Fraction],
    flats: list[tuple[str, Contribution]],
) -> None:
    max_stacks = int(_value(rune, "MaxLegendStacks"))
    given = _int_input(inputs, "legend_stacks", minimum=0, maximum=max_stacks)
    stacks = max_stacks if given is None else given
    note = (
        f"scenario: maximum stacks ({stacks})"
        if given is None
        else f"scenario: legend_stacks={stacks}"
    )
    if rune.key == "LegendAlacrity":
        total = _value(rune, "AttackSpeedBase") + stacks * _value(rune, "AttackSpeedPerStack")
        flats.append(("attack_speed_bonus", Contribution(total, "bonus", source, base, note)))
    elif rune.key == "LegendHaste":
        total = _value(rune, "HasteBase") + stacks * _value(rune, "HasteperStack")
        flats.append(("basic_ability_haste", Contribution(total, "bonus", source, base, note)))
    elif rune.key == "LegendBloodline":
        lifesteal = stacks * _value(rune, "LifeStealPerStack") / 100
        flats.append(("life_steal", Contribution(lifesteal, "bonus", source, base, note)))
        if stacks == max_stacks:
            flats.append(
                ("health", Contribution(_value(rune, "BonusHealth"), "bonus", source, base, note))
            )


def _apply_time_or_conditional(
    rune: Rune,
    source: str,
    base: Label,
    *,
    level: int,
    inputs: Mapping[str, Fraction],
    adaptive: str | None,
    adaptive_label: Label,
    adaptive_note: str,
    flats: list[tuple[str, Contribution]],
    amplifiers: list[StatAmplifier],
    notes: list[str],
    pending: list[str],
) -> bool:
    """Apply scenario-input stat runes; return False when ``rune`` is not one of them."""
    if rune.key == "GatheringStorm":
        minutes = _nonneg_input(inputs, "game_minutes")
        if minutes is None:
            pending.append(
                f"rune {rune.id} {rune.name}: needs --input game_minutes=<min> ({RULES})"
            )
            return True
        interval = _value(rune, "UpdateAfterMinutes")
        step_ap = _value(rune, "{969826da}")
        steps = int(minutes // interval)
        if steps == 0:
            notes.append(
                f"rune {rune.id} {rune.name}: inactive before {format_number(interval)} min"
            )
            return True
        ap_amount = step_ap * steps * (steps + 1) / 2
        note = f"scenario: game_minutes={format_number(minutes)} ({steps} x {int(interval)} min)"
        flats.append(
            _adaptive_contribution(
                ap_amount,
                source,
                base,
                note,
                adaptive=adaptive,
                adaptive_label=adaptive_label,
                adaptive_note=adaptive_note,
            )
        )
        return True

    if rune.key == "Conditioning":
        minutes = _nonneg_input(inputs, "game_minutes")
        required = _value(rune, "MinutesRequired")
        if minutes is None:
            pending.append(
                f"rune {rune.id} {rune.name}: needs --input game_minutes=<min> "
                f"(active from {format_number(required)} min)"
            )
            return True
        if minutes < required:
            notes.append(
                f"rune {rune.id} {rune.name}: inactive before {format_number(required)} min"
            )
            return True
        note = f"scenario: game_minutes={format_number(minutes)}"
        flats.append(
            ("armor", Contribution(_value(rune, "ArmorBase"), "bonus", source, base, note))
        )
        flats.append(
            ("magic_resist", Contribution(_value(rune, "MRBase"), "bonus", source, base, note))
        )
        pct = _value(rune, "ExtraResist") * 100
        amplifiers.append(StatAmplifier("armor", pct, source, base, note))
        amplifiers.append(StatAmplifier("magic_resist", pct, source, base, note))
        return True

    if rune.key == "Overgrowth":
        units = _int_input(inputs, "overgrowth_units", minimum=0)
        if units is None:
            pending.append(
                f"rune {rune.id} {rune.name}: needs --input overgrowth_units=<count> (no cap)"
            )
            return True
        per_tier = int(_value(rune, "UnitsPerTier"))
        tiers = units // per_tier
        note = f"scenario: overgrowth_units={units}"
        if tiers > 0:
            flats.append(
                (
                    "health",
                    Contribution(
                        tiers * _value(rune, "FlatHealthPerTier"), "bonus", source, base, note
                    ),
                )
            )
        else:
            notes.append(f"rune {rune.id} {rune.name}: {units} units absorbed (< {per_tier})")
        if units >= int(_value(rune, "ThresholdUnits")):
            pct = _value(rune, "ThresholdMaxHealthRatio") * 100
            amplifiers.append(StatAmplifier("health", pct, source, base, note))
        return True

    if rune.key == "AbsoluteFocus":
        hp_pct = _fraction_input(inputs, "attacker_health_percent")
        threshold = _value(rune, "HealthPercent")
        if hp_pct is None:
            pending.append(
                f"rune {rune.id} {rune.name}: needs --input attacker_health_percent=<0..1> "
                f"(active above {format_number(threshold * 100)}%)"
            )
            return True
        if hp_pct < threshold:
            pct_text = format_number(threshold * 100)
            notes.append(f"rune {rune.id} {rune.name}: inactive below {pct_text}% health")
            return True
        ap_amount = _linear_by_level(
            _value(rune, "MinAdaptive"), _value(rune, "MaxAdaptive"), level
        )
        label = base
        note = f"scenario: attacker_health_percent={format_number(hp_pct)}"
        if hp_pct == threshold:
            label = Label.PENDING
            note += "; at exact threshold (> vs >= not measured)"
        flats.append(
            _adaptive_contribution(
                ap_amount,
                source,
                label,
                note,
                adaptive=adaptive,
                adaptive_label=adaptive_label,
                adaptive_note=adaptive_note,
            )
        )
        return True

    if rune.key == "Waterwalking":
        in_river = _int_input(inputs, "in_river", minimum=0, maximum=1)
        if in_river is None:
            pending.append(
                f"rune {rune.id} {rune.name}: needs --input in_river=0|1 (only active in the river)"
            )
            return True
        if in_river == 0:
            notes.append(f"rune {rune.id} {rune.name}: inactive outside the river")
            return True
        note = "scenario: in_river=1"
        flats.append(
            ("move_speed", Contribution(_value(rune, "MovementSpeed"), "bonus", source, base, note))
        )
        ap_amount = _linear_by_level(
            _value(rune, "MinAdaptive"), _value(rune, "MaxAdaptive"), level
        )
        flats.append(
            _adaptive_contribution(
                ap_amount,
                source,
                base,
                note,
                adaptive=adaptive,
                adaptive_label=adaptive_label,
                adaptive_note=adaptive_note,
            )
        )
        return True

    return False


def minor_rune_effects(
    runes: Sequence[int],
    data: RuneData,
    *,
    level: int,
    patch: str,
    items: Sequence[ItemData] = (),
    uses_mana: bool = True,
    has_boots: bool | None = None,
    inputs: Mapping[str, Fraction] | None = None,
    adaptive: str | None = None,
    adaptive_label: Label = Label.DERIVED,
    adaptive_note: str = "",
) -> RuneEffects:
    """Stat contributions, informational notes and pending effects for ``runes``."""
    base = Label.DERIVED if data.matches_patch(patch) else Label.PENDING
    scenario = inputs or {}
    flats: list[tuple[str, Contribution]] = []
    percents: list[tuple[str, Contribution]] = []
    amplifiers: list[StatAmplifier] = []
    move_speed_bonus_amp: Contribution | None = None
    notes: list[str] = []
    pending: list[str] = []
    combat_runes: list[int] = []
    seen: set[int] = set()

    for rune_id in runes:
        if rune_id in seen:
            continue
        seen.add(rune_id)
        rune = data.runes.get(rune_id)
        if rune is None:
            pending.append(f"rune {rune_id} {rune_id}: effects not modelled (RUN-04)")
            continue
        source = f"rune:{rune_id} {rune.key} ({data.content_version})"

        if rune.key in NON_COMBAT_MINOR_RUNES:
            notes.append(f"rune {rune_id} {rune.name}: {NON_COMBAT_MINOR_RUNES[rune.key]}")
            continue

        if rune.key in DEFENSE_RUNE_KEYS:
            notes.append(f"rune {rune_id} {rune.name}: defensive rune (applied in survive)")
            continue

        if rune.key == "Revitalize":
            flats.append(
                (
                    "heal_and_shield_power",
                    Contribution(_value(rune, "HealShieldPower"), "bonus", source, base),
                )
            )
            if rune.key in COMBAT_RUNE_KEYS:
                combat_runes.append(rune_id)
            else:
                notes.append(
                    f"rune {rune_id} {rune.name}: +10% healing/shielding below 40% HP "
                    "applies in rotation"
                )
            continue

        if rune.key in COMBAT_RUNE_KEYS:
            combat_runes.append(rune_id)
            continue

        if rune.key == "Transcendence":
            lvl1 = int(_value(rune, "LevelToTurnOn"))
            lvl2 = int(_value(rune, "LevelToTurnOn2"))
            lvl3 = int(_value(rune, "LevelToTurnOn3"))
            haste = Fraction(0)
            if level >= lvl1:
                haste += _value(rune, "HasteBonus1") * 100
            if level >= lvl2:
                haste += _value(rune, "HasteBonus2") * 100
            if haste > 0:
                tier = lvl2 if level >= lvl2 else lvl1
                flats.append(
                    (
                        "ability_haste",
                        Contribution(haste, "bonus", source, base, f"level >= {tier}"),
                    )
                )
            else:
                notes.append(f"rune {rune_id} {rune.name}: active from level {lvl1}")
            if level >= lvl3:
                notes.append(
                    f"rune {rune_id} {rune.name}: basic cooldown refund on takedown is not modelled"
                )
            continue

        if rune.key in ("LegendAlacrity", "LegendHaste", "LegendBloodline"):
            _apply_legend(rune, source, base, scenario, flats)
            continue

        if rune.key == "ManaflowBand":
            if uses_mana:
                flats.append(
                    (
                        "mana",
                        Contribution(
                            _value(rune, "MaxManaIncrease"),
                            "bonus",
                            source,
                            base,
                            "scenario: maximum stacks",
                        ),
                    )
                )
                notes.append(
                    f"rune {rune_id} {rune.name}: missing mana regeneration applies in "
                    "rotation --timeline"
                )
            else:
                notes.append(f"rune {rune_id} {rune.name}: champion does not use mana")
            continue

        if rune.key == "UltimateHunter":
            given = _int_input(scenario, "bounty_stacks", minimum=0, maximum=BOUNTY_MAX_STACKS)
            stacks = BOUNTY_MAX_STACKS if given is None else given
            note = (
                f"scenario: maximum stacks ({stacks})"
                if given is None
                else f"scenario: bounty_stacks={stacks}"
            )
            total = _value(rune, "StartingUltAH") + stacks * _value(rune, "AdditionalUltAH")
            flats.append(("ultimate_haste", Contribution(total, "bonus", source, base, note)))
            continue

        if rune.key == "Celerity":
            percents.append(
                ("move_speed", Contribution(_value(rune, "PercentMS"), "bonus", source, base))
            )
            move_speed_bonus_amp = Contribution(
                _value(rune, "PercentHasteMod"),
                "bonus",
                source,
                Label.PENDING,
                f"self-amplification and bonus order not measured ({RULES})",
            )
            continue

        if rune.key == "JackOfAllTrades":
            stacks, has_unknown = _jack_distinct_stats(items)
            haste_label = Label.PENDING if has_unknown else base
            if stacks == 0:
                notes.append(f"rune {rune_id} {rune.name}: 0 distinct item stats")
                continue
            note = f"{stacks} distinct item stats"
            if has_unknown:
                note += "; item has unknown stat value"
            flats.append(
                (
                    "ability_haste",
                    Contribution(
                        stacks * _value(rune, "HasteperStack"), "bonus", source, haste_label, note
                    ),
                )
            )
            ap_amount = (
                _value(rune, "Adaptive10")
                if stacks >= 10
                else (_value(rune, "Adaptive5") if stacks >= 5 else Fraction(0))
            )
            if ap_amount > 0:
                flats.append(
                    _adaptive_contribution(
                        ap_amount,
                        source,
                        haste_label,
                        note,
                        adaptive=adaptive,
                        adaptive_label=adaptive_label,
                        adaptive_note=adaptive_note,
                    )
                )
            continue

        if rune.key == "MagicalFootwear":
            if has_boots is None:
                pending.append(
                    f"rune {rune_id} {rune.name}: item-groups.json missing, cannot check for boots"
                )
            elif has_boots:
                flats.append(
                    (
                        "move_speed",
                        Contribution(
                            _value(rune, "AdditionalMovementSpeed"),
                            "bonus",
                            source,
                            base,
                            "boots upgraded from Slightly Magical Footwear",
                        ),
                    )
                )
            else:
                notes.append(
                    f"rune {rune_id} {rune.name}: no boots in build "
                    "(+10 move speed applies to boots)"
                )
            continue

        if rune.key == "BiscuitDelivery":
            interval = _value(rune, "BiscuitMinuteInterval")
            end = _value(rune, "SwapOverMinute")
            max_biscuits = int(end // interval)
            minutes = _nonneg_input(scenario, "game_minutes")
            if minutes is None:
                biscuits = max_biscuits
                note = f"scenario: maximum stacks ({biscuits} biscuits)"
            else:
                biscuits = min(max_biscuits, int(minutes // interval))
                note = f"scenario: game_minutes={format_number(minutes)} ({biscuits} biscuits)"
            if biscuits > 0:
                flats.append(
                    (
                        "health",
                        Contribution(
                            biscuits * _value(rune, "PermanentHP"), "bonus", source, base, note
                        ),
                    )
                )
            notes.append(f"rune {rune_id} {rune.name}: consumable healing is not modelled")
            continue

        if _apply_time_or_conditional(
            rune,
            source,
            base,
            level=level,
            inputs=scenario,
            adaptive=adaptive,
            adaptive_label=adaptive_label,
            adaptive_note=adaptive_note,
            flats=flats,
            amplifiers=amplifiers,
            notes=notes,
            pending=pending,
        ):
            continue

        pending.append(f"rune {rune_id} {rune.name}: effects not modelled (RUN-04)")

    return RuneEffects(
        flats=tuple(flats),
        percents=tuple(percents),
        amplifiers=tuple(amplifiers),
        move_speed_bonus_amp=move_speed_bonus_amp,
        notes=tuple(notes),
        pending=tuple(pending),
        combat_runes=tuple(combat_runes),
    )
