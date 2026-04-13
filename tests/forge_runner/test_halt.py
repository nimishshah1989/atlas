"""Tests for scripts/forge_runner/halt.py (T024).

Tests each HaltDecision with mocked subprocess calls to quality scripts.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch


from scripts.forge_runner.halt import EXIT_CODES, HaltDecision, evaluate_halt


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_ctx(repo: Path) -> SimpleNamespace:
    return SimpleNamespace(repo=repo)


def _mock_run(returncode: int = 0, stdout: str = "", stderr: str = "") -> MagicMock:
    """Create a mock subprocess.CompletedProcess."""
    mock = MagicMock()
    mock.returncode = returncode
    mock.stdout = stdout
    mock.stderr = stderr
    return mock


# ---------------------------------------------------------------------------
# COMPLETE decision
# ---------------------------------------------------------------------------


class TestHaltComplete:
    def test_complete_when_quality_passes_and_no_validator(self, fake_repo: Path) -> None:
        """COMPLETE when quality gate passes (exit 0) and no validator script."""
        ctx = _make_ctx(fake_repo)

        # No .quality/checks.py in fake_repo — returns False (no script)
        # We need to create it or mock subprocess
        quality_script = fake_repo / ".quality" / "checks.py"
        quality_script.parent.mkdir(exist_ok=True)
        quality_script.write_text("import sys; sys.exit(0)\n")

        # No validate-v1-completion.py either → criteria_ok defaults True
        result = evaluate_halt(ctx)
        assert result == HaltDecision.COMPLETE

    def test_complete_when_both_scripts_pass(self, fake_repo: Path) -> None:
        """COMPLETE when both quality gate and criteria validator pass."""
        ctx = _make_ctx(fake_repo)

        (fake_repo / ".quality").mkdir(exist_ok=True)
        (fake_repo / ".quality" / "checks.py").write_text("import sys; sys.exit(0)\n")
        scripts_dir = fake_repo / "scripts"
        scripts_dir.mkdir(exist_ok=True)
        (scripts_dir / "validate-v1-completion.py").write_text("import sys; sys.exit(0)\n")

        result = evaluate_halt(ctx)
        assert result == HaltDecision.COMPLETE


# ---------------------------------------------------------------------------
# STALLED decision
# ---------------------------------------------------------------------------


class TestHaltStalled:
    def test_stalled_when_quality_fails(self, fake_repo: Path) -> None:
        """STALLED when quality gate script exits non-zero."""
        ctx = _make_ctx(fake_repo)

        (fake_repo / ".quality").mkdir(exist_ok=True)
        (fake_repo / ".quality" / "checks.py").write_text("import sys; sys.exit(1)\n")

        result = evaluate_halt(ctx)
        assert result == HaltDecision.STALLED

    def test_stalled_when_quality_script_missing(self, fake_repo: Path) -> None:
        """STALLED when quality script does not exist (conservative default)."""
        ctx = _make_ctx(fake_repo)
        # No .quality/checks.py in fake_repo

        result = evaluate_halt(ctx)
        assert result == HaltDecision.STALLED

    def test_stalled_when_criteria_validator_fails(self, fake_repo: Path) -> None:
        """STALLED when quality passes but criteria validator exits non-zero."""
        ctx = _make_ctx(fake_repo)

        (fake_repo / ".quality").mkdir(exist_ok=True)
        (fake_repo / ".quality" / "checks.py").write_text("import sys; sys.exit(0)\n")
        scripts_dir = fake_repo / "scripts"
        scripts_dir.mkdir(exist_ok=True)
        (scripts_dir / "validate-v1-completion.py").write_text("import sys; sys.exit(1)\n")

        result = evaluate_halt(ctx)
        assert result == HaltDecision.STALLED

    def test_stalled_when_quality_subprocess_timeout(self, fake_repo: Path) -> None:
        """STALLED when subprocess.run raises TimeoutExpired."""
        ctx = _make_ctx(fake_repo)

        (fake_repo / ".quality").mkdir(exist_ok=True)
        (fake_repo / ".quality" / "checks.py").write_text("# dummy\n")

        with patch(
            "scripts.forge_runner.halt.subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd="python", timeout=120),
        ):
            result = evaluate_halt(ctx)

        assert result == HaltDecision.STALLED


# ---------------------------------------------------------------------------
# EXIT_CODES dict
# ---------------------------------------------------------------------------


class TestExitCodes:
    def test_complete_maps_to_zero(self) -> None:
        assert EXIT_CODES[HaltDecision.COMPLETE.value] == 0

    def test_stalled_maps_to_two(self) -> None:
        assert EXIT_CODES[HaltDecision.STALLED.value] == 2

    def test_auth_failure_maps_to_one(self) -> None:
        assert EXIT_CODES["auth_failure"] == 1

    def test_chunk_failed_maps_to_three(self) -> None:
        assert EXIT_CODES["chunk_failed"] == 3

    def test_crash_maps_to_four(self) -> None:
        assert EXIT_CODES["crash"] == 4

    def test_dead_man_maps_to_five(self) -> None:
        assert EXIT_CODES["dead_man_detected"] == 5

    def test_concurrent_maps_to_six(self) -> None:
        assert EXIT_CODES["concurrent_runner"] == 6
