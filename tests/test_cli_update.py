"""Tests for the update command exit codes and messages."""

from pathlib import Path

import pytest

from lol_knowledge.cli import main
from lol_knowledge.errors import NetworkError, PayloadError, SnapshotError
from lol_knowledge.snapshot import UpdateResult


def stub_build(monkeypatch: pytest.MonkeyPatch, outcome) -> None:
    def fake_build(data_dir: Path, *, patch: str = "latest", client=None) -> UpdateResult:
        if isinstance(outcome, Exception):
            raise outcome
        return UpdateResult(patch="16.20.1", data_dir=data_dir, file_count=3, changed=outcome)

    monkeypatch.setattr("lol_knowledge.cli.build_snapshot", fake_build)


def test_update_reports_written_snapshot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    stub_build(monkeypatch, True)

    assert main(["update", "--data-dir", str(tmp_path)]) == 0
    assert "updated: patch 16.20.1" in capsys.readouterr().out


def test_update_reports_unchanged_snapshot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    stub_build(monkeypatch, False)

    assert main(["update", "--data-dir", str(tmp_path)]) == 0
    assert "unchanged: patch 16.20.1" in capsys.readouterr().out


def test_invalid_payload_exits_with_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    stub_build(monkeypatch, PayloadError("champion data is broken"))

    assert main(["update", "--data-dir", str(tmp_path)]) == 1
    assert "champion data is broken" in capsys.readouterr().err


def test_network_failure_exits_with_two(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    stub_build(monkeypatch, NetworkError("unreachable"))

    assert main(["update", "--data-dir", str(tmp_path)]) == 2
    assert "unreachable" in capsys.readouterr().err


def test_snapshot_failure_exits_with_two(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    stub_build(monkeypatch, SnapshotError("cannot publish"))

    assert main(["update", "--data-dir", str(tmp_path)]) == 2
    assert "cannot publish" in capsys.readouterr().err
