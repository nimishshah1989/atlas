-- ATLAS Forge orchestrator state database.
-- SQLite. One file at orchestrator/state.db. Single-writer (the runner).

PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS chunks (
    id              TEXT PRIMARY KEY,          -- e.g. "C5"
    title           TEXT NOT NULL,
    status          TEXT NOT NULL,             -- see state_machine.STATES
    attempts        INTEGER NOT NULL DEFAULT 0,
    last_error      TEXT,
    plan_version    TEXT NOT NULL,
    depends_on      TEXT NOT NULL,             -- JSON array of chunk ids
    created_at      TEXT NOT NULL,             -- ISO8601 UTC
    updated_at      TEXT NOT NULL,
    started_at      TEXT,
    finished_at     TEXT
);

CREATE INDEX IF NOT EXISTS idx_chunks_status ON chunks(status);

-- Every state transition is logged, append-only. Full audit trail.
CREATE TABLE IF NOT EXISTS transitions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    chunk_id        TEXT NOT NULL REFERENCES chunks(id) ON DELETE CASCADE,
    from_state      TEXT,
    to_state        TEXT NOT NULL,
    reason          TEXT,
    at              TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_transitions_chunk ON transitions(chunk_id, at);

-- Quality gate results — one row per gate invocation per chunk attempt.
CREATE TABLE IF NOT EXISTS quality_runs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    chunk_id        TEXT NOT NULL REFERENCES chunks(id) ON DELETE CASCADE,
    attempt         INTEGER NOT NULL,
    overall_score   INTEGER NOT NULL,
    passed          INTEGER NOT NULL,          -- 0/1
    report_json     TEXT NOT NULL,             -- full .quality/report.json snapshot
    at              TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_quality_runs_chunk ON quality_runs(chunk_id, attempt);

-- Claude subprocess sessions — one row per spawn.
CREATE TABLE IF NOT EXISTS sessions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    chunk_id        TEXT NOT NULL REFERENCES chunks(id) ON DELETE CASCADE,
    attempt         INTEGER NOT NULL,
    phase           TEXT NOT NULL,             -- PLANNING, IMPLEMENTING, TESTING
    pid             INTEGER,
    started_at      TEXT NOT NULL,
    finished_at     TEXT,
    exit_code       INTEGER,
    log_path        TEXT
);

CREATE INDEX IF NOT EXISTS idx_sessions_chunk ON sessions(chunk_id, attempt);
