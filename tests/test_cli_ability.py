"""Tests for the ``ability`` command."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from lol_knowledge.cli import main

ROOT = Path(__file__).resolve().parents[1]
BASE = ["ability", "--root", str(ROOT), "--champion", "Zaahen", "--level", "16"]


def run(capsys, *args):
    code = main([*BASE, *args])
    return code, capsys.readouterr()


def test_text_report(capsys):
    code, captured = run(
        capsys,
        "--ability",
        "R",
        "--rank",
        "3",
        "--item",
        "3036",
        "--target-armor",
        "150",
        "--target-mr",
        "50",
    )
    assert code == 0, captured.err
    lines = captured.out.splitlines()
    assert "ability: R Redención funesta, rank 3" in lines
    assert "  part 1 physical: raw 620 [Derivado] (rank, bonus_attack_damage)" in lines
    assert (
        "    resistance 150 -> 68.25 (percent pen 35%, 30%, flat pen 0); "
        "multiplier 0.594354 -> 368.499257"
    ) in lines
    assert "  total: 368.499257" in lines
    assert lines[-1] == "label: Calculado (weakest input: Derivado)"


def test_json_report_against_a_target_champion(capsys):
    code, captured = run(
        capsys,
        "--ability", "E", "--rank", "5", "--case", "edge", "--learned", "R=3",
        "--target-champion", "ahri", "--target-level", "16", "--json",
    )  # fmt: skip
    assert code == 0, captured.err
    report = json.loads(captured.out)
    assert report["target"]["description"].startswith("Ahri level 16")
    (case,) = report["cases"]
    assert case["id"] == "edge"
    assert [part["damage_type"] for part in case["parts"]] == ["physical", "magic"]
    assert case["parts"][0]["percent_penetration"] == [0.3]
    assert case["total"] == pytest.approx(sum(part["damage"] for part in case["parts"]))


@pytest.mark.parametrize(
    ("args", "message"),
    [
        (["--ability", "R", "--rank", "3"], "give --target-champion, or both"),
        (
            [
                "--ability",
                "R",
                "--rank",
                "3",
                "--target-armor",
                "1",
                "--target-mr",
                "1",
                "--target-champion",
                "Ahri",
            ],
            "not both",
        ),
        (["--ability", "R", "--rank", "3", "--target-champion", "Ahri"], "needs --target-level"),
        (
            [
                "--ability",
                "R",
                "--rank",
                "3",
                "--target-armor",
                "1",
                "--target-mr",
                "1",
                "--target-level",
                "5",
            ],
            "need --target-champion",
        ),
        (
            ["--ability", "R", "--rank", "4", "--target-armor", "1", "--target-mr", "1"],
            "rank must be between 1 and 3",
        ),
        (
            [
                "--ability",
                "R",
                "--rank",
                "3",
                "--learned",
                "R=2",
                "--target-armor",
                "1",
                "--target-mr",
                "1",
            ],
            "contradicts",
        ),
        (
            [
                "--ability",
                "R",
                "--rank",
                "3",
                "--learned",
                "Q=x",
                "--target-armor",
                "1",
                "--target-mr",
                "1",
            ],
            "rank must be an integer",
        ),
        (
            [
                "--ability",
                "E",
                "--rank",
                "5",
                "--case",
                "edge",
                "--target-armor",
                "1",
                "--target-mr",
                "1",
            ],
            "target:max_health",
        ),
        (
            [
                "--ability",
                "E",
                "--rank",
                "5",
                "--case",
                "rim",
                "--target-armor",
                "1",
                "--target-mr",
                "1",
            ],
            "unknown case",
        ),
        (
            ["--ability", "R", "--rank", "3", "--target-armor", "abc", "--target-mr", "1"],
            "not a number",
        ),
        (
            ["--ability", "X", "--rank", "1", "--target-armor", "1", "--target-mr", "1"],
            "no kit entry",
        ),
    ],
)
def test_invalid_requests_exit_2(capsys, args, message):
    code, captured = run(capsys, *args)
    assert code == 2
    assert captured.out == ""
    assert captured.err.startswith("error: ")
    assert message in captured.err


def test_champion_without_kit(capsys):
    code = main(
        ["ability", "--root", str(ROOT), "--champion", "Lux", "--level", "1", "--ability", "Q",
         "--rank", "1", "--target-armor", "1", "--target-mr", "1"]
    )  # fmt: skip
    assert code == 2
    assert "Lux has no kit yet" in capsys.readouterr().err
