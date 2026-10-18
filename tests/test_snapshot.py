"""Tests for snapshot building, idempotency and rollback."""

import hashlib
import json
import os
import time
from pathlib import Path

import pytest

from lol_knowledge.errors import NetworkError, PayloadError, SnapshotError
from lol_knowledge.snapshot import build_snapshot

PATCH = "16.20.1"
EXPECTED_FILES = {
    "champion-index.json",
    "items.json",
    "runes.json",
    "champions/Aatrox.json",
    "champions/Zaahen.json",
}


def read_manifest(data_dir: Path) -> dict:
    return json.loads((data_dir / "current" / "manifest.json").read_text(encoding="utf-8"))


def test_build_snapshot_writes_expected_files(tmp_path: Path, fake_source) -> None:
    result = build_snapshot(tmp_path, client=fake_source.client())

    assert result.changed is True
    assert result.patch == PATCH
    assert result.file_count == len(EXPECTED_FILES)

    current = tmp_path / "current"
    for relative in EXPECTED_FILES:
        assert (current / relative).is_file(), relative
    assert (current / "manifest.json").is_file()


def test_manifest_records_patch_checksums_and_sizes(tmp_path: Path, fake_source) -> None:
    build_snapshot(tmp_path, client=fake_source.client())

    manifest = read_manifest(tmp_path)
    assert manifest["schema_version"] == 1
    assert manifest["patch"] == PATCH
    assert manifest["locale"] == "es_ES"
    assert manifest["source"] == "https://ddragon.example"
    assert manifest["fetched_at"].endswith("Z")
    assert set(manifest["files"]) == EXPECTED_FILES

    current = tmp_path / "current"
    for relative, record in manifest["files"].items():
        content = (current / relative).read_bytes()
        assert record["bytes"] == len(content)
        assert record["sha256"] == hashlib.sha256(content).hexdigest()


def test_champion_index_is_a_compact_projection(tmp_path: Path, fake_source) -> None:
    build_snapshot(tmp_path, client=fake_source.client())

    index = json.loads((tmp_path / "current" / "champion-index.json").read_text("utf-8"))
    assert [entry["id"] for entry in index] == ["Aatrox", "Zaahen"]
    assert set(index[0]) == {"id", "key", "name", "title", "tags"}


def test_snapshot_text_is_utf8_without_ascii_escapes(tmp_path: Path, fake_source) -> None:
    build_snapshot(tmp_path, client=fake_source.client())

    content = (tmp_path / "current" / "champions" / "Zaahen.json").read_text("utf-8")
    assert "Impertérrito" in content
    assert "\\u00e9" not in content


def test_second_build_reports_unchanged_and_rewrites_nothing(tmp_path: Path, fake_source) -> None:
    build_snapshot(tmp_path, client=fake_source.client())
    manifest_path = tmp_path / "current" / "manifest.json"
    before_bytes = manifest_path.read_bytes()
    before_mtime = manifest_path.stat().st_mtime_ns
    time.sleep(0.05)

    result = build_snapshot(tmp_path, client=fake_source.client())

    assert result.changed is False
    assert result.file_count == len(EXPECTED_FILES)
    assert manifest_path.read_bytes() == before_bytes
    assert manifest_path.stat().st_mtime_ns == before_mtime


def test_download_failure_keeps_previous_snapshot(tmp_path: Path, fake_source) -> None:
    build_snapshot(tmp_path, client=fake_source.client())
    before = read_manifest(tmp_path)
    fake_source.failures[fake_source.url("champion/Zaahen.json")] = NetworkError("unreachable")

    with pytest.raises(NetworkError):
        build_snapshot(tmp_path, client=fake_source.client())

    assert read_manifest(tmp_path) == before
    assert not (tmp_path / ".staging").exists()


def test_invalid_champion_data_keeps_previous_snapshot(tmp_path: Path, fake_source) -> None:
    build_snapshot(tmp_path, client=fake_source.client())
    before = read_manifest(tmp_path)
    del fake_source.champions["Zaahen"]["stats"]

    with pytest.raises(PayloadError):
        build_snapshot(tmp_path, client=fake_source.client())

    assert read_manifest(tmp_path) == before
    assert not (tmp_path / ".staging").exists()


def test_invalid_items_are_rejected(tmp_path: Path, fake_source) -> None:
    fake_source.items["1001"]["gold"]["total"] = -1

    with pytest.raises(PayloadError):
        build_snapshot(tmp_path, client=fake_source.client())

    assert not (tmp_path / "current").exists()


def test_item_with_non_string_name_is_rejected(tmp_path: Path, fake_source) -> None:
    fake_source.items["1001"]["name"] = 5

    with pytest.raises(PayloadError):
        build_snapshot(tmp_path, client=fake_source.client())


def test_item_with_empty_name_is_kept_as_official_data(tmp_path: Path, fake_source) -> None:
    fake_source.items["2008"] = {
        "name": "",
        "description": "",
        "gold": {"total": 60, "purchasable": False},
        "maps": {"11": False},
    }

    build_snapshot(tmp_path, client=fake_source.client())

    items = json.loads((tmp_path / "current" / "items.json").read_text("utf-8"))
    assert items["2008"]["name"] == ""


def test_removed_champion_disappears_from_snapshot(tmp_path: Path, fake_source) -> None:
    build_snapshot(tmp_path, client=fake_source.client())
    del fake_source.summary["Zaahen"]
    del fake_source.champions["Zaahen"]

    result = build_snapshot(tmp_path, client=fake_source.client())

    assert result.changed is True
    assert not (tmp_path / "current" / "champions" / "Zaahen.json").exists()


def test_publish_failure_restores_previous_snapshot(
    tmp_path: Path, fake_source, monkeypatch: pytest.MonkeyPatch
) -> None:
    build_snapshot(tmp_path, client=fake_source.client())
    before = read_manifest(tmp_path)
    real_replace = os.replace

    def failing_replace(source: str, destination: str) -> None:
        if Path(source).name == ".staging":
            raise OSError("simulated rename failure")
        real_replace(source, destination)

    monkeypatch.setattr("lol_knowledge.snapshot.os.replace", failing_replace)
    fake_source.champions["Aatrox"]["name"] = "Aatrox modificado"

    with pytest.raises(SnapshotError):
        build_snapshot(tmp_path, client=fake_source.client())

    assert read_manifest(tmp_path) == before
    assert (tmp_path / "current" / "champions" / "Aatrox.json").is_file()
    assert not (tmp_path / ".staging").exists()
    assert not (tmp_path / ".backup").exists()
