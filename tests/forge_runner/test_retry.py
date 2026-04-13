"""Tests for --retry CLI flow (T039).

Covers:
  - Pre-stage a FAILED chunk with an existing failure record
  - Invoke cli.main(["--retry", "TEST-2", ...])
  - Assert state.db row reset to PENDING
  - Assert failure record archived to archive/TEST-2.<ts>.failure.json
  - Assert one iteration was attempted (spy on mocked run_loop)
"""

from __future__ import annotations

import json
import sqlite3
import subprocess
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from scripts.forge_runner._time import now_ist, to_iso
from scripts.forge_runner.state import get_chunk

# ---------------------------------------------------------------------------
# DB helpers (same schema as conftest.py)
# ---------------------------------------------------------------------------

CREATE_CHUNKS_DDL = """
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
CREATE INDEX IF NOT EXISTS idx_chunks_status ON chunks(status);
"""


def _make_state_db(db_path: str, chunk_id: str, status: str = "FAILED") -> None:
    """Seed a minimal state.db with one chunk row."""
    conn = sqlite3.connect(db_path)
    conn.executescript(CREATE_CHUNKS_DDL)
    now = to_iso(now_ist())
    conn.execute(
        """INSERT INTO chunks
           (id, title, status, attempts, plan_version, depends_on, created_at, updated_at)
           VALUES (?, 'Test chunk 2', ?, 1, 'v1', '[]', ?, ?)""",
        (chunk_id, status, now, now),
    )
    conn.commit()
    conn.close()


def _write_failure_record_file(log_dir: Path, chunk_id: str) -> Path:
    """Write a minimal failure.json for chunk_id, return path."""
    path = log_dir / f"{chunk_id}.failure.json"
    record = {
        "chunk_id": chunk_id,
        "failed_at": to_iso(now_ist()),
        "failed_check": "state_db_not_done",
        "failed_check_detail": "status was FAILED, expected DONE",
        "session_id": f"forge-{chunk_id}-99999",
        "last_events": [],
        "state_row": {},
        "git_status": "",
        "git_log_last_5": [],
        "suggested_recovery": "run scripts/post-chunk.sh",
        "runner_pid": 99999,
        "runner_version": "abc1234",
    }
    path.write_text(json.dumps(record), encoding="utf-8")
    return path


def _init_git_repo(repo: Path) -> None:
    """Initialise a minimal git repo so precondition checks pass."""
    subprocess.run(["git", "init"], cwd=str(repo), capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@test.local"],
        cwd=str(repo),
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=str(repo),
        capture_output=True,
    )
    (repo / "README.md").write_text("test\n")
    subprocess.run(["git", "add", "README.md"], cwd=str(repo), capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "chore: init"],
        cwd=str(repo),
        capture_output=True,
    )


# ---------------------------------------------------------------------------
# Main test fixture
# ---------------------------------------------------------------------------


@pytest.fixture()
def retry_env(tmp_path: Path):
    """Set up everything needed for a --retry test."""
    chunk_id = "TEST-2"

    # Git repo (needed for precondition checks in cli.py)
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_git_repo(repo)

    # Forge directory structure
    forge_dir = repo / ".forge"
    forge_dir.mkdir()
    (forge_dir / "CONDUCTOR.md").write_text("# Conductor\n")
    (forge_dir / "last-run.json").write_text("{}")

    # state.db inside orchestrator/ (as expected by cli.py)
    orch_dir = repo / "orchestrator"
    orch_dir.mkdir()
    db_path = str(orch_dir / "state.db")
    _make_state_db(db_path, chunk_id, status="FAILED")

    # Log dir with an existing failure record
    log_dir = forge_dir / "logs"
    log_dir.mkdir()
    failure_path = _write_failure_record_file(log_dir, chunk_id)

    return {
        "chunk_id": chunk_id,
        "repo": repo,
        "log_dir": log_dir,
        "db_path": db_path,
        "failure_path": failure_path,
    }


# ---------------------------------------------------------------------------
# T039a: state.db row reset to PENDING
# ---------------------------------------------------------------------------


def test_retry_resets_chunk_to_pending(retry_env: dict[str, Any]) -> None:
    """After --retry, state.db row should be PENDING."""
    chunk_id = retry_env["chunk_id"]
    db_path = retry_env["db_path"]
    repo = retry_env["repo"]
    log_dir = retry_env["log_dir"]

    # Pre-check: chunk is FAILED
    row = get_chunk(chunk_id, db_path)
    assert row is not None
    assert row.status == "FAILED"

    # Monkeypatch run_loop so no real session is attempted
    async def _fake_loop(ctx: Any) -> int:
        return 0

    with patch("scripts.forge_runner.loop.run_loop", side_effect=_fake_loop):
        from scripts.forge_runner.cli import main

        main(
            [
                "--retry",
                chunk_id,
                "--repo",
                str(repo),
                "--log-dir",
                str(log_dir),
            ]
        )

    # Post-check: chunk should be PENDING (reset_to_pending was called)
    row_after = get_chunk(chunk_id, db_path)
    assert row_after is not None
    assert row_after.status == "PENDING", f"Expected PENDING after --retry, got {row_after.status}"


# ---------------------------------------------------------------------------
# T039b: failure record archived
# ---------------------------------------------------------------------------


