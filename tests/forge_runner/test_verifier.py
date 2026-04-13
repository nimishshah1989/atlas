"""Tests for scripts/forge_runner/verifier.py (T022).

Tests:
  - All four checks passing
  - Each check failing individually
  - shipped_needs_sync edge case (commit prefix exists but state.db not DONE)
  - Uses fake_repo fixture for git state
"""

from __future__ import annotations

import json
import sqlite3
import subprocess
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any


from scripts.forge_runner._time import now_ist
from scripts.forge_runner.verifier import run_four_checks


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_ctx(
    repo: Path,
    db_path: str,
    session_started_at: Any = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        repo=repo,
        state_db_path=db_path,
        session_started_at=session_started_at or now_ist(),
    )


def _insert_chunk(
    conn: sqlite3.Connection,
    chunk_id: str,
    status: str = "DONE",
) -> None:
    conn.execute(
        """INSERT OR REPLACE INTO chunks
               (id, title, status, attempts, plan_version, depends_on,
                created_at, updated_at)
           VALUES (?, ?, ?, 0, 'v1', '[]',
                   '2026-01-01T00:00:00+05:30', '2026-01-01T00:00:00+05:30')""",
        (chunk_id, f"Title {chunk_id}", status),
    )
    conn.commit()


def _write_db_to_file(conn: sqlite3.Connection, tmp_path: Path, filename: str = "state.db") -> str:
    db_file = tmp_path / filename
    disk = sqlite3.connect(str(db_file))
    for line in conn.iterdump():
        disk.execute(line)
    disk.commit()
    disk.close()
    return str(db_file)


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        ["git", *args],
        cwd=str(repo),
        capture_output=True,
        text=True,
    )
    return result


def _git_commit(repo: Path, message: str) -> None:
    """Create an empty commit with the given message."""
    result = _git(repo, "commit", "--allow-empty", "-m", message)
    if result.returncode != 0:
        raise RuntimeError(f"git commit failed: {result.stderr}")


def _write_last_run_json(repo: Path, content: dict[str, Any] | None = None) -> Path:
    """Write .forge/last-run.json with optional content."""
    forge_dir = repo / ".forge"
    forge_dir.mkdir(exist_ok=True)
    stamp = forge_dir / "last-run.json"
    stamp.write_text(json.dumps(content or {"status": "ok"}))
    return stamp


# ---------------------------------------------------------------------------
# All-pass test
# ---------------------------------------------------------------------------


class TestAllChecksPassing:
    def test_all_four_checks_pass(
        self,
        fake_repo: Path,
        fake_state_db: sqlite3.Connection,
        tmp_path: Path,
    ) -> None:
        chunk_id = "TEST-1"

        # Check 1: state.db DONE
        _insert_chunk(fake_state_db, chunk_id, "DONE")
        db_path = _write_db_to_file(fake_state_db, tmp_path)

        # Check 2: commit with prefix
        _git_commit(fake_repo, f"{chunk_id}: implement feature")

        # Check 3: fresh stamp
        _write_last_run_json(fake_repo)

        # Check 4: clean tree (no modifications)
        ctx = _make_ctx(fake_repo, db_path)
        result = run_four_checks(chunk_id, ctx)

        assert result.passed is True
        assert result.failed_check is None
        assert result.needs_sync is False


# ---------------------------------------------------------------------------
# Check 1: state.db not DONE
# ---------------------------------------------------------------------------


class TestCheck1StatDbNotDone:
    def test_check1_fails_when_status_pending(
        self,
        fake_repo: Path,
        fake_state_db: sqlite3.Connection,
        tmp_path: Path,
    ) -> None:
        chunk_id = "TEST-1"
        _insert_chunk(fake_state_db, chunk_id, "PENDING")
        db_path = _write_db_to_file(fake_state_db, tmp_path)

        # No commit with prefix
        ctx = _make_ctx(fake_repo, db_path)
        result = run_four_checks(chunk_id, ctx)

        assert result.passed is False
        assert result.failed_check == "state_db_not_done"
        assert result.needs_sync is False

    def test_check1_fails_when_chunk_missing(
        self,
        fake_repo: Path,
        fake_state_db: sqlite3.Connection,
        tmp_path: Path,
    ) -> None:
        db_path = _write_db_to_file(fake_state_db, tmp_path)
        ctx = _make_ctx(fake_repo, db_path)
        result = run_four_checks("NONEXISTENT", ctx)

        assert result.passed is False
        assert result.failed_check == "state_db_not_done"


# ---------------------------------------------------------------------------
# Check 2: no commit with prefix
# ---------------------------------------------------------------------------


