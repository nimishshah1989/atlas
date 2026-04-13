# Chunk 1 — Backend data plane

**Depends on:** none
**Blocks:** Chunk 3 (frontend needs these endpoints live)
**Complexity:** M (1–2h)
**PRD sections:** §6.3, §7, §9

---

## Goal

Four read-only FastAPI endpoints that are the single source of dashboard data, plus a check evaluator module that turns declarative step specs from `roadmap.yaml` into live ✓/✗ results. Backend owns all filesystem access; frontend never touches `fs`.

## Files

### New
- `backend/core/roadmap_checks.py` — check evaluator: `file_exists`, `command`, `http_ok`, `db_query`, **`smoke_list`**. Hard 5s per-check timeout. Subprocess sandbox for `command`.
- `backend/core/roadmap_loader.py` — parses `orchestrator/roadmap.yaml`, Pydantic models for Version / Chunk / Step / Check.
- `tests/routes/test_system.py` — route tests for all 4 endpoints.
- `tests/core/test_roadmap_checks.py` — unit tests for each check type + sandbox escape attempts.

### Modified
- `backend/routes/system.py` — add `/heartbeat`, `/roadmap`, `/quality`, `/logs/tail`. Add 10s in-process cache decorator.
- `backend/main.py` — if any router wiring needed. (Currently has uncommitted changes — preserve.)

## Contracts (frozen in PRD §7)

Enforce with Pydantic response models. Must match PRD §7 byte-for-byte.
- `SystemHeartbeatResponse`
- `SystemRoadmapResponse` (contains `Version`, `Chunk`, `Step`)
- `SystemQualityResponse` — passthrough of `.quality/report.json` + `as_of`
- `SystemLogsTailResponse`

Step check result enum: `ok | fail | slow-skipped | error`.

## Implementation notes

**Caching.** Use a simple `functools.lru_cache`-with-TTL pattern or a small `AsyncTTLCache` — 10s cache on all four endpoints. Cache key = endpoint name (no params for heartbeat/roadmap/quality; for `logs/tail` key on `lines`).

**State.db join.** Read-only SQLAlchemy or direct `sqlite3` (state.db is small, direct `sqlite3` is fine and has no async surface). Never acquire a write lock.

**`command:` sandbox.** `subprocess.run(cmd_list, shell=False, cwd=REPO_ROOT, env={"PATH": os.environ["PATH"]}, timeout=5, capture_output=True)`. If command is a string, reject in Pydantic validation — must be a list. On `TimeoutExpired` return `check="error"`, `detail="timeout"`.

**`http_ok:` check.** `httpx.get(url, timeout=5.0)`. Only permit URLs starting with `http://localhost:` or `http://127.0.0.1:` — external URLs rejected. Status 2xx = ok.

**`db_query:` check.** Parameterized SQL only. Reject any query containing `;`, `--`, `/*`. Run against `state.db` or `data_engine` DB based on `target:` field. Result expected to be a single row with a single integer/bool; non-zero = ok.

**`file_exists:` check.** `Path(repo_root / path).exists()`. Reject absolute paths and `..` in path.

**`smoke_list:` check.** Runs the same probe `scripts/post-chunk.sh` Step 3.5 runs — but inline, so the dashboard always reflects current slice health, not just post-deploy state. Implementation: shells out to `scripts/smoke-probe.sh` with `SMOKE_QUIET=1`, parses its stdout for `summary: total=N passed=P hard_fail=H soft_skip=S`, returns aggregate `check` result plus per-URL detail. `check: "ok"` if `hard_fail=0`, `check: "fail"` if any hard fail, `check: "slow-skipped"` if `evaluate_slow` is false (smoke_list is ALWAYS `slow: true` implicitly — never blocks a page render). Cached 60s separately from the 10s endpoint cache because curl probes are expensive. Parameters: `list: scripts/smoke-endpoints.txt` (default) — validates that the path stays under `scripts/` to prevent arbitrary file execution. One optional `smoke_list` step is wired per version in the seeded `roadmap.yaml` (Chunk 2), so the V-level rollup can reflect live slice health.

**Whole-endpoint timeout.** `/roadmap` wraps check evaluation in `asyncio.wait_for(..., timeout=15.0)`. On timeout returns partial response with remaining checks marked `error: "endpoint-timeout"`.

**Log tail.** `glob("orchestrator/logs/*.log")` → most recent mtime → `deque(fh, maxlen=lines)`. Cap `lines` at 1000.

## Acceptance criteria

1. `GET /api/v1/system/heartbeat` returns all 9 fields of the frozen contract, all tz-aware IST timestamps, `backend_uptime_seconds` a positive integer.
2. `GET /api/v1/system/roadmap` on a seeded `roadmap.yaml` with one V1 chunk containing one `file_exists` step that points at `README.md` returns `check: "ok"` for that step.
3. `GET /api/v1/system/roadmap` with a deliberately-failing `command: ["false"]` step returns `check: "fail"`, not 500.
4. `GET /api/v1/system/roadmap` with a malicious `command: ["rm", "-rf", "/"]` attempt: a) blocked by Pydantic validation (list-only is fine, but we also want a blocklist), b) if it slips through, runs sandboxed and does nothing destructive. Test proves no side effects.
5. `http_ok` check with external URL (`https://example.com`) returns `check: "error"`, `detail: "external-url-blocked"`.
6. `db_query` check with `SELECT 1; DROP TABLE chunks; --` rejected as `check: "error"`, `detail: "unsafe-sql"`. Chunks table still intact.
7. `GET /api/v1/system/quality` returns existing `.quality/report.json` verbatim with `as_of` set to its mtime. If file missing, returns `{"as_of": null, "scores": null}`, status 200 (not 500).
8. `GET /api/v1/system/logs/tail?lines=50` returns last 50 lines of most recent file in `orchestrator/logs/`. `lines=0` → empty array. `lines=5000` → capped at 1000.
8a. `smoke_list` check with `scripts/smoke-endpoints.txt` returns `check: "slow-skipped"` by default; with `?evaluate_slow=true` it runs `scripts/smoke-probe.sh` and returns `check: "ok"` when all hard endpoints pass, `check: "fail"` with per-URL detail when any hard endpoint fails. Attempted path outside `scripts/` rejected as `check: "error"`, `detail: "unsafe-list-path"`.
8b. `/api/v1/system/heartbeat` response includes three extra fields: `last_smoke_run_at` (mtime of most recent `orchestrator/logs/*.smoke.log` if present, else `null`), `last_smoke_result` (`"green" | "red" | null`), `last_smoke_summary` (e.g. `"3/3 green"` or `null`). These are cheap — just reading a file mtime and last line — so they stay inside the 10s heartbeat cache.
9. All four endpoints cache responses for 10s (provable by mtime-touching a file and seeing stale response within window).
10. `pytest tests/routes/test_system.py tests/core/test_roadmap_checks.py -v` passes. Coverage ≥90% on new files.
11. `ruff check backend/ --select E,F,W` clean.
12. `mypy backend/ --ignore-missing-imports` clean on new files.

## Out of scope for this chunk

- Writing `roadmap.yaml` content (that's Chunk 2).
- Any frontend work (Chunk 3).
- Any systemd / deployment changes (Chunk 4).
- Auth / token middleware — endpoints remain unauthenticated at the HTTP level; security is via localhost binding.
