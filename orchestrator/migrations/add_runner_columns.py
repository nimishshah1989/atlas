"""Forward-only migration: add runner_pid and failure_reason to chunks table.

Migration design rationale
--------------------------
The atlas alembic setup (alembic/env.py) targets the PostgreSQL atlas_* schema,
NOT orchestrator/state.db (SQLite).  There is no alembic configuration for the
orchestrator database, and creating one would require a second alembic.ini,
a second versions/ directory, and a separate env.py — all for two nullable
columns on a ~50-row table.

Instead: this standalone Python script applies the migration directly via sqlite3.
It is idempotent — it checks PRAGMA table_info(chunks) before each ALTER TABLE
and skips the column if it already exists.

Downgrade note: SQLite ALTER TABLE DROP COLUMN requires SQLite 3.35+.  EC2
instances may run an older version, so downgrade is intentionally unsupported.
To roll back manually: recreate the table without the new columns and
INSERT … SELECT the old columns from a backup.  This is acceptable because
runner_pid and failure_reason are nullable and additive — removing them does
not break existing orchestrator code.

Usage:
    python -m orchestrator.migrations.add_runner_columns

    # or with an explicit db path (useful in tests):
    python -m orchestrator.migrations.add_runner_columns --db /path/to/state.db
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

_DEFAULT_DB = Path(__file__).parent.parent / "state.db"

_NEW_COLUMNS: list[tuple[str, str]] = [
    ("runner_pid", "INTEGER"),
    ("failure_reason", "TEXT"),
]


def _existing_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    """Return the set of column names already present in *table*."""
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return {row[1] for row in rows}


def migrate(db_path: Path) -> None:
    """Apply forward migration to *db_path*, idempotently."""
    if not db_path.exists():
        print(  # noqa: T201 — migration script, not production code
            f"ERROR: database not found: {db_path}", file=sys.stderr
        )
        sys.exit(1)

    conn = sqlite3.connect(str(db_path), isolation_level=None)
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        existing = _existing_columns(conn, "chunks")

        added: list[str] = []
        skipped: list[str] = []

        for col_name, col_type in _NEW_COLUMNS:
            if col_name in existing:
                skipped.append(col_name)
                continue
            conn.execute(f"ALTER TABLE chunks ADD COLUMN {col_name} {col_type}")
            added.append(col_name)

        if added:
            print(f"Added columns: {', '.join(added)}")  # noqa: T201
        if skipped:
            print(f"Already present (skipped): {', '.join(skipped)}")  # noqa: T201

        # Verify
        final_cols = _existing_columns(conn, "chunks")
        for col_name, _ in _NEW_COLUMNS:
            if col_name not in final_cols:
                print(  # noqa: T201
                    f"ERROR: column {col_name} not present after migration!",
                    file=sys.stderr,
                )
                sys.exit(1)

        print(f"Migration complete. DB: {db_path}")  # noqa: T201
    finally:
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Add runner_pid and failure_reason columns to chunks table."
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=_DEFAULT_DB,
        help=f"Path to state.db (default: {_DEFAULT_DB})",
    )
    args = parser.parse_args()
    migrate(args.db)


if __name__ == "__main__":
    main()
