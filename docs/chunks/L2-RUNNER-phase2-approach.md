---
chunk: L2-RUNNER Phase 2
project: atlas
date: 2026-04-13
status: in-progress
---

# Approach: L2-RUNNER Phase 2 — Foundational Modules

## T006 Migration approach

The atlas alembic env.py points at PostgreSQL (backend/config.get_settings().database_url_sync).
orchestrator/state.db is a SEPARATE SQLite file with NO alembic setup.

Choice: standalone Python migration script at `orchestrator/migrations/add_runner_columns.py`
- Uses PRAGMA table_info(chunks) idempotency guard before each ALTER TABLE
- Applied via `python -m orchestrator.migrations.add_runner_columns`
- One-way forward migration (SQLite ALTER TABLE DROP COLUMN requires SQLite 3.35+;
  EC2 may have older version — document and skip downgrade)
- columns to add: runner_pid INTEGER (nullable), failure_reason TEXT (nullable)
- started_at TEXT already exists (confirmed by PRAGMA inspection)
- finished_at TEXT also already exists

## T007 ORM model location

orchestrator/state.py uses raw sqlite3, NOT SQLAlchemy ORM. The Chunk is returned
as a plain dict by _row_to_chunk(). There is no SQLAlchemy Chunk model to update.

Instead: create a ChunkRow dataclass in scripts/forge_runner/state.py that mirrors
the table columns including the two new columns (runner_pid, failure_reason).

## T008 CONDUCTOR.md

Port from .ralph/PROMPT.md — strip RALPH_STATUS block and ralph references,
adapt language to forge-runner SDK model (not ralph iteration model).
End with FORGE_RUNNER_DONE sentinel directive.

## Data scale
orchestrator/state.db chunks table: ~50-100 rows. Everything is synchronous sqlite3.
No pandas, no SQL aggregation needed.

## Edge cases
- started_at already exists in live schema — skip adding
- NULL values in all three new columns when status=PENDING
- BEGIN IMMEDIATE for all writes to prevent concurrent-write corruption
- WAL mode already enabled on live state.db

## Expected runtime
All operations < 1ms each. No bulk data operations.
