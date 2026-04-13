"""SC-008: Per-chunk overhead timing assertion.

Runs the loop pipeline (picker + state update + verifier stub + log flush)
9 times on canned data and asserts average per-chunk overhead < 5 seconds.

"Overhead" here means everything except the actual inner session time (which
is a no-op in this test because we use a canned event generator with zero
network latency).

This test does NOT make real SDK calls — it uses the same canned-event
pattern as test_integration_canned.py.
"""

from __future__ import annotations

import asyncio
import json
import os
import sqlite3
import subprocess
import time
from pathlib import Path
from typing import Any, AsyncGenerator
from unittest.mock import patch

import pytest

from scripts.forge_runner._time import now_ist, to_iso
from scripts.forge_runner.state import ChunkRow


# ---------------------------------------------------------------------------
# Helpers (duplicated locally to keep this test self-contained)
# ---------------------------------------------------------------------------


def _git(repo: Path, *args: str) -> None:
    result = subprocess.run(["git", *args], cwd=str(repo), capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed:\n{result.stderr}")


def _setup_repo(repo: Path) -> None:
    _git(repo, "init")
    _git(repo, "config", "--local", "user.email", "timing@atlas.local")
    _git(repo, "config", "--local", "user.name", "Timing Test")
    readme = repo / "README.md"
    readme.write_text("timing repo\n")
    _git(repo, "add", "README.md")
    _git(repo, "commit", "-m", "chore: timing base commit")


def _add_commit(repo: Path, chunk_id: str) -> None:
    dummy = repo / f"dummy_{chunk_id}.py"
    dummy.write_text(f"# {chunk_id}\n")
    _git(repo, "add", str(dummy.name))
    _git(repo, "commit", "-m", f"{chunk_id}: timing test canned commit")


def _write_stamp(repo: Path) -> None:
    forge_dir = repo / ".forge"
    forge_dir.mkdir(exist_ok=True)
    stamp = forge_dir / "last-run.json"
    stamp.write_text(json.dumps({"status": "ok", "chunk_id": "any"}))


def _create_db(db_path: Path) -> None:
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript("""
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
    """)
    conn.commit()
    conn.close()


def _insert_chunk(db_path: Path, chunk_id: str) -> None:
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute(
        """INSERT INTO chunks (id, title, status, plan_version, depends_on,
               created_at, updated_at)
           VALUES (?, ?, 'PENDING', 'timing-v1', '[]',
                   '2026-01-01T00:00:00+05:30', '2026-01-01T00:00:00+05:30')""",
        (chunk_id, f"Timing chunk {chunk_id}"),
    )
    conn.commit()
    conn.close()


def _set_done(db_path: Path, chunk_id: str) -> None:
    conn = sqlite3.connect(str(db_path), isolation_level=None)
    conn.execute("PRAGMA journal_mode=WAL")
    now = to_iso(now_ist())
    conn.execute("BEGIN IMMEDIATE")
    conn.execute(
        "UPDATE chunks SET status='DONE', runner_pid=NULL, updated_at=? WHERE id=?",
        (now, chunk_id),
    )
    conn.execute("COMMIT")
    conn.close()


def _make_canned_events(chunk_id: str) -> list[dict[str, Any]]:
    t = to_iso(now_ist())
    return [
        {
            "t": t,
            "chunk_id": chunk_id,
            "kind": "session_start",
            "payload": {
                "cwd": "/fake",
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
            "kind": "session_end",
            "payload": {
                "stop_reason": "end_turn",
                "turns": 1,
                "usage": {},
            },
        },
    ]


# ---------------------------------------------------------------------------
# SC-008 timing test
# ---------------------------------------------------------------------------


class TestSC008Timing:
    """SC-008: average per-chunk overhead must be < 5 seconds over 9 iterations."""

    CHUNKS = [f"SC008-{i}" for i in range(1, 10)]  # 9 chunks
    MAX_OVERHEAD_PER_CHUNK_SECONDS = 5.0

    @pytest.mark.asyncio
    async def test_per_chunk_overhead_under_5s(self, tmp_path: Path) -> None:
        repo = tmp_path / "repo"
        repo.mkdir()
        _setup_repo(repo)
        (repo / ".forge").mkdir()
        (repo / ".forge" / "CONDUCTOR.md").write_text("# Test Conductor\n")

        db_path = tmp_path / "state.db"
        _create_db(db_path)

        log_dir = tmp_path / "logs"
        log_dir.mkdir()

        # Pre-create commits and chunks for all 9 iterations
        for chunk_id in self.CHUNKS:
            _add_commit(repo, chunk_id)
            _insert_chunk(db_path, chunk_id)

        from scripts.forge_runner.config import RunConfig
        from scripts.forge_runner.loop import run_loop
        from scripts.forge_runner.stages import RunContext

        iteration_times: list[float] = []

        for chunk_id in self.CHUNKS:
            _write_stamp(repo)

            config = RunConfig(
                filter_regex=rf"^{chunk_id}$",
                timeout_sec=120,
                max_turns=10,
                repo=str(repo),
                log_dir=str(log_dir),
                once=True,
            )

            ctx = RunContext(
                config=config,
                repo=repo,
                log_dir=log_dir,
                state_db_path=str(db_path),
                cancellation=asyncio.Event(),
                current_chunk=None,
                session_started_at=None,
                timeout_sec=120,
                max_turns=10,
                runner_pid=os.getpid(),
                loop_started_at=now_ist(),
                filter_regex=rf"^{chunk_id}$",
            )

            _chunk_id = chunk_id  # capture for closure

            async def _canned(chunk: ChunkRow, c: Any) -> AsyncGenerator:
                for ev in _make_canned_events(chunk.id):
                    yield ev
                    await asyncio.sleep(0)
                _set_done(db_path, chunk.id)

            t_start = time.monotonic()
            with patch("scripts.forge_runner.stages.run_session", side_effect=_canned):
                await run_loop(ctx)
            t_elapsed = time.monotonic() - t_start
            iteration_times.append(t_elapsed)

        avg = sum(iteration_times) / len(iteration_times)
        max_seen = max(iteration_times)

        print("\nSC-008 timing results:")
        print(f"  iterations : {len(iteration_times)}")
        print(f"  avg/chunk  : {avg:.3f}s")
        print(f"  max/chunk  : {max_seen:.3f}s")
        print(f"  all times  : {[f'{t:.3f}' for t in iteration_times]}")

        assert avg < self.MAX_OVERHEAD_PER_CHUNK_SECONDS, (
            f"SC-008 FAIL: average per-chunk overhead {avg:.3f}s >= "
            f"{self.MAX_OVERHEAD_PER_CHUNK_SECONDS}s limit"
        )
