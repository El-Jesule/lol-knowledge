"""XXH64 tests: published vectors and hashes observed in the local client."""

from __future__ import annotations

import pytest
from binmodel.xxh64 import path_hash, xxh64


@pytest.mark.parametrize(
    ("data", "expected"),
    [
        (b"", 0xEF46DB3751D8E999),
        (b"a", 0xD24EC4F1A98C6E5B),
        (b"abc", 0x44BC2CF5AD770999),
    ],
)
def test_published_vectors(data, expected):
    assert xxh64(data) == expected


# Observed in Zaahen.wad.client and zaahen.bin (content 16.22.8348910), 2026-11-15.
@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("data/characters/zaahen/zaahen.bin", 0xDA8757EDBD3A54D7),
        ("data/characters/zaahen/skins/skin0.bin", 0x0F6F4BCA77C5044B),
        ("assets/characters/viego/hud/icons2d/viego_w.dds", 2274810219433150328),
        ("assets/characters/zaahen/hud/icons2d/zaahenp.dds", 8214508006260588659),
        ("assets/spells/textures/darius_cleave_outside.tex", 420034760926066490),
    ],
)
def test_client_path_hashes(path, expected):
    assert path_hash(path) == expected


def test_path_hash_lowercases():
    assert path_hash("DATA/Characters/Zaahen/Zaahen.bin") == 0xDA8757EDBD3A54D7


def test_long_input_uses_the_stripe_loop():
    # 100 bytes covers the 32-byte stripes, an 8-byte lane, a 4-byte lane and the tail.
    assert xxh64(bytes(range(100))) != xxh64(bytes(range(99)))
    assert xxh64(b"x" * 64, seed=1) != xxh64(b"x" * 64)
