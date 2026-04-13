"""pytest fixtures for forge_runner tests.

These fixtures are Phase 1 scaffolding.  They pre-include the three new
columns (started_at, runner_pid, failure_reason) that the Phase 2 alembic
migration will add to the real state.db.

Fixture inventory:
  fake_state_db   — in-memory SQLite with full chunks schema + new columns
  fake_repo       — tmp dir with git init + initial empty commit
  fake_event_stream — async generator yielding a scripted SDK event sequence
  runner_ctx      — factory returning a SimpleNamespace RunContext-like object
"""

from __future__ import annotations

import sqlite3
import subprocess
import threading
from pathlib import Path
from types import SimpleNamespace
from typing import AsyncGenerator

import pytest


# ---------------------------------------------------------------------------
# fake_state_db
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

CREATE_TRANSITIONS_DDL = """
CREATE TABLE transitions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    chunk_id        TEXT NOT NULL REFERENCES chunks(id) ON DELETE CASCADE,
    from_state      TEXT,
    to_state        TEXT NOT NULL,
    reason          TEXT,
    at              TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_transitions_chunk ON transitions(chunk_id, at);
"""

CREATE_SESSIONS_DDL = """
CREATE TABLE sessions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    chunk_id        TEXT NOT NULL REFERENCES chunks(id) ON DELETE CASCADE,
    attempt         INTEGER NOT NULL,
    phase           TEXT NOT NULL,
    pid             INTEGER,
    started_at      TEXT NOT NULL,
    finished_at     TEXT,
    exit_code       INTEGER,
    log_path        TEXT
);
CREATE INDEX IF NOT EXISTS idx_sessions_chunk ON sessions(chunk_id, attempt);
"""

CREATE_QUALITY_RUNS_DDL = """
CREATE TABLE quality_runs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    chunk_id        TEXT NOT NULL REFERENCES chunks(id) ON DELETE CASCADE,
    attempt         INTEGER NOT NULL,
    overall_score   INTEGER NOT NULL,
    passed          INTEGER NOT NULL,
    report_json     TEXT NOT NULL,
    at              TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_quality_runs_chunk ON quality_runs(chunk_id, attempt);
"""


@pytest.fixture
def fake_state_db() -> sqlite3.Connection:
    """In-memory SQLite with the full orchestrator schema plus the three new
    runner columns (started_at already exists; runner_pid and failure_reason
    are Phase 2 additions pre-included here for test fixture completeness).

    Returns an open sqlite3.Connection.  The caller is responsible for closing
    it, but pytest garbage-collection handles in-memory databases automatically
    when the connection object is collected.
    """
    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")

    for ddl in (
        CREATE_CHUNKS_DDL,
        CREATE_TRANSITIONS_DDL,
        CREATE_SESSIONS_DDL,
        CREATE_QUALITY_RUNS_DDL,
    ):
        conn.executescript(ddl)

    conn.commit()
    return conn


# ---------------------------------------------------------------------------
# fake_repo
# ---------------------------------------------------------------------------


