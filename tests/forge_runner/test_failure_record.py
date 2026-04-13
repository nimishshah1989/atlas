"""Tests for build_failure_record / write_failure_record (T038).

Covers:
  - Record is valid JSON and contains all required schema fields
  - Each failed_check value produces the correct suggested_recovery
  - Secrets scrubbed (API key in an event is redacted in last_events)
  - Atomic write: concurrent reader never sees partial file
  - Malformed log file handled gracefully (last_events = [])
"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from scripts.forge_runner._time import now_ist, to_iso
from scripts.forge_runner.logs import build_failure_record, write_failure_record

# ---------------------------------------------------------------------------
# Required top-level fields per contracts/failure-record.schema.json
# ---------------------------------------------------------------------------

REQUIRED_FIELDS = {
    "chunk_id",
    "failed_at",
    "failed_check",
    "failed_check_detail",
    "session_id",
    "last_events",
    "state_row",
    "git_status",
    "git_log_last_5",
    "suggested_recovery",
    "runner_pid",
    "runner_version",
}

ALL_FAILED_CHECKS = [
    "state_db_not_done",
    "no_commit_with_prefix",
    "stamp_not_fresh",
    "dirty_working_tree",
    "shipped_needs_sync",
]

# Expected substring in suggested_recovery for each failed_check
_RECOVERY_SUBSTRINGS: dict[str, str] = {
    "state_db_not_done": "post-chunk.sh",
    "no_commit_with_prefix": "forge-ship.sh",
    "stamp_not_fresh": "last-run.json",
    "dirty_working_tree": "git status",
    "shipped_needs_sync": "post-chunk.sh",
}


# ---------------------------------------------------------------------------
# Helpers / fixtures
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
"""


def _make_state_db(tmp_path: Path, chunk_id: str = "TEST-1", status: str = "FAILED") -> str:
    """Create a minimal SQLite DB with one chunk row, return the path."""
    db_path = str(tmp_path / "state.db")
    conn = sqlite3.connect(db_path)
    conn.executescript(CREATE_CHUNKS_DDL)
    now = to_iso(now_ist())
    conn.execute(
        """INSERT INTO chunks
           (id, title, status, attempts, plan_version, depends_on, created_at, updated_at)
           VALUES (?, 'Test chunk', ?, 1, 'v1', '[]', ?, ?)""",
        (chunk_id, status, now, now),
    )
    conn.commit()
    conn.close()
    return db_path


def _make_ctx(
    tmp_path: Path,
    chunk_id: str = "TEST-1",
    log_dir: Path | None = None,
    db_status: str = "FAILED",
) -> SimpleNamespace:
    """Build a minimal RunContext-like namespace for tests."""
    if log_dir is None:
        log_dir = tmp_path / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    db_path = _make_state_db(tmp_path, chunk_id=chunk_id, status=db_status)

    import os

    return SimpleNamespace(
        log_dir=log_dir,
        repo=str(tmp_path),  # not a real git repo — git calls return empty string
        state_db_path=db_path,
        runner_pid=os.getpid(),
        session_id=f"forge-{chunk_id}-{os.getpid()}",
    )


def _write_log_events(log_dir: Path, chunk_id: str, events: list[Any]) -> None:
    """Write a series of events as JSONL to the chunk log."""
    log_path = log_dir / f"{chunk_id}.log"
    with log_path.open("w", encoding="utf-8") as fh:
        for event in events:
            fh.write(json.dumps(event) + "\n")


# ---------------------------------------------------------------------------
# T038a: all required fields present
# ---------------------------------------------------------------------------


def test_build_failure_record_contains_all_required_fields(tmp_path: Path) -> None:
    chunk_id = "TEST-1"
    ctx = _make_ctx(tmp_path, chunk_id=chunk_id)
    record = build_failure_record(
        chunk_id=chunk_id,
        failed_check="state_db_not_done",
        detail="status is FAILED, not DONE",
        ctx=ctx,
    )
    missing = REQUIRED_FIELDS - set(record.keys())
    assert not missing, f"Missing fields: {missing}"


def test_build_failure_record_is_json_serialisable(tmp_path: Path) -> None:
    chunk_id = "TEST-1"
    ctx = _make_ctx(tmp_path, chunk_id=chunk_id)
    record = build_failure_record(
        chunk_id=chunk_id,
        failed_check="dirty_working_tree",
        detail="dirty: M some_file.py",
        ctx=ctx,
    )
    # Should not raise
    serialised = json.dumps(record)
    parsed = json.loads(serialised)
    assert parsed["chunk_id"] == chunk_id


def test_build_failure_record_chunk_id_preserved(tmp_path: Path) -> None:
    chunk_id = "V1-1"
    ctx = _make_ctx(tmp_path, chunk_id=chunk_id)
    record = build_failure_record(
        chunk_id=chunk_id,
        failed_check="no_commit_with_prefix",
        detail="latest commit 'chore: something' does not start with V1-1:",
        ctx=ctx,
    )
    assert record["chunk_id"] == chunk_id


