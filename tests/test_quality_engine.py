"""Smoke tests for the .quality/ scorer.

Verifies the scorer is importable, runnable, and emits a report with the
expected top-level shape. Detailed per-dimension assertions live with each
dimension's own check; this file just guards the contract.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / ".quality" / "checks.py"
REPORT = REPO_ROOT / ".quality" / "report.json"
STANDARDS = REPO_ROOT / ".quality" / "standards.md"


def test_quality_script_exists():
    assert SCRIPT.exists(), "quality engine script missing"
    assert STANDARDS.exists(), "frozen standards missing"


def test_quality_script_runs_and_emits_report():
    result = subprocess.run(
        [sys.executable, str(SCRIPT)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=180,
    )
    # Exit code may be non-zero (gate may fail at v1 baseline). What we
    # require is that the report file is produced and parseable.
    assert REPORT.exists(), f"no report.json after run; stderr={result.stderr}"
    data = json.loads(REPORT.read_text())
    assert "overall" in data
    assert isinstance(data["overall"], (int, float))
    assert "dimensions" in data
    assert isinstance(data["dimensions"], list)
    assert data["dimensions"], "no dimensions scored"
    expected = {"security", "code", "architecture", "frontend",
                "devops", "docs", "api"}
    seen = {d["dimension"] for d in data["dimensions"] if "dimension" in d}
    assert expected.issubset(seen), f"missing dimensions: {expected - seen}"
