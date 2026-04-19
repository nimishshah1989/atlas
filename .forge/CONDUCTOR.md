# ATLAS Forge Conductor

You are running inside a forge-runner session.  Each session is a **fresh
Claude Code invocation** — exactly matching CLAUDE.md's "one chunk per
session" rule.  Your job this session: build the assigned chunk, ship it,
emit the completion sentinel, and exit.  The forge-runner loop picks the
next chunk in the next fresh session.

A single line at the end of this file names the chunk you are building:
`FORGE_RUNNER_CHUNK: <chunk_id>`.  That is your sole target.

---

## Step 0 — Boot context (fast — max 5 reads total)

1. `CLAUDE.md` (project root) — skim headings only, do NOT read end-to-end.
2. `~/.claude/projects/-home-ubuntu-atlas/memory/MEMORY.md` — read index only; follow at most 2 links relevant to this chunk's files.
3. `docs/specs/chunks/<chunk_id>.md` — the chunk spec IS your context; trust it.
4. Skip wiki and ATLAS-DEFINITIVE-SPEC.md unless the spec explicitly names a section you must read.

**Do not read feedback_*, project_v15_chunk_status.md, or any spec section not named in the punch list. Get to implementation inside 10 turns.**

---

## Step 1 — Confirm chunk assignment

Read the chunk spec at `docs/specs/chunks/<chunk_id>.md` if it exists.
Cross-check against `orchestrator/plan.yaml` for the punch list.
The spec file supersedes plan.yaml where they overlap.

The state.db row for your chunk is already `IN_PROGRESS` (set by the runner
before spawning you).  Do not touch state.db yourself.

---

## Step 2 — Implement

Spawn the `implementer` subagent via the `Agent` tool with
`subagent_type: implementer`.  Pass it:

- The chunk id and title
- The full punch list / spec path
- The Four Laws and System Guarantees (from CLAUDE.md)
- Domain constraints: `Decimal` not `float`, `Numeric(20,4)` for money,
  IST-aware datetimes, JIP client for any `de_*` reads (never direct SQL),
  every FK `index=True`, alembic for schema, no `print()` in prod

The subagent returns a summary.  You do not see its intermediate work.

---

## Step 3 — Verify (pre-ship gate)

Run in order.  On any failure, retry up to 3 times (edit + re-run), then
enter the hard-stop path (see §Hard stops below):

```bash
ruff check . --select E,F,W
mypy . --ignore-missing-imports
pytest tests/ -v --tb=short
python .quality/checks.py
```

All four MUST pass before shipping.

---

## Step 4 — Ship (forge-ship.sh is the ONLY legal commit path)

Per `feedback_forge_ship_protocol.md`: **never run `git commit` directly**.
The PreToolUse hook refuses raw `git commit` without a fresh
`.forge/last-run.json` stamp.  Use:

```bash
scripts/forge-ship.sh "<chunk_id>: <short message describing what shipped>"
```

The commit message MUST start with the chunk id.

---

## Step 5 — Post-chunk sync (non-negotiable)

```bash
scripts/post-chunk.sh "<chunk_id>"
```

This is the sync invariant from CLAUDE.md §Post-chunk sync: residual
commit+push, backend service restart, smoke probe, `/forge-compile` into the
wiki, and memory sync.  Do not hand-roll any of those steps.

Then verify:

```bash
sqlite3 orchestrator/state.db "SELECT status FROM chunks WHERE id='<chunk_id>';"
```

Must return `DONE`.  If not, emit the hard-stop block and exit.

---

## Hard stops

Halt immediately and log to `BUILD_STATUS.md` if you hit any of these:

- Attempting to write to a `de_*` table (JIP is read-only via the client)
- Financial calculation producing `float` instead of `Decimal`
- Non-deterministic test (different result on consecutive runs)
- Schema mismatch between a Pydantic contract and its implementation
- Starting V2+ work before V1 completion criteria pass
- Any verify step still fails after 3 retries

On hard stop:
1. Mark the chunk FAILED in state.db:
   ```bash
   sqlite3 orchestrator/state.db \
     "UPDATE chunks SET status='FAILED', failure_reason='<reason>' WHERE id='<chunk_id>';"
   ```
2. Append a failure row to `docs/decisions/session-log.md`
3. Emit the completion sentinel below with `status: BLOCKED`

---

## Completion sentinel (CRITICAL — forge-runner parses this)

When you reach **post-chunk sync DONE** (state.db row = DONE, sync complete),
emit a final message that begins **exactly** with:

```
FORGE_RUNNER_DONE: <chunk_id>
```

followed by a one-paragraph summary (chunk id, commit hash, gate score, what
shipped).  Then exit.

If hard-stopped, emit:

```
FORGE_RUNNER_DONE: <chunk_id> status=BLOCKED reason=<one-line reason>
```

The forge-runner loop detects the `FORGE_RUNNER_DONE:` prefix to know the
session has ended and inspect the outcome.  Do NOT omit it.

---
