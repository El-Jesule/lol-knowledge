"""Tests of the patch refresh procedure that need no client."""

from __future__ import annotations

import json

import pytest
from tools.refresh_patch import (
    RefreshError,
    _without_sources,
    client_version,
    differences,
    main,
    snapshot_patch,
)


def test_differences_ignore_provenance_at_any_depth():
    old = {"content_version": "a", "items": {"1": {"bin_sha256": "x", "value": 9}}}
    new = {"content_version": "b", "items": {"1": {"bin_sha256": "y", "value": 8}}}
    assert list(differences(old, new)) == ["~ items.1.value: 9 -> 8"]


def test_differences_report_added_and_removed_keys():
    assert list(differences({"a": 1}, {"b": 1})) == ["- a", "+ b"]
    assert list(differences([1, 2], [1, 2, 3])) == ["~ : [1, 2] -> [1, 2, 3]"]


def test_kits_are_compared_without_the_version_of_their_sources():
    kit = {
        "content_version": "16.22.1+x",
        "verified_against": {"bin_sha256": "a"},
        "parts": [{"source": "Characters/A.Calc (16.22.8348910+branch.releases-16-22.content)"}],
    }
    other = {
        "content_version": "16.23.1+y",
        "verified_against": {"bin_sha256": "b"},
        "parts": [{"source": "Characters/A.Calc (16.23.8399929+branch.releases-16-23.content)"}],
    }
    assert _without_sources(kit) == _without_sources(other)
    assert _without_sources(kit)["parts"][0]["source"] == "Characters/A.Calc"


def test_the_client_and_the_snapshot_must_be_readable(tmp_path):
    with pytest.raises(RefreshError, match="content-metadata.json not found"):
        client_version(tmp_path)
    (tmp_path / "content-metadata.json").write_text('{"version": "nope"}', encoding="utf-8")
    with pytest.raises(RefreshError, match="unexpected version"):
        client_version(tmp_path)
    with pytest.raises(RefreshError, match="no snapshot"):
        snapshot_patch(tmp_path)


def test_a_client_of_another_patch_stops_before_any_extraction(tmp_path, capsys):
    game = tmp_path / "Game"
    game.mkdir()
    version = {"version": "16.23.8399929+branch.releases-16-23.content.release"}
    (game / "content-metadata.json").write_text(json.dumps(version), encoding="utf-8")
    manifest = tmp_path / "root" / "data" / "current" / "manifest.json"
    manifest.parent.mkdir(parents=True)
    manifest.write_text('{"patch": "16.22.1"}', encoding="utf-8")
    code = main(
        ["--game", str(game), "--hashes", str(tmp_path), "--retrieved-at", "2026-11-19",
         "--root", str(tmp_path / "root")]
    )  # fmt: skip
    assert code == 2
    assert "client 16.23 but snapshot 16.22.1" in capsys.readouterr().err
