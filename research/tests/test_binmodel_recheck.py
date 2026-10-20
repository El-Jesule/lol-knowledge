"""Regression probes from the independent re-verification."""

from __future__ import annotations

import json
from pathlib import Path

from binmodel.cli import _summary, main
from binmodel.extract import extract_champion
from binmodel.model import Ability, ChampionExtract
from binmodel.registry import Registry
from binmodel.stats import stat_ref
from binmodel.traverse import TraversalContext, parse_part, ranked_values

RESEARCH_ROOT = Path(__file__).resolve().parents[1]
FIXTURE = RESEARCH_ROOT / "fixtures" / "zaahen_extract_min.json"


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


def _context():
    return TraversalContext(
        document={},
        registry=Registry(),
        source_sha256="synthetic",
        content_version="synthetic",
        spell_path="Test",
    )


def test_broken_calculation_reference_is_reported():
    context = _context()
    node = parse_part(
        {"__type": "{f3cbe7b2}", "mSpellCalculationKey": "Missing"},
        context=context,
        pointer="/Test/0",
    )
    assert node["kind"] == "calculation_reference"
    assert node["key"] == "Missing"
    assert node["confidence"] == "unverified"
    assert any(item["pointer"] == "/Test/0" for item in context.unresolved)


def test_summary_counts_child_botdata_unresolved():
    ability = Ability(
        ability_id="q",
        slot="Q",
        path="TestQ",
        name="TestQ",
        root_spell="TestQ",
        level_count=1,
        source_level_count="synthetic",
        bot_data={"unresolved": [{"pointer": "/top"}]},
        child_spells=[{"path": "TestQ2", "bot_data": {"unresolved": [{"pointer": "/child"}]}}],
    )
    extract = ChampionExtract(
        schema_version=1,
        game_version="16.20",
        content_version="",
        source={},
        champion={"id": "Test"},
        abilities=[ability],
        unresolved=[],
        diagnostics=[],
        registry={},
    )
    summary = _summary(extract, validation=None, damage=None)
    assert "unresolved BotData nodes: 2" in summary


def test_typed_tree_nodes_have_confidence(extract_document):
    extract = _extract(extract_document)
    allowed = {
        "source_explicit",
        "derived",
        "inferred",
        "corroborated",
        "verified",
        "unverified",
        "conflict",
    }
    nodes = []

    def walk(node):
        if isinstance(node, dict):
            if "kind" in node and "provenance" in node:
                nodes.append(node)
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(extract.to_dict())
    assert nodes
    assert all(node.get("confidence") in allowed for node in nodes)


def test_child_spells_do_not_repeat_the_root(extract_document):
    extract = _extract(extract_document)
    for ability in extract.abilities:
        child_paths = [child["path"] for child in ability.child_spells]
        assert ability.path not in child_paths


def test_cli_separates_input_and_artifact_hash(capsys):
    code = main(["--input", str(FIXTURE), "--json"])
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["source"]["input_sha256"] != payload["source"]["artifact_sha256"]
    assert payload["source"]["artifact_sha256"] == (
        "76e32de67667917769cc6022a818b13e5024ea521a23c70436dc48eea533ed0b"
    )


def test_inferred_formula_does_not_inflate_confidence():
    assert stat_ref(2, 2)["confidence"] == "corroborated"
    assert stat_ref(2, 1)["confidence"] == "inferred"


def test_ambiguous_rank_alignment_is_diagnosed():
    diagnostics = []
    result = ranked_values([1.0, 2.0, 3.0, 4.0, 5.0], 5, "probe", diagnostics)
    assert result is None
    assert [item.code for item in diagnostics] == ["ambiguous_rank_alignment"]
