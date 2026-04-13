# forge-runner — Architecture and Operations Guide

Component: `scripts/forge_runner/`
Deployed as: `systemd/atlas-forge-runner.service` (user unit)
Status CLI: `scripts/forge-runner-status`
State store: `orchestrator/state.db` (SQLite WAL)
Audit trail: `.forge/logs/<chunk_id>.log` (JSONL per chunk)
Runner state: `.forge/runner-state.json` (live, atomic writes)

---

## Component Diagram (ASCII)

```
  ┌─────────────────────────────────────────────────────────────┐
  │  forge-runner loop  (scripts/forge_runner/loop.py)          │
  │                                                             │
  │   ┌──────────┐   pick    ┌──────────────────┐              │
  │   │ picker   │ ───────>  │  state.db         │              │
  │   │ (lexico- │ <───────  │  chunks table     │              │
  │   │  graphic)│ update    │  (WAL, IMMEDIATE) │              │
  │   └──────────┘           └──────────────────┘              │
  │        │ chunk_id                                           │
  │        v                                                    │
  │   ┌──────────────────────────────────┐                      │
  │   │  session.py                      │                      │
  │   │  claude_agent_sdk.query()        │ <── .forge/CONDUCTOR.md
  │   │  + backoff wrapper (529/RL)      │     (system_prompt_append)
  │   │  + asyncio.wait_for (timeout)    │                      │
  │   └──────────────────────────────────┘                      │
  │        │ event stream                                       │
  │        v                                                    │
  │   ┌──────────────────────────────────┐                      │
  │   │  logs.py                         │                      │
  │   │  write_event()  →  chunk.log     │ <── .forge/logs/     │
  │   │  update_runner_state() (atomic)  │     runner-state.json│
  │   └──────────────────────────────────┘                      │
  │        │ session done                                       │
  │        v                                                    │
  │   ┌──────────────────────────────────┐                      │
  │   │  verifier.py  (four checks)      │                      │
  │   │  1. state.db row DONE            │                      │
  │   │  2. git log subject has prefix   │                      │
  │   │  3. .forge/last-run.json fresh   │                      │
  │   │  4. git status --porcelain clean │                      │
  │   └──────────────────────────────────┘                      │
  │        │                                                    │
  │   PASS: advance / FAIL: write failure.json + halt           │
  │        v                                                    │
  │   ┌──────────────────────────────────┐                      │
  │   │  halt.py                         │                      │
  │   │  quality gate + criteria check   │                      │
  │   │  → CONTINUE | COMPLETE | STALLED │                      │
  │   └──────────────────────────────────┘                      │
  └─────────────────────────────────────────────────────────────┘

  Visibility layer (read-only, never writes state):
  ┌────────────────────────────────────────┐
  │  scripts/forge-runner-status           │
  │  reads runner-state.json              │
  │  prints one-line summary              │
  │  --watch refreshes every 2s           │
  │  --json for machine-readable output   │
  └────────────────────────────────────────┘
```

---

## Data Flow Per Chunk

1. **Pick** — `picker.pick_next(filter_regex, state_db_path)` scans `chunks` table for PENDING rows matching the regex, checks `depends_on` (all deps must be DONE), returns the lexicographically first eligible chunk. Read-only.

2. **Transition IN_PROGRESS** — `state.mark_in_progress(chunk_id, pid, started_at)` writes inside `BEGIN IMMEDIATE`; sets `runner_pid`, `started_at`.

3. **Session** — `session.run_session(chunk, ctx)` wraps `claude_agent_sdk.query()`. Emits synthetic `session_start` and `session_end` events around the real stream. Retries on 529/rate-limit with exponential backoff. Hard wall-clock timeout via `asyncio.wait_for`.

4. **Log** — every event passes through `secrets.scrub()` then `logs.write_event()`. The per-chunk JSONL file is fsynced on every write so `tail -f` works without delay.

