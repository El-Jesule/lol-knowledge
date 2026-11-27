"""Tests for unified StatSheet loadout assembly shared by CLI and Contract."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from lol_knowledge.cli import main as cli_main
from lol_knowledge.contract import CONTRACT_SCHEMA, execute_request
from lol_knowledge.loadout import LoadoutError, assemble_stat_sheet, resolve_crit_base
from lol_knowledge.stats import Label, load_champion, load_issues, load_items, load_records

ROOT = Path(__file__).resolve().parents[1]


def test_cli_and_contract_stats_parity_with_runes_elixir_ornn(capsys) -> None:
    rc = cli_main(
        [
            "stats",
            "--champion",
            "Ahri",
            "--level",
            "11",
            "--item",
            "3089",
            "--item",
            "3020",
            "--rune",
            "8112",
            "--rune",
            "8143",
            "--rune",
            "8137",
            "--rune",
            "8106",
            "--rune",
            "8226",
            "--rune",
            "8210",
            "--shard",
            "5008",
            "--shard",
            "5008",
            "--shard",
            "5001",
            "--elixir",
            "2139",
            "--ornn-item",
            "3089",
            "--json",
            "--root",
            str(ROOT),
        ]
    )
    assert rc == 0
    cli_json = json.loads(capsys.readouterr().out)

    contract_res = execute_request(
        {
            "schema": CONTRACT_SCHEMA,
            "operation": "stats",
            "params": {
                "champion": "Ahri",
                "level": 11,
                "items": ["3089", "3020"],
                "runes": [8112, 8143, 8137, 8106, 8226, 8210],
                "shards": [5008, 5008, 5001],
                "elixir": "2139",
                "ornn_item": "3089",
            },
        },
        ROOT,
    )
    assert contract_res["ok"] is True
    c_stats = contract_res["result"]["stats"]
    for stat_id in ("health", "ability_power", "ability_haste", "mana", "move_speed"):
        assert cli_json["stats"][stat_id]["exact"] == c_stats[stat_id]["exact"]
        assert cli_json["stats"][stat_id]["label"] == c_stats[stat_id]["label"]
    assert cli_json["notes"] == c_stats_notes(contract_res["result"]["notes"])


def c_stats_notes(notes: list[str]) -> list[str]:
    return notes


def test_loadout_error_codes_and_combat_contexts() -> None:
    champion = load_champion(ROOT, "Garen")
    issues = load_issues(ROOT)
    records = load_records(ROOT)
    items = load_items(ROOT, ["3047", "3111"])

    with pytest.raises(LoadoutError) as exc_info:
        assemble_stat_sheet(
            ROOT,
            champion,
            11,
            items,
            [],
            [],
            issues,
            {},
            records,
            check_items_legality=True,
        )
    assert exc_info.value.code == "illegal_build"

    allowed = assemble_stat_sheet(
        ROOT,
        champion,
        11,
        items,
        [8010, 9111, 9104, 8014, 8473, 8451],
        [5005, 5008, 5001],
        issues,
        {},
        records,
        allow_illegal=True,
        check_items_legality=True,
        combat_context="ability",
    )
    assert allowed.warnings
    assert any("applied in rotation, not in ability" in n for n in allowed.sheet.pending_effects)

    crit = resolve_crit_base(champion.id, champion.patch, records)
    assert crit is not None
    assert crit.label is Label.DERIVED
