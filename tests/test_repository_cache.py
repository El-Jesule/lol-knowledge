"""Tests for RepositoryCache, load_model_data, invalidation, and warm MCP/contract calls."""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from typing import Any

import pytest

from lol_knowledge.cache import DEFAULT_CACHE, clear_cache
from lol_knowledge.contract import CONTRACT_SCHEMA, execute_request
from lol_knowledge.errors import KitError, StatsError
from lol_knowledge.kit import load_kit
from lol_knowledge.mcp_server import MCPServer
from lol_knowledge.objects import load_model, load_model_data
from lol_knowledge.objects.legality import ITEM_GROUPS_PATH, load_item_groups
from lol_knowledge.runes import RUNES_PATH, load_runes
from lol_knowledge.stats import load_champion, load_issues, load_items, load_records
from lol_knowledge.stats.derived import RECORDS_PATH
from lol_knowledge.stats.issues import ISSUES_PATH
from lol_knowledge.summoners import SUMMONERS_PATH, load_summoner_spells

ROOT = Path(__file__).resolve().parents[1]


def _bump_mtime(path: Path, delta_ns: int = 10_000_000) -> None:
    st = path.stat()
    os.utime(path, ns=(st.st_atime_ns, st.st_mtime_ns + delta_ns))


def _write_json(path: Path, payload: Any, *, bump: bool = True) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    had_file = path.exists()
    old_mtime = path.stat().st_mtime_ns if had_file else None
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if bump and old_mtime is not None and path.stat().st_mtime_ns <= old_mtime:
        os.utime(path, ns=(path.stat().st_atime_ns, old_mtime + 10_000_000))


def _make_minimal_repo(tmp_path: Path) -> None:
    """Create a minimal repository layout in ``tmp_path`` with one champion and one item."""
    current = tmp_path / "data" / "current"
    (current / "champions").mkdir(parents=True, exist_ok=True)
    (tmp_path / "lol-knowledge" / "objects").mkdir(parents=True, exist_ok=True)

    items = {
        "1001": {
            "name": "Boots",
            "description": "<stats>+25 de velocidad de movimiento</stats>",
            "stats": {"FlatMovementSpeedMod": 25},
            "gold": {"base": 300, "total": 300, "sell": 210, "purchasable": True},
            "maps": {"11": True, "12": False},
            "tags": ["Boots"],
        }
    }
    items_bytes = (json.dumps(items, ensure_ascii=False) + "\n").encode("utf-8")
    _write_json(current / "items.json", items, bump=False)

    import hashlib

    items_sha = hashlib.sha256(
        (current / "items.json").read_text(encoding="utf-8").encode("utf-8")
    ).hexdigest()
    assert len(items_sha) == 64 and len(items_bytes) > 0

    _write_json(
        current / "manifest.json",
        {
            "patch": "16.23.1",
            "locale": "es_ES",
            "files": {"items.json": {"sha256": items_sha}},
        },
        bump=False,
    )
    _write_json(current / "champion-index.json", [{"id": "Ahri", "name": "Ahri"}], bump=False)
    _write_json(
        current / "champions" / "Ahri.json",
        {
            "id": "Ahri",
            "name": "Ahri",
            "partype": "Maná",
            "stats": {"hp": 590, "attackdamage": 53, "armor": 21, "spellblock": 30},
            "spells": [
                {"id": f"Ahri{slot}", "name": slot, "maxrank": 5, "cooldown": [7, 7, 7, 7, 7]}
                for slot in ("Q", "W", "E", "R")
            ],
        },
        bump=False,
    )
    _write_json(
        tmp_path / "lol-knowledge" / "objects" / "catalog.json",
        {
            "schema_version": 1,
            "kind": "lol-object-model-catalog",
            "catalog_version": 1,
            "game_version": "16.23.1",
            "objects": [
                {
                    "id": "1001",
                    "effect_review": "complete",
                    "stats": [],
                    "effects": [],
                }
            ],
        },
        bump=False,
    )
    _write_json(
        tmp_path / "lol-knowledge" / "objects" / "catalog-stats.json",
        {
            "schema_version": 1,
            "kind": "lol-object-description-stats",
            "objects": [{"id": "1001", "stats": [], "effects_in_description": False}],
        },
        bump=False,
    )


def test_load_model_data_matches_load_model() -> None:
    clear_cache()
    assert load_model_data(ROOT, validate=False) == load_model(ROOT)[0]


