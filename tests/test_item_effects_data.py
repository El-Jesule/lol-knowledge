"""Shape checks of the client item effect data (lol-knowledge/derived/item-effects.json)."""

from __future__ import annotations

import copy
import json
import shutil
from pathlib import Path

import pytest

from lol_knowledge.objects.client_effects import ITEM_EFFECTS_PATH, item_effects_problems
from lol_knowledge.validate import validate_project

ROOT = Path(__file__).resolve().parents[1]


def item(**changes):
    entry = {
        "data_values": {"CritMax": 25.0, "Cooldown": 30.0},
        "mode_overrides": {"ARAM": {"CritMax": 20.0}},
        "effect_amounts": [0.5],
        "calculations": {"CritPerStackCalc": {"class": "GameCalculation"}},
        "string_calculations": {"Split": {"melee": "@CritMax@", "ranged": "@Cooldown@"}},
        "texts": {
            "tooltip": "@CritPerStackCalc@ hasta @CritMax*100@% @Effect1Amount@ @Split@ "
            "@f1@ @Later@",
            "active": "@spell.SummonerSmite:PetDPS@ @Missing@",
        },
        "placeholders": {
            "CritMax": "data_value",
            "CritPerStackCalc": "calculation",
            "Effect1Amount": "effect_amount",
            "Split": "string_calculation",
            "f1": "runtime",
            "Later": "data_value_without_amount",
            "spell.SummonerSmite:PetDPS": "other_record",
            "Missing": None,
        },
        "data_values_without_amount": ["Later"],
    }
    entry.update(changes)
    return entry


def document(**changes):
    result = {
        "schema": "lol-derived-item-effects/1",
        "label": "Derivado",
        "content_version": "16.22.1+x",
        "game_version": "16.22",
        "retrieved_at": "2026-11-16",
        "locale": "es_ES",
        "source": "cliente",
        "method": "binmodel",
        "bin_sha256": "a" * 64,
        "strings_sha256": "b" * 64,
        "skipped_entries": [],
        "items": {"3032": item(), "1001": item(**EMPTY)},
        "failures": {},
    }
    result.update(changes)
    return result


EMPTY = {
    "data_values": None,
    "mode_overrides": {},
    "effect_amounts": None,
    "calculations": {},
    "string_calculations": {},
    "texts": {},
    "placeholders": {},
}


def test_a_well_formed_document_has_no_problems():
    assert item_effects_problems(document(), patch="16.22.1", item_ids={"3032", "1001"}) == []


def test_the_project_file_matches_the_snapshot_and_the_catalog():
    stats = json.loads((ROOT / "lol-knowledge/objects/catalog-stats.json").read_text("utf-8"))
    manifest = json.loads((ROOT / "data/current/manifest.json").read_text("utf-8"))
    published = json.loads((ROOT / ITEM_EFFECTS_PATH).read_text("utf-8"))
    ids = {entry["id"] for entry in stats["objects"]}
    assert item_effects_problems(published, patch=manifest["patch"], item_ids=ids) == []
    assert set(published["items"]) == ids and published["failures"] == {}
    yun_tal = published["items"]["3032"]
    assert yun_tal["data_values"]["CritMax"] == 25.0
    assert yun_tal["data_values"]["CritPerStackMelee"] == 0.4
    assert yun_tal["data_values"]["StackRangedMultiplier"] == 0.5
    assert yun_tal["placeholders"]["CritPerStackCalc"] == "calculation"


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"schema": "x"}, "schema must be 'lol-derived-item-effects/1'"),
        ({"label": "Oficial"}, "label must be 'Derivado'"),
        ({"locale": ""}, "locale must be a non-empty string"),
        ({"bin_sha256": "abc"}, "bin_sha256 must be a SHA-256 hex digest"),
        ({"game_version": "16"}, "game_version must be <major>.<minor>"),
        ({"game_version": "16.21"}, "client 16.21 data for snapshot 16.22.1; regenerate"),
        ({"items": []}, "items must be an object"),
        ({"failures": {"1": 2}}, "failures must map item ids to reasons"),
    ],
)
def test_header_problems(changes, message):
    problems = item_effects_problems(document(**changes), patch="16.22.1")
    assert any(message in problem for problem in problems), problems


