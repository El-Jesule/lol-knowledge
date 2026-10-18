"""Repository checks: the committed snapshot must match its manifest on checkout."""

import hashlib
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_published_snapshot_contains_no_crlf() -> None:
    base = REPO_ROOT / "data" / "current"
    offenders = [
        path.relative_to(base).as_posix()
        for path in base.rglob("*")
        if path.is_file() and b"\r\n" in path.read_bytes()
    ]

    assert offenders == []


def test_published_snapshot_matches_its_manifest() -> None:
    base = REPO_ROOT / "data" / "current"
    manifest = json.loads((base / "manifest.json").read_text(encoding="utf-8"))

    assert manifest["files"]
    for relative, record in manifest["files"].items():
        content = (base / relative).read_bytes()
        assert record["bytes"] == len(content), relative
        assert record["sha256"] == hashlib.sha256(content).hexdigest(), relative


def test_gitattributes_pins_lf_line_endings() -> None:
    attributes = (REPO_ROOT / ".gitattributes").read_text(encoding="utf-8")

    assert "eol=lf" in attributes