def test_cache_hit_skips_reparse_and_clear_cache_resets(monkeypatch: pytest.MonkeyPatch) -> None:
    clear_cache()
    real_loads = json.loads
    calls = 0

    def spy_loads(text: str, *args: Any, **kwargs: Any) -> Any:
        nonlocal calls
        calls += 1
        return real_loads(text, *args, **kwargs)

    monkeypatch.setattr(json, "loads", spy_loads)

    c1 = load_champion(ROOT, "Ahri")
    i1 = load_items(ROOT, ["3089"])
    is1 = load_issues(ROOT)
    r1 = load_records(ROOT)
    g1 = load_item_groups(ROOT)
    ru1 = load_runes(ROOT)
    s1 = load_summoner_spells(ROOT)
    k1 = load_kit(ROOT, "Ahri")
    assert calls > 0

    warm_start = calls
    c2 = load_champion(ROOT, "ahri")
    i2 = load_items(ROOT, ["3089"])
    i3 = load_items(ROOT, ["3153"])
    is2 = load_issues(ROOT)
    r2 = load_records(ROOT)
    g2 = load_item_groups(ROOT)
    ru2 = load_runes(ROOT)
    s2 = load_summoner_spells(ROOT)
    k2 = load_kit(ROOT, "Ahri")

    assert calls == warm_start
    assert c2 is c1
    assert i2[0] is i1[0]
    assert i3[0].id == "3153"
    assert is2 is is1
    assert r2 is r1
    assert g2 is g1
    assert ru2 is ru1
    assert s2 is s1
    assert k2 is k1

    clear_cache()
    is3 = load_issues(ROOT)
    assert calls > warm_start
    assert is3 == is1


def test_invalidation_for_champion_and_items(tmp_path: Path) -> None:
    clear_cache()
    _make_minimal_repo(tmp_path)

    champ1 = load_champion(tmp_path, "Ahri")
    assert champ1.patch == "16.23.1"
    assert champ1.stats["hp"] == 590

    champ_path = tmp_path / "data" / "current" / "champions" / "Ahri.json"
    doc = json.loads(champ_path.read_text(encoding="utf-8"))
    doc["stats"]["hp"] = 605
    _write_json(champ_path, doc)

    champ2 = load_champion(tmp_path, "Ahri")
    assert champ2 is not champ1
    assert champ2.stats["hp"] == 605

    manifest_path = tmp_path / "data" / "current" / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["patch"] = "16.24.1"
    _write_json(manifest_path, manifest)

    champ3 = load_champion(tmp_path, "Ahri")
    assert champ3.patch == "16.24.1"

    item1 = load_items(tmp_path, ["1001"])[0]
    assert item1.game_version == "16.24.1"
    assert item1.stats[0].value == 25

    items_path = tmp_path / "data" / "current" / "items.json"
    items_doc = json.loads(items_path.read_text(encoding="utf-8"))
    items_doc["1001"]["stats"]["FlatMovementSpeedMod"] = 30
    _write_json(items_path, items_doc)

    item2 = load_items(tmp_path, ["1001"])[0]
    assert item2 is not item1
    assert item2.stats[0].value == 30


def test_invalidation_create_modify_delete_for_optional_and_issues(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    clear_cache()
    _make_minimal_repo(tmp_path)

    # Absent optional files cache None, then invalidate when created, modified, and deleted.
    assert load_records(tmp_path) is None
    assert load_item_groups(tmp_path) is None
    assert load_runes(tmp_path) is None
    assert load_summoner_spells(tmp_path) is None
    assert load_kit(tmp_path, "Ahri") is None

    # Verify absent None results are cached without re-statting/parsing failures.
    real_loads = json.loads
    loads_count = 0

    def count_loads(text: str, *args: Any, **kwargs: Any) -> Any:
        nonlocal loads_count
        loads_count += 1
        return real_loads(text, *args, **kwargs)

    monkeypatch.setattr(json, "loads", count_loads)
    assert load_records(tmp_path) is None
    assert loads_count == 0

    # Copy valid derived/kit/issues files from ROOT into tmp_path.
    for rel in (ISSUES_PATH, RECORDS_PATH, ITEM_GROUPS_PATH, RUNES_PATH, SUMMONERS_PATH):
        dst = tmp_path / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / rel, dst)

    kit_dst = tmp_path / "lol-knowledge" / "champions" / "Ahri" / "kit.json"
    kit_dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(ROOT / "lol-knowledge" / "champions" / "Ahri" / "kit.json", kit_dst)

    issues1 = load_issues(tmp_path)
    rec1 = load_records(tmp_path)
    grp1 = load_item_groups(tmp_path)
    runes1 = load_runes(tmp_path)
    sum1 = load_summoner_spells(tmp_path)
    kit1 = load_kit(tmp_path, "Ahri")
    assert issues1 and rec1 and grp1 and runes1 and sum1 and kit1

    # Modify same-size (via mtime_ns bump) or content change and verify invalidation.
    _bump_mtime(tmp_path / ISSUES_PATH)
    assert load_issues(tmp_path) is not issues1

    rec_doc = json.loads((tmp_path / RECORDS_PATH).read_text(encoding="utf-8"))
    rec_doc["champions"]["Ahri"]["fields"]["hp"] = 999.0
    _write_json(tmp_path / RECORDS_PATH, rec_doc)
    rec2 = load_records(tmp_path)
    assert rec2 is not None and rec2.value("Ahri", "hp") == 999

    grp_doc = json.loads((tmp_path / ITEM_GROUPS_PATH).read_text(encoding="utf-8"))
    grp_doc["game_version"] = "16.99"
    _write_json(tmp_path / ITEM_GROUPS_PATH, grp_doc)
    grp2 = load_item_groups(tmp_path)
    assert grp2 is not None and grp2.game_version == "16.99"

    runes_doc = json.loads((tmp_path / RUNES_PATH).read_text(encoding="utf-8"))
    runes_doc["game_version"] = "16.99"
    _write_json(tmp_path / RUNES_PATH, runes_doc)
    runes2 = load_runes(tmp_path)
    assert runes2 is not None and runes2.game_version == "16.99"

    sum_doc = json.loads((tmp_path / SUMMONERS_PATH).read_text(encoding="utf-8"))
    sum_doc["game_version"] = "16.99"
    _write_json(tmp_path / SUMMONERS_PATH, sum_doc)
    sum2 = load_summoner_spells(tmp_path)
    assert sum2 is not None and sum2.game_version == "16.99"

    kit_doc = json.loads(kit_dst.read_text(encoding="utf-8"))
    kit_doc["game_version"] = "16.99"
    _write_json(kit_dst, kit_doc)
    kit2 = load_kit(tmp_path, "Ahri")
    assert kit2 is not None and kit2.game_version == "16.99"

    # Delete files and verify invalidation back to None (or StatsError for issues).
    (tmp_path / ISSUES_PATH).unlink()
    with pytest.raises(StatsError):
        load_issues(tmp_path)

    for rel in (RECORDS_PATH, ITEM_GROUPS_PATH, RUNES_PATH, SUMMONERS_PATH):
        (tmp_path / rel).unlink()
    kit_dst.unlink()

    assert load_records(tmp_path) is None
    assert load_item_groups(tmp_path) is None
    assert load_runes(tmp_path) is None
    assert load_summoner_spells(tmp_path) is None
    assert load_kit(tmp_path, "Ahri") is None