5. **Verify** — `verifier.run_four_checks(chunk_id, ctx)` runs the four post-session checks (see diagram above). On `NEEDS_SYNC`, attempts outer-process sync and either advances or halts.

6. **Halt evaluation** — `halt.evaluate_halt(ctx)` checks the quality gate and V1 criteria. Returns `CONTINUE` (keep looping), `COMPLETE` (all done, exit 0), or `STALLED` (no eligible chunks and not complete, exit 6).

7. **Next iteration** — context is reset, loop resumes at step 1.

---

## Monitoring

### forge-runner-status

```bash
# One-shot summary
./scripts/forge-runner-status

# Auto-refresh every 2 seconds
./scripts/forge-runner-status --watch

# Machine-readable JSON
./scripts/forge-runner-status --json
```

Output states: `running`, `stalled`, `between-chunks`, `halted-complete`, `halted-failed`, `idle`.

### Live log streaming

```bash
# Follow the current chunk's event stream
CHUNK=$(jq -r '.current_chunk' .forge/runner-state.json)
tail -f .forge/logs/${CHUNK}.log | python -m json.tool

# Just tool calls
tail -f .forge/logs/V1-3.log | jq -c 'select(.kind == "tool_use") | {t, tool: .payload.tool}'

# Just text output
tail -f .forge/logs/V1-3.log | jq -c 'select(.kind == "text") | .payload.content'
```

### jq recipes for runner-state.json

```bash
# Current status
jq '{current_chunk, state, health, event_count, last_event_at}' .forge/runner-state.json

# Last tool used
jq '.last_tool' .forge/runner-state.json

# How long the current chunk has been running
jq '.session_started_at' .forge/runner-state.json
```

### state.db queries

```bash
# V1 chunk status overview
sqlite3 orchestrator/state.db \
  "SELECT id, status, started_at, failure_reason FROM chunks WHERE id GLOB 'V1-*' ORDER BY id;"

# All IN_PROGRESS (should be 0 or 1)
sqlite3 orchestrator/state.db \
  "SELECT id, runner_pid, started_at FROM chunks WHERE status='IN_PROGRESS';"
```

---

## Debugging Playbook

### Reading a failure record

```bash
# Inspect what failed
cat .forge/logs/V1-3.failure.json | jq '{failed_check, failed_check_detail, suggested_recovery}'

# See the last events before failure
jq '.last_events[-5:]' .forge/logs/V1-3.failure.json

# Git state at time of failure
jq '{git_status, git_log_last_5}' .forge/logs/V1-3.failure.json
```

Failure check values and what they mean:
- `state_db_not_done` — session ended but state.db row is not DONE; post-chunk.sh did not run
- `no_commit_with_prefix` — no git commit with chunk_id prefix; forge-ship.sh may have failed
- `stamp_not_fresh` — `.forge/last-run.json` mtime is too old; check if forge-ship ran
- `dirty_working_tree` — uncommitted files left behind; check git status
- `shipped_needs_sync` — commit landed but post-chunk sync failed (partial completion)

### How to retry a failed chunk

```bash
# Read the failure first
jq -r .suggested_recovery .forge/logs/V1-3.failure.json

# Fix the root cause, then:
python -m scripts.forge_runner --retry V1-3

# If retry succeeds, resume the full loop:
python -m scripts.forge_runner --filter '^V1-\d+$'
```

### How to inspect state.db directly

```bash
# Show schema (including the three runner columns added by L2-RUNNER)
sqlite3 orchestrator/state.db ".schema chunks"

# Manual state reset (ONLY after stopping the runner)
sqlite3 orchestrator/state.db \
  "UPDATE chunks SET status='PENDING', runner_pid=NULL, started_at=NULL, failure_reason=NULL WHERE id='V1-3';"
```

---

## Recovery Scenarios

### Crash / OOM / machine reboot (orphaned IN_PROGRESS)

On next runner startup, `deadman.scan_on_startup(ctx)` checks every IN_PROGRESS row. If the `runner_pid` is no longer alive, the row is auto-reset to PENDING and a WARN is logged.

