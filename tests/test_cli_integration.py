"""Integration tests that run ``python -m lol_knowledge`` as a subprocess.

These tests require the package to be installed in the active interpreter
(``pip install -e .``). They intentionally do not inject ``PYTHONPATH``:
a missing installation must fail visibly instead of being hidden.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from lol_knowledge import __version__

REPO_ROOT = Path(__file__).resolve().parents[1]


def run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    """Run the CLI module with the current interpreter and capture UTF-8 output."""
    return subprocess.run(
        [sys.executable, "-m", "lol_knowledge", *args],
        cwd=REPO_ROOT,
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
