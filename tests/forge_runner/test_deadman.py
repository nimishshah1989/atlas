"""Tests for scripts/forge_runner/deadman.py (T043).

Covers:
  - orphan with dead pid → auto_reset in normal mode
  - orphan with dead pid → strict_halt when strict_dead_man=True
  - live pid owned by a forge_runner process → owned_by_other
  - live pid owned by a non-forge process → auto_reset (pid reused)
  - no IN_PROGRESS rows → clean

Uses:
  - os.getpid() as a safely-alive pid
  - 99999999 as a safely-dead pid (no sane system runs 100M processes)
  - monkeypatching of _pid_alive / _is_forge_runner for precision control
  - file-based SQLite temp DB (matches state.py's sqlite3.connect interface)
"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from scripts.forge_runner.deadman import DeadmanResult, scan_on_startup


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_ALIVE_PID = os.getpid()
_DEAD_PID = 99999999

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


def _make_db(tmp_path: Path, rows: list[dict[str, Any]]) -> str:
    """Create a temp state.db with the given chunk rows. Returns the path."""
    db_path = str(tmp_path / "state.db")
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(_DDL)
    for row in rows:
        conn.execute(
            """INSERT INTO chunks
               (id, title, status, attempts, last_error, plan_version,
                depends_on, created_at, updated_at, started_at, finished_at,
                runner_pid, failure_reason)
               VALUES (?, ?, ?, 0, NULL, 'v1', '[]',
                       '2026-01-01T00:00:00+05:30',
                       '2026-01-01T00:00:00+05:30',
                       NULL, NULL, ?, NULL)""",
            (row["id"], row.get("title", row["id"]), row["status"], row.get("pid")),
        )
    conn.commit()
    conn.close()
    return db_path


def _ctx(db_path: str, strict: bool = False) -> SimpleNamespace:
    """Build a minimal RunContext-like object."""
    config = SimpleNamespace(strict_dead_man=strict)
    return SimpleNamespace(
        state_db_path=db_path,
        config=config,
    )


def _get_status(db_path: str, chunk_id: str) -> str:
    conn = sqlite3.connect(db_path)
    row = conn.execute("SELECT status FROM chunks WHERE id = ?", (chunk_id,)).fetchone()
    conn.close()
    return row[0] if row else "NOT_FOUND"


# ---------------------------------------------------------------------------
# Test: no IN_PROGRESS rows → clean
# ---------------------------------------------------------------------------


def test_scan_no_in_progress_rows_returns_clean(tmp_path: Path) -> None:
    db = _make_db(tmp_path, [{"id": "V1-1", "status": "PENDING", "pid": None}])
    result = scan_on_startup(_ctx(db))
    assert result.action == "clean"
    assert "no IN_PROGRESS rows" in result.message


def test_scan_empty_table_returns_clean(tmp_path: Path) -> None:
    db = _make_db(tmp_path, [])
    result = scan_on_startup(_ctx(db))
    assert result.action == "clean"


# ---------------------------------------------------------------------------
# Test: dead pid → auto_reset in normal mode
# ---------------------------------------------------------------------------


def test_scan_dead_pid_auto_resets_in_normal_mode(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db = _make_db(tmp_path, [{"id": "V1-2", "status": "IN_PROGRESS", "pid": _DEAD_PID}])
    # Ensure _pid_alive returns False for the dead pid
    import scripts.forge_runner.deadman as dm

    monkeypatch.setattr(dm, "_pid_alive", lambda pid: False)

    result = scan_on_startup(_ctx(db, strict=False))

    assert result.action == "auto_reset"
    assert "V1-2" in result.message or any(d["chunk_id"] == "V1-2" for d in result.details)
    # Row must be reset
    assert _get_status(db, "V1-2") == "PENDING"


def test_scan_none_pid_auto_resets_in_normal_mode(tmp_path: Path) -> None:
    """runner_pid=NULL in DB (pid never recorded) → orphan → auto_reset."""
    db = _make_db(tmp_path, [{"id": "V1-3", "status": "IN_PROGRESS", "pid": None}])
    result = scan_on_startup(_ctx(db, strict=False))
    assert result.action == "auto_reset"
    assert _get_status(db, "V1-3") == "PENDING"


# ---------------------------------------------------------------------------
# Test: dead pid + strict mode → strict_halt
# ---------------------------------------------------------------------------


def test_scan_dead_pid_strict_mode_returns_strict_halt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db = _make_db(tmp_path, [{"id": "V1-4", "status": "IN_PROGRESS", "pid": _DEAD_PID}])
    import scripts.forge_runner.deadman as dm

    monkeypatch.setattr(dm, "_pid_alive", lambda pid: False)

    result = scan_on_startup(_ctx(db, strict=True))

    assert result.action == "strict_halt"
    assert "V1-4" in result.message
    # Row must NOT have been reset (strict mode halts without resetting)
    assert _get_status(db, "V1-4") == "IN_PROGRESS"


def test_scan_none_pid_strict_mode_returns_strict_halt(tmp_path: Path) -> None:
    db = _make_db(tmp_path, [{"id": "V1-5", "status": "IN_PROGRESS", "pid": None}])
    result = scan_on_startup(_ctx(db, strict=True))
    assert result.action == "strict_halt"
    assert _get_status(db, "V1-5") == "IN_PROGRESS"


# ---------------------------------------------------------------------------
# Test: live pid owned by forge_runner → owned_by_other
# ---------------------------------------------------------------------------


def test_scan_live_forge_runner_pid_returns_owned_by_other(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db = _make_db(tmp_path, [{"id": "V1-6", "status": "IN_PROGRESS", "pid": _ALIVE_PID}])
    import scripts.forge_runner.deadman as dm

    monkeypatch.setattr(dm, "_pid_alive", lambda pid: True)
    monkeypatch.setattr(dm, "_is_forge_runner", lambda pid: True)

    result = scan_on_startup(_ctx(db))

    assert result.action == "owned_by_other"
    assert str(_ALIVE_PID) in result.message or "V1-6" in result.message
    # Row must NOT be touched
    assert _get_status(db, "V1-6") == "IN_PROGRESS"


# ---------------------------------------------------------------------------
# Test: live pid NOT a forge_runner → treated as orphan (pid reused)
# ---------------------------------------------------------------------------


def test_scan_live_non_forge_pid_treated_as_orphan(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db = _make_db(tmp_path, [{"id": "V1-7", "status": "IN_PROGRESS", "pid": _ALIVE_PID}])
    import scripts.forge_runner.deadman as dm

    # Pid is alive but belongs to a different process (e.g. python httpserver)
    monkeypatch.setattr(dm, "_pid_alive", lambda pid: True)
    monkeypatch.setattr(dm, "_is_forge_runner", lambda pid: False)

    result = scan_on_startup(_ctx(db, strict=False))

    assert result.action == "auto_reset"
    assert _get_status(db, "V1-7") == "PENDING"


def test_scan_live_non_forge_pid_strict_mode_halts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Even a pid-reused orphan triggers strict_halt in strict mode."""
    db = _make_db(tmp_path, [{"id": "V1-8", "status": "IN_PROGRESS", "pid": _ALIVE_PID}])
    import scripts.forge_runner.deadman as dm

    monkeypatch.setattr(dm, "_pid_alive", lambda pid: True)
    monkeypatch.setattr(dm, "_is_forge_runner", lambda pid: False)

    result = scan_on_startup(_ctx(db, strict=True))

    assert result.action == "strict_halt"
    assert _get_status(db, "V1-8") == "IN_PROGRESS"


