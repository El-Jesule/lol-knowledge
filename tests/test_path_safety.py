"""Regression tests: external ids must never escape the snapshot layout."""

import json
from dataclasses import replace
from pathlib import Path

import pytest

from lol_knowledge.ddragon import ChampionPayload, PatchPayload, validate_champion_id
from lol_knowledge.errors import PayloadError, SnapshotError
from lol_knowledge.snapshot import _publish, build_snapshot

PATCH = "16.20.1"

INVALID_IDS = [
    "",
    ".",
    "..",
    "../escape",
    "..\\escape",
    "evil/../../escape",
    "evil\\..\\..\\escape",
    "/absolute",
    "C:/absolute",
    "C:\\absolute",
    "Aatrox/child",
    "Aatrox\\child",
    "Aatrox.json",
    "aatrox",
    "1Aatrox",
    "Aatrox ",
    " Aatrox",
    "Aatrox-1",
    "Aatrox.x",
    "Aatrox\n",
]


def champion_doc(champion_id: str) -> dict:
    return {
        "id": champion_id,
        "key": "1",
        "name": "Campeón",
        "title": "el Prueba",
        "tags": ["Fighter"],
        "partype": "Maná",
        "stats": {
            name: 10
            for name in ("hp", "hpperlevel", "movespeed", "armor", "attackdamage", "attackrange")
        },
        "passive": {"name": "Pasiva"},
        "spells": [
            {
                "id": f"S{index}",
                "name": "Habilidad",
                "description": "descripción",
                "tooltip": "tooltip",
                "cooldownBurn": "1",
                "costBurn": "1",
            }
            for index in range(4)
        ],
    }


def patch_payload(champion_id: str) -> PatchPayload:
    return PatchPayload(
        patch=PATCH,
        locale="es_ES",
        source="https://ddragon.example",
        summary={
            champion_id: {
                "id": champion_id,
                "key": "1",
                "name": "Campeón",
                "title": "el Prueba",
                "tags": ["Fighter"],
            }
        },
        champions=(
            ChampionPayload(
                champion_id=champion_id,
                url="https://ddragon.example/champion.json",
                payload=champion_doc(champion_id),
            ),
        ),
        items={"1001": {"name": "Botas", "gold": {"total": 300}, "maps": {"11": True}}},
        runes=[
            {
                "id": 8000,
                "key": "Precision",
                "name": "Precisión",
                "slots": [{"runes": [{"id": 1}]}],
            }
        ],
    )


class StaticClient:
    """Client stub that returns one crafted payload without any network access."""

    def __init__(self, payload: PatchPayload) -> None:
        self.payload = payload

    def latest_patch(self) -> str:
        return self.payload.patch

    def fetch_patch(self, patch: str) -> PatchPayload:
        return self.payload


@pytest.mark.parametrize("value", INVALID_IDS)
def test_invalid_champion_ids_are_rejected(value: str) -> None:
    with pytest.raises(PayloadError):
        validate_champion_id(value)


@pytest.mark.parametrize("value", ["Aatrox", "AurelionSol", "KSante", "Yunara", "A1"])
def test_official_id_shapes_are_accepted(value: str) -> None:
    assert validate_champion_id(value) == value


@pytest.mark.parametrize("value", [266, None, b"Aatrox"])
def test_non_string_champion_ids_are_rejected(value: object) -> None:
    with pytest.raises(PayloadError):
        validate_champion_id(value)


@pytest.mark.parametrize(
    "champion_id", ["../escape", "..\\escape", "evil/../../escape", "evil\\..\\..\\escape"]
)
def test_build_snapshot_rejects_traversal_ids_without_writing(
    tmp_path: Path, champion_id: str
) -> None:
    data_dir = tmp_path / "data"

    with pytest.raises(PayloadError):
        build_snapshot(data_dir, client=StaticClient(patch_payload(champion_id)))

    assert not data_dir.exists()
    assert not (tmp_path / "escape.json").exists()
    assert not (tmp_path / "evil").exists()


def test_champion_payload_id_must_match_the_validated_id(tmp_path: Path) -> None:
    payload = patch_payload("Aatrox")
    poisoned = replace(
        payload,
        champions=(
            ChampionPayload(
                champion_id="Aatrox",
                url="https://ddragon.example/champion/Aatrox.json",
                payload=champion_doc("../escape"),
            ),
        ),
    )

    with pytest.raises(PayloadError):
        build_snapshot(tmp_path / "data", client=StaticClient(poisoned))

    assert not (tmp_path / "data").exists()
    assert not (tmp_path / "escape.json").exists()


def test_fetch_patch_rejects_a_traversal_summary_key_before_any_request(fake_source) -> None:
    fake_source.summary["../escape"] = {}

    with pytest.raises(PayloadError):
        fake_source.client().fetch_patch(PATCH)


def test_publish_refuses_a_relative_path_outside_staging(tmp_path: Path) -> None:
    with pytest.raises(SnapshotError):
        _publish(tmp_path / "data", {"../escape.json": b"payload"})

    assert not (tmp_path / "escape.json").exists()
    assert not (tmp_path / "data" / ".staging").exists()


def test_publish_refuses_an_absolute_path(tmp_path: Path) -> None:
    absolute = tmp_path / "absolute.json"

    with pytest.raises(SnapshotError):
        _publish(tmp_path / "data", {str(absolute): b"payload"})

    assert not absolute.exists()


def test_every_published_champion_id_matches_the_supported_pattern() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    current = repo_root / "data" / "current"
    index = json.loads((current / "champion-index.json").read_text(encoding="utf-8"))

    assert len(index) > 100
    for entry in index:
        assert validate_champion_id(entry["id"]) == entry["id"]

    filenames = {path.stem for path in (current / "champions").glob("*.json")}
    assert filenames == {entry["id"] for entry in index}
