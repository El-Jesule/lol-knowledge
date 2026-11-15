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
    assert "champion: Zaahen (Zaahen), patch 16.22.1, level 1" in out
    assert "  health: 640 [Oficial]" in out
    assert "  attack_damage: 63 [Oficial]" in out
    assert "note: ddragon-attack-damage-growth does not affect level 1" in out
    assert "  Q La guja de los Oscuros: 8/7.5/7/6.5/6" in out
    assert out.rstrip().endswith("label: Calculado")


def test_attack_speed_scales_growth_and_items_by_the_client_ratio(capsys):
    code, captured = run(capsys, "--champion", "Zaahen", "--level", "10", "--item", "3153")
    assert code == 0, captured.err
    out = captured.out
    # 2.5 % x 9 x (0.7025 + 0.0175 x 9) = 19.35 % growth + 25 % from the item, x ratio 0.625.
    assert "  attack_speed_bonus: 0.4435 (base 0.1935 + bonus 0.25) [Derivado]" in out
    assert "  attack_speed: 0.902188 (base 0.625 + bonus 0.277187) [Derivado]" in out
    code, captured = run(
        capsys, "--champion", "Zaahen", "--level", "10", "--item", "3153", "--json"
    )
    speed = json.loads(captured.out)["stats"]["attack_speed"]
    assert speed["exact"] == "2887/3200"
    assert speed["capped"] is False and speed["cap"] == 3.0
    assert speed["contributions"][1]["source"].startswith(
        "lol-knowledge/derived/champion-records.json Zaahen.attackspeedratio (16.22."
    )


def test_ad_uses_the_client_record_of_the_same_patch_as_derived(capsys):
    code, captured = run(capsys, "--champion", "Zaahen", "--level", "11", "--item", "3067")
    assert code == 0, captured.err
    out = captured.out
    assert "  attack_damage: 98.1 [Derivado]\n" in out
    assert "  health: 1840.35 (base 1640.35 + bonus 200) [Derivado]" in out
    assert "cooldowns (ability haste 10): [Derivado]" in out
    assert "  R Redención funesta: 100/86.363636/72.727273" in out


def test_ad_without_a_client_record_stays_blocked(capsys):
    code, captured = run(capsys, "--champion", "Senna", "--level", "11")
    assert code == 0, captured.err
    assert "  attack_damage: blocked: ddragon-attack-damage-growth" in captured.out
    assert "No derived record for Senna" in captured.out


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
    assert report["patch"] == "16.22.1"
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
