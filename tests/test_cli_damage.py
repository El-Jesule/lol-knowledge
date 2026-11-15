"""Tests for the ``damage`` command."""

from __future__ import annotations

import json

import pytest

from lol_knowledge.cli import main

PHYSICAL = [
    "damage",
    "--raw", "450",
    "--type", "physical",
    "--resistance", "100",
    "--percent-penetration", "0.3",
    "--flat-penetration", "18",
]  # fmt: skip


def test_text_report(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(PHYSICAL) == 0
    captured = capsys.readouterr()
    assert captured.err == ""
    assert captured.out.splitlines() == [
        "damage type: physical",
        "raw damage: 450",
        "resistance: 100",
        "  after flat reduction: 100",
        "  after percent reduction: 100",
        "  after percent penetration: 70",
        "  after flat penetration: 52",
        "multiplier: 0.657895",
        "post-mitigation damage: 296.052632",
        "label: Calculado",
        "rules: lol-knowledge/mechanics/damage-mitigation.md",
    ]


def test_json_report(capsys: pytest.CaptureFixture[str]) -> None:
    assert main([*PHYSICAL, "--json"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["resistance"]["effective"] == 52.0
    assert report["exact"]["post_mitigation_damage"] == "5625/19"
    assert report["label"] == "Calculado"


def test_repeated_options_are_independent_sources(capsys: pytest.CaptureFixture[str]) -> None:
    args = [
        "damage", "--raw", "100", "--type", "magic", "--resistance", "100",
        "--percent-penetration", "0.3", "--percent-penetration", "0.35",
        "--flat-reduction", "10", "--flat-reduction", "10", "--json",
    ]  # fmt: skip
    assert main(args) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["input"]["percent_penetration"] == [0.3, 0.35]
    assert report["resistance"]["after_flat_reduction"] == 80.0
    assert report["resistance"]["effective"] == pytest.approx(36.4)
    assert report["exact"]["multiplier"] == "250/341"


def test_true_damage(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["damage", "--raw", "275", "--type", "true"]) == 0
    out = capsys.readouterr().out
    assert "resistance: not applicable" in out
    assert "post-mitigation damage: 275" in out


@pytest.mark.parametrize(
    ("args", "message"),
    [
        (["--raw", "100", "--type", "physical"], "needs the target's resistance"),
        (["--raw", "100", "--type", "true", "--resistance", "30"], "true damage ignores"),
        (["--raw", "-5", "--type", "magic", "--resistance", "30"], "raw damage"),
        (["--raw", "abc", "--type", "magic", "--resistance", "30"], "is not a number"),
        (
            [
                "--raw",
                "100",
                "--type",
                "physical",
                "--resistance",
                "30",
                "--percent-penetration",
                "30",
            ],
            "between 0 and 1",
        ),
        (
            [
                "--raw",
                "100",
                "--type",
                "physical",
                "--resistance",
                "30",
                "--flat-penetration",
                "-1",
            ],
            "negative",
        ),
    ],
)
def test_invalid_inputs_exit_2_without_output(
    capsys: pytest.CaptureFixture[str], args: list[str], message: str
) -> None:
    assert main(["damage", *args]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.startswith("error: ")
    assert message in captured.err


@pytest.mark.parametrize(
    "args",
    [["damage"], ["damage", "--raw", "1"], ["damage", "--raw", "1", "--type", "chaos"]],
)
def test_usage_errors_exit_2(capsys: pytest.CaptureFixture[str], args: list[str]) -> None:
    with pytest.raises(SystemExit) as excinfo:
        main(args)
    assert excinfo.value.code == 2
    assert capsys.readouterr().out == ""
