"""Tests for session.py backoff retry logic (T028).

Monkeypatches claude_agent_sdk.query to raise ProcessError(stderr="rate limit 529")
twice then succeed on the third call. Verifies retries don't count against max_turns.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from scripts.forge_runner.session import run_session
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


def _make_ctx(repo: Path, timeout_sec: int = 120, max_turns: int = 10) -> SimpleNamespace:
    return SimpleNamespace(
        repo=repo,
        timeout_sec=timeout_sec,
        max_turns=max_turns,
    )


def _make_result_message() -> MagicMock:
    msg = MagicMock()
    msg.stop_reason = "end_turn"
    msg.usage = None
    # Not an assistant message (no .content list)
    del msg.content
    del msg.tool_use_id
    return msg


async def _fake_query_success(*args, **kwargs) -> AsyncGenerator:
    """Successful SDK response with one result message."""
    msg = _make_result_message()
    yield msg


class _FakeProcessError(Exception):
    """Mimics claude_agent_sdk.ProcessError."""

    def __init__(self, stderr: str, returncode: int = 1) -> None:
        self.stderr = stderr
        self.returncode = returncode
        super().__init__(stderr)


class TestSessionBackoffRetry:
    """Verify backoff retry on transient errors does not count turns."""

    @pytest.mark.asyncio
    async def test_retries_on_rate_limit_and_succeeds(self, fake_repo: Path) -> None:
        """Two rate-limit errors then success — should complete without error."""
        chunk = _fake_chunk()
        ctx = _make_ctx(fake_repo, max_turns=5)

        call_count = 0

        async def _flaky_query(*args, **kwargs) -> AsyncGenerator:
            nonlocal call_count
            call_count += 1
            if call_count <= 2:
                raise _FakeProcessError("rate limit 529 overloaded")
            # Third call succeeds
            async for msg in _fake_query_success():
                yield msg

        events = []

        # Patch asyncio.sleep to avoid real delays
        with patch("scripts.forge_runner.session.asyncio.sleep", new_callable=AsyncMock):
            with patch(
                "scripts.forge_runner.session.claude_agent_sdk.query",
                side_effect=_flaky_query,
            ):
                with patch(
                    "scripts.forge_runner.session.ProcessError",
                    _FakeProcessError,
                ):
                    async for event in run_session(chunk, ctx):
                        events.append(event)

        # Should have session_start + session_end at minimum
        kinds = [e["kind"] for e in events]
        assert "session_start" in kinds
        assert "session_end" in kinds

        # 3 calls made (2 transient + 1 success)
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_retry_count_not_in_turns(self, fake_repo: Path) -> None:
        """Turns counter must reflect tool uses, not retry attempts."""
        chunk = _fake_chunk()
        ctx = _make_ctx(fake_repo, max_turns=5)

        call_count = 0

        async def _flaky_query(*args, **kwargs) -> AsyncGenerator:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise _FakeProcessError("529 rate limit hit")
            async for msg in _fake_query_success():
                yield msg

        with patch("scripts.forge_runner.session.asyncio.sleep", new_callable=AsyncMock):
            with patch(
                "scripts.forge_runner.session.claude_agent_sdk.query",
                side_effect=_flaky_query,
            ):
                with patch(
                    "scripts.forge_runner.session.ProcessError",
                    _FakeProcessError,
                ):
                    events = [e async for e in run_session(chunk, ctx)]

        session_end_events = [e for e in events if e["kind"] == "session_end"]
        assert len(session_end_events) == 1
        # 0 tool_use blocks in the fake message → turns should be 0
        assert session_end_events[0]["payload"]["turns"] == 0

    @pytest.mark.asyncio
    async def test_exhausted_retries_raises(self, fake_repo: Path) -> None:
        """After _MAX_BACKOFF_RETRIES attempts, the error propagates."""
        chunk = _fake_chunk()
        ctx = _make_ctx(fake_repo)

        async def _always_fail(*args, **kwargs) -> AsyncGenerator:
            raise _FakeProcessError("rate limit 529")
            yield  # make it a generator

        with patch("scripts.forge_runner.session.asyncio.sleep", new_callable=AsyncMock):
            with patch(
                "scripts.forge_runner.session.claude_agent_sdk.query",
                side_effect=_always_fail,
            ):
                with patch(
                    "scripts.forge_runner.session.ProcessError",
                    _FakeProcessError,
                ):
                    with pytest.raises(_FakeProcessError):
                        async for _ in run_session(chunk, ctx):
                            pass
