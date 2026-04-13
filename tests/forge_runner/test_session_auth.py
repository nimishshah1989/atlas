"""Tests for session.py authentication error handling (T029).

Verifies that ProcessError with auth-related stderr raises AuthFailure,
and the caller receives it (does NOT mark chunk FAILED, should reset to PENDING).
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import AsyncGenerator
from unittest.mock import patch

import pytest

from scripts.forge_runner.session import AuthFailure, run_session
from scripts.forge_runner.state import ChunkRow


def _fake_chunk(chunk_id: str = "V1-1") -> ChunkRow:
    return ChunkRow(
        id=chunk_id,
        title=f"Title {chunk_id}",
        status="IN_PROGRESS",
        attempts=1,
        last_error=None,
        plan_version="v1",
        depends_on=[],
        created_at="2026-01-01T00:00:00+05:30",
        updated_at="2026-01-01T00:00:00+05:30",
        started_at=None,
        finished_at=None,
        runner_pid=None,
        failure_reason=None,
    )


def _make_ctx(repo: Path) -> SimpleNamespace:
    return SimpleNamespace(repo=repo, timeout_sec=120, max_turns=10)


class _FakeProcessError(Exception):
    def __init__(self, stderr: str, returncode: int = 1) -> None:
        self.stderr = stderr
        self.returncode = returncode
        super().__init__(stderr)


class TestSessionAuthFailure:
    @pytest.mark.asyncio
    async def test_auth_failure_on_401_stderr(self, fake_repo: Path) -> None:
        """ProcessError with '401' in stderr raises AuthFailure."""
        chunk = _fake_chunk()
        ctx = _make_ctx(fake_repo)

        async def _auth_fail_query(*args, **kwargs) -> AsyncGenerator:
            raise _FakeProcessError("401 unauthorized authentication failed")
            yield

        with patch(
            "scripts.forge_runner.session.claude_agent_sdk.query",
            side_effect=_auth_fail_query,
        ):
            with patch("scripts.forge_runner.session.ProcessError", _FakeProcessError):
                with pytest.raises(AuthFailure):
                    async for _ in run_session(chunk, ctx):
                        pass

    @pytest.mark.asyncio
    async def test_auth_failure_on_authentication_keyword(self, fake_repo: Path) -> None:
        """ProcessError with 'authentication' in stderr raises AuthFailure."""
        chunk = _fake_chunk()
        ctx = _make_ctx(fake_repo)

        async def _auth_fail_query(*args, **kwargs) -> AsyncGenerator:
            raise _FakeProcessError("authentication error: invalid credentials")
            yield

        with patch(
            "scripts.forge_runner.session.claude_agent_sdk.query",
            side_effect=_auth_fail_query,
        ):
            with patch("scripts.forge_runner.session.ProcessError", _FakeProcessError):
                with pytest.raises(AuthFailure):
                    async for _ in run_session(chunk, ctx):
                        pass

    @pytest.mark.asyncio
    async def test_auth_failure_on_invalid_api_key(self, fake_repo: Path) -> None:
        """ProcessError with 'invalid api key' in stderr raises AuthFailure."""
        chunk = _fake_chunk()
        ctx = _make_ctx(fake_repo)

        async def _auth_fail_query(*args, **kwargs) -> AsyncGenerator:
            raise _FakeProcessError("invalid api key provided")
            yield

        with patch(
            "scripts.forge_runner.session.claude_agent_sdk.query",
            side_effect=_auth_fail_query,
        ):
            with patch("scripts.forge_runner.session.ProcessError", _FakeProcessError):
                with pytest.raises(AuthFailure):
                    async for _ in run_session(chunk, ctx):
                        pass

    @pytest.mark.asyncio
    async def test_auth_failure_error_event_emitted(self, fake_repo: Path) -> None:
        """An error event is emitted before AuthFailure is raised."""
        chunk = _fake_chunk()
        ctx = _make_ctx(fake_repo)

        async def _auth_fail_query(*args, **kwargs) -> AsyncGenerator:
            raise _FakeProcessError("authentication failure 401")
            yield

        events = []
        with patch(
            "scripts.forge_runner.session.claude_agent_sdk.query",
            side_effect=_auth_fail_query,
        ):
            with patch("scripts.forge_runner.session.ProcessError", _FakeProcessError):
                with pytest.raises(AuthFailure):
                    async for event in run_session(chunk, ctx):
                        events.append(event)

        # session_start was emitted, error event was emitted
        kinds = [e["kind"] for e in events]
        assert "session_start" in kinds
        assert "error" in kinds

    @pytest.mark.asyncio
    async def test_non_auth_process_error_propagates(self, fake_repo: Path) -> None:
        """ProcessError without auth markers propagates as-is (not AuthFailure)."""
        chunk = _fake_chunk()
        ctx = _make_ctx(fake_repo)

        async def _generic_error_query(*args, **kwargs) -> AsyncGenerator:
            raise _FakeProcessError("something exploded unexpectedly")
            yield

        with patch(
            "scripts.forge_runner.session.claude_agent_sdk.query",
            side_effect=_generic_error_query,
        ):
            with patch("scripts.forge_runner.session.ProcessError", _FakeProcessError):
                # Should NOT raise AuthFailure — should raise _FakeProcessError
                with pytest.raises(_FakeProcessError):
                    async for _ in run_session(chunk, ctx):
                        pass
