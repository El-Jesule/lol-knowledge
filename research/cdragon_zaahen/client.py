"""Pinned, read-only CommunityDragon client for the Zaahen prototype.

No authentication, no API key, single pinned content version. A network failure
never overwrites the local cache.
"""

from __future__ import annotations

import hashlib
import json
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

PINNED_CONTENT_VERSION = "16.20"
BASE_URL = f"https://raw.communitydragon.org/{PINNED_CONTENT_VERSION}"
BIN_URL = f"{BASE_URL}/game/data/characters/zaahen/zaahen.bin.json"
METADATA_URL = f"{BASE_URL}/content-metadata.json"
USER_AGENT = "LoL-Knowledge-research/0.1"
REQUEST_TIMEOUT_SECONDS = 30.0
CACHE_FILENAME = "zaahen-16.20.bin.json"
CACHE_MANIFEST = "manifest.json"

Opener = Callable[[str, float], bytes]


class SourceError(Exception):
    """Base class for source failures."""


class NetworkFailure(SourceError):
    """The source could not be reached."""


class HttpFailure(SourceError):
    """The source answered with a non-success status."""

    def __init__(self, status: int, url: str) -> None:
        super().__init__(f"HTTP {status} for {url}")
        self.status = status
        self.url = url


class InvalidPayload(SourceError):
    """The downloaded document is not the expected JSON shape."""


@dataclass(frozen=True)
class SourceFile:
    payload: Mapping[str, Any]
    url: str
    content_version: str
    sha256: str
    from_cache: bool


def build_request(url: str) -> urllib.request.Request:
    """Build a request with no credentials of any kind."""
    return urllib.request.Request(url, headers={"User-Agent": USER_AGENT})


def _default_open(url: str, timeout: float) -> bytes:
    try:
        with urllib.request.urlopen(build_request(url), timeout=timeout) as response:
            return response.read()
    except urllib.error.HTTPError as exc:
        raise HttpFailure(exc.code, url) from exc
    except urllib.error.URLError as exc:
        raise NetworkFailure(f"cannot reach {url}: {exc.reason}") from exc
    except TimeoutError as exc:
        raise NetworkFailure(f"timed out after {timeout:g}s: {url}") from exc


def _decode(payload: bytes, url: str) -> Mapping[str, Any]:
    try:
        document = json.loads(payload.decode("utf-8"))
    except UnicodeDecodeError as exc:
        raise InvalidPayload(f"{url} is not valid UTF-8") from exc
    except json.JSONDecodeError as exc:
        raise InvalidPayload(f"{url} is not valid JSON: {exc.msg}") from exc
    if not isinstance(document, Mapping):
        raise InvalidPayload(f"{url} must be a JSON object")
    return document


def content_version(opener: Opener = _default_open) -> str:
    """Read the build identifier published next to the pinned content path."""
    payload = _decode(opener(METADATA_URL, REQUEST_TIMEOUT_SECONDS), METADATA_URL)
    version = payload.get("version")
    if not isinstance(version, str) or not version:
        raise InvalidPayload(f"{METADATA_URL} has no version string")
    return version


def _read_cache(cache_dir: Path) -> SourceFile | None:
    manifest_path = cache_dir / CACHE_MANIFEST
    data_path = cache_dir / CACHE_FILENAME
    if not manifest_path.is_file() or not data_path.is_file():
        return None
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        payload = data_path.read_bytes()
    except OSError, json.JSONDecodeError:
        return None
    if not isinstance(manifest, Mapping):
        return None
    if hashlib.sha256(payload).hexdigest() != manifest.get("sha256"):
        return None
    document = _decode(payload, str(data_path))
    return SourceFile(
        payload=document,
        url=str(manifest.get("url")),
        content_version=str(manifest.get("content_version")),
        sha256=str(manifest.get("sha256")),
        from_cache=True,
    )


def _write_cache(cache_dir: Path, payload: bytes, version: str) -> None:
    cache_dir.mkdir(parents=True, exist_ok=True)
    data_path = cache_dir / CACHE_FILENAME
    staging = cache_dir / f"{CACHE_FILENAME}.staging"
    staging.write_bytes(payload)
    staging.replace(data_path)
    manifest = {
        "url": BIN_URL,
        "content_version": version,
        "sha256": hashlib.sha256(payload).hexdigest(),
        "fetched_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    (cache_dir / CACHE_MANIFEST).write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def load_pinned(
    cache_dir: Path,
    *,
    opener: Opener | None = None,
    offline: bool = False,
) -> SourceFile:
    """Load the pinned document, downloading only when allowed.

    In offline mode the cache must already be valid. Online failures propagate
    without touching the cache.
    """
    open_fn = opener or _default_open

    if offline:
        cached = _read_cache(cache_dir)
        if cached is None:
            raise SourceError(f"no valid cache in {cache_dir}")
        return cached

    version = content_version(open_fn)
    payload = open_fn(BIN_URL, REQUEST_TIMEOUT_SECONDS)
    document = _decode(payload, BIN_URL)
    _require_spells(document)
    digest = hashlib.sha256(payload).hexdigest()
    _write_cache(cache_dir, payload, version)
    return SourceFile(
        payload=document,
        url=BIN_URL,
        content_version=version,
        sha256=digest,
        from_cache=False,
    )


def _require_spells(document: Mapping[str, Any]) -> None:
    required = "Characters/Zaahen/Spells/ZaahenQAbility/ZaahenQ"
    node = document.get(required)
    if not isinstance(node, Mapping) or "mSpell" not in node:
        raise InvalidPayload(f"document does not contain {required}.mSpell")
