"""Tests for snapshot integrity and knowledge base validation."""

import hashlib
import json
from pathlib import Path

import pytest

from lol_knowledge.cli import main
from lol_knowledge.snapshot import build_snapshot
from lol_knowledge.validate import validate_project


def make_project(tmp_path: Path, fake_source) -> Path:
    root = tmp_path / "project"
    build_snapshot(root / "data", client=fake_source.client())
    return root


def current(root: Path) -> Path:
    return root / "data" / "current"


def refresh_manifest(root: Path) -> None:
    base = current(root)
    files = {}
    for path in sorted(base.rglob("*")):
        if path.is_file() and path.name != "manifest.json":
            content = path.read_bytes()
            files[path.relative_to(base).as_posix()] = {
                "sha256": hashlib.sha256(content).hexdigest(),
                "bytes": len(content),
            }
    manifest_path = base / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["files"] = files
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")


def write_kb(root: Path, relative: str, text: str) -> Path:
    path = root / "lol-knowledge" / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def messages(report) -> str:
    return "\n".join(str(violation) for violation in report.violations)


def test_valid_project_passes(tmp_path: Path, fake_source) -> None:
    report = validate_project(make_project(tmp_path, fake_source))

    assert report.ok, messages(report)
    assert report.checked_files >= 5
    assert any("link and reference checks were skipped" in note for note in report.skipped)


def test_detects_sha256_mismatch(tmp_path: Path, fake_source) -> None:
    root = make_project(tmp_path, fake_source)
    champion = current(root) / "champions" / "Aatrox.json"
    champion.write_bytes(champion.read_bytes() + b" ")

    report = validate_project(root)

    assert not report.ok
    assert "sha256 mismatch" in messages(report)


def test_detects_missing_listed_file(tmp_path: Path, fake_source) -> None:
    root = make_project(tmp_path, fake_source)
    (current(root) / "items.json").unlink()

    report = validate_project(root)

    assert "listed in manifest.json but missing on disk" in messages(report)


def test_detects_unlisted_file(tmp_path: Path, fake_source) -> None:
    root = make_project(tmp_path, fake_source)
    (current(root) / "champions" / "Ghost.json").write_text("{}", encoding="utf-8")

    report = validate_project(root)

    assert "file is not listed in manifest.json" in messages(report)


def test_detects_invalid_manifest_patch(tmp_path: Path, fake_source) -> None:
    root = make_project(tmp_path, fake_source)
    manifest_path = current(root) / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["patch"] = "latest"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    report = validate_project(root)

    assert "patch must look like 16.20.1" in messages(report)


def test_detects_manifest_path_escape(tmp_path: Path, fake_source) -> None:
    root = make_project(tmp_path, fake_source)
    manifest_path = current(root) / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["files"]["../escape.json"] = {"sha256": "0" * 64, "bytes": 1}
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    report = validate_project(root)

    assert "path escapes the snapshot directory" in messages(report)


def test_detects_champion_without_four_spells(tmp_path: Path, fake_source) -> None:
    root = make_project(tmp_path, fake_source)
    champion_path = current(root) / "champions" / "Aatrox.json"
    champion = json.loads(champion_path.read_text(encoding="utf-8"))
    champion["spells"] = champion["spells"][:3]
    champion_path.write_text(json.dumps(champion), encoding="utf-8")
    refresh_manifest(root)

    report = validate_project(root)

    assert "at least 4 entries" in messages(report)


def test_detects_non_numeric_stat(tmp_path: Path, fake_source) -> None:
    root = make_project(tmp_path, fake_source)
    champion_path = current(root) / "champions" / "Aatrox.json"
    champion = json.loads(champion_path.read_text(encoding="utf-8"))
    champion["stats"]["hp"] = "650"
    champion_path.write_text(json.dumps(champion), encoding="utf-8")
    refresh_manifest(root)

    report = validate_project(root)

    assert "hp must be a number" in messages(report)


def test_detects_champion_file_missing_from_index(tmp_path: Path, fake_source) -> None:
    root = make_project(tmp_path, fake_source)
    (current(root) / "champions" / "Ghost.json").write_text("{}", encoding="utf-8")
    refresh_manifest(root)

    report = validate_project(root)

    assert "is not listed in champion-index.json" in messages(report)


def test_detects_duplicate_index_entry(tmp_path: Path, fake_source) -> None:
    root = make_project(tmp_path, fake_source)
    index_path = current(root) / "champion-index.json"
    index = json.loads(index_path.read_text(encoding="utf-8"))
    index.append(dict(index[0]))
    index_path.write_text(json.dumps(index), encoding="utf-8")
    refresh_manifest(root)

    report = validate_project(root)

    assert "duplicate champion id" in messages(report)


def test_detects_invalid_gold_total(tmp_path: Path, fake_source) -> None:
    root = make_project(tmp_path, fake_source)
    items_path = current(root) / "items.json"
    items = json.loads(items_path.read_text(encoding="utf-8"))
    items["1001"]["gold"]["total"] = "300"
    items_path.write_text(json.dumps(items), encoding="utf-8")
    refresh_manifest(root)

    report = validate_project(root)

    assert "gold.total must be a non-negative integer" in messages(report)


