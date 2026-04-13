---
chunk: L2-RUNNER-phase5
project: atlas
date: 2026-04-13
status: in-progress
---

# Phase 5 Approach: T036–T039 (US3 Halt+retry)

## Data scale
- state.db: orchestrator/state.db — ~30 chunk rows, SQLite WAL. No performance concern.
- Log files: per-chunk JSONL. Last 100 events = last 100 lines. Small.

## Approach

### T036 — `build_failure_record` + flesh out `write_failure_record`
- Add `build_failure_record(chunk_id, failed_check, detail, ctx)` helper in `logs.py`
- It shells out: `git status --porcelain`, `git log -5 --pretty=format:"%h %s"`
- Reads last 100 lines of `<log_dir>/<chunk_id>.log` as JSONL events (malformed lines → `[]`)
- Gets `state_row` from `state.get_chunk()` → `dataclasses.asdict()`
- `session_id` = `f"forge-{chunk_id}-{os.getpid()}"` (matches schema pattern `^forge-[A-Z0-9-]+-[0-9]+$`)
- `runner_version` = `git rev-parse --short HEAD` or "0000000" (fallback must match `^[0-9a-f]{7,40}$`)
- `suggested_recovery` = switch on `failed_check` enum
- Calls `secrets.scrub()` before writing (already done by `_atomic_write`)

### T037 — `--retry` path in cli.py
- Already implemented with `reset_to_pending`, `_archive_failure_record`, and `run_loop` call
- Only gap: `re` import needed for `re.escape` but the current code uses `f"^{chunk_id}$"` directly (no re.escape). Need to add `import re` and use `re.escape(chunk_id)`.
- Check if `re` is already imported.

### T038 — `test_failure_record.py`
- Valid JSON + all schema fields
- Each `failed_check` → correct `suggested_recovery`
- Secrets scrubbed in `last_events`
- Atomic write: thread + read loop
- Malformed log → `last_events = []`

### T039 — `test_retry.py`
- Pre-stage FAILED chunk in tmp state.db
- Write a failure.json in tmp log_dir
- Monkeypatch `run_loop` → returns 0 (spy)
- Call `cli.main(["--retry", "TEST-2", ...])`
- Assert state PENDING, failure record archived, run_loop called once

## Edge cases
- `runner_version` fallback: if git fails, use "0000000" (7 hex chars, valid pattern)
- `session_id` must match `^forge-[A-Z0-9-]+-[0-9]+$` — chunk_id is already upper
- Malformed JSONL lines in log: skip with warning, still return valid list
- `last_events` capped at 100

## Expected runtime
- Tests: <2s total (no real git sessions, all mocked)