def test_build_failure_record_failed_check_preserved(tmp_path: Path) -> None:
    chunk_id = "TEST-1"
    ctx = _make_ctx(tmp_path, chunk_id=chunk_id)
    for check in ALL_FAILED_CHECKS:
        record = build_failure_record(
            chunk_id=chunk_id,
            failed_check=check,
            detail=f"test detail for {check}",
            ctx=ctx,
        )
        assert record["failed_check"] == check


def test_build_failure_record_runner_pid_is_int(tmp_path: Path) -> None:
    chunk_id = "TEST-1"
    ctx = _make_ctx(tmp_path, chunk_id=chunk_id)
    record = build_failure_record(
        chunk_id=chunk_id,
        failed_check="stamp_not_fresh",
        detail="stamp too old",
        ctx=ctx,
    )
    assert isinstance(record["runner_pid"], int)
    assert record["runner_pid"] >= 1


def test_build_failure_record_last_events_is_list(tmp_path: Path) -> None:
    chunk_id = "TEST-1"
    ctx = _make_ctx(tmp_path, chunk_id=chunk_id)
    record = build_failure_record(
        chunk_id=chunk_id,
        failed_check="state_db_not_done",
        detail="not done",
        ctx=ctx,
    )
    assert isinstance(record["last_events"], list)


def test_build_failure_record_git_status_is_string(tmp_path: Path) -> None:
    chunk_id = "TEST-1"
    ctx = _make_ctx(tmp_path, chunk_id=chunk_id)
    record = build_failure_record(
        chunk_id=chunk_id,
        failed_check="dirty_working_tree",
        detail="dirty",
        ctx=ctx,
    )
    assert isinstance(record["git_status"], str)


def test_build_failure_record_git_log_last_5_is_list(tmp_path: Path) -> None:
    chunk_id = "TEST-1"
    ctx = _make_ctx(tmp_path, chunk_id=chunk_id)
    record = build_failure_record(
        chunk_id=chunk_id,
        failed_check="dirty_working_tree",
        detail="dirty",
        ctx=ctx,
    )
    assert isinstance(record["git_log_last_5"], list)
    assert len(record["git_log_last_5"]) <= 5


def test_build_failure_record_state_row_is_dict(tmp_path: Path) -> None:
    chunk_id = "TEST-1"
    ctx = _make_ctx(tmp_path, chunk_id=chunk_id)
    record = build_failure_record(
        chunk_id=chunk_id,
        failed_check="state_db_not_done",
        detail="status=FAILED",
        ctx=ctx,
    )
    assert isinstance(record["state_row"], dict)


# ---------------------------------------------------------------------------
# T038b: each failed_check → correct suggested_recovery
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("failed_check", ALL_FAILED_CHECKS)
def test_suggested_recovery_per_check(tmp_path: Path, failed_check: str) -> None:
    chunk_id = "TEST-1"
    ctx = _make_ctx(tmp_path, chunk_id=chunk_id)
    record = build_failure_record(
        chunk_id=chunk_id,
        failed_check=failed_check,
        detail="test",
        ctx=ctx,
    )
    expected_substring = _RECOVERY_SUBSTRINGS[failed_check]
    assert expected_substring in record["suggested_recovery"], (
        f"For {failed_check!r}, expected {expected_substring!r} in "
        f"suggested_recovery, got: {record['suggested_recovery']!r}"
    )


def test_suggested_recovery_contains_chunk_id(tmp_path: Path) -> None:
    """chunk_id should be interpolated into suggested_recovery."""
    chunk_id = "V2-42"
    ctx = _make_ctx(tmp_path, chunk_id=chunk_id)
    record = build_failure_record(
        chunk_id=chunk_id,
        failed_check="state_db_not_done",
        detail="not done",
        ctx=ctx,
    )
    assert chunk_id in record["suggested_recovery"]


# ---------------------------------------------------------------------------
# T038c: secrets scrubbed in last_events
# ---------------------------------------------------------------------------

_FAKE_SENTINEL_KEY = "sk-ant-api03-AAAAAAAAAAAAAAAAAAAAAA"


def test_secrets_scrubbed_in_last_events(tmp_path: Path) -> None:
    """API key appearing in a log event must be redacted in last_events."""
    chunk_id = "TEST-1"
    log_dir = tmp_path / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    # Write a log with a secret in it
    events = [
        {"kind": "tool_use", "payload": {"api_key": _FAKE_SENTINEL_KEY}},
        {"kind": "text", "payload": {"text": f"Bearer {_FAKE_SENTINEL_KEY}"}},
    ]
    _write_log_events(log_dir, chunk_id, events)

    ctx = _make_ctx(tmp_path, chunk_id=chunk_id, log_dir=log_dir)
    record = build_failure_record(
        chunk_id=chunk_id,
        failed_check="state_db_not_done",
        detail="not done",
        ctx=ctx,
    )

    # Serialise to JSON and check no raw API key appears
    serialised = json.dumps(record)
    assert _FAKE_SENTINEL_KEY not in serialised, (
        "API key should have been scrubbed from last_events"
    )
    # Verify the redaction placeholder is present
    assert "<redacted" in serialised