def test_detects_invalid_rune_tree(tmp_path: Path, fake_source) -> None:
    root = make_project(tmp_path, fake_source)
    runes_path = current(root) / "runes.json"
    runes = json.loads(runes_path.read_text(encoding="utf-8"))
    runes[0]["slots"] = []
    runes_path.write_text(json.dumps(runes), encoding="utf-8")
    refresh_manifest(root)

    report = validate_project(root)

    assert "slots must be a non-empty list" in messages(report)


def test_detects_broken_link(tmp_path: Path, fake_source) -> None:
    root = make_project(tmp_path, fake_source)
    write_kb(root, "champions/Zaahen/overview.md", "[falta](missing.md)\n")

    report = validate_project(root)

    assert "broken link: missing.md" in messages(report)


def test_accepts_existing_link(tmp_path: Path, fake_source) -> None:
    root = make_project(tmp_path, fake_source)
    write_kb(root, "champions/Zaahen/overview.md", "[fuente](sources.md)\n")
    write_kb(root, "champions/Zaahen/sources.md", "# Fuentes\n")

    report = validate_project(root)

    assert report.ok, messages(report)


def test_detects_link_escaping_the_repository(tmp_path: Path, fake_source) -> None:
    root = make_project(tmp_path, fake_source)
    write_kb(root, "champions/Zaahen/overview.md", "[fuera](../../../../outside.md)\n")

    report = validate_project(root)

    assert "link escapes the repository" in messages(report)


def test_detects_unknown_item_reference(tmp_path: Path, fake_source) -> None:
    root = make_project(tmp_path, fake_source)
    write_kb(root, "build-theory/example.md", "Objeto `data:item:9999`.\n")

    report = validate_project(root)

    assert "unknown item reference data:item:9999" in messages(report)


def test_accepts_known_data_references(tmp_path: Path, fake_source) -> None:
    root = make_project(tmp_path, fake_source)
    write_kb(
        root,
        "build-theory/example.md",
        "`data:item:1001` `data:champion:Aatrox` `data:rune:8005`\n",
    )

    report = validate_project(root)

    assert report.ok, messages(report)


def test_detects_unknown_champion_directory(tmp_path: Path, fake_source) -> None:
    root = make_project(tmp_path, fake_source)
    write_kb(root, "champions/ghost/overview.md", "# Fantasma\n")

    report = validate_project(root)

    assert "does not match any published champion id" in messages(report)


def test_detects_invalid_json(tmp_path: Path, fake_source) -> None:
    root = make_project(tmp_path, fake_source)
    (current(root) / "champions" / "Aatrox.json").write_text("{broken", encoding="utf-8")

    report = validate_project(root)

    assert "not valid JSON" in messages(report)


def test_detects_unexpected_file_inside_champions(tmp_path: Path, fake_source) -> None:
    root = make_project(tmp_path, fake_source)
    (current(root) / "champions" / "notes.txt").write_text("hola", encoding="utf-8")

    report = validate_project(root)

    assert "unexpected file inside champions/" in messages(report)


def test_detects_unexpected_directory_inside_champions(tmp_path: Path, fake_source) -> None:
    root = make_project(tmp_path, fake_source)
    (current(root) / "champions" / "archive").mkdir()

    report = validate_project(root)

    assert "unexpected directory inside champions/" in messages(report)


def test_detects_untraceable_number_in_champion_doc(tmp_path: Path, fake_source) -> None:
    root = make_project(tmp_path, fake_source)
    write_kb(root, "champions/Aatrox/overview.md", "| Vida | `9999` |\n")

    report = validate_project(root)

    assert "number 9999 does not appear" in messages(report)


def test_accepts_traceable_numbers_in_champion_doc(tmp_path: Path, fake_source) -> None:
    root = make_project(tmp_path, fake_source)
    write_kb(root, "champions/Aatrox/overview.md", "| Vida | `650` |\n")

    report = validate_project(root)

    assert report.ok, messages(report)


def test_prose_numbers_in_champion_doc_are_not_checked(tmp_path: Path, fake_source) -> None:
    root = make_project(tmp_path, fake_source)
    write_kb(
        root,
        "champions/Aatrox/overview.md",
        "Hay 173 campeones y el parche es 16.20.1.\n",
    )

    report = validate_project(root)

    assert report.ok, messages(report)


def test_cli_validate_returns_zero_for_a_valid_project(
    tmp_path: Path, fake_source, capsys: pytest.CaptureFixture[str]
) -> None:
    root = make_project(tmp_path, fake_source)

    assert main(["validate", "--root", str(root)]) == 0
    assert "valid:" in capsys.readouterr().out


def test_cli_validate_returns_one_for_violations(
    tmp_path: Path, fake_source, capsys: pytest.CaptureFixture[str]
) -> None:
    root = make_project(tmp_path, fake_source)
    (current(root) / "items.json").unlink()

    assert main(["validate", "--root", str(root)]) == 1
    assert "invalid:" in capsys.readouterr().err


def test_cli_validate_returns_two_for_a_missing_root(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["validate", "--root", str(tmp_path / "missing")]) == 2
    assert "is not a directory" in capsys.readouterr().err
