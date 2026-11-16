"""Generated description stats of the Summoner's Rift items (catalog-stats.json)."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from lol_knowledge.objects import ObjectModelError, Snapshot
from lol_knowledge.objects.__main__ import main as objects_main
from lol_knowledge.objects.catalog import load_model, load_snapshot, merge_generated
from lol_knowledge.objects.generate import (
    ZERO_REASON,
    dump_generated,
    generate_description_stats,
    load_generated,
    summoners_rift_items,
)
from lol_knowledge.objects.schema import GENERATED_STATS_RELATIVE_PATH
from lol_knowledge.objects.validate import validate_object_catalog

ROOT = Path(__file__).resolve().parents[1]


def snapshot_item(stats_block="", *, stats=None, maps=None, purchasable=True, effects=""):
    return {
        "name": "Objeto",
        "description": f"<mainText><stats>{stats_block}</stats><br><br>{effects}</mainText>",
        "gold": {"base": 100, "total": 100, "sell": 70, "purchasable": purchasable},
        "maps": {"11": True} if maps is None else maps,
        "stats": stats or {},
        "tags": [],
    }


def snapshot(items, locale="es_ES"):
    return Snapshot(patch="16.22.1", locale=locale, items=items, items_sha256="0" * 64)


def entry_for(items, item_id="1001"):
    document = generate_description_stats(snapshot(items))
    return {entry["id"]: entry for entry in document["objects"]}[item_id]


def line(number, phrase):
    return f"<attention>{number}</attention> de {phrase}"


def test_selection_keeps_purchasable_summoners_rift_items_with_short_ids():
    items = {
        "1001": snapshot_item(),
        "2001": snapshot_item(maps={"11": False, "12": True}),
        "3001": snapshot_item(purchasable=False),
        "221001": snapshot_item(),
        "abc": snapshot_item(),
        "9999": snapshot_item(),
        "10000": snapshot_item(),
        "100": snapshot_item(),
    }
    assert summoners_rift_items(snapshot(items)) == ["100", "1001", "9999"]


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (line("10", "letalidad"), ("lethality", "flat", 10)),
        (line("20", "velocidad de habilidades"), ("ability_haste", "flat", 20)),
        (line("30%", "tenacidad"), ("tenacity", "percent", 30)),
        (line("2.5%", "omnisucción"), ("omnivamp", "percent", 2.5)),
        (line("2,5%", "omnisucción"), ("omnivamp", "percent", 2.5)),
        (line("12", "penetración mágica"), ("magic_penetration_flat", "flat", 12)),
        (line("40%", "penetración mágica"), ("magic_penetration_percent", "percent", 40)),
        (line("25", "velocidad de movimiento"), ("move_speed", "flat", 25)),
        (line("4%", "velocidad de movimiento"), ("move_speed", "percent", 4)),
        (line("100%", "regeneración de vida básica"), ("health_regen", "percent", 100)),
        (line("30%", "daño de impacto crítico"), ("crit_damage_bonus", "percent", 30)),
    ],
)
def test_description_lines_become_quoted_stats(text, expected):
    (stat,) = entry_for({"1001": snapshot_item(text)})["stats"]
    stat_id, kind, value = expected
    quote = text.replace("<attention>", "").replace("</attention>", "")
    assert stat == {"id": stat_id, "kind": kind, "value": value, "quote": quote}


def test_lines_data_dragon_already_has_are_skipped_after_checking_them():
    block = "<br>".join([line("110", "vida"), line("10", "letalidad")])
    entry = entry_for({"1001": snapshot_item(block, stats={"FlatHPPoolMod": 110})})
    assert [stat["id"] for stat in entry["stats"]] == ["lethality"]


def test_a_description_that_contradicts_data_dragon_is_an_error():
    item = snapshot_item(line("120", "vida"), stats={"FlatHPPoolMod": 110})
    with pytest.raises(ObjectModelError, match=r"description says '120 de vida'.*110"):
        generate_description_stats(snapshot({"1001": item}))


def test_a_zero_is_unknown_not_a_real_zero():
    (stat,) = entry_for({"1001": snapshot_item(line("0%", "probabilidad de impacto crítico"))})[
        "stats"
    ]
    assert stat == {
        "id": "crit_chance",
        "kind": "percent",
        "status": "unknown",
        "reason": ZERO_REASON,
        "quote": "0% de probabilidad de impacto crítico",
    }


def test_lines_without_an_engine_stat_are_kept_with_their_reason():
    entry = entry_for({"1001": snapshot_item(line("8%", "poder de curaciones y escudos"))})
    assert entry["stats"] == []
    assert entry["unmodelled_stats"] == [
        {
            "quote": "8% de poder de curaciones y escudos",
            "reason": "heal and shield power is not a stat of the engine",
        }
    ]
    assert "unmodelled_stats" not in entry_for({"1001": snapshot_item(line("10", "letalidad"))})


@pytest.mark.parametrize(
    ("text", "message"),
    [
        (line("10", "suerte"), "unknown stat phrase 'suerte'"),
        ("Brilla mucho", "is not 'N de …'"),
        (line("25", "velocidad de ataque"), "does not match kind 'percent'"),
        (line("10%", "letalidad"), "does not match kind 'flat'"),
    ],
)
def test_unreadable_lines_are_errors(text, message):
    with pytest.raises(ObjectModelError, match=message):
        generate_description_stats(snapshot({"1001": snapshot_item(text)}))


@pytest.mark.parametrize(
    ("effects", "expected"),
    [("", False), ("<passive>Algo</passive>", True), ("<active>Algo</active>", True)],
)
def test_effects_in_the_description_are_flagged(effects, expected):
    assert entry_for({"1001": snapshot_item(effects=effects)})["effects_in_description"] is expected


def test_only_the_spanish_phrases_are_known():
    with pytest.raises(ObjectModelError, match="for es_ES only, not en_US"):
        generate_description_stats(snapshot({"1001": snapshot_item()}, locale="en_US"))


def test_an_item_without_description_is_an_error():
    item = snapshot_item()
    del item["description"]
    with pytest.raises(ObjectModelError, match="has no description"):
        generate_description_stats(snapshot({"1001": item}))


def test_the_document_header_and_its_dump_are_deterministic():
    document = generate_description_stats(snapshot({"1001": snapshot_item()}))
    assert document["kind"] == "lol-object-description-stats"
    assert document["game_version"] == "16.22.1" and document["items_sha256"] == "0" * 64
    assert dump_generated(document) == dump_generated(json.loads(dump_generated(document)))
    assert dump_generated(document).endswith("}\n")


def test_the_committed_file_matches_the_snapshot():
    generated = load_generated(ROOT)
    expected = generate_description_stats(load_snapshot(ROOT))
    assert dump_generated(generated) == dump_generated(expected)
    assert len(generated["objects"]) == 218


# Merge with the curated catalog


def test_merge_keeps_curated_effects_and_marks_the_rest():
    catalog = {
        "catalog_version": 1,
        "objects": [
            {"id": "1", "effect_review": "partial", "stats": [], "effects": ["e"]},
            {"id": "9", "effect_review": "complete", "stats": [], "effects": []},
        ],
    }
    generated = {
        "objects": [
            {"id": "1", "stats": ["s1"], "effects_in_description": True},
            {"id": "2", "stats": ["s2"], "effects_in_description": True},
            {
                "id": "3",
                "stats": [],
                "effects_in_description": False,
                "unmodelled_stats": ["u"],
            },
        ]
    }
    merged = {entry["id"]: entry for entry in merge_generated(catalog, generated)["objects"]}
    assert merged["1"] == {"id": "1", "effect_review": "partial", "stats": ["s1"], "effects": ["e"]}
    assert merged["2"]["effect_review"] == "pending" and merged["2"]["effects"] == []
    assert merged["3"]["effect_review"] == "complete"
    assert merged["3"]["unmodelled_stats"] == ["u"]
    assert merged["9"]["effect_review"] == "complete"
    assert catalog["objects"][0]["stats"] == []  # the input is not modified
    assert merge_generated(catalog, None) is catalog


# Validation of the project files


@pytest.fixture
def project(tmp_path):
    for relative in ("data/current", "lol-knowledge/objects"):
        shutil.copytree(ROOT / relative, tmp_path / relative)
    return tmp_path


def messages(root):
    return [str(violation) for violation in validate_object_catalog(root).violations]


def test_the_project_files_are_valid(project):
    assert messages(project) == []


def test_a_stale_generated_file_is_reported(project):
    path = project / GENERATED_STATS_RELATIVE_PATH
    document = json.loads(path.read_text(encoding="utf-8"))
    document["objects"][0]["name"] = "Otro"
    path.write_text(dump_generated(document), encoding="utf-8")
    assert any("does not match the snapshot; regenerate" in m for m in messages(project))


def test_a_missing_generated_file_is_reported(project):
    (project / GENERATED_STATS_RELATIVE_PATH).unlink()
    assert any("catalog-stats.json: not found; regenerate" in m for m in messages(project))


def test_curated_stats_for_a_generated_item_are_reported(project):
    path = project / "lol-knowledge/objects/catalog.json"
    catalog = json.loads(path.read_text(encoding="utf-8"))
    (treads,) = [entry for entry in catalog["objects"] if entry["id"] == "3111"]
    treads["stats"] = [
        {"id": "tenacity", "kind": "percent", "value": 30, "quote": "30% de tenacidad"}
    ]
    path.write_text(json.dumps(catalog, ensure_ascii=False), encoding="utf-8")
    found = messages(project)
    assert any("item 3111 takes its description stats from" in m for m in found)


def test_a_confirmed_zero_without_a_generated_unknown_is_reported(project):
    path = project / "lol-knowledge/objects/catalog.json"
    catalog = json.loads(path.read_text(encoding="utf-8"))
    (treads,) = [entry for entry in catalog["objects"] if entry["id"] == "3111"]
    treads["confirmed_zero_stats"] = [
        {"id": "armor", "kind": "flat", "reason": "x"},
        {"id": "tenacity", "kind": "percent", "reason": "x"},
    ]
    path.write_text(json.dumps(catalog, ensure_ascii=False), encoding="utf-8")
    found = messages(project)
    assert any("has no unknown armor (flat) for item 3111" in m for m in found)
    assert any("has no unknown tenacity (percent) for item 3111" in m for m in found)


def test_yun_tal_crit_is_a_confirmed_zero_in_the_model(project):
    model, _ = load_model(project)
    (yun_tal,) = [entry for entry in model["objects"] if entry["id"] == "3032"]
    (crit,) = [stat for stat in yun_tal["stats"] if stat["id"] == "crit_chance"]
    assert (crit["value"], crit["status"]) == (0.0, "declared")
    assert crit["note"].startswith("confirmed zero: the item has no crit chance stat")


def test_the_generate_command_rewrites_the_file(project, capsys):
    path = project / GENERATED_STATS_RELATIVE_PATH
    path.write_text("{}", encoding="utf-8")
    assert objects_main(["--root", str(project), "--generate-stats"]) == 0
    assert "218 items, 134 stats" in capsys.readouterr().out
    assert path.read_text(encoding="utf-8") == (ROOT / GENERATED_STATS_RELATIVE_PATH).read_text(
        encoding="utf-8"
    )
    assert messages(project) == []
