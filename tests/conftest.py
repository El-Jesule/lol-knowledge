"""Offline fixtures: a fake Data Dragon source with no network access."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest

from lol_knowledge.ddragon import DataDragonClient
from lol_knowledge.objects import load_catalog, load_model, load_snapshot

BASE_URL = "https://ddragon.example"
PATCH = "16.20.1"
LOCALE = "es_ES"


def _json_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False).encode("utf-8")


def _spell(champion_id: str, slot: str) -> dict[str, Any]:
    return {
        "id": f"{champion_id}{slot}",
        "name": f"{slot} ability",
        "description": f"{slot} description with {{{{ e1 }}}} damage",
        "tooltip": f"{slot} tooltip with {{{{ e1 }}}} damage",
        "cooldownBurn": "10/9/8/7/6",
        "costBurn": "25",
    }


def _champion(
    champion_id: str, *, key: str, name: str, title: str, tags: list[str]
) -> dict[str, Any]:
    return {
        "id": champion_id,
        "key": key,
        "name": name,
        "title": title,
        "tags": tags,
        "partype": "Maná",
        "stats": {
            "hp": 650,
            "hpperlevel": 114,
            "mp": 300,
            "mpperlevel": 40,
            "movespeed": 345,
            "armor": 38,
            "armorperlevel": 4.45,
            "spellblock": 32,
            "spellblockperlevel": 2.05,
            "attackrange": 175,
            "hpregen": 3,
            "hpregenperlevel": 0.5,
            "mpregen": 8,
            "mpregenperlevel": 0.8,
            "crit": 0,
            "critperlevel": 0,
            "attackdamage": 60,
            "attackdamageperlevel": 5,
            "attackspeedperlevel": 2.5,
            "attackspeed": 0.651,
        },
        "spells": [_spell(champion_id, slot) for slot in ("Q", "W", "E", "R")],
        "passive": {"name": f"{name} passive", "description": "Passive description"},
    }


class FakeSource:
    """Mutable stand-in for Data Dragon that only answers known URLs."""

    def __init__(self) -> None:
        self.versions: Any = [PATCH, "16.19.1"]
        self.summary: dict[str, Any] = {
            "Aatrox": {
                "id": "Aatrox",
                "key": "266",
                "name": "Aatrox",
                "title": "la Espada Darkin",
                "tags": ["Fighter"],
            },
            "Zaahen": {
                "id": "Zaahen",
                "key": "950",
                "name": "Zaahen",
                "title": "El Impertérrito",
                "tags": ["Fighter"],
            },
        }
        self.champions: dict[str, Any] = {
            "Aatrox": _champion(
                "Aatrox", key="266", name="Aatrox", title="la Espada Darkin", tags=["Fighter"]
            ),
            "Zaahen": _champion(
                "Zaahen", key="950", name="Zaahen", title="El Impertérrito", tags=["Fighter"]
            ),
        }
        self.items: dict[str, Any] = {
            "1001": {
                "name": "Botas",
                "description": "Botas básicas.",
                "gold": {"base": 300, "total": 300, "sell": 210, "purchasable": True},
                "maps": {"11": True, "12": False},
                "tags": ["Boots"],
            }
        }
        self.runes: Any = [
            {
                "id": 8000,
                "key": "Precision",
                "name": "Precisión",
                "slots": [
                    {
                        "runes": [
                            {
                                "id": 8005,
                                "key": "PressTheAttack",
                                "name": "Ataque intensificado",
                            }
                        ]
                    },
                    {"runes": [{"id": 9101, "key": "AbsorbLife", "name": "Absorber vida"}]},
                    {
                        "runes": [
                            {
                                "id": 9103,
                                "key": "LegendBloodline",
                                "name": "Leyenda: Linaje",
                            }
                        ]
                    },
                    {"runes": [{"id": 8014, "key": "CoupDeGrace", "name": "Golpe de gracia"}]},
                ],
            }
        ]
        self.failures: dict[str, Exception] = {}

    def url(self, resource: str) -> str:
        return f"{BASE_URL}/cdn/{PATCH}/data/{LOCALE}/{resource}"

    def opener(self, url: str, timeout: float) -> bytes:
        if url in self.failures:
            raise self.failures[url]
        if url == f"{BASE_URL}/api/versions.json":
            return _json_bytes(self.versions)
        if url == self.url("champion.json"):
            return _json_bytes({"data": self.summary})
        for champion_id, payload in self.champions.items():
            if url == self.url(f"champion/{champion_id}.json"):
                return _json_bytes({"data": {champion_id: payload}})
        if url == self.url("item.json"):
            return _json_bytes({"data": self.items})
        if url == self.url("runesReforged.json"):
            return _json_bytes(self.runes)
        raise AssertionError(f"unexpected URL requested: {url}")

    def client(self) -> DataDragonClient:
        return DataDragonClient(base_url=BASE_URL, locale=LOCALE, opener=self.opener)


@pytest.fixture
def fake_source() -> FakeSource:
    return FakeSource()


@pytest.fixture
def fake_client(fake_source: FakeSource) -> DataDragonClient:
    return fake_source.client()


PROJECT_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session")
def project_root() -> Path:
    return PROJECT_ROOT


@pytest.fixture(scope="session")
def object_model(project_root: Path) -> dict[str, Any]:
    model, _serialized = load_model(project_root)
    return model


@pytest.fixture(scope="session")
def object_catalog(project_root: Path) -> Mapping[str, Any]:
    return load_catalog(project_root)


@pytest.fixture(scope="session")
def object_snapshot(project_root: Path):
    return load_snapshot(project_root)


@pytest.fixture
def summary_entry() -> Mapping[str, Any]:
    return {
        "id": "Aatrox",
        "key": "266",
        "name": "Aatrox",
        "title": "la Espada Darkin",
        "tags": ["Fighter"],
    }
