# PRD — L2-RUNNER: `forge-runner` on Claude Agent SDK

**Status:** draft → ready for speckit pipeline
**Owner:** Forge OS infra
**Author:** conductor (2026-04-13)
**Target chunk id prefix:** `L2-RUNNER` (single atomic chunk unless speckit-tasks decomposes it)
**Category:** infrastructure (L-series, like L1-MIN) — not a product feature, not a V-slice

---

## 1. Problem

Forge OS today has two layers of loop automation, both broken:

1. **`/forge-build` interactive** — a conductor playbook the user drives by
   hand, one chunk per session, manual session recycling between chunks. It
   works but defeats the "walk-away autonomy" goal; user cannot leave a
   multi-chunk run unsupervised.
2. **`ralph`** — adopted as the autonomous wrapper around `claude -p`.
   Attempted V1-1 multiple times today (2026-04-13) and failed in these
   distinct ways:
   - `ralph-enable` rewrote our custom `.ralph/PROMPT.md` back to a generic
     template, silently losing the Forge Conductor prompt
   - `ALLOWED_TOOLS` comma-splitting in `ralph_loop.sh` mangles
     `Bash(git add *)` into three broken tokens (`Bash(git`, `add`, `*)`)
     because bash word-splits on spaces inside parens — disabling most of
     the expanded whitelist
   - `ralph_loop.sh` line 716 arithmetic bug on empty `fix_plan.md`
     checkbox counts (`((0\n0 + 0\n0))` → `0: syntax error in expression`)
   - 15-minute default timeout is too tight for real chunks (V1-1 needs
     schema + alembic + tests + ship + post-chunk sync in one session)
   - `--output-format json` buffers the entire session until exit, so
     `claude_output_*.log` is 0 bytes for the entire run — no live visibility
   - Pre-loop git backup+stash dance fights the PreToolUse forge-ship hook
     and fails on every iteration with "Backup failed: commit failed for
     loop #N"
   - When the inner session dies or times out, ralph itself does not
     graceful-exit — `ralph.log` freezes with no exit line, leaving the
     chunk stuck on `IN_PROGRESS` in `state.db` with half-applied edits and
     no git commit, requiring manual rollback
   - Ralph's generic fix_plan.md + AGENT.md integrity check imposes a
     workflow model that does not match the Forge orchestrator (which uses
     `plan.yaml` + `state.db`, not task checkboxes)

Net result: zero unattended V1 chunks shipped through ralph. Every attempt
requires human rollback and restart. Unsustainable for V1-1 through V10.

## 2. Why now

V1 build is blocked on unattended loop automation. V1 has 9 chunks
(V1-1..V1-9). V2 has 10. V3+ will add more. The user explicitly stated
"I don't want to be sitting and asking the same questions for each of the
chunks; forge-build should take care of everything." Without a reliable
loop driver, every chunk burns ~20 minutes of human attention on session
plumbing instead of review.

Fixing this now has compounding ROI: every subsequent chunk runs through
the same runner, gaining the same reliability.

## 3. Goal

Build **`forge-runner`** — a Python driver on top of
`claude-agent-sdk` — that replaces `ralph` as the autonomous loop driver
for Forge OS. The runner picks the next eligible chunk from
`orchestrator/state.db`, spawns a fresh Claude Code session per chunk, and
advances the loop if and only if the chunk reaches `DONE` cleanly. It is
read-only toward Forge OS conventions: CLAUDE.md, MEMORY.md, hooks,
skills, subagents, `forge-ship.sh`, `post-chunk.sh`, and `.quality/checks.py`
all continue to work unchanged.

## 4. Non-goals

- **Not a Ralph fork.** No bash wrapping, no shell-script loop, no ralph
  compatibility layer. Clean break.
- **Not a multi-LLM framework.** Claude Code only. If the user later wants
  Gemini/GPT fallback, that's a separate chunk.
- **Not a replacement for `/forge-build` interactive.** The interactive
  conductor stays for supervised work. `forge-runner` is the unattended
  counterpart.
- **Not a new chunk-authoring surface.** Specs still go through
  `chunkmaster` (for V-slices) or hand-authored `plan.yaml` edits (for L/S
  infra). The runner only executes, not designs.
- **Not a dashboard.** The existing `/forge` dashboard reads state.db and
  gets the live status for free. Runner only writes runner-state.json for
  the CLI status tool.
- **No scope creep into V2.** Runner must honor the same V-filter
  discipline the current ralph prompt does.
- **No in-tree fork of `claude-agent-sdk`.** Consume as a pinned pypi dep.

## 5. Target users

