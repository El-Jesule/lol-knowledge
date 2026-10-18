"""Tests for the Data Dragon client. No network access."""

import pytest

from lol_knowledge.ddragon import DataDragonClient
from lol_knowledge.errors import (
    HttpStatusError,
    NetworkError,
    PatchNotAvailable,
    PayloadError,
)

BASE_URL = "https://ddragon.example"
PATCH = "16.20.1"


def test_latest_patch_returns_newest(fake_client: DataDragonClient) -> None:
    assert fake_client.latest_patch() == PATCH


def test_versions_rejects_non_list(fake_source) -> None:
    fake_source.versions = {"16.20.1": True}

    with pytest.raises(PayloadError):
        fake_source.client().versions()


def test_versions_rejects_non_string_entries(fake_source) -> None:
    fake_source.versions = [PATCH, 16]

    with pytest.raises(PayloadError):
        fake_source.client().versions()


def test_fetch_patch_returns_sorted_champions(fake_client: DataDragonClient) -> None:
    payload = fake_client.fetch_patch(PATCH)

    assert payload.patch == PATCH
    assert payload.locale == "es_ES"
    assert payload.source == BASE_URL
    assert [champion.champion_id for champion in payload.champions] == ["Aatrox", "Zaahen"]


def test_fetch_patch_rejects_unpublished_patch(fake_client: DataDragonClient) -> None:
    with pytest.raises(PatchNotAvailable):
        fake_client.fetch_patch("0.0.1")


def test_fetch_json_rejects_invalid_json() -> None:
    client = DataDragonClient(opener=lambda url, timeout: b"{not json")

    with pytest.raises(PayloadError):
        client.fetch_json("https://ddragon.example/broken.json")


def test_fetch_json_rejects_invalid_utf8() -> None:
    client = DataDragonClient(opener=lambda url, timeout: b"\xff\xfe")

    with pytest.raises(PayloadError):
        client.fetch_json("https://ddragon.example/broken.json")


def test_network_error_propagates(fake_source) -> None:
    fake_source.failures[f"{BASE_URL}/api/versions.json"] = NetworkError("unreachable")

    with pytest.raises(NetworkError):
        fake_source.client().latest_patch()


def test_http_status_error_is_a_network_error(fake_source) -> None:
    fake_source.failures[f"{BASE_URL}/api/versions.json"] = HttpStatusError(
        503, f"{BASE_URL}/api/versions.json"
    )

    with pytest.raises(NetworkError):
        fake_source.client().latest_patch()