# ---------------------------------------------------------------------------
# T038d: atomic write — concurrent reader never sees partial JSON
# ---------------------------------------------------------------------------


def test_write_failure_record_atomic(tmp_path: Path) -> None:
    """Concurrent reader loop never hits a JSONDecodeError during write."""
    chunk_id = "TEST-ATOMIC"
    log_dir = tmp_path / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    failure_path = log_dir / f"{chunk_id}.failure.json"

    ctx = _make_ctx(tmp_path, chunk_id=chunk_id, log_dir=log_dir)
    record = build_failure_record(
        chunk_id=chunk_id,
        failed_check="dirty_working_tree",
        detail="dirty tree test",
        ctx=ctx,
    )

    errors: list[str] = []
    stop_flag = threading.Event()

    def reader() -> None:
        while not stop_flag.is_set():
            if failure_path.exists():
                try:
                    data = failure_path.read_text(encoding="utf-8")
                    if data:
                        json.loads(data)
                except json.JSONDecodeError as exc:
                    errors.append(str(exc))
            time.sleep(0.0001)

    reader_thread = threading.Thread(target=reader, daemon=True)
    reader_thread.start()

    # Write many times rapidly
    for _ in range(50):
        write_failure_record(chunk_id, record, log_dir)

    stop_flag.set()
    reader_thread.join(timeout=2)

    assert not errors, f"Concurrent reader saw JSON decode errors: {errors}"


# ---------------------------------------------------------------------------
# T038e: malformed log file handled gracefully
# ---------------------------------------------------------------------------


def test_malformed_log_file_gives_empty_last_events(tmp_path: Path) -> None:
    """If the log file contains non-JSON lines, last_events is [] (or partial valid)."""
    chunk_id = "TEST-BAD-LOG"
    log_dir = tmp_path / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    log_path = log_dir / f"{chunk_id}.log"
    log_path.write_text("this is not json\n{broken: json}\n\n", encoding="utf-8")

    ctx = _make_ctx(tmp_path, chunk_id=chunk_id, log_dir=log_dir)
    record = build_failure_record(
        chunk_id=chunk_id,
        failed_check="stamp_not_fresh",
        detail="stamp old",
        ctx=ctx,
    )
    # Should not raise; last_events should be an empty list (malformed lines skipped)
    assert isinstance(record["last_events"], list)
    assert len(record["last_events"]) == 0


def test_missing_log_file_gives_empty_last_events(tmp_path: Path) -> None:
    """If no log file exists, last_events is []."""
    chunk_id = "TEST-NO-LOG"
    ctx = _make_ctx(tmp_path, chunk_id=chunk_id)
    record = build_failure_record(
        chunk_id=chunk_id,
        failed_check="stamp_not_fresh",
        detail="stamp old",
        ctx=ctx,
    )
    assert record["last_events"] == []


# ---------------------------------------------------------------------------
# T038f: last_events capped at 100
# ---------------------------------------------------------------------------


def test_last_events_capped_at_100(tmp_path: Path) -> None:
    """Even if log has >100 lines, last_events only contains the last 100."""
    chunk_id = "TEST-CAP"
    log_dir = tmp_path / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    events = [{"seq": i, "kind": "text"} for i in range(150)]
    _write_log_events(log_dir, chunk_id, events)

    ctx = _make_ctx(tmp_path, chunk_id=chunk_id, log_dir=log_dir)
    record = build_failure_record(
        chunk_id=chunk_id,
        failed_check="state_db_not_done",
        detail="not done",
        ctx=ctx,
    )
    assert len(record["last_events"]) == 100
    # Confirms we got the LAST 100, not the first 100
    assert record["last_events"][0]["seq"] == 50
    assert record["last_events"][-1]["seq"] == 149


# ---------------------------------------------------------------------------
# T038g: write_failure_record creates parent dir if missing
# ---------------------------------------------------------------------------


def test_write_failure_record_creates_parent_dir(tmp_path: Path) -> None:
    chunk_id = "TEST-MKDIR"
    log_dir = tmp_path / "deep" / "nested" / "logs"
    # Do NOT create the directory first
    ctx = _make_ctx(tmp_path, chunk_id=chunk_id, log_dir=log_dir)
    record = build_failure_record(
        chunk_id=chunk_id,
        failed_check="state_db_not_done",
        detail="not done",
        ctx=ctx,
    )
    write_failure_record(chunk_id, record, log_dir)

    written_path = log_dir / f"{chunk_id}.failure.json"
    assert written_path.exists()
    parsed = json.loads(written_path.read_text())
    assert parsed["chunk_id"] == chunk_id