def test_exceptions_are_not_cached(tmp_path: Path) -> None:
    clear_cache()
    _make_minimal_repo(tmp_path)

    issues_path = tmp_path / ISSUES_PATH
    issues_path.parent.mkdir(parents=True, exist_ok=True)
    issues_path.write_text("{broken json", encoding="utf-8")

    with pytest.raises(StatsError):
        load_issues(tmp_path)
    with pytest.raises(StatsError):
        load_issues(tmp_path)

    shutil.copy2(ROOT / ISSUES_PATH, issues_path)
    _bump_mtime(issues_path)
    assert len(load_issues(tmp_path)) >= 1

    kit_path = tmp_path / "lol-knowledge" / "champions" / "Ahri" / "kit.json"
    kit_path.parent.mkdir(parents=True, exist_ok=True)
    kit_path.write_text("{broken", encoding="utf-8")

    with pytest.raises(KitError):
        load_kit(tmp_path, "Ahri")
    with pytest.raises(KitError):
        load_kit(tmp_path, "Ahri")

    shutil.copy2(ROOT / "lol-knowledge" / "champions" / "Ahri" / "kit.json", kit_path)
    _bump_mtime(kit_path)
    assert load_kit(tmp_path, "Ahri") is not None


def test_warm_contract_stats_and_mcp_server(monkeypatch: pytest.MonkeyPatch) -> None:
    clear_cache()
    req = {
        "schema": CONTRACT_SCHEMA,
        "operation": "stats",
        "params": {"champion": "Ahri", "level": 9, "items": ["6655"]},
    }
    cold = execute_request(req, ROOT)
    assert cold["ok"] is True

    server = MCPServer(ROOT)
    assert server.cache is DEFAULT_CACHE
    first_res = server.handle_message(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "resources/read",
            "params": {"uri": "lol-knowledge://index"},
        }
    )
    assert first_res is not None
    assert "INDEX" in first_res["result"]["contents"][0]["text"] or first_res["result"]["contents"]

    first_lookup_items = server.handle_message(
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {"name": "lol_lookup", "arguments": {"entity": "items", "query": "Luden"}},
        }
    )
    assert first_lookup_items is not None
    assert first_lookup_items["result"]["isError"] is False

    real_loads = json.loads
    loads_calls = 0

    def spy_loads(text: str, *args: Any, **kwargs: Any) -> Any:
        nonlocal loads_calls
        loads_calls += 1
        return real_loads(text, *args, **kwargs)

    monkeypatch.setattr(json, "loads", spy_loads)

    warm = execute_request(req, ROOT)
    assert warm == cold

    second_res = server.handle_message(
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "resources/read",
            "params": {"uri": "lol-knowledge://index"},
        }
    )
    assert second_res is not None
    assert second_res["result"]["contents"] == first_res["result"]["contents"]

    second_lookup_items = server.handle_message(
        {
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {"name": "lol_lookup", "arguments": {"entity": "items", "query": "Luden"}},
        }
    )
    assert second_lookup_items is not None
    assert (
        second_lookup_items["result"]["structuredContent"]
        == first_lookup_items["result"]["structuredContent"]
    )
    assert loads_calls == 0