# ---------------------------------------------------------------------------
# Test: first non-clean action wins (multiple IN_PROGRESS rows)
# ---------------------------------------------------------------------------


def test_scan_first_owned_by_other_short_circuits(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With two rows, the first owned_by_other stops scanning."""
    db = _make_db(
        tmp_path,
        [
            {"id": "V1-10", "status": "IN_PROGRESS", "pid": _ALIVE_PID},
            {"id": "V1-11", "status": "IN_PROGRESS", "pid": _DEAD_PID},
        ],
    )
    import scripts.forge_runner.deadman as dm

    call_log: list[int] = []

    def fake_alive(pid: int) -> bool:
        call_log.append(pid)
        return pid == _ALIVE_PID

    monkeypatch.setattr(dm, "_pid_alive", fake_alive)
    monkeypatch.setattr(dm, "_is_forge_runner", lambda pid: True)

    result = scan_on_startup(_ctx(db))

    assert result.action == "owned_by_other"
    # V1-11 row should be untouched
    assert _get_status(db, "V1-11") == "IN_PROGRESS"


def test_scan_multiple_orphans_all_reset(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """All orphaned rows are reset when no owned_by_other is found."""
    db = _make_db(
        tmp_path,
        [
            {"id": "V1-12", "status": "IN_PROGRESS", "pid": _DEAD_PID},
            {"id": "V1-13", "status": "IN_PROGRESS", "pid": _DEAD_PID},
        ],
    )
    import scripts.forge_runner.deadman as dm

    monkeypatch.setattr(dm, "_pid_alive", lambda pid: False)

    result = scan_on_startup(_ctx(db))

    assert result.action == "auto_reset"
    assert _get_status(db, "V1-12") == "PENDING"
    assert _get_status(db, "V1-13") == "PENDING"
    assert len(result.details) == 2


# ---------------------------------------------------------------------------
# Test: DeadmanResult dataclass
# ---------------------------------------------------------------------------


def test_deadman_result_defaults() -> None:
    r = DeadmanResult(action="clean")
    assert r.details == []
    assert r.message == ""


def test_deadman_result_all_actions_accepted() -> None:
    for action in ("clean", "auto_reset", "owned_by_other", "strict_halt"):
        r = DeadmanResult(action=action)  # type: ignore[arg-type]
        assert r.action == action
