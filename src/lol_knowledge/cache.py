"""Process-local repository cache invalidated by file metadata."""

from __future__ import annotations

import os
import stat
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Any, TypeVar

if TYPE_CHECKING:
    from .stats.data import ItemData

T = TypeVar("T")

FileSig = tuple[str, int, int] | None
PathsSig = tuple[FileSig, ...]

_MANIFEST_REL = Path("data") / "current" / "manifest.json"
_CHAMPION_INDEX_REL = Path("data") / "current" / "champion-index.json"
_CHAMPIONS_DIR_REL = Path("data") / "current" / "champions"
_ITEMS_REL = Path("data") / "current" / "items.json"
_CATALOG_REL = Path("lol-knowledge") / "objects" / "catalog.json"
_GENERATED_STATS_REL = Path("lol-knowledge") / "objects" / "catalog-stats.json"
_ISSUES_REL = Path("lol-knowledge") / "data-issues.json"
_RECORDS_REL = Path("lol-knowledge") / "derived" / "champion-records.json"
_ITEM_GROUPS_REL = Path("lol-knowledge") / "derived" / "item-groups.json"
_RUNES_REL = Path("lol-knowledge") / "derived" / "runes.json"
_SUMMONERS_REL = Path("lol-knowledge") / "derived" / "summoner-spells.json"
_CHAMPIONS_KB_REL = Path("lol-knowledge") / "champions"


def _file_sig(path: Path) -> FileSig:
    try:
        st = path.stat()
    except OSError:
        return None
    if not stat.S_ISREG(st.st_mode):
        return None
    return (str(path), st.st_mtime_ns, st.st_size)


def _paths_sig(paths: Sequence[Path]) -> PathsSig:
    return tuple(_file_sig(path) for path in paths)


