"""Data issue registry tests."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from lol_knowledge.errors import StatsError
from lol_knowledge.stats import load_issues, parse_issues

ROOT = Path(__file__).resolve().parents[1]
VALID = {
    "schema": "lol-data-issues/2",
    "issues": [
        {
            "id": "x",
            "source": "data_dragon",
            "patches": ["16.20.1"],
            "field": "attackdamageperlevel",
            "champions": "*",
            "status": "open",
            "summary": "s",
            "documentation": "doc.md",
        }
    ],
}


def _with(**changes):
    document = copy.deepcopy(VALID)
    document["issues"][0].update(changes)
    return document


def test_project_issues_load_and_block_ad_growth():
    issues = load_issues(ROOT)
    issue = next(item for item in issues if item.field == "attackdamageperlevel")
    assert issue.status == "open"
    assert issue.patches == ("16.20.1", "16.22.1")
    assert issue.applies_to("Zaahen", "16.22.1")
    assert issue.applies_to("Ahri", "16.20.1")
    assert not issue.applies_to("Zaahen", "16.23.1")
    assert (ROOT / issue.documentation).is_file()


def test_champion_list_limits_scope():
    (issue,) = parse_issues(_with(champions=["Zaahen"]))
    assert issue.applies_to("Zaahen", "16.20.1")
    assert not issue.applies_to("Ahri", "16.20.1")


def test_resolved_issue_does_not_apply():
    (issue,) = parse_issues(_with(status="resolved"))
    assert not issue.applies_to("Zaahen", "16.20.1")


@pytest.mark.parametrize(
    ("document", "message"),
    [
        ([], "JSON object"),
        ({**VALID, "schema": "other"}, "schema"),
        ({**VALID, "issues": "x"}, "list"),
        (_with(status="maybe"), "status"),
        (_with(source="wiki"), "source"),
        (_with(champions=[]), "champions"),
        (_with(champions="Zaahen"), "champions"),
        (_with(summary=""), "summary"),
        (_with(extra=1), "unknown keys"),
        ({**VALID, "issues": VALID["issues"] * 2}, "duplicate"),
        (_with(patches=[]), "patches"),
        (_with(patches="16.20.1"), "patches"),
        (_with(patches=["16.20.1", "16.20.1"]), "patches"),
        (_with(patches=[""]), "patches"),
    ],
)
def test_rejects_malformed_documents(document, message):
    with pytest.raises(StatsError, match=message):
        parse_issues(document)


def test_missing_file_is_an_error(tmp_path):
    with pytest.raises(StatsError, match="not found"):
        load_issues(tmp_path)


def test_invalid_json_is_an_error(tmp_path):
    path = tmp_path / "lol-knowledge" / "data-issues.json"
    path.parent.mkdir()
    path.write_text("{", encoding="utf-8")
    with pytest.raises(StatsError, match="JSON"):
        load_issues(tmp_path)


def test_file_round_trip(tmp_path):
    path = tmp_path / "lol-knowledge" / "data-issues.json"
    path.parent.mkdir()
    path.write_text(json.dumps(VALID), encoding="utf-8")
    assert load_issues(tmp_path)[0].id == "x"
