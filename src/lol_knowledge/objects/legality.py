"""Build legality: which item sets one inventory may hold.

Rules: lol-knowledge/mechanics/build-legality.md.

The limits come from the client's item groups, published as ``Derivado`` in
``lol-knowledge/derived/item-groups.json`` by ``research/binmodel/item_groups.py``:
each group may cap how many of its items an inventory owns (``max_ownable``)
and may pin its items to one inventory slot (trinkets). The number of ordinary
slots is not in the item bin; it is a documented rule (``INVENTORY_SLOTS``).
The CLI never reads the client; it reads the published file.
"""

from __future__ import annotations

import json
import math
import re
from collections import Counter
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..errors import StatsError
from ..stats.labels import Label

ITEM_GROUPS_PATH = Path("lol-knowledge") / "derived" / "item-groups.json"
SCHEMA = "lol-derived-item-groups/1"
RULE_PATH = "lol-knowledge/mechanics/build-legality.md"
REGENERATE = "regenerate it with python -m binmodel.item_groups (research/README.md)"
# Ordinary inventory slots of Summoner's Rift; trinkets take a slot of their own.
# Source: League of Legends Wiki, «Items» (secondary), build-legality.md rule 1.
INVENTORY_SLOTS = 6
GAME_VERSION = re.compile(r"\d+\.\d+")
SHA256 = re.compile(r"[0-9a-f]{64}")
GROUP_KEY = re.compile(r"[0-9a-f]{8}")
GROUP_INTEGERS = ("max_ownable", "inventory_slot_min", "inventory_slot_max")
HEADER_STRINGS = ("content_version", "retrieved_at", "source", "method")


@dataclass(frozen=True)
class Group:
    key: str
    name: str
    max_ownable: int | None
    slot: int | None  # the only slot its items may take, when min == max


@dataclass(frozen=True)
class ItemLimits:
    groups: tuple[str, ...]
    max_stack: int | None
    required_champion: str | None


@dataclass(frozen=True)
class ItemGroups:
    path: str
    content_version: str
    game_version: str
    groups: Mapping[str, Group]
    items: Mapping[str, ItemLimits]

    def matches_patch(self, patch: str) -> bool:
        return ".".join(patch.split(".")[:2]) == self.game_version


@dataclass(frozen=True)
class Violation:
    rule: str
    message: str
    items: tuple[str, ...]


@dataclass(frozen=True)
class LegalityReport:
    items: tuple[str, ...]
    violations: tuple[Violation, ...]
    notes: tuple[str, ...]
    label: Label
    source: str

    @property
    def legal(self) -> bool:
        return not self.violations


