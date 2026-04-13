---
chunk: L2-RUNNER-phase4
project: atlas
date: 2026-04-13
---

# Phase 4 (T031–T035): US2 Live Visibility

## State at start
137 tests passing (2 pre-existing fails in test_halt.py due to `python` not found on PATH — unrelated).
Full module list under scripts/forge_runner/ is complete from Phases 1–3.

## What needs to be done

### T031 — logs.py hardening
Current logs.py already has:
- `fsync` in `write_event` and `_atomic_write`
- `secrets.scrub()` in `_atomic_write` and `write_event`
- `rotate_old_logs` already implemented

Missing:
- `append_event_and_update_state()` helper combining write_event + update_runner_state
- `last_tool.input_preview` scrubbing is done in `stages.py._update_runner_state` but raw_input is not scrubbed before truncation
- `event_count` is always 0 — needs to be tracked

The spec says `append_event_and_update_state(chunk_id, event, state_dict, log_dir)` should do both atomically. The `state_dict` is mutated in-place (event_count++, last_tool, last_event_at) then written. This belongs in logs.py, called from loop or stages.

Fix approach:
1. Add `append_event_and_update_state` to logs.py — modifies state_dict, increments event_count, sets last_tool with scrubbed+truncated input_preview, then calls update_runner_state
2. Fix stages.py._update_runner_state to scrub raw_input before truncation
3. logs.py rotate_old_logs already implemented and correct

### T032 — test_logs.py
New test file. Tests: flush visibility, atomic concurrency, last_tool scrub+truncate, rotation.

### T033 — test_secrets.py extensions
Extend existing test_secrets.py with: nested dict deep key, case-insensitive key names, list non-string pass-through, no side effects deepcopy check, integration scan of canned test outputs.

### T034 — forge_runner_status.py + launcher
Create scripts/forge_runner_status.py (module) and scripts/forge-runner-status (thin shell launcher).
The module reads runner-state.json, computes state/health, prints summary, supports --json/--watch/--tail.

Import approach: `scripts/forge_runner_status.py` imports from `scripts.forge_runner.*` normally since scripts/ is in sys.path when run as `python -m scripts.forge_runner_status`. The shell launcher does `exec python -m scripts.forge_runner_status "$@"`.

### T035 — test_status_cli.py
Tests: each state/health combination, --json output, stalled detection at 30s, invoke via import.

## Edge cases
- runner-state.json missing → exit 1
- runner-state.json mid-write → retry once after 100ms, exit 2 if still fails
- current_chunk is None → idle/between-chunks state
- event_count None in state_dict → treat as 0 before increment

## Expected runtime
All operations: <1ms per write. Tests: <5s total.
