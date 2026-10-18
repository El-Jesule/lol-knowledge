"""Build and publish a deterministic Data Dragon snapshot."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import shutil
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .ddragon import DataDragonClient, PatchPayload, validate_champion_id
from .errors import PayloadError, SnapshotError

LOGGER = logging.getLogger(__name__)

SNAPSHOT_SCHEMA_VERSION = 1
CURRENT_DIRNAME = "current"
STAGING_DIRNAME = ".staging"
BACKUP_DIRNAME = ".backup"
MANIFEST_FILENAME = "manifest.json"
CHAMPION_INDEX_FILENAME = "champion-index.json"
CHAMPIONS_DIRNAME = "champions"
ITEMS_FILENAME = "items.json"
RUNES_FILENAME = "runes.json"

REQUIRED_CHAMPION_STATS = (
    "hp",
    "hpperlevel",
    "movespeed",
    "armor",
    "attackdamage",
    "attackrange",
)
REQUIRED_SPELL_FIELDS = ("id", "name", "description", "tooltip", "cooldownBurn", "costBurn")
MINIMUM_SPELL_COUNT = 4


@dataclass(frozen=True)
class UpdateResult:
    """Outcome of one snapshot build. ``file_count`` excludes ``manifest.json``."""

    patch: str
    data_dir: Path
    file_count: int
    changed: bool


def build_snapshot(
    data_dir: Path,
    *,
    patch: str = "latest",
    client: DataDragonClient | None = None,
) -> UpdateResult:
    """Download, validate and publish a snapshot, keeping the previous one on failure."""
    client = client or DataDragonClient()
    resolved_patch = client.latest_patch() if patch == "latest" else patch
    payload = client.fetch_patch(resolved_patch)

    files = _snapshot_files(payload)
    data_file_count = len(files)
    fingerprint = _fingerprint(files)
    current = data_dir / CURRENT_DIRNAME
    existing = _read_manifest(current / MANIFEST_FILENAME)

    if _is_current(existing, payload.patch, payload.locale, fingerprint):
        LOGGER.info("patch %s is already current, nothing to write", payload.patch)
        return UpdateResult(payload.patch, data_dir, data_file_count, changed=False)

    manifest = {
        "schema_version": SNAPSHOT_SCHEMA_VERSION,
        "patch": payload.patch,
        "locale": payload.locale,
        "source": payload.source,
        "fetched_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "files": fingerprint,
    }
    # The manifest is written last so a partially staged snapshot is never
    # published as if it were complete.
    files[MANIFEST_FILENAME] = _dump_json(manifest)

    _publish(data_dir, files)
    LOGGER.info(
        "published patch %s with %d files into %s",
        payload.patch,
        len(files),
        data_dir,
    )
    return UpdateResult(payload.patch, data_dir, data_file_count, changed=True)


def _snapshot_files(payload: PatchPayload) -> dict[str, bytes]:
    files: dict[str, bytes] = {CHAMPION_INDEX_FILENAME: _dump_json(_champion_index(payload))}

    for champion in payload.champions:
        champion_id = validate_champion_id(champion.champion_id)
        validate_champion_payload(champion_id, champion.payload)
        files[f"{CHAMPIONS_DIRNAME}/{champion_id}.json"] = _dump_json(champion.payload)

    for item_id, item in payload.items.items():
        validate_item_payload(item_id, item)
    unnamed_items = sorted(
        item_id for item_id, item in payload.items.items() if item.get("name") == ""
    )
    if unnamed_items:
        # Data Dragon keeps legacy placeholder items (not purchasable, no map).
        # They are official data, so they are stored; the count stays visible.
        LOGGER.warning(
            "%d items have an empty name in patch %s (first: %s)",
            len(unnamed_items),
            payload.patch,
            unnamed_items[0],
        )
    files[ITEMS_FILENAME] = _dump_json(dict(payload.items))

    validate_runes_payload(payload.runes)
    files[RUNES_FILENAME] = _dump_json(list(payload.runes))

    return files


def _champion_index(payload: PatchPayload) -> list[dict[str, Any]]:
    index: list[dict[str, Any]] = []
    for champion_id, entry in sorted(payload.summary.items()):
        context = f"champion.json data[{champion_id!r}]"
        record = _require_mapping(entry, context)
        index.append(
            {
                "id": validate_champion_id(_require_str(record, "id", context)),
                "key": _require_str(record, "key", context),
                "name": _require_str(record, "name", context),
                "title": _require_str(record, "title", context),
                "tags": _require_str_list(record, "tags", context),
            }
        )
    return index


def validate_champion_payload(champion_id: str, payload: Mapping[str, Any]) -> None:
    context = f"champion {champion_id}"
    if _require_str(payload, "id", context) != champion_id:
        raise PayloadError(f"{context} declares a different id")

    _require_str(payload, "key", context)
    _require_str(payload, "name", context)
    _require_str(payload, "title", context)
    _require_str_list(payload, "tags", context)

    stats = _require_mapping(payload.get("stats"), f"{context}.stats")
    for stat in REQUIRED_CHAMPION_STATS:
        _require_positive_number(stats, stat, f"{context}.stats")

    passive = _require_mapping(payload.get("passive"), f"{context}.passive")
    _require_str(passive, "name", f"{context}.passive")

    spells = payload.get("spells")
    if not isinstance(spells, Sequence) or isinstance(spells, (str, bytes)):
        raise PayloadError(f"{context}.spells must be a list")
    if len(spells) < MINIMUM_SPELL_COUNT:
        raise PayloadError(f"{context}.spells must contain at least {MINIMUM_SPELL_COUNT} entries")

    for position, spell in enumerate(spells):
        spell_context = f"{context}.spells[{position}]"
        record = _require_mapping(spell, spell_context)
        for field in REQUIRED_SPELL_FIELDS:
            _require_str(record, field, spell_context)


def validate_item_payload(item_id: str, item: Mapping[str, Any]) -> None:
    context = f"item {item_id}"
    record = _require_mapping(item, context)
    if not isinstance(record.get("name"), str):
        # Official data contains legacy placeholders with an empty name.
        raise PayloadError(f"{context}.name must be a string")
    gold = _require_mapping(record.get("gold"), f"{context}.gold")
    total = gold.get("total")
    if isinstance(total, bool) or not isinstance(total, int) or total < 0:
        raise PayloadError(f"{context}.gold.total must be a non-negative integer")
    _require_mapping(record.get("maps"), f"{context}.maps")


def validate_runes_payload(runes: Sequence[Any]) -> None:
    if not isinstance(runes, Sequence) or isinstance(runes, (str, bytes)) or not runes:
        raise PayloadError("runes must be a non-empty list of rune trees")

    for position, tree in enumerate(runes):
        context = f"runes[{position}]"
        record = _require_mapping(tree, context)
        _require_str(record, "key", context)
        _require_str(record, "name", context)
        if not isinstance(record.get("id"), int) or isinstance(record.get("id"), bool):
            raise PayloadError(f"{context}.id must be an integer")

        slots = record.get("slots")
        if not isinstance(slots, Sequence) or isinstance(slots, (str, bytes)) or not slots:
            raise PayloadError(f"{context}.slots must be a non-empty list")

        for slot_position, slot in enumerate(slots):
            slot_context = f"{context}.slots[{slot_position}]"
            slot_record = _require_mapping(slot, slot_context)
            rune_entries = slot_record.get("runes")
            if (
                not isinstance(rune_entries, Sequence)
                or isinstance(rune_entries, (str, bytes))
                or not rune_entries
            ):
                raise PayloadError(f"{slot_context}.runes must be a non-empty list")


def _require_mapping(value: Any, context: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise PayloadError(f"{context} must be an object")
    return value


def _require_str(record: Mapping[str, Any], key: str, context: str) -> str:
    value = record.get(key)
    if not isinstance(value, str) or not value.strip():
        raise PayloadError(f"{context}.{key} must be a non-empty string")
    return value


def _require_str_list(record: Mapping[str, Any], key: str, context: str) -> list[str]:
    value = record.get(key)
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)) or not value:
        raise PayloadError(f"{context}.{key} must be a non-empty list of strings")
    if any(not isinstance(item, str) or not item for item in value):
        raise PayloadError(f"{context}.{key} must contain non-empty strings only")
    return list(value)


def _require_positive_number(record: Mapping[str, Any], key: str, context: str) -> float:
    value = record.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise PayloadError(f"{context}.{key} must be a number")
    if value <= 0:
        raise PayloadError(f"{context}.{key} must be positive")
    return float(value)


def _dump_json(value: Any) -> bytes:
    """Serialize deterministically so identical data yields identical bytes."""
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _fingerprint(files: Mapping[str, bytes]) -> dict[str, dict[str, Any]]:
    return {
        relative: {"sha256": hashlib.sha256(content).hexdigest(), "bytes": len(content)}
        for relative, content in sorted(files.items())
    }


def _read_manifest(path: Path) -> Mapping[str, Any] | None:
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        LOGGER.warning("ignoring unreadable manifest %s: %s", path, exc)
        return None
    return payload if isinstance(payload, Mapping) else None


def _is_current(
    manifest: Mapping[str, Any] | None,
    patch: str,
    locale: str,
    fingerprint: Mapping[str, Any],
) -> bool:
    if manifest is None:
        return False
    return (
        manifest.get("schema_version") == SNAPSHOT_SCHEMA_VERSION
        and manifest.get("patch") == patch
        and manifest.get("locale") == locale
        and manifest.get("files") == fingerprint
    )


def _publish(data_dir: Path, files: Mapping[str, bytes]) -> None:
    staging = data_dir / STAGING_DIRNAME
    current = data_dir / CURRENT_DIRNAME
    backup = data_dir / BACKUP_DIRNAME

    try:
        if staging.exists():
            shutil.rmtree(staging)

        staging_root = staging.resolve()
        for relative, content in sorted(files.items()):
            target = (staging / relative).resolve()
            if not target.is_relative_to(staging_root):
                # Defence in depth: no external value may choose a path outside staging,
                # even if an earlier validation is ever relaxed.
                raise SnapshotError(f"refusing to write {relative!r} outside {staging}")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)

        _swap(current, staging, backup)
    except OSError as exc:
        raise SnapshotError(f"cannot publish snapshot in {data_dir}: {exc}") from exc
    finally:
        if staging.exists():
            shutil.rmtree(staging, ignore_errors=True)


def _swap(current: Path, staging: Path, backup: Path) -> None:
    if backup.exists():
        shutil.rmtree(backup)
    if current.exists():
        os.replace(current, backup)

    try:
        os.replace(staging, current)
    except OSError:
        if backup.exists() and not current.exists():
            os.replace(backup, current)
        raise

    if backup.exists():
        shutil.rmtree(backup)