- **Primary:** the project owner running unattended multi-chunk builds
  (walk-away use case). Starts the runner once, comes back to review.
- **Secondary:** the Forge OS itself — `/forge-build` in future chunks can
  delegate unattended multi-chunk runs to the runner rather than trying to
  re-implement the loop inline.

## 6. User stories

- **US-1 "walk away":** "As the owner, I run `forge-runner --filter
  '^V1-\d+$'` in a tmux session, detach, go make dinner, and come back to
  find V1-1 through V1-9 all `DONE` with commits pushed, services restarted,
  and the wiki updated."
- **US-2 "watch live":** "As the owner, from any terminal, I run
  `forge-runner-status` and see exactly which chunk is running, how long
  it has been running, and the last 20 tool calls — so I never have to
  wonder 'is it running?'."
- **US-3 "halt on first failure":** "As the owner, if chunk V1-4 fails, the
  runner halts at V1-4 without touching V1-5; I fix V1-4 and run
  `forge-runner --resume` and V1-4 retries from clean state."
- **US-4 "audit after the fact":** "As a reviewer (current or future), I
  open `.forge/logs/V1-4.log` and see every tool call, every file edit,
  every test result, and every commit from the V1-4 session — so I can
  audit *how* it was built, not just *what* was built."
- **US-5 "survive terminal close":** "As the owner, closing my SSH tab
  does not kill the runner. It runs under tmux or systemd and keeps going
  even if I log out."
- **US-6 "dead-man's switch":** "As the owner, if the runner itself
  crashes mid-chunk, the chunk does not stay stuck on `IN_PROGRESS`. On
  next start, the runner detects orphaned `IN_PROGRESS` rows and either
  resumes or resets to `PENDING` with a clear diagnostic."

## 7. Functional requirements

### 7.1 Chunk picker

- **FR-1.1** The picker reads `orchestrator/state.db` and selects the
  lowest-id chunk where:
  - `id` matches the `--filter` regex (default: no filter → any)
  - `status == 'PENDING'`
  - every id in `depends_on` (parsed from JSON) has `status == 'DONE'`
- **FR-1.2** If zero eligible chunks exist, the runner evaluates halt
  conditions (FR-6) and exits 0 or 2 accordingly.
- **FR-1.3** The picker NEVER selects a chunk whose id starts with `V2-`,
  `V3-`, etc. when `--filter '^V1-\d+$'` is active. (This is implicit in
  regex filtering, but test explicitly.)
- **FR-1.4** The picker is read-only toward `state.db` — it writes only
  after the session ends (via FR-4 verification).

### 7.2 Session spawn

- **FR-2.1** For the selected chunk id, the runner calls
  `claude_agent_sdk.query()` (or equivalent) with:
  - `cwd = /home/ubuntu/atlas` (or the runner's `--repo` arg)
  - `system_prompt_append` = contents of `.forge/CONDUCTOR.md`
  - `allowed_tools` = a hard-coded Python list (FR-5)
  - `permission_mode = "acceptEdits"` or equivalent that does not
    require interactive approval
  - `session_id = f"forge-{chunk_id}-{epoch_seconds}"` (unique per run)
  - `max_turns = 300` (configurable via `--max-turns`)
- **FR-2.2** The session prompt includes the chunk id explicitly, so the
  inner session does not re-query the picker. The runner is authoritative
  over "which chunk am I building right now."
- **FR-2.3** Before spawning, the runner updates `state.db`:
  `UPDATE chunks SET status='IN_PROGRESS', started_at=NOW(),
  runner_pid=<pid> WHERE id=<chunk_id>`. Schema changes go through an
  alembic migration added in this chunk.
- **FR-2.4** The runner enforces a wall-clock timeout per session
  (default 45 min, configurable via `--timeout`). On timeout, the session
  is killed cleanly, `state.db` row is marked `FAILED` with reason
  `timeout`, and the loop halts.

### 7.3 Live event streaming

- **FR-3.1** Every event from the Agent SDK iterator (`tool_use`,
  `tool_result`, `text`, `session_start`, `session_end`, `error`) is
  written to `.forge/logs/<chunk_id>.log` the instant it arrives. No
  buffering.
- **FR-3.2** Log format is one JSON object per line (jsonl), with
  `timestamp`, `event_type`, `payload`. Human-readable summaries are
  written alongside via a second `.log` file or a formatter flag.
- **FR-3.3** `.forge/runner-state.json` is updated on every event with:
  `current_chunk`, `chunk_started_at`, `last_event_at`, `event_count`,
  `runner_pid`, `last_tool` (name + first 200 chars of input).
- **FR-3.4** A helper CLI `scripts/forge-runner-status` reads
  `runner-state.json` + the last 20 lines of the current chunk log and
  prints a human-readable status in one line.

### 7.4 Post-session verification

After the SDK session ends (normally or by timeout), the runner MUST
verify all four of:

- **FR-4.1** `state.db` row for the chunk is `DONE`. (Flipped by
  `post-chunk.sh` at the end of the inner session.)
- **FR-4.2** `git log -1 --pretty=%s` contains a commit whose subject
  starts with the chunk id (e.g. `V1-1: ...`). This proves
  `forge-ship.sh` ran, which proves the PreToolUse hook fired, which
  proves the commit path is legal.
- **FR-4.3** `.forge/last-run.json` stamp is fresh (mtime within the
  session window). This is the hook's own stamp file.
- **FR-4.4** `git status --porcelain` returns empty (no uncommitted
  changes in tracked files excluding the runner's own state files).

If ANY of the four fail, the runner:
- leaves `state.db` in whatever state the session left it
- writes `.forge/logs/<chunk_id>.failure.json` with which check failed,
  last 100 events, current state.db row, git status dump, suggested
  recovery commands
- halts the loop (does NOT advance to the next chunk)
- exits with code 3

If all four pass, the runner logs `✓ <chunk_id> shipped` and loops back
to FR-1.1.

### 7.5 Allowed tools

- **FR-5.1** The `allowed_tools` list is declared as a Python constant in
  `scripts/forge_runner/tools.py`, not in a config file, so it is
  reviewable in code and version-controlled.
- **FR-5.2** The list MUST cover everything the forge workflow needs:
  `Read`, `Write`, `Edit`, `Glob`, `Grep`, `Agent`, `TaskCreate`,
  `TaskUpdate`, `TaskList`, and Bash prefixes for `git add`, `git diff`,
  `git log`, `git status`, `git push`, `git pull`, `git fetch`,
  `git checkout`, `git branch`, `git stash`, `git merge`, `git tag`,
  `python`, `python3`, `pytest`, `ruff`, `mypy`, `alembic`, `sqlite3`,
  `scripts/*`, `bash scripts/*`, `ls`, `cat`, `sed`, `awk`, `find`,
  `head`, `tail`, `wc`, `sort`, `uniq`, `tr`, `cut`, `jq`, `yq`,
  `systemctl`, `journalctl`, `curl`, `npm`, `npx`.
- **FR-5.3** `git commit` direct is NOT in the whitelist. Commits go
  through `scripts/forge-ship.sh` only. (The forge-ship script itself
  runs `git commit` as a subprocess, which is unaffected by the SDK's
  tool whitelist.)

### 7.6 Halt conditions

- **FR-6.1** Runner exits 0 ("success-complete") when no eligible
  chunk exists AND `python .quality/checks.py` exits 0 AND
  `python scripts/validate-v1-completion.py` exits 0 (when applicable to
  the active filter).
- **FR-6.2** Runner exits 2 ("stalled") when no eligible chunk exists
  BUT the quality gate or criteria validation fails. This means the
  loop has nothing to do but the system is not actually done — human
  intervention required.
- **FR-6.3** Runner exits 3 ("chunk failed") when FR-4 verification
  fails for a chunk.
- **FR-6.4** Runner exits 4 ("timeout") when the SDK session hits its
  wall-clock timeout.
- **FR-6.5** Runner exits 5 ("dead-man detected") when startup finds a
  pre-existing `IN_PROGRESS` row with no live runner process matching
  `runner_pid` — and auto-resets that row to `PENDING` with a log line
  before starting the normal loop. (Graceful recovery, not a halt,
  unless `--strict-dead-man` is passed in which case it halts.)

### 7.7 Dead-man's switch

- **FR-7.1** On startup the runner scans `state.db` for rows where
  `status == 'IN_PROGRESS'`. For each:
  - if `runner_pid` is not null and the process exists AND the pid
    belongs to a live `forge-runner`, error out ("another runner is
    already working on this chunk")
  - otherwise reset to `PENDING`, clear `runner_pid`, log at WARN
- **FR-7.2** On SIGTERM/SIGINT, the runner catches the signal, resets
  the current chunk's `state.db` row to `PENDING`, writes a final log
  entry, and exits cleanly. No stuck IN_PROGRESS after Ctrl+C.
- **FR-7.3** On uncaught exception, the runner writes a crash dump to
  `.forge/logs/<chunk_id>.crash.json` and resets state.db row before
  re-raising.

### 7.8 Resumption

- **FR-8.1** `forge-runner --resume` is equivalent to a fresh run —
  the picker naturally selects whatever is `PENDING` with satisfied
  deps, which is what "resume" semantically means. No special
  "resume state" to persist.
- **FR-8.2** `forge-runner --retry <chunk_id>` resets the given chunk
  to `PENDING`, clears its failure log if any, and runs one iteration
  against it (not a full loop). Useful after a manual fix.

### 7.9 Forward compatibility — Stage protocol (Phase 2 insurance)

The runner's internal architecture MUST be factored around a `Stage`
protocol so that individual stages of the chunk lifecycle can be swapped
between local (Claude Code via Agent SDK) and hosted (Anthropic Managed
Agents via `/v1/agents`) implementations in a future chunk
(`L3-HYBRID-AGENTS`) without rewriting the loop. This is cheap insurance:
~30 lines of abstraction now, a mechanical swap later instead of a
rewrite.

- **FR-9a.1** Define a `Stage` protocol in
  `scripts/forge_runner/stages.py`:
  ```python
  class Stage(Protocol):
      name: str                              # e.g. "implement", "verify"
      def run(self, chunk: Chunk, ctx: RunContext) -> StageResult: ...
      def dry_run(self, chunk: Chunk, ctx: RunContext) -> StageResult: ...
  ```
  where `RunContext` holds repo path, log dir, state.db handle,
  cancellation token, and cumulative usage counters, and `StageResult`
  holds `{status: OK | FAILED | NEEDS_SYNC, artifacts: dict, reason: str}`.
- **FR-9a.2** The main loop (`loop.py`) iterates over a list of `Stage`
  instances in order. Phase 1 ships with exactly one non-trivial stage:
  `LocalImplementStage` — which is the Agent SDK session wrapper. The
  picker, verifier, and shipper are also stages, but they are local-only
  forever (they need filesystem + state.db access).
- **FR-9a.3** Phase 1 pipeline composition (hard-coded in `loop.py`):
  ```python
  PIPELINE: list[Stage] = [
      LocalPickStage(),       # reads state.db
      LocalImplementStage(),  # Agent SDK session
      LocalVerifyStage(),     # 4-check FR-4 verifier
      LocalLoopAdvanceStage() # heartbeat + logs + loop back
  ]
  ```
  `LocalImplementStage` is the only stage that is a candidate for Phase 2
  replacement (`HostedReviewStage`, `HostedSpecStage`, etc. would slot in
  as additional stages *around* implement, not replacing it, since
  implementation must stay local — see PRD §14 R-stages-must-stay-local
  discussion).
- **FR-9a.4** Stages communicate only through `StageResult.artifacts`
  (a plain dict) and `RunContext` — never through module-level globals
  or hidden state. This keeps them independently unit-testable and
  swap-able.
- **FR-9a.5** Phase 2 hosted stages (e.g. `HostedReviewStage`,
  `HostedSpecStage`, `HostedWikiCompileStage`) will be added as separate
  `Stage` subclasses in a new module `scripts/forge_runner/hosted.py`
  under a different chunk. This chunk (L2-RUNNER) does NOT implement
  any hosted stage — but it MUST leave a stubbed
  `HostedStageBase(Stage)` abstract class in `stages.py` documenting the
  expected interface for Managed Agents API calls (request shape,
  response shape, error handling, timeout, retry policy). The stub has
  `raise NotImplementedError("implemented in L3-HYBRID-AGENTS")` in its
  `run` method and a docstring pointing at the Anthropic Managed Agents
  API docs. Zero runtime dependency on the hosted path in Phase 1 —
  just a compile-time interface lock.
- **FR-9a.6** Unit test `test_stages.py` verifies: the protocol is
  satisfiable by both `LocalImplementStage` and `HostedStageBase` (the
  latter via a mock subclass), `StageResult` is JSON-serializable, and
  the pipeline composition in `loop.py` is a pure list of `Stage`
  instances (no hidden order-dependency beyond list order).

**Architectural rationale** (for reviewers, not for code comments):
- Forge OS's power today comes from local Claude Code integration:
  skills, hooks, CLAUDE.md auto-load, `implementer` subagent with
  `context: fork`, `forge-ship.sh` PreToolUse hook, memory. None of
  these survive a migration to hosted Managed Agents without
  significant MCP-server rebuilding.
- Therefore implementation / verify / ship stages must stay local
  indefinitely — they are the stages that touch the filesystem, hooks,
  skills, and memory.
- The stages that genuinely benefit from going hosted are the
  stateless ones: spec authoring, clarify-question generation, plan
  review / red-team, code review on diff, wiki compilation. Those can
  run on different models (Opus for quality, Sonnet for speed, Haiku
  for triage), run in parallel across chunks, and don't need local
  filesystem access.
- This stage protocol is the minimum abstraction that makes that
  future split mechanical. It costs ~30 lines now and saves a
  rewrite later.

### 7.10 Configuration surface

- **FR-9.1** All config is CLI args. No YAML config files, no env vars
  beyond `ANTHROPIC_API_KEY`.
- **FR-9.2** CLI args:
  - `--filter <regex>` (default: `.*`)
  - `--timeout <duration>` (default: `45m`)
  - `--max-turns <int>` (default: `300`)
  - `--repo <path>` (default: `$PWD`)
  - `--log-dir <path>` (default: `.forge/logs`)
  - `--resume` (flag, no-op but documented)
  - `--retry <chunk_id>`
  - `--dry-run` (print what it would do, no session)
  - `--once` (run exactly one chunk then exit)
  - `--strict-dead-man` (halt instead of auto-reset)
- **FR-9.3** `forge-runner --help` prints all of the above with
  defaults and examples.

## 8. Non-functional requirements

- **NFR-1 Predictability:** every failure mode maps to a distinct exit
  code and a named failure artifact. "Mystery freeze" (ralph's failure
  mode) is not an acceptable outcome — either the runner is live and
  writing logs, or it has exited with a diagnosable artifact.
- **NFR-2 Observability:** from any terminal on the machine, one
  command (`forge-runner-status`) answers "what is it doing right now."
  No grep-hunting through log files.
- **NFR-3 Idempotence:** running the runner twice in a row against the
  same state produces the same outcome. Double-starts are safe
  (dead-man switch catches them).
- **NFR-4 Survivability:** runner survives terminal close (tmux or
  systemd). Runner survives single-chunk failures (halts cleanly,
  resumes on next start). Runner does NOT survive SDK-level auth
  failures (those halt immediately with exit 1 and a clear error).
- **NFR-5 Log retention:** logs for the last 50 chunks are kept under
  `.forge/logs/`. Older logs are rotated to `.forge/logs/archive/` by
  a simple counter, not by time.
- **NFR-6 Performance:** picker query < 50ms against state.db (SQLite,
  in-process). SDK session spawn overhead < 2s. Total per-chunk
  overhead outside the inner session < 5s.
- **NFR-7 Security:** runner does not log the `ANTHROPIC_API_KEY`. Runner
  does not write anything to `~/.claude/` or `/etc/`. Runner operates
  only within `$PWD` and `.forge/`.
- **NFR-8 Testability:** every state.db transition, every FR-4
  verification step, and the dead-man switch are unit-testable in
  isolation without actually spawning a Claude session. A `--dry-run`
  mode proves this.
- **NFR-9 Forge OS integration:** the runner loads the existing
  conductor prompt (ported from `.ralph/PROMPT.md` to
  `.forge/CONDUCTOR.md`) without modification. CLAUDE.md, MEMORY.md,
  PreToolUse hooks, skills, and the `implementer` subagent all work
  inside the runner's inner sessions exactly as they do in an
  interactive `claude` session.

## 9. Architecture

```
┌────────────────────────────────────────────────────────────────┐
│                      forge-runner (Python)                     │
│                                                                 │
│  scripts/forge_runner/                                          │
│    __main__.py       CLI entry                                  │
│    loop.py           main loop (picker → spawn → verify)        │
│    picker.py         state.db query + dep resolver              │
│    session.py        Agent SDK wrapper + event stream           │
│    verifier.py       FR-4 four-check verification               │
│    deadman.py        FR-7 signal handling + startup scan        │
│    tools.py          FR-5 allowed_tools constant                │
│    state.py          state.db CRUD (read + status updates)     │
│    logs.py           jsonl writer + runner-state.json updater   │
│    halt.py           FR-6 halt condition evaluator              │
│    config.py         CLI arg parsing + defaults                 │
│                                                                 │
│  scripts/forge-runner-status          one-line status CLI       │
│  systemd/atlas-forge-runner.service   optional systemd unit     │
│                                                                 │
│  .forge/CONDUCTOR.md                  system prompt per session │
│  .forge/runner-state.json             live status               │
│  .forge/logs/<chunk_id>.log           per-chunk jsonl stream    │
│  .forge/logs/<chunk_id>.failure.json  only if FR-4 fails        │
│  .forge/logs/<chunk_id>.crash.json    only if uncaught exc      │
│  .forge/logs/archive/                 rotated older logs        │
└────────────────────────────────────────────────────────────────┘
         │                                                │
         │ reads/writes                                   │ spawns
         ▼                                                ▼
  orchestrator/state.db                          claude-agent-sdk
  orchestrator/plan.yaml (read only)                    │
  .quality/checks.py                                    ▼
  scripts/validate-v1-completion.py         Inner Claude Code
                                            session (fresh per chunk):
                                            - loads CLAUDE.md
                                            - loads MEMORY.md
                                            - activates skills
                                            - spawns implementer
                                            - runs forge-ship.sh
                                            - runs post-chunk.sh
                                            - PreToolUse hooks fire
```

Data flow per chunk:
1. **Picker** → returns chunk_id or None
2. **Dead-man scan** (on startup only)
3. **State update** → IN_PROGRESS, runner_pid, started_at
4. **Session spawn** → Agent SDK iterator begins
5. **Event loop** → each event flushed to .forge/logs and runner-state.json
6. **Session end** → from the SDK (normal exit, max_turns, error, or timeout)
7. **Verifier** → 4 checks, each mapped to an exit code on failure
8. **State update** → DONE is already set by post-chunk.sh inside the
   session; verifier only confirms
9. **Loop back** to 1

## 10. Interfaces

### 10.1 CLI

```
forge-runner [options]
  --filter REGEX           (default .*)
  --timeout DURATION       (default 45m)
  --max-turns INT          (default 300)
  --repo PATH              (default $PWD)
  --log-dir PATH           (default .forge/logs)
  --resume                 (alias for normal start, documented)
  --retry CHUNK_ID
  --dry-run
  --once
  --strict-dead-man

forge-runner-status
  # reads .forge/runner-state.json + tail of current log
  # prints: "V1-3 running 12m, 47 events, last: Edit(backend/agents/rs.py)"
```

### 10.2 state.db schema additions

New columns on `chunks` table (added via alembic migration in this chunk):
- `started_at TEXT` (ISO8601, set when row → IN_PROGRESS)
- `runner_pid INTEGER` (set when row → IN_PROGRESS, cleared on DONE/FAILED/PENDING)
- `failure_reason TEXT` (set when row → FAILED)

### 10.3 Log format

`.forge/logs/V1-3.log` (jsonl):
```
{"t": "2026-04-13T14:22:01+05:30", "evt": "session_start", "session_id": "forge-V1-3-1776090000"}
{"t": "...", "evt": "tool_use", "tool": "Read", "input": {"file_path": "CLAUDE.md"}}
{"t": "...", "evt": "tool_result", "tool": "Read", "summary": "1400 tokens"}
{"t": "...", "evt": "text", "content": "Booting context..."}
...
{"t": "...", "evt": "session_end", "stop_reason": "end_turn", "turns": 87, "usage": {...}}
```

### 10.4 runner-state.json

```json
{
  "current_chunk": "V1-3",
  "chunk_started_at": "2026-04-13T14:22:01+05:30",
  "last_event_at": "2026-04-13T14:34:17+05:30",
  "event_count": 142,
  "runner_pid": 28431,
  "last_tool": {"name": "Edit", "input_preview": "backend/agents/rs_analyzer.py"},
  "loop_started_at": "2026-04-13T14:10:00+05:30",
  "chunks_completed_this_run": 2
}
```

## 11. Acceptance criteria (all must pass for chunk DONE)

- **AC-1** `forge-runner --dry-run --filter '^V1-\d+$'` prints the chunk
  it would pick (V1-1 if all V1 chunks are PENDING) and exits 0 without
  touching state.db.
- **AC-2** `forge-runner --once --filter '^V1-\d+$'` successfully ships
  V1-1 end-to-end: state.db flips to DONE, a new commit with `V1-1:`
  prefix lands, `.forge/last-run.json` stamp is fresh, git status is
  clean. Runner exits 0.
- **AC-3** `forge-runner --filter '^V1-\d+$'` (no `--once`) ships V1-1
  and loops to V1-2 automatically in a fresh session. (Can be stopped
  with Ctrl+C after V1-2 for the test.)
- **AC-4** Running the runner twice in parallel fails cleanly on the
  second instance with exit 5 ("another runner working on V1-X") —
  dead-man switch works.
- **AC-5** Killing the runner with SIGTERM mid-chunk resets the
  in-flight chunk to PENDING in state.db within 2 seconds and exits 0.
- **AC-6** `forge-runner-status` prints a single line showing the
  current chunk, elapsed time, event count, and last tool call, sourced
  from `runner-state.json`.
- **AC-7** Log file `.forge/logs/V1-1.log` exists after V1-1 ships and
  contains at least `session_start`, `session_end`, and >10 `tool_use`
  events.
- **AC-8** If an inner session fails (e.g. by deliberately breaking a
  test expectation), the runner halts, writes
  `.forge/logs/V1-X.failure.json` with all four FR-4 checks and their
  results, and exits 3. The next chunk is NOT attempted.
- **AC-9** Unit tests for `picker`, `state`, `deadman`, `verifier`,
  `halt`, and `tools` all green. Coverage ≥ 80% on `scripts/forge_runner/`.
- **AC-10** `ruff check` and `mypy` clean on `scripts/forge_runner/`.
- **AC-11** `.quality/checks.py` passes on the final commit. Seven
  dimensions: security 100, code ≥80, architecture ≥85, api n/a,
  frontend n/a, backend ≥80, prod ≥80.
- **AC-12** Running the full V1 loop (V1-1 .. V1-9) in a single
  unattended session ships all 9 chunks without human intervention,
  end-to-end, within one continuous runner invocation. (This is the
  north-star test — it validates both forge-runner and the conductor
  prompt end-to-end.)
- **AC-13** Runner is invoked as a regular systemd user unit OR under
  tmux, and surviving terminal close is demonstrated in the integration
  test.
- **AC-14** Ralph scaffolding removed: `.ralph/`, `.ralphrc`,
  `~/.ralph/` reference removed from project docs. `CLAUDE.md`
  updated to reference `forge-runner` as the canonical unattended
  driver. `feedback_forge_ship_protocol.md` memory updated.

## 12. Test strategy

### 12.1 Unit tests
- `test_picker.py`: dep resolution, filter regex, empty result, stale
  IN_PROGRESS handling
- `test_state.py`: transitions PENDING→IN_PROGRESS→DONE, rollback on
  exception, started_at/runner_pid columns
- `test_deadman.py`: startup scan with live pid vs dead pid, SIGTERM
  handler, strict mode
- `test_verifier.py`: all four FR-4 checks pass/fail cases, failure
  artifact format
- `test_halt.py`: exit code matrix for each halt condition
- `test_tools.py`: allowed_tools list is non-empty and contains the
  load-bearing entries (sqlite3, scripts/forge-ship.sh, alembic, Agent)

### 12.2 Integration tests
- `test_dry_run.py`: `forge-runner --dry-run --filter '^V1-\d+$'` on a
  fixture state.db returns V1-1
- `test_retry.py`: `forge-runner --retry V1-3` on a FAILED row resets
  and retries
- `test_once_fake_session.py`: monkeypatch the SDK call to return a
  canned event stream and verify the full loop path without burning
  API budget

### 12.3 Live smoke test (one-shot, gated behind env var)
- `FORGE_RUNNER_LIVE=1 pytest tests/integration/test_forge_runner_live.py`
  — actually spawns a real Claude Code session against a throwaway
  chunk in a test state.db, ships it, verifies. Skipped in normal CI,
  run manually before merging.

### 12.4 North-star test (manual, AC-12)
Run `forge-runner --filter '^V1-\d+$'` against the real orchestrator.
Confirm V1-1..V1-9 ship autonomously. This is the human acceptance
test for the chunk.

## 13. Rollout plan

1. **Build** the runner per the plan above. Ship via `forge-ship.sh`
   under chunk id `L2-RUNNER`.
2. **Validate** on V1-1 first (AC-2). If V1-1 ships cleanly, rest of V1
   follows.
3. **Deprecate ralph**: remove `.ralph/`, `.ralphrc`, any ralph refs in
   docs. Update CLAUDE.md's mention of "autonomous loop" to point at
   `forge-runner`.
4. **Document**: `docs/architecture/forge-runner.md` with monitoring,
   debugging, and recovery playbooks.
5. **Memory update**: add memory entry `feedback_forge_runner.md` to
   codify the rule "use forge-runner for unattended loops; ralph is
   retired."

## 14. Risks and mitigations

- **R-1: Claude Agent SDK API churn.** Mitigation: pin exact SDK
  version in `requirements-dev.txt`, add an integration test that
  fails loudly on SDK upgrade until tests are updated.
- **R-2: Inner session hits `max_turns` mid-ship.** A commit may have
  landed but post-chunk.sh didn't run → state.db stuck on IN_PROGRESS
  with a real commit. Mitigation: verifier's 4-check logic detects this
  specific state (commit exists but state.db != DONE) and marks the
  chunk as `SHIPPED_NEEDS_SYNC`, then on next run the runner detects
  that state and completes post-chunk.sh from the outer process. This
  is a dedicated code path in `verifier.py`.
- **R-3: Concurrent state.db writes.** Mitigation: SQLite with WAL mode
  + `BEGIN IMMEDIATE` on every runner write. Dead-man scan uses a
  lock row. Unit test covers concurrent runner startup.
- **R-4: Conductor prompt drift between ralph and forge-runner.**
  Mitigation: port `.ralph/PROMPT.md` to `.forge/CONDUCTOR.md` as the
  first file touched in the implementation, then delete `.ralph/PROMPT.md`.
  No dual ownership.
- **R-5: SDK auth failures during a long run.** Mitigation: runner
  catches `AuthenticationError` specifically, writes a clear diag,
  exits 1 (not 3 — auth is not a chunk failure). Retry-with-backoff
  on transient 529 / rate-limit errors via an exponential backoff
  wrapper in `session.py`.
- **R-6: Runaway inner session consumes huge token budget.** Mitigation:
  `max_turns=300` default, documented `--max-turns` override, and
  `.forge/runner-state.json` tracks cumulative token usage per run so
  the user can see cost in real time.
- **R-7: User accidentally runs V2 chunks during V1 build.**
  Mitigation: runner's `--filter` is a required-or-defaulted arg; the
  documented invocation in `docs/architecture/forge-runner.md` is
  always `--filter '^V1-\d+$'` until V1 criteria pass. Shell alias
  recommended.
- **R-8: Forge-ship PreToolUse hook rejects the runner's commits.**
  The hook's stamp check (`.forge/last-run.json`) must fire when the
  inner session runs `scripts/forge-ship.sh`. Mitigation: verified
  manually in AC-2 before first V1 chunk ship. If this fails, fall
  back to a temporary hook override via `FORGE_SHIP_ALLOW_STAMP=1`
  env var in the runner's subprocess env (already the pattern used
  by interactive sessions).
- **R-9: Hidden coupling between ralph's `.ralph/status.json` and the
  `/forge` dashboard.** Mitigation: audit the dashboard code
  (`frontend/`) for any ralph reference before deletion. If found,
  re-point at `runner-state.json` as part of this chunk.

## 15. Open questions for /speckit-clarify

- **OQ-1** Should the runner auto-restart on chunk failure after a
  manual fix, or always require explicit `--retry`? (Recommendation:
  explicit only. No surprise retries.)
- **OQ-2** Should `forge-runner` be callable from inside an existing
  interactive Claude Code session (e.g. the user says "run V1-1
  through V1-3" and `/forge-build` delegates to the runner)? Or is it
  always a separate process launched from the shell? (Recommendation:
  separate process only for v1; inline delegation is a V2 feature.)
- **OQ-3** Should the runner write a per-chunk summary to
  `docs/decisions/session-log.md` automatically, or leave that to
  post-chunk.sh which already does it? (Recommendation: leave it.
  Don't duplicate.)
- **OQ-4** Should runner-state.json include the cumulative token cost
  for the current run, or only per-chunk usage? (Recommendation:
  both, because cost visibility matters for a walk-away loop.)
- **OQ-5** Where does the runner itself live in the repo? Options:
  `scripts/forge_runner/` (Python package), `tools/forge-runner/`, or
  `backend/forge_runner/`. Recommendation: `scripts/forge_runner/`,
  matching `scripts/tasks-to-plan.py` and other infra scripts.
- **OQ-6** Dead-man's switch on startup: auto-reset vs halt? Default
  recommendation is auto-reset (more ergonomic) with
  `--strict-dead-man` as an opt-in for paranoid mode.
- **OQ-7** For chunks that only touch `.quality/`, `docs/`, or
  `orchestrator/`, should Phase 4 (QA) be skipped by the inner
  session? CLAUDE.md says yes with a recorded reason. The runner
  should not need to know about this — the inner conductor prompt
  handles it. Confirm no runner-side logic needed.
- **OQ-8** Log rotation policy: last 50 chunks kept, older archived
  to `.forge/logs/archive/`. Acceptable? Or simpler: no rotation at
  all, rely on git ignore + manual cleanup.

## 16. Definition of done for L2-RUNNER

All 14 acceptance criteria pass. V1-1 ships via the runner as the live
smoke test. Ralph scaffolding removed. Documentation merged. Memory
updated. `.quality/checks.py` green on the final commit.

Chunk is shipped via `scripts/forge-ship.sh "L2-RUNNER: <msg>"` and
synced via `scripts/post-chunk.sh L2-RUNNER`. The chunk row in
`orchestrator/state.db` flips to DONE.

After this chunk, V1-1 runs through the runner as a regression check,
and the main V1 build begins unattended.
