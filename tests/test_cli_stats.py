"""Tests for the ``stats`` command against the real snapshot and catalog."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from lol_knowledge.cli import main

ROOT = Path(__file__).resolve().parents[1]


def run(capsys, *args):
    code = main(["stats", "--root", str(ROOT), *args])
    return code, capsys.readouterr()


def test_level_one_text_report(capsys):
    code, captured = run(capsys, "--champion", "zaahen", "--level", "1")
    assert code == 0, captured.err
    out = captured.out
    assert "champion: Zaahen (Zaahen), patch 16.20.1, level 1" in out
    assert "  health: 640 [Oficial]" in out
    assert "  attack_damage: 63 [Oficial]" in out
    assert "note: ddragon-attack-damage-growth does not affect level 1" in out
    assert "  Q La guja de los Oscuros: 10/9/8/7/6" in out
    assert out.rstrip().endswith("label: Calculado")


def test_ad_is_blocked_above_level_one_and_other_stats_resolve(capsys):
    code, captured = run(capsys, "--champion", "Zaahen", "--level", "11", "--item", "3067")
    assert code == 0, captured.err
    out = captured.out
    assert "  attack_damage: blocked: ddragon-attack-damage-growth" in out
    assert "  health: 1840.35 (base 1640.35 + bonus 200) [Derivado]" in out
    assert "cooldowns (ability haste 10): [Derivado]" in out
    assert "  R Redención funesta: 100/86.363636/72.727273" in out


def test_assumption_resolves_ad_with_pending_label(capsys):
    code, captured = run(
        capsys,
        "--champion",
        "Zaahen",
        "--level",
        "11",
        "--assume",
        "attackdamageperlevel=4",
        "--json",
    )
    assert code == 0, captured.err
    report = json.loads(captured.out)
    ad = report["stats"]["attack_damage"]
    assert ad["status"] == "resolved"
    assert ad["label"] == "Pendiente de verificación"
    assert ad["total"] == pytest.approx(63 + 4 * 10 * 0.8775)
    assert report["assumptions"] == {"attackdamageperlevel": 4.0}


def test_json_report_structure(capsys):
    code, captured = run(capsys, "--champion", "Zaahen", "--level", "1", "--item", "3036", "--json")
    assert code == 0, captured.err
    report = json.loads(captured.out)
    assert report["label"] == "Calculado"
    assert report["patch"] == "16.20.1"
    assert report["items"] == [{"id": "3036", "name": "Recuerdos de lord Dominik"}]
    pen = report["stats"]["armor_penetration_percent"]
    assert pen["total"] == pytest.approx(0.35)
    assert pen["contributions"][0]["source"].startswith("data:item:3036")
    assert report["stats"]["tenacity"]["status"] == "pending"
    ehp = report["metrics"]["effective_health"]
    assert ehp["physical"]["value"] == pytest.approx(640 * 1.36)
    assert ehp["true"]["value"] == 640
    cooldowns = report["metrics"]["cooldowns"]
    assert cooldowns["ability_haste"] == 0
    assert cooldowns["spells"][3]["effective"] == [110, 95, 80]


@pytest.mark.parametrize(
    ("args", "message"),
    [
        (["--champion", "Nobody", "--level", "1"], "is not in the snapshot"),
        (["--champion", "../Zaahen", "--level", "1"], "is not in the snapshot"),
        (["--champion", "Zaahen", "--level", "0"], "level must be between"),
        (["--champion", "Zaahen", "--level", "1", "--item", "1001"], "curated object catalog"),
        (["--champion", "Zaahen", "--level", "5", "--assume", "x"], "FIELD=VALUE"),
        (["--champion", "Zaahen", "--level", "5", "--assume", "hp=1"], "open data issue"),
        (
            [
                "--champion",
                "Zaahen",
                "--level",
                "5",
                "--assume",
                "attackdamageperlevel=1",
                "--assume",
                "attackdamageperlevel=2",
            ],
            "repeats",
        ),
    ],
)
def test_invalid_requests_exit_2(capsys, args, message):
    code, captured = run(capsys, *args)
    assert code == 2
    assert captured.out == ""
    assert captured.err.startswith("error: ")
    assert message in captured.err


def test_missing_snapshot_exits_2(capsys, tmp_path):
    assert main(["stats", "--root", str(tmp_path), "--champion", "Zaahen", "--level", "1"]) == 2
    assert "not found" in capsys.readouterr().err