@pytest.fixture
def fake_repo(tmp_path: Path) -> Path:
    """Temporary directory with a git repo initialised and one empty commit.

    Returns the Path to the repo root.

    User identity is set only for this repo (--local) so global git config is
    not polluted.
    """
    repo = tmp_path / "repo"
    repo.mkdir()

    def git(*args: str) -> None:
        result = subprocess.run(
            ["git", *args],
            cwd=str(repo),
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise RuntimeError(f"git {' '.join(args)} failed:\n{result.stderr}")

    git("init")
    git("config", "--local", "user.email", "forge-runner-test@atlas.local")
    git("config", "--local", "user.name", "Forge Runner Test")

    # Create an initial commit so HEAD exists (needed for git log checks)
    readme = repo / "README.md"
    readme.write_text("test repo\n")
    git("add", "README.md")
    git("commit", "-m", "chore: initial empty commit for test fixture")

    return repo


# ---------------------------------------------------------------------------
# fake_event_stream
# ---------------------------------------------------------------------------


class _FakeSessionStart:
    """Minimal stand-in for a session_start SDK event."""

    type: str = "session_start"
    session_id: str = "fake-session-001"


class _FakeToolUse:
    """Minimal stand-in for a tool_use block inside an AssistantMessage."""

    type: str = "tool_use"

    def __init__(self, tool_name: str, tool_id: str, input_data: dict) -> None:
        self.name = tool_name
        self.id = tool_id
        self.input = input_data


class _FakeToolResult:
    """Minimal stand-in for a tool_result event."""

    type: str = "tool_result"

    def __init__(self, tool_use_id: str, content: str) -> None:
        self.tool_use_id = tool_use_id
        self.content = content


class _FakeText:
    """Minimal stand-in for a text block inside an AssistantMessage."""

    type: str = "text"

    def __init__(self, text: str) -> None:
        self.text = text


class _FakeAssistantMessage:
    """Minimal stand-in for an AssistantMessage containing content blocks."""

    type: str = "assistant"

    def __init__(self, content: list) -> None:
        self.content = content


class _FakeResultMessage:
    """Minimal stand-in for a ResultMessage (session end marker)."""

    type: str = "result"
    stop_reason: str = "end_turn"


@pytest.fixture
def fake_event_stream():
    """Async generator fixture yielding a scripted Agent SDK event sequence.

    Sequence: session_start → tool_use(Read) → tool_result → tool_use(Edit)
              → tool_result → text → result(end_turn)

    Usage in tests::

        async for event in fake_event_stream():
            process(event)
    """

    async def _stream() -> AsyncGenerator:
        yield _FakeSessionStart()

        tool_id_read = "tool_read_001"
        yield _FakeAssistantMessage(
            content=[
                _FakeToolUse(
                    tool_name="Read",
                    tool_id=tool_id_read,
                    input_data={"file_path": "/home/ubuntu/atlas/CLAUDE.md"},
                )
            ]
        )

        yield _FakeToolResult(
            tool_use_id=tool_id_read,
            content="# ATLAS\n...(truncated for test)...",
        )

        tool_id_edit = "tool_edit_001"
        yield _FakeAssistantMessage(
            content=[
                _FakeToolUse(
                    tool_name="Edit",
                    tool_id=tool_id_edit,
                    input_data={
                        "file_path": "/home/ubuntu/atlas/some_file.py",
                        "old_string": "old",
                        "new_string": "new",
                    },
                )
            ]
        )

        yield _FakeToolResult(
            tool_use_id=tool_id_edit,
            content="Edit applied successfully.",
        )

        yield _FakeAssistantMessage(
            content=[_FakeText(text="forge: V1-1 — initial scaffold complete")]
        )

        yield _FakeResultMessage()

    return _stream


# ---------------------------------------------------------------------------
# runner_ctx
# ---------------------------------------------------------------------------


@pytest.fixture
def runner_ctx(fake_repo: Path, tmp_path: Path):
    """Factory fixture returning a minimal RunContext-like SimpleNamespace.

    The full RunContext dataclass is implemented in Phase 2 (stages.py / T025).
    This SimpleNamespace satisfies the attrs that Phase 1 fixtures inspect.

    Returns a callable factory so tests can override individual attrs::

        ctx = runner_ctx()
        ctx_with_custom_repo = runner_ctx(repo="/custom/path")
    """
    log_dir = tmp_path / ".forge" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    state_db_path = tmp_path / "state.db"

    def _make(**overrides) -> SimpleNamespace:  # type: ignore[return]
        defaults = dict(
            repo=str(fake_repo),
            log_dir=str(log_dir),
            state_db_path=str(state_db_path),
            cancellation=threading.Event(),
        )
        defaults.update(overrides)
        return SimpleNamespace(**defaults)

    return _make
