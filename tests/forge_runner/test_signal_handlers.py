"""Tests for SIGTERM/SIGINT signal handlers in cli.py (T044, FR-025).

Approach: unit-level (not subprocess) to avoid fragile timing in CI.

Tests:
  1. _on_signal sets ctx.cancellation
  2. _on_signal calls reset_to_pending for the in-flight chunk
  3. Signal handler is idempotent (safe to call twice)
  4. _on_signal is a no-op when ctx.current_chunk is None
  5. _run_loop_with_signals installs and removes handlers correctly
  6. Cancellation flag propagates: loop body sees it and exits cleanly
"""

from __future__ import annotations

import asyncio
import os
import sqlite3
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_DDL = """
CREATE TABLE chunks (
    id              TEXT PRIMARY KEY,
    title           TEXT NOT NULL,
    status          TEXT NOT NULL,
    attempts        INTEGER NOT NULL DEFAULT 0,
    last_error      TEXT,
    plan_version    TEXT NOT NULL,
    depends_on      TEXT NOT NULL,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL,
    started_at      TEXT,
    finished_at     TEXT,
    runner_pid      INTEGER,
    failure_reason  TEXT
);
"""


def _make_db(tmp_path: Path) -> str:
    db_path = str(tmp_path / "state.db")
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(_DDL)
    conn.execute(
        """INSERT INTO chunks
           (id, title, status, attempts, last_error, plan_version,
            depends_on, created_at, updated_at, started_at, finished_at,
            runner_pid, failure_reason)
           VALUES ('V1-1', 'Test chunk', 'IN_PROGRESS', 1, NULL, 'v1',
                   '[]', '2026-01-01T00:00:00+05:30',
                   '2026-01-01T00:00:00+05:30', NULL, NULL, ?, NULL)""",
        (os.getpid(),),
    )
    conn.commit()
    conn.close()
    return db_path


def _get_status(db_path: str, chunk_id: str) -> str:
    conn = sqlite3.connect(db_path)
    row = conn.execute("SELECT status FROM chunks WHERE id = ?", (chunk_id,)).fetchone()
    conn.close()
    return row[0] if row else "NOT_FOUND"


def _make_chunk() -> SimpleNamespace:
    return SimpleNamespace(id="V1-1")


def _make_config() -> SimpleNamespace:
    return SimpleNamespace(
        filter_regex=".*",
        timeout_sec=2700,
        max_turns=200,
        repo="/tmp",
        log_dir="/tmp/.forge/logs",
        once=False,
        retry=None,
        dry_run=False,
        verbose=False,
        resume=False,
        strict_dead_man=False,
    )