```
WARN orphan IN_PROGRESS detected chunk_id=V1-3 stale_pid=98765
WARN auto-reset to PENDING
```

Strict mode — halt instead of auto-reset:
```bash
python -m scripts.forge_runner --filter '^V1-\d+$' --strict-dead-man
# exit 5 — manual intervention required
```

### Concurrent runner detected

The dead-man scan also detects a second live runner instance. This produces exit 5 in strict mode; in default mode it logs a warning. Do not run two runners against the same state.db.

### shipped_needs_sync edge case

A commit landed but `post-chunk.sh` did not run (e.g. inner session timed out mid-ship). The verifier detects this: state.db is not DONE, but a chunk-prefixed commit exists.

The runner attempts to run `post-chunk.sh` from the outer process. If that succeeds, the loop advances normally. If it fails, a failure record is written with `failed_check = "shipped_needs_sync"` and the runner halts (exit 3).

Manual recovery:
```bash
scripts/post-chunk.sh V1-3
python -m scripts.forge_runner --filter '^V1-\d+$'
```

### Authentication failure

Runner halts with exit 1. The in-flight chunk is reset to PENDING (NOT marked FAILED). Check `ANTHROPIC_API_KEY`.

### Stalled session

`forge-runner-status` shows `stalled`. The inner session is alive but produced no events for > 30s.

```bash
# Kill the runner (SIGTERM — resets chunk to PENDING)
pkill -TERM -f forge_runner
# Restart with a longer timeout
python -m scripts.forge_runner --retry V1-3 --timeout 90m
```

### stamp_not_fresh tolerance

The verifier allows `.forge/last-run.json` mtime to be up to 120 seconds older than `session_end_time`. This is the NTP skew / clock tolerance window. If you see repeated stamp failures with small deltas (< 120s), the clock may be drifting — check `timedatectl status`.

---

## Systemd Cheat-Sheet

```bash
# Install (one-time)
mkdir -p ~/.config/systemd/user/
cp systemd/atlas-forge-runner.service ~/.config/systemd/user/
systemctl --user daemon-reload

# Start
systemctl --user start atlas-forge-runner

# Stop (sends SIGTERM — runner exits cleanly within 2s)
systemctl --user stop atlas-forge-runner

# Status
systemctl --user status atlas-forge-runner

# Restart
systemctl --user restart atlas-forge-runner

# Enable on boot (requires linger)
systemctl --user enable atlas-forge-runner
loginctl enable-linger ubuntu

# Live logs via journald
journalctl --user -xeu atlas-forge-runner -f

# Same logs via the runner's own log file
tail -f .forge/logs/systemd.log
```

The `EnvironmentFile` is `/home/ubuntu/.forge/runner.env` — create this file before starting the service:

```bash
cat > /home/ubuntu/.forge/runner.env << 'EOF'
ANTHROPIC_API_KEY=sk-ant-api03-...
EOF
chmod 600 /home/ubuntu/.forge/runner.env
```

---

## Known Edge Cases

- **shipped_needs_sync**: state.db not DONE but chunk-prefixed commit exists. See Recovery Scenarios above.
- **stamp_not_fresh tolerance**: 120s window for NTP skew. Adjust in `verifier.py` if your clock drifts more.
- **Lexicographic vs semantic ordering**: V1-10 sorts before V1-2 (`1` < `2`). This is intentional — `V1-10` is chunk 10 and `V1-2` is chunk 2; the spec IDs are designed to sort correctly (zero-pad if needed for chunks >= 10).
- **Log rotation**: active logs are bounded at 50 files. Older files move to `.forge/logs/archive/`. The archive is not auto-pruned — add a cron if disk is a concern.
- **Binary files in .forge/logs/**: `write_event` always writes valid UTF-8 JSONL. Binary files in that directory should not exist; the log leak checker skips them on UnicodeDecodeError.
