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
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import Any

from .errors import StatsError
from .stats import Label
from .stats.sheet import Contribution

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


def _value(rune: Rune, name: str) -> Fraction:
    try:
        return rune.values[name]
    except KeyError as exc:
        raise StatsError(f"rune {rune.id} {rune.key}: no client value {name!r}") from exc


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
            note = f"{low}–{high} by level, taken as linear ({RULES})"
            flats.append(("health", Contribution(value, "bonus", source, Label.PENDING, note)))
        elif rune.key == "Adaptive":
            if adaptive not in ("attack_damage", "ability_power"):
                raise StatsError(
                    "adaptive shards need the adaptive stat (attack_damage or ability_power)"
                )
            name = "StatGain1" if adaptive == "attack_damage" else "StatGain2"
            label = Label.PENDING if Label.PENDING in (adaptive_label, base) else base
            flats.append(
                (adaptive, Contribution(_value(rune, name), "bonus", source, label, adaptive_note))
            )
        else:
            raise StatsError(f"shard {shard} {rune.key} has no stat rule ({RULES})")
    return flats, percents


def adaptive_stat(
    bonus_attack_damage: Fraction, ability_power: Fraction, ap_weight: Fraction | None
) -> tuple[str, Label, str]:
    """Which stat adaptive force gives: the higher bonus; on a tie, the champion's.

    On a tie the client's ``mAdaptiveForceToAbilityPowerWeight`` decides: 1 gives
    ability power; absent gives attack damage. That reading is not confirmed.
    """
    if bonus_attack_damage > ability_power:
        return "attack_damage", Label.DERIVED, "adaptive: bonus AD is higher than AP"
    if ability_power > bonus_attack_damage:
        return "ability_power", Label.DERIVED, "adaptive: AP is higher than bonus AD"
    stat = "ability_power" if ap_weight == 1 else "attack_damage"
    note = (
        f"adaptive: bonus AD and AP are equal; the champion's adaptiveforceapweight "
        f"({'1' if ap_weight == 1 else 'absent'}) is read as {stat} ({RULES})"
    )
    return stat, Label.PENDING, note


def tree_rune_notes(runes: Collection[int], data: RuneData) -> list[str]:
    """One note per tree rune: their effects are not modelled yet."""
    notes = []
    for rune_id in runes:
        rune = data.runes.get(rune_id)
        name = rune.name if rune else str(rune_id)
        notes.append(f"rune {rune_id} {name}: effects not modelled (RUN-04)")
    return notes