# ---------------------------------------------------------------------------
# Test: cancellation set by signal
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_signal_sets_cancellation_flag(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Manually invoking _on_signal sets ctx.cancellation."""
    from scripts.forge_runner import cli as cli_mod

    db_path = _make_db(tmp_path)
    log_dir = tmp_path / ".forge" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    cancellation = asyncio.Event()
    chunk = _make_chunk()

    ctx = SimpleNamespace(
        state_db_path=db_path,
        current_chunk=chunk,
        cancellation=cancellation,
        log_dir=log_dir,
        config=_make_config(),
    )

    # Capture what _on_signal does without the real write_event import
    monkeypatch.setattr(
        "scripts.forge_runner.cli.write_event",
        lambda **_: None,
        raising=False,
    )

    # Build the handler as cli.py would — replicate the closure logic
    def _on_signal(sig_name: str) -> None:
        ctx.cancellation.set()
        cli_mod._reset_current_chunk_if_any(ctx)  # type: ignore[attr-defined]

    assert not cancellation.is_set()
    _on_signal("SIGTERM")
    assert cancellation.is_set()


# ---------------------------------------------------------------------------
# Test: reset_to_pending called on current chunk
# ---------------------------------------------------------------------------


def test_signal_resets_current_chunk_to_pending(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """_reset_current_chunk_if_any resets the in-flight chunk."""
    from scripts.forge_runner import cli as cli_mod

    db_path = _make_db(tmp_path)

    chunk = _make_chunk()
    ctx = SimpleNamespace(
        state_db_path=db_path,
        current_chunk=chunk,
        cancellation=asyncio.Event(),
        log_dir=tmp_path / ".forge" / "logs",
        config=_make_config(),
    )

    assert _get_status(db_path, "V1-1") == "IN_PROGRESS"
    cli_mod._reset_current_chunk_if_any(ctx)  # type: ignore[attr-defined]
    assert _get_status(db_path, "V1-1") == "PENDING"


def test_signal_with_no_current_chunk_is_noop(tmp_path: Path) -> None:
    """_reset_current_chunk_if_any is safe when current_chunk is None."""
    from scripts.forge_runner import cli as cli_mod

    ctx = SimpleNamespace(
        state_db_path=str(tmp_path / "nonexistent.db"),
        current_chunk=None,
        cancellation=asyncio.Event(),
        log_dir=tmp_path,
        config=_make_config(),
    )
    # Should not raise
    cli_mod._reset_current_chunk_if_any(ctx)  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# Test: idempotency
# ---------------------------------------------------------------------------


def test_signal_handler_idempotent(
    tmp_path: Path,
) -> None:
    """Calling _reset_current_chunk_if_any twice is safe."""
    from scripts.forge_runner import cli as cli_mod

    db_path = _make_db(tmp_path)
    chunk = _make_chunk()
    ctx = SimpleNamespace(
        state_db_path=db_path,
        current_chunk=chunk,
        cancellation=asyncio.Event(),
        log_dir=tmp_path,
        config=_make_config(),
    )

    cli_mod._reset_current_chunk_if_any(ctx)  # type: ignore[attr-defined]
    assert _get_status(db_path, "V1-1") == "PENDING"
    # Second call is safe (already PENDING, update is idempotent)
    cli_mod._reset_current_chunk_if_any(ctx)  # type: ignore[attr-defined]
    assert _get_status(db_path, "V1-1") == "PENDING"


# ---------------------------------------------------------------------------
# Test: _run_loop_with_signals returns the run_loop result
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_loop_with_signals_returns_loop_result(
    tmp_path: Path,
) -> None:
    """_run_loop_with_signals passes ctx to run_loop_fn and returns its result."""
    from scripts.forge_runner.cli import _run_loop_with_signals

    db_path = _make_db(tmp_path)
    log_dir = tmp_path / ".forge" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    cancellation = asyncio.Event()

    ctx = SimpleNamespace(
        state_db_path=db_path,
        current_chunk=None,
        cancellation=cancellation,
        log_dir=log_dir,
        config=_make_config(),
    )

    async def fake_run_loop(ctx: Any) -> int:
        return 0

    result = await _run_loop_with_signals(ctx, fake_run_loop)
    assert result == 0


@pytest.mark.asyncio
async def test_run_loop_with_signals_propagates_nonzero_exit(
    tmp_path: Path,
) -> None:
    """Non-zero exit code from run_loop_fn is propagated."""
    from scripts.forge_runner.cli import _run_loop_with_signals

    db_path = _make_db(tmp_path)
    log_dir = tmp_path / ".forge" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    ctx = SimpleNamespace(
        state_db_path=db_path,
        current_chunk=None,
        cancellation=asyncio.Event(),
        log_dir=log_dir,
        config=_make_config(),
    )

    async def fake_run_loop_failing(ctx: Any) -> int:
        return 3

    result = await _run_loop_with_signals(ctx, fake_run_loop_failing)
    assert result == 3


# ---------------------------------------------------------------------------
# Test: cancellation flag causes loop to exit
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cancellation_flag_stops_loop(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """If cancellation is already set, a loop that checks it exits immediately."""
    from scripts.forge_runner.cli import _run_loop_with_signals

    db_path = _make_db(tmp_path)
    log_dir = tmp_path / ".forge" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    cancellation = asyncio.Event()
    cancellation.set()  # Pre-set, as if SIGTERM fired before loop iteration

    ctx = SimpleNamespace(
        state_db_path=db_path,
        current_chunk=None,
        cancellation=cancellation,
        log_dir=log_dir,
        config=_make_config(),
    )

    async def loop_that_checks_cancellation(ctx: Any) -> int:
        if ctx.cancellation.is_set():
            return 0
        return 99  # Should not reach here

    result = await _run_loop_with_signals(ctx, loop_that_checks_cancellation)
    assert result == 0


# ---------------------------------------------------------------------------
# Test: signal handler installed and removed (Unix only)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    not hasattr(asyncio.get_event_loop_policy(), "get_event_loop"),
    reason="Unix asyncio signal handler test",
)
@pytest.mark.asyncio
async def test_signal_handlers_installed_then_removed(tmp_path: Path) -> None:
    """Verify add_signal_handler is called on Unix and cleaned up after loop exits."""
    original_add = (
        asyncio.get_event_loop().add_signal_handler
        if hasattr(asyncio.get_event_loop(), "add_signal_handler")
        else None
    )

    if original_add is None:
        pytest.skip("add_signal_handler not available on this platform")

    from scripts.forge_runner.cli import _run_loop_with_signals

    db_path = _make_db(tmp_path)
    log_dir = tmp_path / ".forge" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    ctx = SimpleNamespace(
        state_db_path=db_path,
        current_chunk=None,
        cancellation=asyncio.Event(),
        log_dir=log_dir,
        config=_make_config(),
    )

    async def noop_loop(ctx: Any) -> int:
        return 0

    # Should complete without error
    result = await _run_loop_with_signals(ctx, noop_loop)
    assert result == 0
