---
chunk: L2-RUNNER-phase6
project: atlas
date: 2026-04-13
phase: Phase 6 (US4 Dead-man, T041–T044)
---

# Phase 6: US4 Dead-man Switch — Approach

## Context

Phases 1–5 complete. 225 tests passing. cli.py has `_deadman_scan_stub` placeholder.
This phase wires the real dead-man scan + signal handlers.

## Data Scale

state.db is SQLite with WAL mode. IN_PROGRESS rows during startup scan: O(1) in practice
(single-runner design). `list_in_progress` fetches only IN_PROGRESS rows — no full-table load.

## Chosen Approach

### T041 — deadman.py

- `DeadmanResult` dataclass with `Literal["clean","auto_reset","owned_by_other","strict_halt"]`
- `_pid_alive(pid)` checks `/proc/<pid>/status` existence (Linux-native, safe on CI)
- `_is_forge_runner(pid)` reads `/proc/<pid>/cmdline` (null-byte separated), looks for
  `forge_runner` or `forge-runner` in any argument token
- `scan_on_startup` iterates `state.list_in_progress()`. First non-clean result wins
- Returns `DeadmanResult` — caller in cli.py branches on `.action`
- structlog WARN on orphan detection; no print()

### T042 — cli.py signal handlers

- asyncio `loop.add_signal_handler(signal.SIGTERM, handler)` installed inside `asyncio.run()`
  via a wrapper coroutine that installs handlers before `run_loop` is called
- Handler: sets `ctx.cancellation`, calls `reset_to_pending` if chunk in-flight, logs final entry
- Windows-safe: wrap `loop.add_signal_handler` in `try/except AttributeError`
- Replace `_deadman_scan_stub(ctx)` with real `deadman.scan_on_startup(ctx)` + branching

### T043 — test_deadman.py

Unit tests using monkeypatching of `_pid_alive` and `_is_forge_runner`.
- Dead pid → auto_reset (normal mode)
- Dead pid → strict_halt (strict_dead_man=True)
- Live pid + is_forge_runner → owned_by_other
- Live pid + NOT forge_runner → auto_reset (orphan via pid reuse)
- No IN_PROGRESS rows → clean
Uses `os.getpid()` as safe-alive pid, `99999999` as safe-dead pid.
Uses file-based SQLite (not in-memory) to match state.py's `sqlite3.connect(path)` interface.

### T044 — test_signal_handlers.py

Unit-level (not subprocess) test:
- Register the signal handler function directly on a fake context
- Call it manually
- Assert `ctx.cancellation.is_set() == True`
- Assert subsequent iteration (mocked) calls `reset_to_pending`
Subprocess approach rejected: too fragile on CI (timing, PATH, db setup).

## Edge Cases

- `runner_pid=None` in state row → treated as dead pid (False from `_pid_alive`)
- `/proc/<pid>/cmdline` read failure (permission, race) → log WARN, treat as non-forge process
- Windows: `/proc` doesn't exist; `_pid_alive` returns False on OSError (safe default)
- Multiple IN_PROGRESS rows: scan all, return first non-clean action found

## Files Modified

- `scripts/forge_runner/deadman.py` (new)
- `scripts/forge_runner/cli.py` (replace stub + add signal handlers)
- `tests/forge_runner/test_deadman.py` (new)
- `tests/forge_runner/test_signal_handlers.py` (new)

## Expected Runtime

- deadman.py: pure Python + /proc reads → <5ms
- tests: no real subprocesses → <1s per test
