"""Provenance and regression probes from the independent verification."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from binmodel.extract import extract_champion
from binmodel.registry import Registry
from binmodel.traverse import TraversalContext, parse_part

RESEARCH_ROOT = Path(__file__).resolve().parents[1]
CACHE = RESEARCH_ROOT / ".cache" / "zaahen-16.20.bin.json"


def _extract(document):
    meta = document.get("_provenance", {})
    return extract_champion(
        document,
        source={
            "artifact_sha256": meta.get("source_sha256", ""),
            "url": meta.get("url", ""),
        },
        content_version=meta.get("content_version", ""),
    )


def test_mode_override_provenance_points_at_the_override(extract_document):
    extract = _extract(extract_document)
    passive = next(item for item in extract.abilities if item.ability_id == "passive")
    cherry = next(
        value
        for value in passive.data_values
        if value.name == "PBonusADMin" and value.mode == "cherry"
    )
    pointer = cherry.provenance["json_pointer"]
    assert "DataValuesModeOverride" in pointer
    assert pointer.endswith("/SpellDataValues/0")
    assert "DataValuesModeOverride" in cherry.source_path


def test_breakpoint_provenance_uses_the_real_field_key(extract_document):
    extract = _extract(extract_document)
    passive = next(item for item in extract.abilities if item.ability_id == "passive")
    calculation = next(item for item in passive.calculations if item.name == "RevivePercentCalc")
    part = calculation.tree["parts"][0]
    assert part["breakpoints"][0]["provenance"]["json_pointer"].endswith("/{9823b29a}/0")


@pytest.mark.skipif(not CACHE.exists(), reason="local cache is not present")
def test_all_24_game_calculations_have_a_typed_tree():
    document = json.loads(CACHE.read_text(encoding="utf-8"))
    paths: list[str] = []

    def walk(node, path):
        if isinstance(node, dict):
            if node.get("__type") == "GameCalculation":
                paths.append(path)
            for key, value in node.items():
                walk(value, f"{path}/{key}")
        elif isinstance(node, list):
            for index, value in enumerate(node):
                walk(value, f"{path}/{index}")

    walk(document, "")
    extract = _extract(document)
    seen: set[str] = set()

    def collect(node):
        if isinstance(node, dict):
            provenance = node.get("provenance")
            if (
                node.get("kind") == "game_calculation"
                and isinstance(provenance, dict)
                and "json_pointer" in provenance
            ):
                seen.add(provenance["json_pointer"])
            for value in node.values():
                collect(value)
        elif isinstance(node, list):
            for value in node:
                collect(value)

    collect(extract.to_dict())
    assert len(paths) == 24
    missing = [path for path in paths if path not in seen]
    assert missing == []


def test_unknown_part_is_preserved_not_zeroed():
    context = TraversalContext(
        document={},
        registry=Registry(),
        source_sha256="synthetic",
        content_version="synthetic",
        spell_path="Test",
    )
    raw = {"__type": "{deadbeef}", "value": 7}
    node = parse_part(raw, context=context, pointer="/Test/0")
    assert node["kind"] == "unresolved"
    assert node["raw"] == raw
    assert node["kind"] != "number"
    assert context.unresolved[0]["pointer"] == "/Test/0"


def test_malformed_data_value_is_reported(extract_document):
    document = json.loads(json.dumps(extract_document))
    root = document["Characters/Zaahen/CharacterRecords/Root"]
    q_path = root["spells"][0]
    document[q_path]["mSpell"]["DataValues"].append({"values": [1.0]})
    extract = _extract(document)
    codes = [item.code for item in extract.diagnostics]
    assert "malformed_data_value" in codes
