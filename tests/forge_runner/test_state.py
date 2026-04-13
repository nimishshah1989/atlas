"""Tests for scripts/forge_runner/state.py (T012 / T017).

State transitions per data-model.md:
  PENDING → IN_PROGRESS (mark_in_progress)
  IN_PROGRESS → FAILED   (mark_failed)
  IN_PROGRESS → PENDING  (reset_to_pending)

Test naming: test_<function>_<scenario>_<expected>
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from scripts.forge_runner.state import (
    ChunkRow,
    get_chunk,
    list_in_progress,
    list_pending_matching,
    mark_failed,
    mark_in_progress,
    reset_to_pending,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

FULL_SCHEMA_DDL = """
CREATE TABLE IF NOT EXISTS chunks (
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


@pytest.fixture
def db(tmp_path: Path) -> tuple[str, sqlite3.Connection]:
    """Create a temp-file SQLite DB with the full chunks schema.

    Returns (path_str, connection).  Tests insert rows via the connection
    and pass path_str to the state.py functions under test.
    """
    db_path = str(tmp_path / "state.db")
    conn = sqlite3.connect(db_path, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=OFF")  # No transitions table in this minimal schema
    conn.executescript(FULL_SCHEMA_DDL)
    conn.commit()
    yield db_path, conn
    conn.close()


def _insert(
    conn: sqlite3.Connection,
    chunk_id: str,
    status: str = "PENDING",
    depends_on: list[str] | None = None,
    runner_pid: int | None = None,
    failure_reason: str | None = None,
    started_at: str | None = None,
) -> None:
    """Insert a minimal chunk row into *conn*."""
    conn.execute(
        """INSERT INTO chunks
           (id, title, status, plan_version, depends_on,
            created_at, updated_at, runner_pid, failure_reason, started_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            chunk_id,
            f"Test chunk {chunk_id}",
            status,
            "v1",
            json.dumps(depends_on or []),
            "2026-04-13T00:00:00+05:30",
            "2026-04-13T00:00:00+05:30",
            runner_pid,
            failure_reason,
            started_at,
        ),
    )
    conn.commit()


# ---------------------------------------------------------------------------
# get_chunk
# ---------------------------------------------------------------------------


def test_get_chunk_existing_returns_chunk_row(db: tuple) -> None:
    db_path, conn = db
    _insert(conn, "V1-1")
    result = get_chunk("V1-1", db_path)
    assert result is not None
    assert isinstance(result, ChunkRow)
    assert result.id == "V1-1"
    assert result.status == "PENDING"


def test_get_chunk_missing_returns_none(db: tuple) -> None:
    db_path, _ = db
    result = get_chunk("NONEXISTENT", db_path)
    assert result is None


def test_get_chunk_new_columns_populated_correctly(db: tuple) -> None:
    db_path, conn = db
    _insert(conn, "V1-2", status="FAILED", failure_reason="verifier failed")
    result = get_chunk("V1-2", db_path)
    assert result is not None
    assert result.failure_reason == "verifier failed"
    assert result.runner_pid is None


# ---------------------------------------------------------------------------
# mark_in_progress
# ---------------------------------------------------------------------------


def test_mark_in_progress_sets_correct_columns(db: tuple) -> None:
    db_path, conn = db
    _insert(conn, "V1-3")

    mark_in_progress("V1-3", pid=12345, db_path=db_path)

    result = get_chunk("V1-3", db_path)
    assert result is not None
    assert result.status == "IN_PROGRESS"
    assert result.runner_pid == 12345
    assert result.started_at is not None
    assert "+05:30" in result.started_at
    assert result.failure_reason is None


def test_mark_in_progress_increments_attempts(db: tuple) -> None:
    db_path, conn = db
    _insert(conn, "V1-4")

    mark_in_progress("V1-4", pid=1, db_path=db_path)

    result = get_chunk("V1-4", db_path)
    assert result is not None
    # Started at 0 attempts, should be 1 after mark_in_progress
    assert result.attempts == 1


def test_mark_in_progress_clears_failure_reason(db: tuple) -> None:
    db_path, conn = db
    _insert(conn, "V1-5", status="PENDING", failure_reason="old failure")

    mark_in_progress("V1-5", pid=99, db_path=db_path)

    result = get_chunk("V1-5", db_path)
    assert result is not None
    assert result.failure_reason is None


# ---------------------------------------------------------------------------
# mark_failed
# ---------------------------------------------------------------------------


def test_mark_failed_sets_correct_columns(db: tuple) -> None:
    db_path, conn = db
    _insert(
        conn, "V1-6", status="IN_PROGRESS", runner_pid=42, started_at="2026-04-13T10:00:00+05:30"
    )

    mark_failed("V1-6", reason="state_db_not_done", db_path=db_path)

    result = get_chunk("V1-6", db_path)
    assert result is not None
    assert result.status == "FAILED"
    assert result.failure_reason == "state_db_not_done"
    assert result.runner_pid is None


def test_mark_failed_updated_at_is_ist_aware(db: tuple) -> None:
    db_path, conn = db
    _insert(conn, "V1-7", status="IN_PROGRESS", runner_pid=1)

    mark_failed("V1-7", reason="test", db_path=db_path)

    result = get_chunk("V1-7", db_path)
    assert result is not None
    assert "+05:30" in result.updated_at


# ---------------------------------------------------------------------------
# reset_to_pending
# ---------------------------------------------------------------------------


def test_reset_to_pending_clears_all_runner_columns(db: tuple) -> None:
    db_path, conn = db
    _insert(
        conn, "V1-8", status="IN_PROGRESS", runner_pid=777, started_at="2026-04-13T10:00:00+05:30"
    )

    reset_to_pending("V1-8", db_path=db_path)

    result = get_chunk("V1-8", db_path)
    assert result is not None
    assert result.status == "PENDING"
    assert result.started_at is None
    assert result.runner_pid is None
    assert result.failure_reason is None


def test_reset_to_pending_from_failed_state(db: tuple) -> None:
    db_path, conn = db
    _insert(conn, "V1-9", status="FAILED", failure_reason="verifier check failed")

    reset_to_pending("V1-9", db_path=db_path)

    result = get_chunk("V1-9", db_path)
    assert result is not None
    assert result.status == "PENDING"
    assert result.failure_reason is None


# ---------------------------------------------------------------------------
# list_in_progress
# ---------------------------------------------------------------------------


def test_list_in_progress_returns_only_in_progress(db: tuple) -> None:
    db_path, conn = db
    _insert(conn, "A1", status="IN_PROGRESS", runner_pid=1)
    _insert(conn, "A2", status="PENDING")
    _insert(conn, "A3", status="DONE")
    _insert(conn, "A4", status="IN_PROGRESS", runner_pid=2)

    result = list_in_progress(db_path)
    ids = sorted(r.id for r in result)
    assert ids == ["A1", "A4"]


def test_list_in_progress_empty_when_none(db: tuple) -> None:
    db_path, conn = db
    _insert(conn, "B1", status="PENDING")
    assert list_in_progress(db_path) == []


# ---------------------------------------------------------------------------
# list_pending_matching
# ---------------------------------------------------------------------------


def test_list_pending_matching_returns_matching_pending(db: tuple) -> None:
    db_path, conn = db
    _insert(conn, "V1-1", status="PENDING")
    _insert(conn, "V1-2", status="PENDING")
    _insert(conn, "V2-1", status="PENDING")
    _insert(conn, "C10", status="PENDING")

    result = list_pending_matching(r"^V1-\d+$", db_path)
    ids = [r.id for r in result]
    assert "V1-1" in ids
    assert "V1-2" in ids
    assert "V2-1" not in ids
    assert "C10" not in ids


def test_list_pending_matching_excludes_non_pending(db: tuple) -> None:
    db_path, conn = db
    _insert(conn, "V1-10", status="IN_PROGRESS", runner_pid=1)
    _insert(conn, "V1-11", status="DONE")
    _insert(conn, "V1-12", status="PENDING")

    result = list_pending_matching(r"^V1-", db_path)
    ids = [r.id for r in result]
    assert ids == ["V1-12"]


def test_list_pending_matching_sorted_lexicographically(db: tuple) -> None:
    db_path, conn = db
    # Insert in reverse order — result must still be lexicographic
    for cid in ["V1-9", "V1-10", "V1-2", "V1-1"]:
        _insert(conn, cid, status="PENDING")

    result = list_pending_matching(r"^V1-", db_path)
    ids = [r.id for r in result]
    # Lexicographic: V1-1, V1-10, V1-2, V1-9
    assert ids == ["V1-1", "V1-10", "V1-2", "V1-9"]


def test_list_pending_matching_empty_on_no_match(db: tuple) -> None:
    db_path, conn = db
    _insert(conn, "C5", status="PENDING")
    result = list_pending_matching(r"^V1-", db_path)
    assert result == []


# ---------------------------------------------------------------------------
# depends_on JSON parsing
# ---------------------------------------------------------------------------


def test_get_chunk_parses_depends_on_json(db: tuple) -> None:
    db_path, conn = db
    _insert(conn, "V1-20", depends_on=["V1-1", "S4"])
    result = get_chunk("V1-20", db_path)
    assert result is not None
    assert result.depends_on == ["V1-1", "S4"]


def test_get_chunk_empty_depends_on(db: tuple) -> None:
    db_path, conn = db
    _insert(conn, "V1-21", depends_on=[])
    result = get_chunk("V1-21", db_path)
    assert result is not None
    assert result.depends_on == []
