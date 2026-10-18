"""Minimal Data Dragon client built on the standard library."""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from .errors import HttpStatusError, NetworkError, PatchNotAvailable, PayloadError

DDRAGON_BASE_URL = "https://ddragon.leagueoflegends.com"
DEFAULT_LOCALE = "es_ES"
REQUEST_TIMEOUT_SECONDS = 30.0
USER_AGENT = "LoL-Knowledge/0.1 (+https://github.com/El-Jesule/lol-knowledge)"

Opener = Callable[[str, float], bytes]


@dataclass(frozen=True)
class ChampionPayload:
    """Raw champion document together with the URL it came from."""

    champion_id: str
    url: str
    payload: Mapping[str, Any]


@dataclass(frozen=True)
class PatchPayload:
    """Everything the snapshot needs for one patch and locale."""

    patch: str
    locale: str
    source: str
    summary: Mapping[str, Any]
    champions: tuple[ChampionPayload, ...]
    items: Mapping[str, Any]
    runes: Sequence[Any]


def _default_open(url: str, timeout: float) -> bytes:
    """Fetch a URL and translate transport failures into project errors."""
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.read()
    except urllib.error.HTTPError as exc:
        raise HttpStatusError(exc.code, url) from exc
    except urllib.error.URLError as exc:
        raise NetworkError(f"cannot reach {url}: {exc.reason}") from exc
    except TimeoutError as exc:
        raise NetworkError(f"timed out after {timeout:g}s: {url}") from exc


class DataDragonClient:
    """Read-only access to the published Data Dragon documents."""

    def __init__(
        self,
        *,
        base_url: str = DDRAGON_BASE_URL,
        locale: str = DEFAULT_LOCALE,
        timeout: float = REQUEST_TIMEOUT_SECONDS,
        opener: Opener = _default_open,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.locale = locale
        self.timeout = timeout
        self._opener = opener

    def fetch_json(self, url: str) -> Any:
        """Download one document and decode it as JSON."""
        raw = self._opener(url, self.timeout)
        try:
            return json.loads(raw.decode("utf-8"))
        except UnicodeDecodeError as exc:
            raise PayloadError(f"{url} is not valid UTF-8") from exc
        except json.JSONDecodeError as exc:
            raise PayloadError(f"{url} is not valid JSON: {exc.msg}") from exc

    def versions(self) -> list[str]:
        """Return every published patch, newest first."""
        payload = self.fetch_json(f"{self.base_url}/api/versions.json")
        if not isinstance(payload, list) or not payload:
            raise PayloadError("versions.json must be a non-empty list of patch strings")

        versions = [item for item in payload if isinstance(item, str) and item]
        if len(versions) != len(payload):
            raise PayloadError("versions.json contains entries that are not patch strings")
        return versions

    def latest_patch(self) -> str:
        """Return the newest published patch."""
        return self.versions()[0]

    def fetch_patch(self, patch: str) -> PatchPayload:
        """Download the summary, every champion, items and runes for one patch."""
        available = self.versions()
        if patch not in available:
            raise PatchNotAvailable(f"patch {patch} is not published by Data Dragon")

        summary_url = self._data_url(patch, "champion.json")
        summary_payload = self.fetch_json(summary_url)
        summary = _require_data_mapping(summary_payload, summary_url)

        champions = tuple(
            self._fetch_champion(patch, champion_id) for champion_id in sorted(summary)
        )

        items_url = self._data_url(patch, "item.json")
        items = _require_data_mapping(self.fetch_json(items_url), items_url)

        runes_url = self._data_url(patch, "runesReforged.json")
        runes = self.fetch_json(runes_url)
        if not isinstance(runes, list) or not runes:
            raise PayloadError(f"{runes_url} must be a non-empty list of rune trees")

        return PatchPayload(
            patch=patch,
            locale=self.locale,
            source=self.base_url,
            summary=summary,
            champions=champions,
            items=items,
            runes=runes,
        )

    def _fetch_champion(self, patch: str, champion_id: str) -> ChampionPayload:
        url = self._data_url(patch, f"champion/{urllib.parse.quote(champion_id, safe='')}.json")
        payload = self.fetch_json(url)
        data = _require_data_mapping(payload, url)
        if champion_id not in data:
            raise PayloadError(f"{url} does not contain champion {champion_id!r}")
        return ChampionPayload(champion_id=champion_id, url=url, payload=data[champion_id])

    def _data_url(self, patch: str, resource: str) -> str:
        return f"{self.base_url}/cdn/{patch}/data/{self.locale}/{resource}"


def _require_data_mapping(payload: Any, url: str) -> Mapping[str, Any]:
    if not isinstance(payload, Mapping):
        raise PayloadError(f"{url} must be a JSON object")
    data = payload.get("data")
    if not isinstance(data, Mapping) or not data:
        raise PayloadError(f"{url} must contain a non-empty 'data' object")
    return data