def _is_count(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _group_problems(key: str, group: Any) -> list[str]:
    where = f"groups.{key}"
    if not GROUP_KEY.fullmatch(key):
        return [f"{where}: key must be 8 lowercase hex digits"]
    if not isinstance(group, Mapping):
        return [f"{where} must be an object"]
    expected = {"entry", "group_id", *GROUP_INTEGERS}
    if set(group) != expected:
        return [f"{where} must have exactly {sorted(expected)}"]
    problems = []
    if group["entry"] is not None and not isinstance(group["entry"], str):
        problems.append(f"{where}.entry must be a string or null")
    if not isinstance(group["group_id"], str) or not group["group_id"]:
        problems.append(f"{where}.group_id must be a non-empty string")
    for field in GROUP_INTEGERS:
        if group[field] is not None and not _is_count(group[field]):
            problems.append(f"{where}.{field} must be a non-negative integer or null")
    return problems


def _item_problems(item_id: str, item: Any, groups: Mapping[str, Any]) -> list[str]:
    where = f"items.{item_id}"
    if not isinstance(item, Mapping):
        return [f"{where} must be an object"]
    expected = {"groups", "max_stack", "required_champion"}
    if set(item) != expected:
        return [f"{where} must have exactly {sorted(expected)}"]
    problems = []
    links = item["groups"]
    if not isinstance(links, list) or not all(isinstance(link, str) for link in links):
        problems.append(f"{where}.groups must be a list of group keys")
    else:
        unknown = sorted(set(links) - set(groups))
        if unknown:
            problems.append(f"{where}.groups links to unknown groups {unknown}")
    stack = item["max_stack"]
    if stack is not None and not (_is_count(stack) and stack >= 1):
        problems.append(f"{where}.max_stack must be a positive integer or null")
    champion = item["required_champion"]
    if champion is not None and (not isinstance(champion, str) or not champion):
        problems.append(f"{where}.required_champion must be a non-empty string or null")
    return problems


def item_groups_problems(
    document: Any, *, patch: str | None = None, item_ids: Collection[str] | None = None
) -> list[str]:
    """Every reason why ``document`` is not a usable ``item-groups.json``."""
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
    if not isinstance(document.get("bin_sha256"), str) or not SHA256.fullmatch(
        document["bin_sha256"]
    ):
        problems.append("bin_sha256 must be a SHA-256 hex digest")
    game_version = document.get("game_version")
    if not isinstance(game_version, str) or not GAME_VERSION.fullmatch(game_version):
        problems.append("game_version must be <major>.<minor>")
    elif patch is not None and not patch.startswith(f"{game_version}."):
        problems.append(f"client {game_version} data for snapshot {patch}; {REGENERATE}")
    groups = document.get("groups")
    items = document.get("items")
    failures = document.get("failures")
    if not isinstance(groups, Mapping):
        return [*problems, "groups must be an object"]
    if not isinstance(items, Mapping):
        return [*problems, "items must be an object"]
    if not isinstance(failures, Mapping) or not all(
        isinstance(reason, str) for reason in failures.values()
    ):
        return [*problems, "failures must map item ids to reasons"]
    for key, group in groups.items():
        problems += _group_problems(str(key), group)
    for item_id, item in items.items():
        problems += _item_problems(str(item_id), item, groups)
    used = {
        link
        for item in items.values()
        if isinstance(item, Mapping)
        for link in item.get("groups") or ()
    }
    unused = sorted(set(groups) - used)
    if unused:
        problems.append(f"groups no item links to: {unused}")
    if item_ids is not None:
        covered = set(items) | set(failures)
        missing = sorted(set(item_ids) - covered)
        extra = sorted(covered - set(item_ids))
        if missing:
            problems.append(f"items of the catalog without group data: {missing}; {REGENERATE}")
        if extra:
            problems.append(f"items that are not in the catalog: {extra}; {REGENERATE}")
    return problems


def parse_item_groups(document: Any, path: str = ITEM_GROUPS_PATH.as_posix()) -> ItemGroups:
    problems = item_groups_problems(document)
    if problems:
        raise StatsError(f"{path}: {problems[0]}")
    groups: dict[str, Group] = {}
    for key, group in document["groups"].items():
        low, high = group["inventory_slot_min"], group["inventory_slot_max"]
        groups[key] = Group(
            key=key,
            name=group["entry"] or group["group_id"],
            max_ownable=group["max_ownable"],
            slot=low if low is not None and low == high else None,
        )
    items = {
        item_id: ItemLimits(tuple(item["groups"]), item["max_stack"], item["required_champion"])
        for item_id, item in document["items"].items()
    }
    return ItemGroups(path, document["content_version"], document["game_version"], groups, items)


def load_item_groups(root: Path) -> ItemGroups | None:
    """The published item groups, or ``None`` when the file is absent."""
    path = root / ITEM_GROUPS_PATH
    if not path.is_file():
        return None
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise StatsError(f"{ITEM_GROUPS_PATH.as_posix()}: unreadable: {exc}") from exc
    return parse_item_groups(document)


def _slots(item_id: str, count: int, limits: ItemLimits, notes: list[str]) -> int:
    stack = limits.max_stack
    if stack is None:
        if count > 1:
            notes.append(
                f"{item_id}: the client gives no maxStack; each copy is counted in its own slot"
            )
        return count
    return math.ceil(count / stack)


def check_build(
    item_ids: Sequence[str],
    data: ItemGroups,
    *,
    patch: str,
    champion: str | None = None,
) -> LegalityReport:
    """Whether one inventory may hold ``item_ids`` at the same time.

    Rules (build-legality.md): every group caps its items at ``max_ownable``;
    items of a slot-pinned group (trinkets) share that slot; the other items fit
    in ``INVENTORY_SLOTS`` slots, identical items stacking up to ``max_stack``;
    an item with a required champion is only for that champion.
    """
    notes: list[str] = []
    violations: list[Violation] = []
    counts = Counter(str(item_id) for item_id in item_ids)
    unknown = sorted(item_id for item_id in counts if item_id not in data.items)
    if unknown:
        violations.append(
            Violation("no_group_data", f"items without group data: {unknown}", tuple(unknown))
        )
    known = {item_id: count for item_id, count in counts.items() if item_id in data.items}
    # A group counts held stacks: five Health Potions (maxStack 5) are one.
    stacks = {
        item_id: _slots(item_id, count, data.items[item_id], notes)
        for item_id, count in sorted(known.items())
    }
    members: dict[str, list[str]] = {}
    for item_id, used in stacks.items():
        for key in data.items[item_id].groups:
            members.setdefault(key, []).extend([item_id] * used)
    for key, held in sorted(members.items()):
        group = data.groups[key]
        if group.max_ownable is not None and len(held) > group.max_ownable:
            violations.append(
                Violation(
                    "group_limit",
                    f"group {group.name} allows {group.max_ownable} at once; "
                    f"the build holds {len(held)}: {sorted(held)}",
                    tuple(sorted(set(held))),
                )
            )
    pinned: dict[int, list[str]] = {}
    ordinary = 0
    for item_id in sorted(known):
        limits = data.items[item_id]
        slots = {data.groups[key].slot for key in limits.groups} - {None}
        if len(slots) > 1:
            violations.append(
                Violation(
                    "slot", f"{item_id} is pinned to several slots {sorted(slots)}", (item_id,)
                )
            )
            continue
        used = stacks[item_id]
        if slots:
            pinned.setdefault(slots.pop(), []).extend([item_id] * used)
        else:
            ordinary += used
    if ordinary > INVENTORY_SLOTS:
        violations.append(
            Violation(
                "slots",
                f"the items need {ordinary} slots; the inventory has {INVENTORY_SLOTS}",
                tuple(sorted(known)),
            )
        )
    for slot, held in sorted(pinned.items()):
        if len(held) > 1:
            violations.append(
                Violation(
                    "slots",
                    f"slot {slot} holds one item; the build puts {len(held)} there: {sorted(held)}",
                    tuple(sorted(set(held))),
                )
            )
    for item_id in sorted(known):
        required = data.items[item_id].required_champion
        if required is None:
            continue
        if champion is None:
            notes.append(f"{item_id} is only for {required}; the holder is not known")
        elif champion.lower() != required.lower():
            violations.append(
                Violation(
                    "champion", f"{item_id} is only for {required}, not {champion}", (item_id,)
                )
            )
    label = Label.DERIVED if data.matches_patch(patch) else Label.PENDING
    if label is Label.PENDING:
        notes.append(f"item groups are from client {data.game_version}, the snapshot is {patch}")
    return LegalityReport(
        items=tuple(str(item_id) for item_id in item_ids),
        violations=tuple(violations),
        notes=tuple(notes),
        label=label,
        source=f"{data.path} ({data.content_version}); rule: {RULE_PATH}",
    )
