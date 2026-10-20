"""Validate the published snapshot and the knowledge base structure."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .ddragon import validate_champion_id
from .errors import PayloadError
from .objects.validate import validate_object_catalog
from .snapshot import (
    CHAMPION_INDEX_FILENAME,
    CHAMPIONS_DIRNAME,
    ITEMS_FILENAME,
    MANIFEST_FILENAME,
    RUNES_FILENAME,
    validate_champion_payload,
    validate_item_payload,
    validate_runes_payload,
)

SUPPORTED_SCHEMA_VERSIONS = frozenset({1})
KB_DIRNAME = "lol-knowledge"

PATCH_PATTERN = re.compile(r"\d+\.\d+\.\d+")
TIMESTAMP_PATTERN = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z")
SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")
LINK_PATTERN = re.compile(r"\[[^\]]*\]\(([^)]+)\)")
DATA_REF_PATTERN = re.compile(r"data:(item|rune|champion):([A-Za-z0-9_-]+)")
NUMERIC_CODE_SPAN_PATTERN = re.compile(r"`([^`\n]+)`")
NUMBER_PATTERN = re.compile(r"\d+(?:\.\d+)?")
EXTERNAL_LINK_PREFIXES = ("http://", "https://", "mailto:", "#")
CHAMPION_DOC_FILENAMES = ("overview.md", "abilities.md")


@dataclass(frozen=True)
class Violation:
    """One concrete problem found in the repository."""

    path: str
    message: str

    def __str__(self) -> str:
        return f"{self.path}: {self.message}"


@dataclass(frozen=True)
class ValidationReport:
    """Result of validating a project tree."""

    checked_files: int
    violations: tuple[Violation, ...]
    skipped: tuple[str, ...] = ()

    @property
    def ok(self) -> bool:
        return not self.violations


def validate_project(root: Path) -> ValidationReport:
    """Validate the snapshot and the knowledge base under ``root``."""
    return _Validator(root).run()


class _Validator:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.root_resolved = root.resolve()
        self.current = root / "data" / "current"
        self.violations: list[Violation] = []
        self.skipped: list[str] = []
        self.checked_files = 0
        self.champion_ids: set[str] = set()
        self.champion_numbers: dict[str, set[str]] = {}
        self.item_ids: set[str] = set()
        self.rune_ids: set[int] = set()

    def run(self) -> ValidationReport:
        manifest = self._check_manifest()
        if manifest is not None:
            self._check_listed_files(manifest)
        self._check_champions()
        self._check_items()
        self._check_runes()
        self._check_knowledge_base()
        self._check_object_catalog()
        return ValidationReport(
            checked_files=self.checked_files,
            violations=tuple(self.violations),
            skipped=tuple(self.skipped),
        )

    def fail(self, path: Path, message: str) -> None:
        self.violations.append(Violation(self._display(path), message))

    def _display(self, path: Path) -> str:
        try:
            return path.resolve().relative_to(self.root_resolved).as_posix()
        except ValueError:
            return str(path)

    def _read_json(self, path: Path) -> Any | None:
        if not path.is_file():
            self.fail(path, "file not found")
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except UnicodeDecodeError as exc:
            self.fail(path, f"not valid UTF-8: {exc.reason}")
            return None
        except json.JSONDecodeError as exc:
            self.fail(path, f"not valid JSON: {exc.msg}")
            return None

    def _check_manifest(self) -> Mapping[str, Any] | None:
        path = self.current / MANIFEST_FILENAME
        manifest = self._read_json(path)
        if manifest is None:
            return None
        if not isinstance(manifest, Mapping):
            self.fail(path, "must be a JSON object")
            return None

        if manifest.get("schema_version") not in SUPPORTED_SCHEMA_VERSIONS:
            self.fail(path, f"unsupported schema_version {manifest.get('schema_version')!r}")

        patch = manifest.get("patch")
        if not isinstance(patch, str) or PATCH_PATTERN.fullmatch(patch) is None:
            self.fail(path, "patch must look like 16.20.1")

        locale = manifest.get("locale")
        if not isinstance(locale, str) or not locale:
            self.fail(path, "locale must be a non-empty string")

        source = manifest.get("source")
        if not isinstance(source, str) or not source.startswith("https://"):
            self.fail(path, "source must be an https URL")

        fetched_at = manifest.get("fetched_at")
        if not isinstance(fetched_at, str) or TIMESTAMP_PATTERN.fullmatch(fetched_at) is None:
            self.fail(path, "fetched_at must be a UTC timestamp such as 2026-10-18T10:25:29Z")

        files = manifest.get("files")
        if not isinstance(files, Mapping) or not files:
            self.fail(path, "files must be a non-empty object")

        return manifest

    def _check_listed_files(self, manifest: Mapping[str, Any]) -> None:
        listed = manifest.get("files")
        if not isinstance(listed, Mapping) or not listed:
            return

        actual = {
            path.relative_to(self.current).as_posix()
            for path in self.current.rglob("*")
            if path.is_file() and path.relative_to(self.current).as_posix() != MANIFEST_FILENAME
        }

        for relative, record in sorted(listed.items()):
            if not isinstance(relative, str):
                self.fail(self.current, f"manifest file key {relative!r} must be a string")
                continue

            path = self.current / relative
            if not path.resolve().is_relative_to(self.current.resolve()):
                self.fail(path, "path escapes the snapshot directory")
                continue

            self.checked_files += 1
            if not isinstance(record, Mapping):
                self.fail(path, "manifest entry must be an object")
                continue
            if not path.is_file():
                self.fail(path, "listed in manifest.json but missing on disk")
                continue

            content = path.read_bytes()
            expected_bytes = record.get("bytes")
            if (
                not isinstance(expected_bytes, int)
                or isinstance(expected_bytes, bool)
                or expected_bytes != len(content)
            ):
                self.fail(
                    path,
                    f"size mismatch: manifest says {expected_bytes!r}, file has {len(content)}",
                )

            expected_hash = record.get("sha256")
            if (
                not isinstance(expected_hash, str)
                or SHA256_PATTERN.fullmatch(expected_hash) is None
            ):
                self.fail(path, "manifest sha256 must be 64 lowercase hex characters")
            elif hashlib.sha256(content).hexdigest() != expected_hash:
                self.fail(path, "sha256 mismatch")

        for relative in sorted(actual - set(listed)):
            self.fail(self.current / relative, "file is not listed in manifest.json")

    def _check_champions(self) -> None:
        path = self.current / CHAMPION_INDEX_FILENAME
        index = self._read_json(path)
        if index is None:
            return
        if not isinstance(index, list) or not index:
            self.fail(path, "must be a non-empty list")
            return

        for position, entry in enumerate(index):
            if not isinstance(entry, Mapping):
                self.fail(path, f"[{position}] must be an object")
                continue

            try:
                champion_id = validate_champion_id(entry.get("id"))
            except PayloadError as exc:
                self.fail(path, f"[{position}] {exc}")
                continue

            if champion_id in self.champion_ids:
                self.fail(path, f"duplicate champion id {champion_id!r}")
                continue
            self.champion_ids.add(champion_id)

            champion_path = self.current / CHAMPIONS_DIRNAME / f"{champion_id}.json"
            payload = self._read_json(champion_path)
            if payload is None:
                continue
            if not isinstance(payload, Mapping):
                self.fail(champion_path, "must be a JSON object")
                continue

            try:
                validate_champion_payload(champion_id, payload)
            except PayloadError as exc:
                self.fail(champion_path, str(exc))

            self.champion_numbers[champion_id] = numeric_tokens(payload)

            for field in ("key", "name"):
                if entry.get(field) != payload.get(field):
                    self.fail(
                        champion_path,
                        f"{field} does not match {CHAMPION_INDEX_FILENAME}",
                    )

        champions_dir = self.current / CHAMPIONS_DIRNAME
        if not champions_dir.is_dir():
            self.fail(champions_dir, "missing champions directory")
            return

        for child in sorted(champions_dir.iterdir()):
            if child.is_dir():
                self.fail(child, "unexpected directory inside champions/")
            elif child.suffix != ".json":
                self.fail(child, "unexpected file inside champions/")
            elif child.stem not in self.champion_ids:
                self.fail(
                    child,
                    f"champion {child.stem!r} is not listed in {CHAMPION_INDEX_FILENAME}",
                )

    def _check_items(self) -> None:
        path = self.current / ITEMS_FILENAME
        items = self._read_json(path)
        if items is None:
            return
        if not isinstance(items, Mapping) or not items:
            self.fail(path, "must be a non-empty object")
            return

        for item_id, item in sorted(items.items()):
            self.item_ids.add(str(item_id))
            try:
                validate_item_payload(str(item_id), item)
            except PayloadError as exc:
                self.fail(path, str(exc))

    def _check_runes(self) -> None:
        path = self.current / RUNES_FILENAME
        runes = self._read_json(path)
        if runes is None:
            return

        try:
            validate_runes_payload(runes)
        except PayloadError as exc:
            self.fail(path, str(exc))
            return

        self.rune_ids.update(collect_rune_ids(runes))

    def _check_knowledge_base(self) -> None:
        kb_root = self.root / KB_DIRNAME
        if not kb_root.is_dir():
            self.skipped.append(
                f"{KB_DIRNAME}/ is not present; link and reference checks were skipped"
            )
            return

        for md_path in sorted(kb_root.rglob("*.md")):
            self.checked_files += 1
            try:
                text = md_path.read_text(encoding="utf-8")
            except UnicodeDecodeError as exc:
                self.fail(md_path, f"not valid UTF-8: {exc.reason}")
                continue
            self._check_links(md_path, text)
            self._check_data_refs(md_path, text)

        for champion_id, numbers in sorted(self.champion_numbers.items()):
            champion_dir = kb_root / CHAMPIONS_DIRNAME / champion_id
            if not champion_dir.is_dir():
                continue
            for filename in CHAMPION_DOC_FILENAMES:
                doc = champion_dir / filename
                if doc.is_file():
                    self._check_champion_numbers(doc, champion_id, numbers)

        champions_dir = kb_root / CHAMPIONS_DIRNAME
        if champions_dir.is_dir():
            for child in sorted(champions_dir.iterdir()):
                if child.is_dir() and child.name not in self.champion_ids:
                    self.fail(child, "champion directory does not match any published champion id")

    def _check_object_catalog(self) -> None:
        report = validate_object_catalog(self.root)
        self.checked_files += report.checked_files
        self.skipped.extend(report.skipped)
        for violation in report.violations:
            self.violations.append(Violation(violation.path, violation.message))

    def _check_links(self, md_path: Path, text: str) -> None:
        for match in LINK_PATTERN.finditer(text):
            target = match.group(1).strip()
            if not target or target.startswith(EXTERNAL_LINK_PREFIXES):
                continue

            target = target.split()[0].strip("<>")
            path_part = target.split("#", 1)[0]
            if not path_part:
                continue

            resolved = (md_path.parent / path_part).resolve()
            if not resolved.is_relative_to(self.root_resolved):
                self.fail(md_path, f"link escapes the repository: {target}")
            elif not resolved.exists():
                self.fail(md_path, f"broken link: {target}")

    def _check_data_refs(self, md_path: Path, text: str) -> None:
        for match in DATA_REF_PATTERN.finditer(text):
            kind, value = match.group(1), match.group(2)
            if kind == "item" and value not in self.item_ids:
                self.fail(md_path, f"unknown item reference data:item:{value}")
            elif kind == "champion" and value not in self.champion_ids:
                self.fail(md_path, f"unknown champion reference data:champion:{value}")
            elif kind == "rune" and (not value.isdigit() or int(value) not in self.rune_ids):
                self.fail(md_path, f"unknown rune reference data:rune:{value}")

    def _check_champion_numbers(self, path: Path, champion_id: str, numbers: set[str]) -> None:
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            return  # already reported by the Markdown scan

        for match in NUMERIC_CODE_SPAN_PATTERN.finditer(text):
            value = match.group(1).strip()
            if NUMBER_PATTERN.fullmatch(value) is None:
                continue
            if value not in numbers:
                self.fail(
                    path,
                    f"number {value} does not appear in data/current/champions/{champion_id}.json",
                )


def numeric_tokens(value: Any) -> set[str]:
    """Collect every number and numeric fragment so docs can be traced to data."""
    tokens: set[str] = set()

    def walk(node: Any) -> None:
        if isinstance(node, bool):
            return
        if isinstance(node, (int, float)):
            tokens.add(str(node))
            if isinstance(node, float) and node.is_integer():
                tokens.add(str(int(node)))
            return
        if isinstance(node, str):
            tokens.update(NUMBER_PATTERN.findall(node))
            return
        if isinstance(node, Mapping):
            for item in node.values():
                walk(item)
        elif isinstance(node, Sequence) and not isinstance(node, (str, bytes)):
            for item in node:
                walk(item)

    walk(value)
    return tokens


def collect_rune_ids(runes: Sequence[Any]) -> set[int]:
    """Return every rune id in a validated ``runesReforged`` document."""
    ids: set[int] = set()
    for tree in runes:
        for slot in tree.get("slots", []):
            for rune in slot.get("runes", []):
                rune_id = rune.get("id")
                if isinstance(rune_id, int) and not isinstance(rune_id, bool):
                    ids.add(rune_id)
    return ids
