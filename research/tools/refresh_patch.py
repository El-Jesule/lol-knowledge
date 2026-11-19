"""Regenerate every client-derived file for a new patch and say what changed.

After ``python -m lol_knowledge update --patch <patch>`` has refreshed the Data
Dragon snapshot, this runs the client extractors against the installed game and
compares each result with the committed file (odd/procedures/patch-update.md):

1. ``lol-knowledge/objects/catalog-stats.json`` (``lol_knowledge.objects --generate-stats``);
2. ``lol-knowledge/derived/champion-records.json`` (``binmodel.records``);
3. ``lol-knowledge/derived/item-effects.json`` (``binmodel.item_effects``);
4. each committed champion kit, rebuilt from the client bin (``binmodel.bin2json`` →
   ``binmodel`` → ``binmodel.kitgen``) and compared without its provenance fields.

Without ``--write`` nothing in the repository changes: the results go to a
temporary directory and only the report is printed. With ``--write`` the files
of steps 1–3 replace the committed ones; kits are never written, because a kit
keeps citing the bin its numbers were first extracted from (a change in a kit
is a curation task, not a refresh).

Usage::

    PYTHONPATH=research python research/tools/refresh_patch.py --game "<Game>" \\
        --hashes <dir with CommunityDragon hash lists> --retrieved-at 2026-11-19 [--write]

The hash lists (``hashes.binentries.txt``, ``hashes.binfields.txt``,
``hashes.bintypes.txt``, ``hashes.rst.xxh3.txt``) come from the
CommunityDragon/Data repository on GitHub. Exit code: 0 done, 1 a step failed,
2 bad environment (no snapshot, client of another patch, missing files).
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import re
import shutil
import sys
import tempfile
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
RECORDS = Path("lol-knowledge/derived/champion-records.json")
ITEM_EFFECTS = Path("lol-knowledge/derived/item-effects.json")
CATALOG_STATS = Path("lol-knowledge/objects/catalog-stats.json")
HASH_LISTS = (
    "hashes.binentries.txt",
    "hashes.binfields.txt",
    "hashes.bintypes.txt",
    "hashes.rst.xxh3.txt",
)
TOOLTIP_PREFIXES = (
    "spell_",
    "buff_",
    "generatedtip_spell_",
    "generatedtip_passive_",
    "generatedtip_buff_",
)
# Fields that only say where and when a value was read.
PROVENANCE = frozenset(
    {"bin_sha256", "strings_sha256", "content_version", "game_version", "retrieved_at", "source"}
)
VERSION = re.compile(r"(\d+)\.(\d+)\.\d+\+.+")


class RefreshError(Exception):
    """The environment does not allow a refresh without guessing."""


def differences(old: Any, new: Any, path: str = "") -> Iterator[str]:
    """Paths whose values differ, ignoring provenance fields at any depth."""
    if isinstance(old, dict) and isinstance(new, dict):
        for key in sorted(set(old) | set(new)):
            if key in PROVENANCE:
                continue
            where = f"{path}.{key}" if path else str(key)
            if key not in old:
                yield f"+ {where}"
            elif key not in new:
                yield f"- {where}"
            else:
                yield from differences(old[key], new[key], where)
        return
    if isinstance(old, list) and isinstance(new, list) and len(old) == len(new):
        for index, (left, right) in enumerate(zip(old, new, strict=True)):
            yield from differences(left, right, f"{path}[{index}]")
        return
    if old != new:
        before = json.dumps(old, ensure_ascii=False)[:80]
        after = json.dumps(new, ensure_ascii=False)[:80]
        yield f"~ {path}: {before} -> {after}"


def _without_sources(value: Any) -> Any:
    """A kit without the version suffix of its ``source`` strings."""
    if isinstance(value, dict):
        return {
            key: re.sub(r" \(\d+\.\d+\.\d+\+[^)]+\)$", "", item)
            if key == "source" and isinstance(item, str)
            else _without_sources(item)
            for key, item in value.items()
            if key not in {"content_version", "verified_against", "game_version"}
        }
    if isinstance(value, list):
        return [_without_sources(item) for item in value]
    return value


def _run(main: Callable[[list[str]], int], argv: list[str]) -> tuple[int, str]:
    out = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
        code = main(argv)
    return code, out.getvalue().strip()


def _read(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def client_version(game: Path) -> str:
    path = game / "content-metadata.json"
    if not path.is_file():
        raise RefreshError(f"{path} not found: --game must be the client's Game directory")
    version = _read(path).get("version")
    if not isinstance(version, str) or VERSION.fullmatch(version) is None:
        raise RefreshError(f"{path}: unexpected version {version!r}")
    return version


def snapshot_patch(root: Path) -> str:
    manifest = root / "data" / "current" / "manifest.json"
    if not manifest.is_file():
        raise RefreshError("no snapshot: run python -m lol_knowledge update first")
    patch = _read(manifest).get("patch")
    if not isinstance(patch, str):
        raise RefreshError(f"{manifest}: no patch")
    return patch


def _report(name: str, old_path: Path, new_path: Path, limit: int = 40) -> list[str]:
    if not old_path.is_file():
        return [f"{name}: new file"]
    changes = list(differences(_read(old_path), _read(new_path)))
    lines = [f"{name}: {len(changes)} change(s) besides provenance"]
    lines += [f"  {change}" for change in changes[:limit]]
    if len(changes) > limit:
        lines.append(f"  … {len(changes) - limit} more")
    return lines


def refresh(root: Path, game: Path, hashes: Path, retrieved_at: str, *, write: bool) -> int:
    # Imported here so that --help works without PYTHONPATH.
    from binmodel import bin2json, item_effects, kitgen, records
    from binmodel import cli as extract_cli
    from tools import extract_rst

    from lol_knowledge.objects.__main__ import main as objects_main

    version = client_version(game)
    patch = snapshot_patch(root)
    major_minor = ".".join(VERSION.fullmatch(version).groups())
    if not patch.startswith(f"{major_minor}."):
        raise RefreshError(f"client {major_minor} but snapshot {patch}: update the snapshot first")
    missing = [name for name in HASH_LISTS if not (hashes / name).is_file()]
    if missing:
        raise RefreshError(f"hash lists missing in {hashes}: {missing}")
    final = game / "DATA" / "FINAL"
    failed = False
    lines = [f"client {version}; snapshot {patch}"]
    with tempfile.TemporaryDirectory() as scratch:
        work = Path(scratch)
        stats_backup = work / "catalog-stats.committed.json"
        shutil.copyfile(root / CATALOG_STATS, stats_backup)
        code, text = _run(objects_main, ["--root", str(root), "--generate-stats"])
        failed |= code != 0
        lines += [f"catalog-stats: {text}"]
        lines += _report("catalog-stats", stats_backup, root / CATALOG_STATS)
        if not write:
            shutil.copyfile(stats_backup, root / CATALOG_STATS)
        steps = (
            (
                RECORDS,
                records.main,
                ["--wad-dir", str(final / "Champions"),
                 "--index", str(root / "data/current/champion-index.json")],
            ),
            (
                ITEM_EFFECTS,
                item_effects.main,
                ["--wad", str(final / "Global.wad.client"),
                 "--strings", str(final / "Localized/Global.es_ES.wad.client"),
                 "--rst-hashes", str(hashes / "hashes.rst.xxh3.txt"),
                 "--ids-from", str(root / CATALOG_STATS)],
            ),
        )  # fmt: skip
        for relative, main, argv in steps:
            output = work / relative.name
            code, text = _run(
                main,
                [*argv, "--content-version", version, "--retrieved-at", retrieved_at,
                 "--output", str(output)],
            )  # fmt: skip
            lines.append(f"{relative.name}: {text}")
            if code != 0:
                failed = True
                continue
            lines += _report(relative.name, root / relative, output)
            if write:
                shutil.copyfile(output, root / relative)
        for kit_path in sorted((root / "lol-knowledge" / "champions").glob("*/kit.json")):
            champion = kit_path.parent.name
            lower = champion.lower()
            spec = root / "research" / "kits" / f"{champion}.spec.json"
            tooltips = work / f"{lower}-tooltips.json"
            prefixes = [
                arg for prefix in TOOLTIP_PREFIXES for arg in ("--prefix", f"{prefix}{lower}")
            ]
            steps_ok = True
            for main, argv in (
                (extract_rst.main, ["--wad", str(final / "Localized/Global.es_ES.wad.client"),
                                    "--hash-table", str(hashes / "hashes.rst.xxh3.txt"),
                                    "--output", str(tooltips), "--retrieved-at", retrieved_at,
                                    *prefixes]),
                (bin2json.main, ["--wad", str(final / "Champions" / f"{champion}.wad.client"),
                                 "--entry", f"data/characters/{lower}/{lower}.bin",
                                 "--hashes", str(hashes), "--names", str(tooltips),
                                 "--output", str(work / f"{lower}.bin.json")]),
                (extract_cli.main, ["--input", str(work / f"{lower}.bin.json"),
                                    "--output", str(work / f"{lower}-extract.json"),
                                    "--game-version", major_minor, "--content-version", version]),
                (kitgen.main, ["--extract", str(work / f"{lower}-extract.json"),
                               "--tooltips", str(tooltips), "--spec", str(spec),
                               "--output", str(work / f"{lower}-kit.json")]),
            ):  # fmt: skip
                code, text = _run(main, argv)
                if code != 0:
                    lines.append(f"kit {champion}: step failed: {text}")
                    failed, steps_ok = True, False
                    break
            if not steps_ok:
                continue
            changes = list(
                differences(
                    _without_sources(_read(kit_path)),
                    _without_sources(_read(work / f"{lower}-kit.json")),
                )
            )
            lines.append(f"kit {champion}: {len(changes)} change(s) besides provenance")
            lines += [f"  {change}" for change in changes]
    print("\n".join(lines))
    print(
        "next: catalog game_version/catalog_version, data-issues patches, curated effects "
        "against the patch notes, tests and docs that name the patch "
        "(odd/procedures/patch-update.md)"
    )
    return 1 if failed else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--game", type=Path, required=True, help="The client's Game directory.")
    parser.add_argument("--hashes", type=Path, required=True)
    parser.add_argument("--retrieved-at", required=True)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--write", action="store_true", help="Replace the committed files.")
    args = parser.parse_args(argv)
    try:
        return refresh(args.root, args.game, args.hashes, args.retrieved_at, write=args.write)
    except (RefreshError, OSError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
