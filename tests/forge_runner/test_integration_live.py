"""T059: Live smoke test for forge-runner against a real Claude Agent SDK session.

This test is gated behind FORGE_RUNNER_LIVE=1.  It consumes real API quota and
is NOT run as part of the standard CI suite.  Run it manually once before
shipping L2-RUNNER to verify the end-to-end loop works against a live session.

Usage::

    FORGE_RUNNER_LIVE=1 pytest tests/forge_runner/test_integration_live.py -v --tb=short

The test:
  1. Creates a throwaway state.db + git repo in a temp directory.
  2. Inserts a minimal PENDING chunk ("LIVE-SMOKE-1").
  3. Invokes a real claude_agent_sdk.query() session via session.run_session().
  4. Verifies the runner wraps events correctly (session_start, >=1 tool_use or text, session_end).
  5. Verifies one full loop iteration can exit cleanly (no uncaught exception).

SC-001 gate: this test must pass before forge-runner ships.
"""

from __future__ import annotations

import os
import sqlite3
import subprocess
import textwrap
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

LIVE = bool(os.getenv("FORGE_RUNNER_LIVE"))


@pytest.mark.skipif(not LIVE, reason="live smoke test — set FORGE_RUNNER_LIVE=1 to enable")
class TestLiveSmoke:
    """SC-001: real SDK session, real events, one loop iteration."""

    @pytest.fixture(autouse=True)
    def _setup(self, tmp_path: Path) -> None:
        """Create an isolated state.db and git repo for the smoke run."""
        self.tmp = tmp_path

        # ── Git repo ───────────────────────────────────────────────────────────
        repo = tmp_path / "repo"
        repo.mkdir()
        self._git(repo, "init")
        self._git(repo, "config", "--local", "user.email", "smoke@atlas.local")
        self._git(repo, "config", "--local", "user.name", "Smoke Test")
        readme = repo / "README.md"
        readme.write_text("smoke test repo\n")
        self._git(repo, "add", "README.md")
        self._git(repo, "commit", "-m", "chore: initial commit for live smoke")
        self.repo = repo

        # ── state.db ──────────────────────────────────────────────────────────
        db_path = tmp_path / "state.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute("PRAGMA journal_mode=WAL")
        conn.executescript(
            textwrap.dedent("""
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
        )
        conn.execute(
            """
            INSERT INTO chunks (id, title, status, plan_version, depends_on, created_at, updated_at)
            VALUES (?, ?, 'PENDING', 'smoke-v1', '[]', datetime('now'), datetime('now'))
            """,
            ("LIVE-SMOKE-1", "Live smoke test chunk — throwaway"),
        )
        conn.commit()
        conn.close()
        self.db_path = db_path

        # ── log dir ───────────────────────────────────────────────────────────
        log_dir = tmp_path / ".forge" / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        self.log_dir = log_dir

    def _git(self, repo: Path, *args: str) -> None:
        result = subprocess.run(["git", *args], cwd=str(repo), capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"git {' '.join(args)} failed:\n{result.stderr}")

    def test_session_produces_real_events(self) -> None:
        """A real SDK session must produce at least session_start and session_end."""
        import asyncio

        from scripts.forge_runner._time import now_ist, to_iso
        from scripts.forge_runner.logs import write_event
        from scripts.forge_runner.state import get_chunk, mark_in_progress
        from scripts.forge_runner.session import run_session

        chunk_id = "LIVE-SMOKE-1"
        state_db = str(self.db_path)

        mark_in_progress(chunk_id, os.getpid(), to_iso(now_ist()), state_db)

        row = get_chunk(chunk_id, state_db)
        assert row is not None, "chunk row must exist after mark_in_progress"
        assert row.status == "IN_PROGRESS"

        ctx: Any = SimpleNamespace(
            repo=str(self.repo),
            log_dir=self.log_dir,
            state_db_path=state_db,
            runner_pid=os.getpid(),
            max_turns=5,
            timeout_sec=120,
            chunk_id=chunk_id,
        )

        events: list[dict] = []

        async def _collect() -> None:
            async for event in run_session(row, ctx):
                write_event(chunk_id, event, self.log_dir)
                events.append(event)

        asyncio.run(_collect())

        kinds = [e.get("kind") for e in events]
        assert "session_start" in kinds, f"no session_start in {kinds}"
        assert "session_end" in kinds, f"no session_end in {kinds}"

        has_content = any(k in kinds for k in ("tool_use", "text"))
        assert has_content, f"expected at least one tool_use or text event; got {kinds}"

        # Verify every event passes the required-fields check
        from scripts.forge_runner.logs import validate_log_file

        log_file = self.log_dir / f"{chunk_id}.log"
        assert log_file.exists(), "log file must exist after session"
        valid, errors = validate_log_file(log_file)
        assert valid, f"log file failed validation: {errors}"

    def test_loop_iteration_exits_cleanly(self) -> None:
        """One full loop iteration (pick → session → verify stub) must not raise."""
        import asyncio
        from unittest.mock import patch

        from scripts.forge_runner.config import RunConfig
        from scripts.forge_runner.loop import run_loop

        cfg = RunConfig(
            filter_regex="^LIVE-SMOKE-1$",
            state_db_path=str(self.db_path),
            repo=str(self.repo),
            log_dir=self.log_dir,
            once=True,
            dry_run=False,
            timeout_sec=120,
            max_turns=5,
            resume=False,
            retry=None,
            strict_dead_man=False,
            verbose=False,
        )

        # Stub the verifier so we don't need a real post-chunk setup
        with patch("scripts.forge_runner.loop.run_four_checks") as mock_verify:
            from scripts.forge_runner.verifier import CheckResult as VCheckResult

            mock_verify.return_value = VCheckResult(
                passed=True, failed_check=None, detail="smoke stub"
            )
            # Stub halt evaluation so it returns COMPLETE after one chunk
            with patch("scripts.forge_runner.loop.evaluate_halt") as mock_halt:
                from scripts.forge_runner.halt import HaltDecision

                mock_halt.return_value = HaltDecision.COMPLETE

                exit_code = asyncio.run(run_loop(cfg))

        # Accept 0 (complete) or 6 (stalled — chunk not pickable after session)
        # The key invariant is: no uncaught exception.
        assert exit_code in (0, 3, 6), f"loop_iteration expected exit 0/3/6, got {exit_code}"