class TestCheck2NoCommitPrefix:
    def test_check2_fails_when_no_matching_commit(
        self,
        fake_repo: Path,
        fake_state_db: sqlite3.Connection,
        tmp_path: Path,
    ) -> None:
        chunk_id = "TEST-1"
        _insert_chunk(fake_state_db, chunk_id, "DONE")
        db_path = _write_db_to_file(fake_state_db, tmp_path)

        # Commit with WRONG prefix
        _git_commit(fake_repo, "OTHER-1: unrelated commit")

        ctx = _make_ctx(fake_repo, db_path)
        result = run_four_checks(chunk_id, ctx)

        assert result.passed is False
        assert result.failed_check == "no_commit_with_prefix"

    def test_check2_passes_with_colon_prefix(
        self,
        fake_repo: Path,
        fake_state_db: sqlite3.Connection,
        tmp_path: Path,
    ) -> None:
        chunk_id = "V1-1"
        _insert_chunk(fake_state_db, chunk_id, "DONE")
        db_path = _write_db_to_file(fake_state_db, tmp_path)

        _git_commit(fake_repo, "V1-1: ship it")
        _write_last_run_json(fake_repo)

        ctx = _make_ctx(fake_repo, db_path)
        result = run_four_checks(chunk_id, ctx)

        # Should fail on check 4 (dirty tree possibly) or pass — but not check 2
        if not result.passed:
            assert result.failed_check != "no_commit_with_prefix"

    def test_check2_passes_with_space_prefix(
        self,
        fake_repo: Path,
        fake_state_db: sqlite3.Connection,
        tmp_path: Path,
    ) -> None:
        chunk_id = "V1-1"
        _insert_chunk(fake_state_db, chunk_id, "DONE")
        db_path = _write_db_to_file(fake_state_db, tmp_path)

        _git_commit(fake_repo, "V1-1 — some change")
        _write_last_run_json(fake_repo)

        ctx = _make_ctx(fake_repo, db_path)
        result = run_four_checks(chunk_id, ctx)

        if not result.passed:
            assert result.failed_check != "no_commit_with_prefix"


# ---------------------------------------------------------------------------
# Check 3: stamp not fresh
# ---------------------------------------------------------------------------


class TestCheck3StampNotFresh:
    def test_check3_fails_when_stamp_missing(
        self,
        fake_repo: Path,
        fake_state_db: sqlite3.Connection,
        tmp_path: Path,
    ) -> None:
        chunk_id = "TEST-1"
        _insert_chunk(fake_state_db, chunk_id, "DONE")
        db_path = _write_db_to_file(fake_state_db, tmp_path)

        _git_commit(fake_repo, f"{chunk_id}: implement")
        # Do NOT write last-run.json

        ctx = _make_ctx(fake_repo, db_path)
        result = run_four_checks(chunk_id, ctx)

        assert result.passed is False
        assert result.failed_check == "stamp_not_fresh"

    def test_check3_fails_when_stamp_old(
        self,
        fake_repo: Path,
        fake_state_db: sqlite3.Connection,
        tmp_path: Path,
    ) -> None:
        chunk_id = "TEST-1"
        _insert_chunk(fake_state_db, chunk_id, "DONE")
        db_path = _write_db_to_file(fake_state_db, tmp_path)

        _git_commit(fake_repo, f"{chunk_id}: implement")
        stamp = _write_last_run_json(fake_repo)

        # Set stamp mtime to 3 hours ago
        old_time = time.time() - 10800
        import os

        os.utime(str(stamp), (old_time, old_time))

        # session started at now — stamp is much older than tolerance
        ctx = _make_ctx(fake_repo, db_path, session_started_at=now_ist())
        result = run_four_checks(chunk_id, ctx)

        assert result.passed is False
        assert result.failed_check == "stamp_not_fresh"

    def test_check3_passes_with_fresh_stamp(
        self,
        fake_repo: Path,
        fake_state_db: sqlite3.Connection,
        tmp_path: Path,
    ) -> None:
        chunk_id = "TEST-1"
        _insert_chunk(fake_state_db, chunk_id, "DONE")
        db_path = _write_db_to_file(fake_state_db, tmp_path)

        _git_commit(fake_repo, f"{chunk_id}: implement")
        _write_last_run_json(fake_repo)  # just-written → fresh

        ctx = _make_ctx(fake_repo, db_path, session_started_at=now_ist())
        result = run_four_checks(chunk_id, ctx)

        # Should not fail on check 3
        if not result.passed:
            assert result.failed_check != "stamp_not_fresh"


# ---------------------------------------------------------------------------
# Check 4: dirty working tree
# ---------------------------------------------------------------------------