class RepositoryCache:
    """In-memory cache of parsed repository documents keyed by logical key and file stats."""

    def __init__(self) -> None:
        self._resolved_roots: dict[tuple[str, str], Path] = {}
        self._manifests: dict[Path, tuple[PathsSig, Any]] = {}
        self._champion_indices: dict[Path, tuple[PathsSig, Any]] = {}
        self._champions: dict[tuple[Path, str], tuple[PathsSig, Any]] = {}
        self._object_models: dict[Path, tuple[PathsSig, dict[str, Any]]] = {}
        self._items_indices: dict[Path, tuple[PathsSig, tuple[str, dict[str, ItemData]]]] = {}
        self._issues: dict[Path, tuple[PathsSig, Any]] = {}
        self._records: dict[Path, tuple[PathsSig, Any]] = {}
        self._item_groups: dict[Path, tuple[PathsSig, Any]] = {}
        self._runes: dict[Path, tuple[PathsSig, Any]] = {}
        self._summoner_spells: dict[Path, tuple[PathsSig, Any]] = {}
        self._kits: dict[tuple[Path, str], tuple[PathsSig, Any]] = {}
        self._resources: dict[Path, tuple[PathsSig, str | None]] = {}
        self._stores: tuple[dict[Any, tuple[PathsSig, Any]], ...] = (
            self._manifests,
            self._champion_indices,
            self._champions,
            self._object_models,
            self._items_indices,
            self._issues,
            self._records,
            self._item_groups,
            self._runes,
            self._summoner_spells,
            self._kits,
            self._resources,
        )

    def _get_or_load(
        self,
        store: dict[Any, tuple[PathsSig, Any]],
        key: Any,
        paths: Sequence[Path],
        loader: Callable[[], T],
    ) -> T:
        sig = _paths_sig(paths)
        cached = store.get(key)
        if cached is not None and cached[0] == sig:
            return cached[1]
        store.pop(key, None)
        value = loader()
        store[key] = (sig, value)
        return value

    @staticmethod
    def _object_model_paths(resolved_root: Path) -> tuple[Path, ...]:
        return (
            resolved_root / _MANIFEST_REL,
            resolved_root / _ITEMS_REL,
            resolved_root / _CATALOG_REL,
            resolved_root / _GENERATED_STATS_REL,
        )

    def _resolve(self, root: Path) -> Path:
        key = (os.getcwd(), str(root))
        resolved = self._resolved_roots.get(key)
        if resolved is None:
            resolved = root.resolve()
            if len(self._resolved_roots) >= 256:
                self._resolved_roots.clear()
            self._resolved_roots[key] = resolved
        return resolved

    def manifest(self, root: Path, loader: Callable[[], T]) -> T:
        resolved = self._resolve(root)
        return self._get_or_load(self._manifests, resolved, (resolved / _MANIFEST_REL,), loader)

    def champion_index(self, root: Path, loader: Callable[[], T]) -> T:
        resolved = self._resolve(root)
        return self._get_or_load(
            self._champion_indices, resolved, (resolved / _CHAMPION_INDEX_REL,), loader
        )

    def champion(self, root: Path, champion_id: str, loader: Callable[[], T]) -> T:
        resolved = self._resolve(root)
        paths = (
            resolved / _MANIFEST_REL,
            resolved / _CHAMPIONS_DIR_REL / f"{champion_id}.json",
        )
        return self._get_or_load(self._champions, (resolved, champion_id), paths, loader)

    def object_model_data(
        self, root: Path, loader: Callable[[], dict[str, Any]] | None = None
    ) -> dict[str, Any]:
        resolved = self._resolve(root)

        def _default_loader() -> dict[str, Any]:
            from .objects.catalog import load_model_data

            return load_model_data(root, validate=False)

        return self._get_or_load(
            self._object_models,
            resolved,
            self._object_model_paths(resolved),
            loader if loader is not None else _default_loader,
        )

    def items_index(
        self,
        root: Path,
        builder: Callable[[dict[str, Any]], tuple[str, dict[str, ItemData]]] | None = None,
    ) -> tuple[str, dict[str, ItemData]]:
        resolved = self._resolve(root)

        def _build() -> tuple[str, dict[str, ItemData]]:
            model = self.object_model_data(root)
            if builder is not None:
                return builder(model)
            from .stats.data import _all_items_from_model

            return _all_items_from_model(model)

        return self._get_or_load(
            self._items_indices,
            resolved,
            self._object_model_paths(resolved),
            _build,
        )

    def issues(self, root: Path, loader: Callable[[], T]) -> T:
        resolved = self._resolve(root)
        return self._get_or_load(self._issues, resolved, (resolved / _ISSUES_REL,), loader)

    def records(self, root: Path, loader: Callable[[], T]) -> T:
        resolved = self._resolve(root)
        return self._get_or_load(self._records, resolved, (resolved / _RECORDS_REL,), loader)

    def item_groups(self, root: Path, loader: Callable[[], T]) -> T:
        resolved = self._resolve(root)
        return self._get_or_load(
            self._item_groups, resolved, (resolved / _ITEM_GROUPS_REL,), loader
        )

    def runes(self, root: Path, loader: Callable[[], T]) -> T:
        resolved = self._resolve(root)
        return self._get_or_load(self._runes, resolved, (resolved / _RUNES_REL,), loader)

    def summoner_spells(self, root: Path, loader: Callable[[], T]) -> T:
        resolved = self._resolve(root)
        return self._get_or_load(
            self._summoner_spells, resolved, (resolved / _SUMMONERS_REL,), loader
        )

    def kit(self, root: Path, champion_id: str, loader: Callable[[], T]) -> T:
        resolved = self._resolve(root)
        path = resolved / _CHAMPIONS_KB_REL / champion_id / "kit.json"
        return self._get_or_load(self._kits, (resolved, champion_id), (path,), loader)

    def resource_text(self, path: Path) -> str | None:
        resolved = self._resolve(path)

        def _read() -> str | None:
            try:
                st = resolved.stat()
            except OSError:
                return None
            if not stat.S_ISREG(st.st_mode):
                return None
            return resolved.read_text(encoding="utf-8")

        return self._get_or_load(self._resources, resolved, (resolved,), _read)

    def clear(self) -> None:
        self._resolved_roots.clear()
        for store in self._stores:
            store.clear()


DEFAULT_CACHE = RepositoryCache()


def clear_cache() -> None:
    """Clear all cached repository documents from ``DEFAULT_CACHE``."""
    DEFAULT_CACHE.clear()
