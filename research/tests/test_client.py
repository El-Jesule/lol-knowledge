"""Offline tests for the pinned client. No network access."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from cdragon_zaahen.client import (
    BIN_URL,
    CACHE_FILENAME,
    CACHE_MANIFEST,
    HttpFailure,
    InvalidPayload,
    NetworkFailure,
    SourceError,
    build_request,
    load_pinned,
)


def _opener(metadata: dict, payload: bytes):
    def open_url(url: str, timeout: float) -> bytes:
        if url.endswith("content-metadata.json"):
            return json.dumps(metadata).encode("utf-8")
        if url == BIN_URL:
            return payload
        raise AssertionError(f"unexpected URL: {url}")

    return open_url


def _payload() -> bytes:
    return json.dumps(
        {
            "Characters/Zaahen/Spells/ZaahenQAbility/ZaahenQ": {
                "ObjectName": "ZaahenQ",
                "mSpell": {"DataValues": [], "mSpellCalculations": {}},
            }
        }
    ).encode("utf-8")


def test_download_writes_cache_and_returns_hash(tmp_path: Path) -> None:
    source = load_pinned(tmp_path, opener=_opener({"version": "16.20.test"}, _payload()))

    assert source.from_cache is False
    assert source.content_version == "16.20.test"
    assert (tmp_path / CACHE_FILENAME).is_file()
    manifest = json.loads((tmp_path / CACHE_MANIFEST).read_text(encoding="utf-8"))
    assert manifest["sha256"] == source.sha256


def test_offline_uses_valid_cache(tmp_path: Path) -> None:
    first = load_pinned(tmp_path, opener=_opener({"version": "16.20.test"}, _payload()))
    cached = load_pinned(tmp_path, offline=True)

    assert cached.from_cache is True
    assert cached.sha256 == first.sha256
    assert cached.content_version == "16.20.test"


def test_offline_without_cache_fails(tmp_path: Path) -> None:
    with pytest.raises(SourceError):
        load_pinned(tmp_path, offline=True)


def test_network_failure_leaves_cache_untouched(tmp_path: Path) -> None:
    load_pinned(tmp_path, opener=_opener({"version": "16.20.test"}, _payload()))
    before = (tmp_path / CACHE_MANIFEST).read_bytes()

    def failing(url: str, timeout: float) -> bytes:
        raise NetworkFailure("offline")

    with pytest.raises(NetworkFailure):
        load_pinned(tmp_path, opener=failing)

    assert (tmp_path / CACHE_MANIFEST).read_bytes() == before


def test_http_failure_is_typed(tmp_path: Path) -> None:
    def failing(url: str, timeout: float) -> bytes:
        raise HttpFailure(503, url)

    with pytest.raises(HttpFailure):
        load_pinned(tmp_path, opener=failing)


def test_invalid_json_does_not_write_cache(tmp_path: Path) -> None:
    with pytest.raises(InvalidPayload):
        load_pinned(
            tmp_path,
            opener=_opener({"version": "16.20.test"}, b"{not json"),
        )

    assert not (tmp_path / CACHE_FILENAME).exists()


def test_unexpected_shape_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(InvalidPayload):
        load_pinned(
            tmp_path,
            opener=_opener({"version": "16.20.test"}, b"{}"),
        )


def test_requests_carry_no_credentials() -> None:
    request = build_request(BIN_URL)

    assert not any(key.lower() == "authorization" for key in request.headers)
    assert all(key.lower() != "cookie" for key in request.headers)
