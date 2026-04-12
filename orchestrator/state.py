"""SQLite state store for the forge orchestrator.

Single-writer (the runner). Callers pass a Path to the DB file; the store
creates/migrates the schema on open. All timestamps are ISO8601 UTC strings.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterator, Optional

SCHEMA_PATH = Path(__file__).parent / "schema.sql"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class StateStore:
    def __init__(self, db_path: Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.db_path, isolation_level=None)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._migrate()

    def _migrate(self) -> None:
        schema = SCHEMA_PATH.read_text()
        self._conn.executescript(schema)

    def close(self) -> None:
        self._conn.close()

    @contextmanager
    def tx(self) -> Iterator[sqlite3.Connection]:
        try:
            self._conn.execute("BEGIN")
            yield self._conn
            self._conn.execute("COMMIT")
        except (sqlite3.Error, KeyError, ValueError):
            self._conn.execute("ROLLBACK")
            raise

    # ---- chunks -------------------------------------------------------

    def upsert_chunk(
        self,
        chunk_id: str,
        title: str,
        status: str,
        plan_version: str,
        depends_on: list[str],
    ) -> None:
        now = _now()
        with self.tx() as c:
            existing = c.execute(
                "SELECT id, status FROM chunks WHERE id = ?", (chunk_id,)
            ).fetchone()
            if existing is None:
                c.execute(
                    """INSERT INTO chunks
                       (id, title, status, plan_version, depends_on,
                        created_at, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (
                        chunk_id,
                        title,
                        status,
                        plan_version,
                        json.dumps(depends_on),
                        now,
                        now,
                    ),
                )
                c.execute(
                    """INSERT INTO transitions
                       (chunk_id, from_state, to_state, reason, at)
                       VALUES (?, NULL, ?, 'initial load', ?)""",
                    (chunk_id, status, now),
                )
            else:
                # Refresh title + depends_on; leave status untouched — the
                # state machine owns that.
                c.execute(
                    """UPDATE chunks
                       SET title = ?, plan_version = ?, depends_on = ?,
                           updated_at = ?
                       WHERE id = ?""",
                    (title, plan_version, json.dumps(depends_on), now, chunk_id),
                )

    def get_chunk(self, chunk_id: str) -> Optional[dict[str, Any]]:
        row = self._conn.execute(
            "SELECT * FROM chunks WHERE id = ?", (chunk_id,)
        ).fetchone()
        return _row_to_chunk(row) if row else None

    def list_chunks(self) -> list[dict[str, Any]]:
        rows = self._conn.execute("SELECT * FROM chunks ORDER BY id").fetchall()
        return [_row_to_chunk(r) for r in rows]

    def set_status(
        self,
        chunk_id: str,
        new_status: str,
        reason: str = "",
    ) -> None:
        now = _now()
        with self.tx() as c:
            row = c.execute(
                "SELECT status FROM chunks WHERE id = ?", (chunk_id,)
            ).fetchone()
            if row is None:
                raise KeyError(f"unknown chunk {chunk_id}")
            old_status = row["status"]
            c.execute(
                """UPDATE chunks SET status = ?, updated_at = ?,
                       started_at = COALESCE(started_at,
                           CASE WHEN ? = 'PLANNING' THEN ? ELSE started_at END),
                       finished_at = CASE WHEN ? IN ('DONE','BLOCKED')
                                          THEN ? ELSE finished_at END
                   WHERE id = ?""",
                (new_status, now, new_status, now, new_status, now, chunk_id),
            )
            c.execute(
                """INSERT INTO transitions
                   (chunk_id, from_state, to_state, reason, at)
                   VALUES (?, ?, ?, ?, ?)""",
                (chunk_id, old_status, new_status, reason, now),
            )

    def record_attempt(self, chunk_id: str, error: Optional[str] = None) -> int:
        with self.tx() as c:
            c.execute(
                """UPDATE chunks
                   SET attempts = attempts + 1, last_error = ?, updated_at = ?
                   WHERE id = ?""",
                (error, _now(), chunk_id),
            )
            row = c.execute(
                "SELECT attempts FROM chunks WHERE id = ?", (chunk_id,)
            ).fetchone()
            return int(row["attempts"])

    # ---- quality runs -------------------------------------------------

    def record_quality_run(
        self,
        chunk_id: str,
        attempt: int,
        overall_score: int,
        passed: bool,
        report: dict[str, Any],
    ) -> None:
        with self.tx() as c:
            c.execute(
                """INSERT INTO quality_runs
                   (chunk_id, attempt, overall_score, passed, report_json, at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    chunk_id,
                    attempt,
                    overall_score,
                    1 if passed else 0,
                    json.dumps(report, default=_json_default),
                    _now(),
                ),
            )

    def latest_quality_run(self, chunk_id: str) -> Optional[dict[str, Any]]:
        row = self._conn.execute(
            """SELECT * FROM quality_runs WHERE chunk_id = ?
               ORDER BY id DESC LIMIT 1""",
            (chunk_id,),
        ).fetchone()
        if not row:
            return None
        return {
            "chunk_id": row["chunk_id"],
            "attempt": row["attempt"],
            "overall_score": row["overall_score"],
            "passed": bool(row["passed"]),
            "report": json.loads(row["report_json"]),
            "at": row["at"],
        }

    # ---- sessions -----------------------------------------------------

    def open_session(
        self, chunk_id: str, attempt: int, phase: str, log_path: Path
    ) -> int:
        with self.tx() as c:
            cur = c.execute(
                """INSERT INTO sessions
                   (chunk_id, attempt, phase, started_at, log_path)
                   VALUES (?, ?, ?, ?, ?)""",
                (chunk_id, attempt, phase, _now(), str(log_path)),
            )
            return int(cur.lastrowid or 0)

    def close_session(
        self, session_id: int, pid: Optional[int], exit_code: int
    ) -> None:
        with self.tx() as c:
            c.execute(
                """UPDATE sessions
                   SET pid = ?, exit_code = ?, finished_at = ?
                   WHERE id = ?""",
                (pid, exit_code, _now(), session_id),
            )


def _row_to_chunk(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "title": row["title"],
        "status": row["status"],
        "attempts": row["attempts"],
        "last_error": row["last_error"],
        "plan_version": row["plan_version"],
        "depends_on": json.loads(row["depends_on"]),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "started_at": row["started_at"],
        "finished_at": row["finished_at"],
    }


def _json_default(obj: Any) -> Any:
    if isinstance(obj, Decimal):
        return str(obj)
    if isinstance(obj, (datetime,)):
        return obj.isoformat()
    raise TypeError(f"cannot serialize {type(obj).__name__}")