def test_retry_archives_failure_record(retry_env: dict[str, Any]) -> None:
    """Existing failure.json should be moved to archive/<chunk_id>.<ts>.failure.json."""
    chunk_id = retry_env["chunk_id"]
    repo = retry_env["repo"]
    log_dir = retry_env["log_dir"]
    failure_path = retry_env["failure_path"]

    assert failure_path.exists(), "Pre-condition: failure record must exist"

    async def _fake_loop(ctx: Any) -> int:
        return 0

    with patch("scripts.forge_runner.loop.run_loop", side_effect=_fake_loop):
        from scripts.forge_runner.cli import main

        main(
            [
                "--retry",
                chunk_id,
                "--repo",
                str(repo),
                "--log-dir",
                str(log_dir),
            ]
        )

    # The original failure.json should be gone
    assert not failure_path.exists(), "Original failure.json should be moved to archive"

    # An archived copy should exist in archive/
    archive_dir = log_dir / "archive"
    assert archive_dir.exists(), "archive/ directory should be created"
    archived_files = list(archive_dir.glob(f"{chunk_id}.*.failure.json"))
    assert len(archived_files) == 1, (
        f"Expected 1 archived failure file, found: {[f.name for f in archived_files]}"
    )


# ---------------------------------------------------------------------------
# T039c: one iteration was attempted (spy on run_loop)
# ---------------------------------------------------------------------------


def test_retry_runs_exactly_one_iteration(retry_env: dict[str, Any]) -> None:
    """run_loop must be called exactly once during --retry."""
    chunk_id = retry_env["chunk_id"]
    repo = retry_env["repo"]
    log_dir = retry_env["log_dir"]

    call_count = 0

    async def _spy_loop(ctx: Any) -> int:
        nonlocal call_count
        call_count += 1
        return 0

    with patch("scripts.forge_runner.loop.run_loop", side_effect=_spy_loop):
        from scripts.forge_runner.cli import main

        main(
            [
                "--retry",
                chunk_id,
                "--repo",
                str(repo),
                "--log-dir",
                str(log_dir),
            ]
        )

    assert call_count == 1, (
        f"Expected run_loop to be called exactly once, called {call_count} times"
    )


# ---------------------------------------------------------------------------
# T039d: exit code propagated from loop
# ---------------------------------------------------------------------------


def test_retry_propagates_loop_exit_code(retry_env: dict[str, Any]) -> None:
    """Exit code from run_loop is returned by cli.main."""
    chunk_id = retry_env["chunk_id"]
    repo = retry_env["repo"]
    log_dir = retry_env["log_dir"]

    async def _failing_loop(ctx: Any) -> int:
        return 3  # CHUNK_FAILED

    with patch("scripts.forge_runner.loop.run_loop", side_effect=_failing_loop):
        from scripts.forge_runner.cli import main

        result = main(
            [
                "--retry",
                chunk_id,
                "--repo",
                str(repo),
                "--log-dir",
                str(log_dir),
            ]
        )

    assert result == 3


# ---------------------------------------------------------------------------
# T039e: --retry with no existing failure record (no archive dir created)
# ---------------------------------------------------------------------------


def test_retry_without_failure_record_succeeds(tmp_path: Path) -> None:
    """--retry should work even if no .failure.json exists."""
    chunk_id = "TEST-2"

    repo = tmp_path / "repo"
    repo.mkdir()
    _init_git_repo(repo)

    forge_dir = repo / ".forge"
    forge_dir.mkdir()
    (forge_dir / "CONDUCTOR.md").write_text("# Conductor\n")

    orch_dir = repo / "orchestrator"
    orch_dir.mkdir()
    db_path = str(orch_dir / "state.db")
    _make_state_db(db_path, chunk_id, status="FAILED")

    log_dir = forge_dir / "logs"
    log_dir.mkdir()
    # Deliberately NOT writing a failure.json

    async def _fake_loop(ctx: Any) -> int:
        return 0

    with patch("scripts.forge_runner.loop.run_loop", side_effect=_fake_loop):
        from scripts.forge_runner.cli import main

        result = main(
            [
                "--retry",
                chunk_id,
                "--repo",
                str(repo),
                "--log-dir",
                str(log_dir),
            ]
        )

    assert result == 0
    # archive dir should NOT be created since there was nothing to archive
    archive_dir = log_dir / "archive"
    assert not archive_dir.exists()


# ---------------------------------------------------------------------------
# T039f: --retry with non-existent chunk returns precondition error
# ---------------------------------------------------------------------------


def test_retry_unknown_chunk_returns_error(tmp_path: Path) -> None:
    """--retry with a chunk ID not in state.db should return exit 7 (precondition)."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_git_repo(repo)

    forge_dir = repo / ".forge"
    forge_dir.mkdir()
    (forge_dir / "CONDUCTOR.md").write_text("# Conductor\n")

    orch_dir = repo / "orchestrator"
    orch_dir.mkdir()
    db_path = str(orch_dir / "state.db")
    # Create DB but don't insert the chunk we'll retry
    conn = sqlite3.connect(db_path)
    conn.executescript(CREATE_CHUNKS_DDL)
    conn.commit()
    conn.close()

    log_dir = forge_dir / "logs"
    log_dir.mkdir()

    from scripts.forge_runner.cli import main

    result = main(
        [
            "--retry",
            "DOES-NOT-EXIST",
            "--repo",
            str(repo),
            "--log-dir",
            str(log_dir),
        ]
    )
    assert result == 7  # _EXIT_PRECONDITION
