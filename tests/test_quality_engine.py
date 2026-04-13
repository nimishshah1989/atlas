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
    proc = subprocess.run(
        [sys.executable, str(SCRIPT)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert REPORT.exists(), f"no report.json after run; stderr={proc.stderr}"
    report = json.loads(REPORT.read_text())
    # S1 removed the composite "overall" score — 7 independent dims now.
    assert "dims" in report, "report missing dims block"
    assert isinstance(report["dims"], dict)
    expected = {
        "security",
        "code",
        "architecture",
        "api",
        "frontend",
        "backend",
        "product",
    }
    seen = set(report["dims"].keys())
    assert expected == seen, (
        f"dim drift: extra={seen - expected} missing={expected - seen}"
    )
    for name, dim in report["dims"].items():
        assert "score" in dim, f"{name} missing score"
        assert "gating" in dim, f"{name} missing gating flag"
