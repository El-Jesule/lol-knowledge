"""WAD v3 entry reader tests on synthetic archives."""

from __future__ import annotations

import pytest
from binmodel.wad import WadError, read_entry
from propbuild import encode_wad


def _write(tmp_path, files):
    path = tmp_path / "Test.wad.client"
    path.write_bytes(encode_wad(files))
    return path


def test_reads_raw_and_zstd_entries(tmp_path):
    wad = _write(tmp_path, {"data/a.bin": (0, b"PROPraw"), "data/b.bin": (3, b"PROP" * 50)})
    assert read_entry(wad, "data/a.bin") == b"PROPraw"
    assert read_entry(wad, "DATA/B.bin") == b"PROP" * 50


def test_missing_entry_is_an_error(tmp_path):
    wad = _write(tmp_path, {"data/a.bin": (0, b"x")})
    with pytest.raises(WadError, match="not in"):
        read_entry(wad, "data/missing.bin")


def test_subchunked_entries_are_refused_not_guessed(tmp_path):
    wad = _write(tmp_path, {"data/a.bin": (4, b"PROP" * 10)})
    with pytest.raises(WadError, match="type 4"):
        read_entry(wad, "data/a.bin")


def test_rejects_non_wad_files(tmp_path):
    path = tmp_path / "x.wad.client"
    path.write_bytes(b"XX" + bytes(300))
    with pytest.raises(WadError, match="not a WAD"):
        read_entry(path, "data/a.bin")


def test_rejects_corrupt_compressed_data(tmp_path):
    data = bytearray(encode_wad({"data/a.bin": (3, b"PROP" * 50)}))
    data[-5] ^= 0xFF
    path = tmp_path / "bad.wad.client"
    path.write_bytes(bytes(data))
    with pytest.raises(WadError):
        read_entry(path, "data/a.bin")
