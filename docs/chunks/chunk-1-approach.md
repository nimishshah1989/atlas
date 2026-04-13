---
chunk: FD-1
project: atlas-forge-dashboard-v2
date: 2026-04-13
---

# Chunk FD-1 — Approach

## Data scale
- state.db: small SQLite, 11 chunks, ~50 transitions. Direct sqlite3 (no async surface needed).
- .quality/report.json: single file, ~5KB. Read verbatim.
- orchestrator/logs/: ~10 files. glob + mtime sort + deque tail.
- All file reads are O(1). No DB query scale concern.

## Chosen approach
- roadmap_loader.py: PyYAML parse into Pydantic models. Returns RoadmapFile(versions=[]) if file missing.
- roadmap_checks.py: sync evaluator (subprocess.run + httpx.get sync). Called from async endpoint via asyncio.to_thread for the blocking calls.
- Caching: simple time-based dict cache (dict[str, tuple[Any, float]]) — 10s TTL on endpoints, 60s for smoke_list results. No external lib needed.
- Whole-endpoint timeout on /roadmap: asyncio.wait_for wrapping check evaluation, 15s.

## Sandbox rules enforced
- command: shell=False, list-only (string rejected), cwd=REPO_ROOT, env={PATH only}, timeout=5s
- http_ok: localhost/127.0.0.1 only
- db_query: reject ; -- /* patterns
- file_exists: reject absolute paths and ..
- smoke_list: path must stay under scripts/, implicitly slow

## Edge cases
- roadmap.yaml missing: return RoadmapFile(versions=[])
- state.db missing: chunk status = PENDING fallback
- .quality/report.json missing: {"as_of": null, "scores": null}
- No log files: SystemLogsTailResponse with file="", lines=[], as_of=now
- lines=0: empty list. lines>1000: capped at 1000.
- NULLs in state.db fields: handled with None defaults

## Expected runtime
- /heartbeat: <50ms (file mtimes + small sqlite query)
- /roadmap: <15s max (endpoint timeout), typical <2s (file_exists checks fast)
- /quality: <10ms (single file read)
- /logs/tail: <50ms (deque tail of small files)

## Existing code reused
- backend/routes/system.py: extend, preserve health/ready/status endpoints
- backend/core/computations.py: not relevant
- orchestrator/state.db: read-only sqlite3
