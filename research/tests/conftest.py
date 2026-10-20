"""Shared offline fixtures for the prototype."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

RESEARCH_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = RESEARCH_ROOT.parent


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture
def bin_document():
    return load_json(RESEARCH_ROOT / "fixtures" / "zaahen_spells_min.json")


@pytest.fixture
def extract_document():
    return load_json(RESEARCH_ROOT / "fixtures" / "zaahen_extract_min.json")


@pytest.fixture
def darius_document():
    return load_json(RESEARCH_ROOT / "fixtures" / "darius_extract_min.json")


@pytest.fixture
def ddragon_document():
    return load_json(REPO_ROOT / "data" / "current" / "champions" / "Zaahen.json")


@pytest.fixture
def rcp_document():
    return load_json(RESEARCH_ROOT / "fixtures" / "zaahen_rcp_min.json")


@pytest.fixture
def provenance_meta(bin_document):
    return bin_document["_provenance"]
