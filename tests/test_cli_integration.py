"""Integration tests that run ``python -m lol_knowledge`` as a subprocess.

These tests require the package to be installed in the active interpreter
(``pip install -e .``). They intentionally do not inject ``PYTHONPATH``:
a missing installation must fail visibly instead of being hidden.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from lol_knowledge import __version__

REPO_ROOT = Path(__file__).resolve().parents[1]


def run_cli(*args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    """Run the CLI module with the current interpreter and capture UTF-8 output."""
    return subprocess.run(
        [sys.executable, "-m", "lol_knowledge", *args],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=60,
        check=False,
    )


def test_version_command_in_subprocess() -> None:
    result = run_cli("version")

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == __version__


def test_help_in_subprocess() -> None:
    result = run_cli("--help")

    assert result.returncode == 0, result.stderr
    assert "usage: lol_knowledge" in result.stdout
    assert "--version" in result.stdout


def test_damage_command_in_subprocess() -> None:
    result = run_cli(
        "damage",
        "--raw",
        "450",
        "--type",
        "physical",
        "--resistance",
        "100",
        "--percent-penetration",
        "0.3",
        "--flat-penetration",
        "18",
    )

    assert result.returncode == 0, result.stderr
    assert "post-mitigation damage: 296.052632" in result.stdout
    assert result.stderr == ""


def test_damage_command_rejects_invalid_input_in_subprocess() -> None:
    result = run_cli("damage", "--raw", "100", "--type", "physical")

    assert result.returncode == 2
    assert result.stdout == ""
    assert result.stderr.startswith("error: ")


def test_stats_command_in_subprocess() -> None:
    result = run_cli("stats", "--champion", "Senna", "--level", "11")

    assert result.returncode == 0, result.stderr
    assert "attack_damage: blocked: ddragon-attack-damage-growth" in result.stdout
    assert "label: Calculado" in result.stdout


def test_output_is_utf8_even_with_a_legacy_console_encoding() -> None:
    """Regression: on Windows a piped stdout defaults to the ANSI code page (cp1252).

    Accented text such as "Maná" must still reach the caller as UTF-8.
    """
    env = {**os.environ, "PYTHONIOENCODING": "cp1252", "PYTHONUTF8": "0"}

    result = run_cli("stats", "--champion", "Zaahen", "--level", "1", env=env)

    assert result.returncode == 0, result.stderr
    assert "resource: Maná" in result.stdout
    assert "La guja de los Oscuros" in result.stdout


def test_errors_are_utf8_even_with_a_legacy_console_encoding() -> None:
    env = {**os.environ, "PYTHONIOENCODING": "cp1252", "PYTHONUTF8": "0"}

    result = run_cli("stats", "--champion", "Ñoño", "--level", "1", env=env)

    assert result.returncode == 2
    assert "Ñoño" in result.stderr


def test_ability_command_in_subprocess() -> None:
    result = run_cli(
        "ability",
        "--champion",
        "Zaahen",
        "--level",
        "16",
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

    assert result.returncode == 0, result.stderr
    assert "ability: R Redención funesta, rank 3" in result.stdout
    assert "total: 368.499257" in result.stdout