def test_coverage_of_the_catalog_is_checked():
    problems = item_effects_problems(
        document(failures={"7": "no record"}), item_ids={"3032", "1001", "9"}
    )
    assert any("without client data: ['9']" in problem for problem in problems)
    assert any("not in the catalog: ['7']" in problem for problem in problems)


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"extra": 1}, "has unknown keys ['extra']"),
        ({"data_values": {"A": "1"}}, "data_values must map names to finite numbers"),
        ({"data_values": {"A": float("nan")}}, "data_values must map names to finite numbers"),
        ({"mode_overrides": {"ARAM": {"A": True}}}, "mode_overrides must map modes"),
        ({"effect_amounts": [1, "2"]}, "effect_amounts must be a list of numbers"),
        ({"data_values_without_amount": []}, "data_values_without_amount must be a non-empty"),
        ({"repeated_data_values": [1]}, "repeated_data_values must be a non-empty"),
        ({"calculations": []}, "calculations must be an object"),
        ({"string_calculations": {"S": {"both": "x"}}}, "string_calculations must map"),
        ({"texts": {"name": "x"}}, "texts must map"),
        ({"placeholders": {"CritMax": "guess"}}, "placeholders must map names to a known kind"),
        ({"placeholders": {}}, "do not match the placeholders of its texts"),
    ],
)
def test_item_problems(changes, message):
    problems = item_effects_problems(document(items={"3032": item(**changes)}))
    assert any(message in problem for problem in problems), problems


def test_missing_item_keys_are_reported():
    entry = item()
    del entry["texts"]
    problems = item_effects_problems(document(items={"3032": entry, "1": "x"}))
    assert "items.3032 lacks ['texts']" in problems
    assert "items.1 must be an object" in problems


@pytest.mark.parametrize(
    ("name", "field", "message"),
    [
        ("CritMax", "data_values", "data_value not found in data_values"),
        (
            "Later",
            "data_values_without_amount",
            "data_value_without_amount not found in data_values_without_amount",
        ),
        ("CritPerStackCalc", "calculations", "calculation not found in calculations"),
        ("Split", "string_calculations", "string_calculation not found in string_calculations"),
    ],
)
def test_each_placeholder_kind_must_point_to_its_data(name, field, message):
    entry = copy.deepcopy(item())
    if field == "data_values_without_amount":
        entry[field] = ["Other"]
    else:
        del entry[field][name]
    problems = item_effects_problems(document(items={"3032": entry}))
    assert f"items.3032.placeholders.{name}: {message}" in problems


@pytest.mark.parametrize("amounts", [None, []])
def test_an_effect_amount_placeholder_needs_the_amount(amounts):
    problems = item_effects_problems(document(items={"3032": item(effect_amounts=amounts)}))
    assert "items.3032.placeholders.Effect1Amount: no such effect amount" in problems


def test_a_non_object_document_is_rejected():
    assert item_effects_problems([]) == ["the document must be a JSON object"]


def test_an_effect_amount_beyond_the_list_is_reported():
    entry = item()
    entry["texts"] = {"tooltip": "@Effect2Amount@"}
    entry["placeholders"] = {"Effect2Amount": "effect_amount"}
    problems = item_effects_problems(document(items={"3032": entry}))
    assert "items.3032.placeholders.Effect2Amount: no such effect amount" in problems


def test_validate_checks_the_coverage_of_the_generated_catalog(tmp_path):
    for relative in ("data/current", "lol-knowledge"):
        shutil.copytree(ROOT / relative, tmp_path / relative)
    path = tmp_path / ITEM_EFFECTS_PATH
    published = json.loads(path.read_text("utf-8"))
    del published["items"]["3032"]
    path.write_text(json.dumps(published, ensure_ascii=False), encoding="utf-8")
    found = [violation.message for violation in validate_project(tmp_path).violations]
    assert any("items of the catalog without client data: ['3032']" in m for m in found)