class TestCheck4DirtyTree:
    def test_check4_fails_when_untracked_file(
        self,
        fake_repo: Path,
        fake_state_db: sqlite3.Connection,
        tmp_path: Path,
    ) -> None:
        chunk_id = "TEST-1"
        _insert_chunk(fake_state_db, chunk_id, "DONE")
        db_path = _write_db_to_file(fake_state_db, tmp_path)

        _git_commit(fake_repo, f"{chunk_id}: implement")
        _write_last_run_json(fake_repo)

        # Create an untracked file outside exempt paths
        dirty_file = fake_repo / "dirty_untracked.py"
        dirty_file.write_text("# dirty\n")

        ctx = _make_ctx(fake_repo, db_path, session_started_at=now_ist())
        result = run_four_checks(chunk_id, ctx)

        assert result.passed is False
        assert result.failed_check == "dirty_working_tree"

    def test_check4_ignores_forge_dir(
        self,
        fake_repo: Path,
        fake_state_db: sqlite3.Connection,
        tmp_path: Path,
    ) -> None:
        chunk_id = "TEST-1"
        _insert_chunk(fake_state_db, chunk_id, "DONE")
        db_path = _write_db_to_file(fake_state_db, tmp_path)

        _git_commit(fake_repo, f"{chunk_id}: implement")
        _write_last_run_json(fake_repo)

        # Create file in .forge/ — should be exempt
        forge_extra = fake_repo / ".forge" / "extra.json"
        forge_extra.write_text("{}")

        ctx = _make_ctx(fake_repo, db_path, session_started_at=now_ist())
        result = run_four_checks(chunk_id, ctx)

        # Should pass (or fail on something else), but NOT fail on dirty_working_tree
        if not result.passed:
            assert result.failed_check != "dirty_working_tree"

    def test_check4_ignores_ralph_dir(
        self,
        fake_repo: Path,
        fake_state_db: sqlite3.Connection,
        tmp_path: Path,
    ) -> None:
        chunk_id = "TEST-1"
        _insert_chunk(fake_state_db, chunk_id, "DONE")
        db_path = _write_db_to_file(fake_state_db, tmp_path)

        _git_commit(fake_repo, f"{chunk_id}: implement")
        _write_last_run_json(fake_repo)

        # Create file in .ralph/ — should be exempt
        ralph_dir = fake_repo / ".ralph"
        ralph_dir.mkdir()
        (ralph_dir / "PROMPT.md").write_text("ralph prompt\n")

        ctx = _make_ctx(fake_repo, db_path, session_started_at=now_ist())
        result = run_four_checks(chunk_id, ctx)

        if not result.passed:
            assert result.failed_check != "dirty_working_tree"

    def test_check4_ignores_forge_runner_dir(
        self,
        fake_repo: Path,
        fake_state_db: sqlite3.Connection,
        tmp_path: Path,
    ) -> None:
        chunk_id = "TEST-1"
        _insert_chunk(fake_state_db, chunk_id, "DONE")
        db_path = _write_db_to_file(fake_state_db, tmp_path)

        _git_commit(fake_repo, f"{chunk_id}: implement")
        _write_last_run_json(fake_repo)

        # Create file in scripts/forge_runner/ — should be exempt
        fr_dir = fake_repo / "scripts" / "forge_runner"
        fr_dir.mkdir(parents=True)
        (fr_dir / "new_module.py").write_text("# new\n")

        ctx = _make_ctx(fake_repo, db_path, session_started_at=now_ist())
        result = run_four_checks(chunk_id, ctx)

        if not result.passed:
            assert result.failed_check != "dirty_working_tree"


# ---------------------------------------------------------------------------
# shipped_needs_sync edge case
# ---------------------------------------------------------------------------


class TestShippedNeedsSync:
    def test_needs_sync_when_commit_exists_but_db_not_done(
        self,
        fake_repo: Path,
        fake_state_db: sqlite3.Connection,
        tmp_path: Path,
    ) -> None:
        """Commit with chunk prefix exists but state.db says PENDING → needs_sync."""
        chunk_id = "TEST-1"
        # state.db NOT done
        _insert_chunk(fake_state_db, chunk_id, "PENDING")
        db_path = _write_db_to_file(fake_state_db, tmp_path)

        # But a commit with the prefix DID land
        _git_commit(fake_repo, f"{chunk_id}: shipped but sync missed")

        ctx = _make_ctx(fake_repo, db_path)
        result = run_four_checks(chunk_id, ctx)

        assert result.passed is False
        assert result.failed_check == "shipped_needs_sync"
        assert result.needs_sync is True
        assert "state.db not DONE" in result.detail or chunk_id in result.detail

    def test_no_needs_sync_when_both_missing(
        self,
        fake_repo: Path,
        fake_state_db: sqlite3.Connection,
        tmp_path: Path,
    ) -> None:
        """State.db not done AND no commit → standard state_db_not_done."""
        chunk_id = "TEST-1"
        _insert_chunk(fake_state_db, chunk_id, "PENDING")
        db_path = _write_db_to_file(fake_state_db, tmp_path)

        # No commit with chunk prefix (only the initial fixture commit)
        ctx = _make_ctx(fake_repo, db_path)
        result = run_four_checks(chunk_id, ctx)

        assert result.passed is False
        assert result.failed_check == "state_db_not_done"
        assert result.needs_sync is False
