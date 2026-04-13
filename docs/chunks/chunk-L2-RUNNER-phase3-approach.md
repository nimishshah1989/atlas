---
chunk: L2-RUNNER-Phase3
project: atlas
date: 2026-04-13
status: success
---

# Approach: L2-RUNNER Phase 3 (T015–T030 + T040)

## Scale
- No data scale concerns — this is pure infrastructure (SQLite CRUD, subprocess, asyncio)
- state.db rows: <100 chunks, trivially fast

## Modules to implement
1. picker.py — pure read, dep chain check
2. config.py — argparse RunConfig
3. session.py — async SDK wrapper, backoff, AuthFailure
4. verifier.py — 4 checks, CheckResult dataclass
5. halt.py — subprocess to quality gates, HaltDecision enum
6. stages.py — Stage protocol, 4 local stages, HostedStageBase stub, RunContext
7. loop.py — run_loop async driver
8. cli.py — main() replacing stub

## Key decisions
- RunContext in stages.py uses asyncio.Event for cancellation (not threading.Event)
- session.py catches ProcessError and checks stderr substrings for auth vs transient
- AuthFailure is a custom exception defined in session.py
- cli.py stubs scan_on_startup as no-op per spec (Phase 6)
- filter uses re.fullmatch semantics per cli.md
- list_pending_matching uses re.search — need to ensure fullmatch in picker

## Edge cases
- depends_on may be NULL or empty JSON → treat as []
- ProcessError has no .stderr attr in stubs — need to extend stubs
- asyncio.wait_for raises asyncio.TimeoutError
- git commands in verifier use subprocess with cwd=ctx.repo

## Expected runtime
- All tests: <10s (no real API calls, no real git sessions)
