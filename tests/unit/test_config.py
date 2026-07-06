"""Configuration contract tests for isolated demo and test runs."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest


pytestmark = pytest.mark.unit


def test_database_path_can_be_overridden(tmp_path: Path) -> None:
    target = tmp_path / "isolated-raqib.sqlite3"
    environment = os.environ.copy()
    environment["RAQIB_DB_PATH"] = str(target)

    result = subprocess.run(
        [sys.executable, "-c", "import config; print(config.DB_PATH)"],
        check=True,
        capture_output=True,
        cwd=Path(__file__).resolve().parents[2],
        env=environment,
        text=True,
    )

    assert Path(result.stdout.strip()) == target.resolve()
