"""End-to-end integration test with canned session (T030).

FakeSession yields scripted events and has a side-effect of marking the chunk DONE
(emulating the inner conductor calling post-chunk.sh).

Asserts:
  - picker picks TEST-1
  - state transitions correctly (PENDING → IN_PROGRESS → DONE)
  - events written to log file
  - verifier passes
  - loop exits 0 after one iteration under --once
  - runner-state.json written
"""

from __future__ import annotations

import asyncio
import json
import os
import sqlite3
import subprocess
from pathlib import Path
from typing import Any, AsyncGenerator
from unittest.mock import patch

import pytest

from scripts.forge_runner._time import now_ist, to_iso
from scripts.forge_runner.state import ChunkRow, get_chunk


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _git(repo: Path, *args: str) -> None:
    result = subprocess.run(["git", *args], cwd=str(repo), capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed:\n{result.stderr}")


def _setup_repo_with_commit(repo: Path, chunk_id: str) -> None:
    """Add a commit with the chunk_id prefix to fake_repo."""
    # Create a file and commit it
    dummy = repo / "dummy.py"
    dummy.write_text("# dummy\n")
    _git(repo, "add", "dummy.py")
    _git(repo, "commit", "-m", f"{chunk_id}: implement feature via canned test")


def _write_last_run_json(repo: Path) -> None:
    forge_dir = repo / ".forge"
    forge_dir.mkdir(exist_ok=True)
    stamp = forge_dir / "last-run.json"
    stamp.write_text(json.dumps({"status": "ok", "chunk_id": "TEST-1"}))


def _insert_chunk_to_conn(
    conn: sqlite3.Connection,
    chunk_id: str,
    status: str = "PENDING",
    depends_on: str = "[]",
) -> None:
    conn.execute(
        """INSERT INTO chunks (id, title, status, attempts, plan_version,
               depends_on, created_at, updated_at)
           VALUES (?, ?, ?, 0, 'v1', ?, '2026-01-01T00:00:00+05:30',
                   '2026-01-01T00:00:00+05:30')""",
        (chunk_id, f"Title {chunk_id}", status, depends_on),
    )
    conn.commit()


def _dump_db_to_file(conn: sqlite3.Connection, path: Path) -> str:
    disk = sqlite3.connect(str(path))
    for line in conn.iterdump():
        disk.execute(line)
    disk.commit()
    disk.close()
    return str(path)


def _set_chunk_done_in_db(db_path: str, chunk_id: str) -> None:
    """Directly set chunk status to DONE in the sqlite file."""
    conn = sqlite3.connect(db_path, isolation_level=None)
    conn.execute("PRAGMA journal_mode=WAL")
    now = to_iso(now_ist())
    conn.execute("BEGIN IMMEDIATE")
    conn.execute(
        """UPDATE chunks SET status='DONE', runner_pid=NULL, failure_reason=NULL,
               updated_at=? WHERE id=?""",
        (now, chunk_id),
    )
    conn.execute("COMMIT")
    conn.close()


# ---------------------------------------------------------------------------
# Fake session
# ---------------------------------------------------------------------------


def _make_fake_session_events(chunk_id: str) -> list[dict[str, Any]]:
    """Return a list of runner event dicts (already translated from SDK messages)."""
    t = to_iso(now_ist())
    return [
        {
            "t": t,
            "chunk_id": chunk_id,
            "kind": "session_start",
            "payload": {
                "session_id": f"fake-{chunk_id}-001",
                "cwd": "/fake/repo",
                "allowed_tools_count": 9,
                "max_turns": 10,
            },
        },
        {
            "t": t,
            "chunk_id": chunk_id,
            "kind": "tool_use",
            "payload": {
                "tool": "Read",
                "input": {"file_path": "/fake/CLAUDE.md"},
            },
        },
        {
            "t": t,
            "chunk_id": chunk_id,
            "kind": "tool_result",
            "payload": {
                "tool_use_id": "tu_001",
                "is_error": False,
                "summary": "# ATLAS",
            },
        },
        {
            "t": t,
            "chunk_id": chunk_id,
            "kind": "text",
            "payload": {
                "content": "Implementing chunk...",
            },
        },
        {
            "t": t,
            "chunk_id": chunk_id,
            "kind": "session_end",
            "payload": {
                "session_id": f"fake-{chunk_id}-001",
                "stop_reason": "end_turn",
                "turns": 1,
                "usage": {},
            },
        },
    ]


async def _fake_run_session(
    chunk: ChunkRow, ctx: Any, *, db_path: str
) -> AsyncGenerator[dict[str, Any], None]:
    """Canned run_session that also side-effects state.db → DONE."""
    events = _make_fake_session_events(chunk.id)
    for event in events:
        yield event
        await asyncio.sleep(0)

    # Side-effect: mark chunk DONE (emulates post-chunk.sh)
    _set_chunk_done_in_db(db_path, chunk.id)


# ---------------------------------------------------------------------------
# Integration test
# ---------------------------------------------------------------------------


class TestIntegrationCanned:
    @pytest.mark.asyncio
    async def test_one_iteration_exits_zero(
        self,
        fake_repo: Path,
        fake_state_db: sqlite3.Connection,
        tmp_path: Path,
    ) -> None:
        """Full pipeline: pick → implement (canned) → verify → advance, exit 0."""
        chunk_id = "TEST-1"

        # Setup state.db with chunk PENDING
        _insert_chunk_to_conn(fake_state_db, chunk_id, "PENDING", "[]")
        db_path = _dump_db_to_file(fake_state_db, tmp_path / "state.db")

        # Setup repo: commit with chunk prefix + fresh stamp
        _setup_repo_with_commit(fake_repo, chunk_id)
        _write_last_run_json(fake_repo)

        # Setup conductor
        forge_dir = fake_repo / ".forge"
        forge_dir.mkdir(exist_ok=True)
        (forge_dir / "CONDUCTOR.md").write_text("# Test Conductor\n")

        # Setup log dir
        log_dir = tmp_path / "logs"
        log_dir.mkdir()

        # Import after setup
        from scripts.forge_runner.config import RunConfig
        from scripts.forge_runner.loop import run_loop
        from scripts.forge_runner.stages import RunContext

        config = RunConfig(
            filter_regex=rf"^{chunk_id}$",
            timeout_sec=120,
            max_turns=10,
            repo=str(fake_repo),
            log_dir=str(log_dir),
            once=True,
        )

        ctx = RunContext(
            config=config,
            repo=fake_repo,
            log_dir=log_dir,
            state_db_path=db_path,
            cancellation=asyncio.Event(),
            current_chunk=None,
            session_started_at=None,
            timeout_sec=120,
            max_turns=10,
            runner_pid=os.getpid(),
            loop_started_at=now_ist(),
            filter_regex=rf"^{chunk_id}$",
        )

        # Patch run_session with our canned version
        async def _canned_session(chunk: ChunkRow, c: Any) -> AsyncGenerator:
            async for ev in _fake_run_session(chunk, c, db_path=db_path):
                yield ev

        with patch(
            "scripts.forge_runner.stages.run_session",
            side_effect=_canned_session,
        ):
            exit_code = await run_loop(ctx)

        # Assertions
        assert exit_code == 0, f"Expected exit 0, got {exit_code}"

    @pytest.mark.asyncio
    async def test_state_db_row_done_after_loop(
        self,
        fake_repo: Path,
        fake_state_db: sqlite3.Connection,
        tmp_path: Path,
    ) -> None:
        """After successful loop iteration, state.db row is DONE."""
        chunk_id = "TEST-2"

        _insert_chunk_to_conn(fake_state_db, chunk_id, "PENDING", "[]")
        db_path = _dump_db_to_file(fake_state_db, tmp_path / "state.db")
        _setup_repo_with_commit(fake_repo, chunk_id)
        _write_last_run_json(fake_repo)
        (fake_repo / ".forge" / "CONDUCTOR.md").write_text("# Conductor\n")

        log_dir = tmp_path / "logs"
        log_dir.mkdir()

        from scripts.forge_runner.config import RunConfig
        from scripts.forge_runner.loop import run_loop
        from scripts.forge_runner.stages import RunContext

        config = RunConfig(
            filter_regex=rf"^{chunk_id}$",
            timeout_sec=120,
            max_turns=10,
            repo=str(fake_repo),
            log_dir=str(log_dir),
            once=True,
        )

        ctx = RunContext(
            config=config,
            repo=fake_repo,
            log_dir=log_dir,
            state_db_path=db_path,
            cancellation=asyncio.Event(),
            current_chunk=None,
            session_started_at=None,
            timeout_sec=120,
            max_turns=10,
            runner_pid=os.getpid(),
            loop_started_at=now_ist(),
            filter_regex=rf"^{chunk_id}$",
        )

        async def _canned_session(chunk: ChunkRow, c: Any) -> AsyncGenerator:
            async for ev in _fake_run_session(chunk, c, db_path=db_path):
                yield ev

        with patch("scripts.forge_runner.stages.run_session", side_effect=_canned_session):
            await run_loop(ctx)

        row = get_chunk(chunk_id, db_path)
        assert row is not None
        assert row.status == "DONE"

    @pytest.mark.asyncio
    async def test_log_file_written(
        self,
        fake_repo: Path,
        fake_state_db: sqlite3.Connection,
        tmp_path: Path,
    ) -> None:
        """Events are written to .forge/logs/<chunk_id>.log."""
        chunk_id = "TEST-3"

        _insert_chunk_to_conn(fake_state_db, chunk_id, "PENDING", "[]")
        db_path = _dump_db_to_file(fake_state_db, tmp_path / "state.db")
        _setup_repo_with_commit(fake_repo, chunk_id)
        _write_last_run_json(fake_repo)
        (fake_repo / ".forge" / "CONDUCTOR.md").write_text("# Conductor\n")

        log_dir = tmp_path / "logs"
        log_dir.mkdir()

        from scripts.forge_runner.config import RunConfig
        from scripts.forge_runner.loop import run_loop
        from scripts.forge_runner.stages import RunContext

        config = RunConfig(
            filter_regex=rf"^{chunk_id}$",
            timeout_sec=120,
            max_turns=10,
            repo=str(fake_repo),
            log_dir=str(log_dir),
            once=True,
        )

        ctx = RunContext(
            config=config,
            repo=fake_repo,
            log_dir=log_dir,
            state_db_path=db_path,
            cancellation=asyncio.Event(),
            current_chunk=None,
            session_started_at=None,
            timeout_sec=120,
            max_turns=10,
            runner_pid=os.getpid(),
            loop_started_at=now_ist(),
            filter_regex=rf"^{chunk_id}$",
        )

        async def _canned_session(chunk: ChunkRow, c: Any) -> AsyncGenerator:
            async for ev in _fake_run_session(chunk, c, db_path=db_path):
                yield ev

        with patch("scripts.forge_runner.stages.run_session", side_effect=_canned_session):
            await run_loop(ctx)

        log_file = log_dir / f"{chunk_id}.log"
        assert log_file.exists(), f"Log file not found: {log_file}"

        lines = [json.loads(line) for line in log_file.read_text().splitlines() if line.strip()]
        kinds = [ln["kind"] for ln in lines]
        assert "session_start" in kinds
        assert "session_end" in kinds

    @pytest.mark.asyncio
    async def test_runner_state_json_written(
        self,
        fake_repo: Path,
        fake_state_db: sqlite3.Connection,
        tmp_path: Path,
    ) -> None:
        """runner-state.json is written during the loop."""
        chunk_id = "TEST-4"

        _insert_chunk_to_conn(fake_state_db, chunk_id, "PENDING", "[]")
        db_path = _dump_db_to_file(fake_state_db, tmp_path / "state.db")
        _setup_repo_with_commit(fake_repo, chunk_id)
        _write_last_run_json(fake_repo)
        (fake_repo / ".forge" / "CONDUCTOR.md").write_text("# Conductor\n")

        log_dir = tmp_path / "logs"
        log_dir.mkdir()

        from scripts.forge_runner.config import RunConfig
        from scripts.forge_runner.loop import run_loop
        from scripts.forge_runner.stages import RunContext

        config = RunConfig(
            filter_regex=rf"^{chunk_id}$",
            timeout_sec=120,
            max_turns=10,
            repo=str(fake_repo),
            log_dir=str(log_dir),
            once=True,
        )

        ctx = RunContext(
            config=config,
            repo=fake_repo,
            log_dir=log_dir,
            state_db_path=db_path,
            cancellation=asyncio.Event(),
            current_chunk=None,
            session_started_at=None,
            timeout_sec=120,
            max_turns=10,
            runner_pid=os.getpid(),
            loop_started_at=now_ist(),
            filter_regex=rf"^{chunk_id}$",
        )

        async def _canned_session(chunk: ChunkRow, c: Any) -> AsyncGenerator:
            async for ev in _fake_run_session(chunk, c, db_path=db_path):
                yield ev

        with patch("scripts.forge_runner.stages.run_session", side_effect=_canned_session):
            await run_loop(ctx)

        runner_state_file = log_dir / "runner-state.json"
        assert runner_state_file.exists(), "runner-state.json not written"

        state = json.loads(runner_state_file.read_text())
        assert state.get("schema_version") == "1"
        assert "runner_pid" in state


class TestCliDryRunIntegration:
    def test_dry_run_exits_two_on_stalled(
        self,
        fake_repo: Path,
        fake_state_db: sqlite3.Connection,
        tmp_path: Path,
    ) -> None:
        """--dry-run exits 2 when no eligible chunk."""
        from scripts.forge_runner.cli import main

        db_path = tmp_path / "state.db"
        disk = sqlite3.connect(str(db_path))
        for line in fake_state_db.iterdump():
            disk.execute(line)
        disk.commit()
        disk.close()

        # Setup conductor + state.db structure
        forge_dir = fake_repo / ".forge"
        forge_dir.mkdir(exist_ok=True)
        (forge_dir / "CONDUCTOR.md").write_text("# Conductor\n")

        log_dir = tmp_path / "logs"
        log_dir.mkdir()

        # Patch state_db resolution to our tmp file
        # Create orchestrator dir with state.db
        (fake_repo / "orchestrator").mkdir(exist_ok=True)
        import shutil

        shutil.copy(str(db_path), str(fake_repo / "orchestrator" / "state.db"))

        exit_code = main(
            [
                "--dry-run",
                "--filter",
                "^NOPE$",
                "--repo",
                str(fake_repo),
                "--log-dir",
                str(log_dir),
            ]
        )
        # No matching chunk → stalled → exit 2
        assert exit_code == 2
