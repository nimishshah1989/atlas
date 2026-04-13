# PRD — ATLAS Forge Dashboard v2 ("PM View")

**Owner:** Nimish (ATLAS product owner)
**Author:** Forge Conductor (post-CEO-review of design-doc.md)
**Date:** 2026-04-13
**Status:** DRAFT — awaiting user approval before Phase 2 (chunk plan)
**Inputs:** `docs/specs/design-doc.md`, `CLAUDE.md` (Build Order section), memory files `project_v15_chunk_status.md`, `project_c8_build_dashboard.md`.

---

## 0. CEO review — where I pushed back on my own design doc

Before writing this PRD I stress-tested the design doc against 10 sharp questions. Summary of what changed:

| # | Challenge | Verdict |
|---|-----------|---------|
| 1 | Is the roadmap tree worth building, or just fix the pipeline? | Build it. User was explicit: both. Pipeline fix alone doesn't answer "what are we building." |
| 2 | Why a new `roadmap.yaml` instead of extending `plan.yaml` with a `version:` field? | Because `plan.yaml` is the executable spine for *currently running* chunks. Mixing roadmap structure into it couples "what will happen someday" with "what the runner dispatches tomorrow." Keep them separate. Lint enforces consistency. |
| 3 | Is the declarative `check:` spec over-engineered? | No, and cutting it kills the main point. Without live ✓/✗ on steps, the dashboard is just a prettier `plan.yaml` viewer. Keep `file_exists`, `command`, `http_ok`, `db_query` — four check types only. No plugin system. |
| 4 | Heartbeat strip — over-designed? | No. It's the single feature that prevents "is this thing even alive" confusion. Keep. |
| 5 | Should we have a "re-run checks" button even once? | **No.** Deferred. User explicitly chose post-chunk only. Adding a button introduces auth surface + CPU spikes. Revisit after a month of real use. |
| 6 | Systemd frontend unit — is this creep? | No. It's the single highest-impact pipeline fix. Without it we're still debugging wedged next-dev processes in a month. |
| 7 | V2-V10 empty placeholders vs "populate as planned" — user answered this. Does the answer actually work? | Yes, but only because we seed `roadmap.yaml` with V-level *goals* from `CLAUDE.md`. Empty `chunks: []` arrays render as "PLANNED · 0 chunks" cards. When a chunk gets added to `roadmap.yaml`, it auto-appears. No code change. |
| 8 | Is "polling quality scores post-chunk only" enough if a build stalls mid-chunk? | Edge case, but real. Mitigation: heartbeat strip surfaces `state_db_mtime` and `backend_uptime`. If a chunk is mid-run and quality hasn't moved in 30 min, heartbeat turns amber. You see staleness without needing fresh scores. |
| 9 | What's the minimum lovable version? | Heartbeat strip + roadmap tree (V1 only, real) + quality tile pointing at existing report.json + systemd frontend unit. Everything else (log tail, context files drill-down, V2-V10 seed, step-level checks) is a nice-to-have that can ship in a follow-up chunk. We'll structure the chunk plan so Phase 3 can cut early if needed. |
| 10 | What's the biggest risk to the whole thing being pointless? | User stops looking at it. Prevented by: heartbeat strip is the bold first thing; roadmap tree answers "what am I building"; both update without a deploy. If user opens it daily for a week after ship, we've won. |

**Scope survived CEO review mostly intact.** The only real cut: no "re-run checks" button, ever, in v1. If needed, it's a v2 feature behind an auth token.

---

## 1. Problem

Today the user cannot answer three questions in one place:

1. **Is the build machine alive?** (Are MEMORY.md, the wiki, state.db, and the backend all fresh — or is something silently wedged?)
2. **Where are we on the V1 → V10 product arc?** (What's done, what's next, what's even planned?)
3. **What's the quality of what we just shipped?** (Architecture / Code / Security scores — and when were they last computed?)

There is a dashboard at `atlas.jslwealth.in/forge` today, but it (a) appears stale to the user, and (b) shows a flat C1–C11 list that reflects the V1.5 retrofit, not the V1–V10 product roadmap. The user opened this conversation with: *"none of the project chunks are getting updated here."*

**Why now:** V1.5 retrofit just hit DONE (97/100 gate). V2 planning starts next. The user needs the dashboard to be the ground truth for the next 9 vertical slices — starting immediately.

---

## 2. Goal

A single URL (`atlas.jslwealth.in/forge`) that, within 3 seconds of loading, lets the user answer "alive? where are we? quality?" without scrolling, without clicking, without refreshing.

Dashboard reflects the roadmap **automatically** whenever `roadmap.yaml` or `state.db` changes. No deploys required to keep it current.

---

## 3. Non-goals (explicit cuts)

- No write actions. Read-only dashboard.
- No auth system. Shared-link token only (env var checked in middleware).
- No quality-score polling / on-demand button. Post-chunk only.
- No rewrite of `orchestrator/runner.py` or state machine.
- No multi-user, no RBAC, no tenancy.
- No historical time-series, no sparklines, no charts beyond the quality tiles.
- No V-level punch lists. Steps live at chunk level only.
- No "trigger a run" / "accept chunk" / "override status" buttons.
- No migration of existing `plan.yaml` chunks — `roadmap.yaml` is additive.

---

## 4. Users

- **Primary user:** Nimish. Opens dashboard every morning during active builds. Needs to know overnight state in 3 seconds.
- **Secondary:** occasional stakeholders (advisor, investor, collaborator) shown the link every few weeks. Needs to understand what ATLAS is building without a walkthrough.

No third-party users. No retail end-users.

---

## 5. User stories

**US-1 — Morning check-in (primary).**
As Nimish, at 8am after an overnight build, I want to open `atlas.jslwealth.in/forge` and immediately see whether any chunk advanced, whether quality held, and whether anything is red. Success = I close the tab within 10 seconds on a good day.

**US-2 — Mid-build spot check.**
As Nimish, while a chunk is mid-run, I want to see the log tail and current state.db entry so I can tell if the runner is still making progress. Success = no need to SSH to the EC2 box just to check.

**US-3 — Roadmap thinking.**
As Nimish, when planning V3, I want to see V1–V10 laid out with their current states so I can think about what to tackle next. Success = the roadmap tree is enough to reason about scheduling without opening `CLAUDE.md`.

**US-4 — Adding a new chunk, zero friction.**
As Nimish, when I define a new chunk in `roadmap.yaml` and push, I want it to appear on the dashboard on the next page load without touching frontend code. Success = `git push` → reload → new card visible.

**US-5 — Showing a stakeholder.**
As Nimish, when an advisor asks "how's ATLAS going?", I want to share a link and have them understand the arc without a 20-minute explainer. Success = they get it in under a minute.

**US-6 — Detecting silent failure.**
As Nimish, if `next dev` wedges or the orchestrator crashes, I want the dashboard itself to TELL me, not look normal. Success = heartbeat strip turns red / amber within one page load of the break.

---

## 6. Scope (what v1 ships)

### 6.1 Pipeline fixes

- **P1. Frontend systemd unit.** New file `backend/systemd/atlas-frontend.service` running `next start` against a pre-built `.next/` directory. Mirrors existing `atlas-backend.service`.
- **P2. Frontend build + restart in post-chunk hook.** Extend `scripts/post-chunk.sh`: after backend restart, run `npm run build` in `frontend/` and restart `atlas-frontend.service` if installed.
- **P3. Backend-owned filesystem reads.** New endpoints in `backend/routes/system.py` (see §7). Frontend stops touching `fs` directly in `/forge/api/route.ts`.

### 6.2 Roadmap spine

- **R1. `orchestrator/roadmap.yaml`** — new file. Seeded with V1 (full, real, joined to existing C1–C11) and V2–V10 (V-level goals only, empty `chunks: []`).
- **R2. `scripts/roadmap-lint.py`** — validates `roadmap.yaml` ↔ `plan.yaml` consistency. Runs in pre-commit hook. Fails on drift.
- **R3. Declarative check evaluator** — new module `backend/core/roadmap_checks.py`. Supports four check types: `file_exists`, `command`, `http_ok`, `db_query`. `command` is sandboxed to the repo root and has a hard 5s timeout. `slow: true` steps are not evaluated unless the API request includes `?evaluate_slow=true`.

### 6.3 Backend API (new endpoints, all in `backend/routes/system.py`)

- **A1.** `GET /api/v1/system/heartbeat`
- **A2.** `GET /api/v1/system/roadmap`
- **A3.** `GET /api/v1/system/quality`
- **A4.** `GET /api/v1/system/logs/tail?lines=N` (default 200, max 1000)

All four are read-only, unauthenticated (behind shared-link token at the edge — §9), cached 10s in-process.

### 6.4 Frontend redesign

- **F1. `HeartbeatStrip.tsx`** (new). Five chips: MEMORY.md, Wiki, state.db, Quality, Backend. Sticky on scroll. Amber >1h, red >6h.
- **F2. `RoadmapTree.tsx`** (new). Primary panel. Collapsible V1–V10 cards with rollup counts. Expand → chunks. Expand chunk → steps with live check results.
- **F3. `QualityScores.tsx`** (existing, repointed). Three primary tiles: Architecture / Code / Security. Four secondary tiles: Frontend / DevOps / Docs / API. `as_of` timestamp prominently shown.
- **F4. `ContextFiles.tsx`** (existing, demoted). Below the fold.
- **F5. `LogTail.tsx`** (existing, repointed to `/api/v1/system/logs/tail`).
- **F6.** `/forge/api/route.ts` rewritten as thin proxy to backend. Zero `fs` calls.
- **F7.** Middleware (`frontend/src/middleware.ts`) checks `FORGE_SHARE_TOKEN` env var on `/forge/*`. If unset, route is open (dev mode). If set, requires `?token=...` or cookie.

---

## 7. API contracts (freeze before Phase 2)

### `GET /api/v1/system/heartbeat`
```json
{
  "memory_md_mtime": "2026-04-13T09:14:22+05:30",
  "wiki_index_mtime": "2026-04-13T07:01:11+05:30",
  "state_db_mtime": "2026-04-13T09:18:44+05:30",
  "last_chunk_done_at": "2026-04-13T09:18:44+05:30",
  "last_chunk_id": "C11",
  "last_quality_run_at": "2026-04-13T09:19:02+05:30",
  "last_quality_score": 97,
  "backend_uptime_seconds": 14321,
  "as_of": "2026-04-13T09:20:01+05:30"
}
```
All timestamps IST, tz-aware. Any missing field returned as `null`, never omitted.

### `GET /api/v1/system/roadmap`
```json
{
  "as_of": "2026-04-13T09:20:01+05:30",
  "versions": [
    {
      "id": "V1",
      "title": "Market → Sector → Stock → Decision",
      "goal": "FM can navigate Market → Sector → Stock → Decision end-to-end",
      "status": "DONE",
      "rollup": { "done": 11, "total": 11, "pct": 100 },
      "chunks": [
        {
          "id": "C11",
          "title": "Live API quality checks against running backend",
          "status": "DONE",
          "attempts": 1,
          "updated_at": "2026-04-13T09:18:44+05:30",
          "steps": [
            { "id": "C11.1", "text": "/health returns 200", "check": "ok", "detail": "" }
          ]
        }
      ]
    },
    {
      "id": "V2",
      "title": "MF slice",
      "goal": "Category → fund → holdings drill-down works end-to-end",
      "status": "PLANNED",
      "rollup": { "done": 0, "total": 0, "pct": 0 },
      "chunks": []
    }
  ]
}
```
Status enum: `DONE | IN_PROGRESS | PENDING | PLANNED | BLOCKED | FAILED | EMPTY`.
`check` enum (step-level): `ok | fail | slow-skipped | error`.

### `GET /api/v1/system/quality`
Returns `.quality/report.json` verbatim plus `as_of` (file mtime). Missing file → `{"as_of": null, "scores": null}`.

### `GET /api/v1/system/logs/tail?lines=N`
```json
{
  "file": "orchestrator/logs/2026-04-13T08-55-12.log",
  "lines": ["...", "..."],
  "as_of": "2026-04-13T09:20:01+05:30"
}
```

---

## 8. Success metrics

1. **Freshness during active build:** 100% of page loads show MEMORY.md mtime within last 30 minutes. Measured by a probe script hitting `/heartbeat` every 5 min during a live build.
2. **Pipeline honesty:** When `next dev` or `atlas-frontend.service` is killed, heartbeat strip shows red within 60 seconds of the next page load. Tested by deliberately killing the unit in staging.
3. **Roadmap liveness:** Adding a new chunk to `roadmap.yaml` and pushing = card appears next page load, zero frontend code change, zero deploy. Tested with a throwaway fake chunk on a branch.
4. **Drift prevention:** `scripts/roadmap-lint.py` catches 3-of-3 deliberate drift cases in the test fixture. Runs in pre-commit.
5. **Time to confidence (qualitative):** After 7 days of real use, user reports "I know what's up in under 3 seconds" on 5+ of those days. If not, we missed.

---

## 9. Security

- **Shared-link token** (`FORGE_SHARE_TOKEN`) lives in `atlas-frontend.service` environment. Rotated monthly. Checked in Next.js middleware for `/forge/*`. Token absent from env = dashboard is open (dev mode only).
- Backend endpoints (`/api/v1/system/*`) are **not** behind token in v1 — they're bound to `localhost:8010` and only reachable via the Next.js proxy. Nginx/Cloudflare does not expose `:8010` publicly. (Verify before ship.)
- `command:` checks in `roadmap.yaml` run in a subprocess with: `cwd=repo_root`, `shell=False`, `timeout=5s`, no env inherited except `PATH`. Commands in `roadmap.yaml` are author-trusted (file is in-repo, code review gates it), but the sandbox is belt-and-suspenders.
- No secrets rendered to the dashboard. `report.json` is whitelisted-field-only (if it ever carries secrets in future, we pre-redact).

---

## 10. Risks & mitigations

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Systemd frontend unit doesn't work on EC2 (wrong user, wrong paths) | Medium | High — dashboard still stale | Test on staging EC2 before cutting over. Keep next-dev as fallback for one week. |
| `command:` checks run user code with loose sandbox | Low | High — RCE via PR to `roadmap.yaml` | Author-trust model + subprocess sandbox. Document in CONTRIBUTING.md that `roadmap.yaml` changes require review. |
| 10s backend cache makes the dashboard feel laggy on refresh | Low | Low | Tunable. Start at 10s, drop to 5s if user complains. |
| User adds V2 chunks to `roadmap.yaml` before they exist in `plan.yaml`, lint blocks commit | Medium | Low | Add `future: true` flag — linted as "allowed to be roadmap-only." |
| `check:` evaluator times out and whole roadmap endpoint hangs | Medium | Medium | Hard per-check 5s timeout + whole-endpoint 15s timeout. Slow checks opt-in only. |
| Frontend `next build` fails in post-chunk hook and leaves dashboard broken | Medium | High | Hook catches build failure, alerts in log, but does NOT restart frontend — stale frontend keeps serving the last working build. |

---

## 11. Open questions (must resolve before Phase 2)

1. **Share-link token enforcement:** token at Next.js middleware (my recommendation) or at Cloudflare Access (more work, more secure)? Defaulting to middleware unless user objects.
2. **V2–V10 goal text source:** pull V-level goals verbatim from `CLAUDE.md` "Build Order — Vertical Slices" section? (I'll seed with that.)
3. **Log tail source:** most recent file in `orchestrator/logs/` (my pick) or `journalctl -u atlas-backend`? Going with orchestrator logs — they're what the user actually cares about.
4. **`roadmap.yaml` location:** `orchestrator/roadmap.yaml` (my pick — lives with the state it joins to) or `docs/roadmap.yaml` (lives with other specs)? Going with `orchestrator/` — it's a runtime input, not a doc.
5. **Backend test strategy for live checks:** do we run `command:` checks in CI? No — too flaky. Lint the spec, don't execute.

These all default to my picks unless the user flags otherwise at the approval gate.

---

## 12. Dependencies

- Existing: `orchestrator/state.db` (read-only), `.quality/report.json` (read-only), `~/.claude/projects/-home-ubuntu-atlas/memory/MEMORY.md` (read mtime), `~/.forge/knowledge/wiki/index.md` (read mtime), `backend/routes/system.py` (extend), `frontend/src/app/forge/*` (rewrite), `scripts/post-chunk.sh` (extend).
- New packages: `pyyaml` for roadmap parsing (likely already present — verify in Phase 2). No frontend deps added.
- Infra: ability to install a new systemd unit on the ATLAS EC2 box. (Already have sudo.)

---

## 13. Rollout

1. Merge + deploy backend endpoints first (dashboard can fall back to old file-reading path while frontend is in transition).
2. Deploy new `roadmap.yaml` + lint.
3. Ship frontend redesign.
4. Install `atlas-frontend.service`; run in parallel with `next dev` for 24h; cut over when stable.
5. Decommission old file-reading path in `/forge/api/route.ts`.

No DB migrations. No data backfill. Nothing user-facing in ATLAS proper changes — this is all `/forge`.

---

## 14a. Amendments from parallel-session harmonization (2026-04-13)

A second in-flight session shipped V2-readiness infra (`scripts/smoke-probe.sh`, `scripts/smoke-endpoints.txt`, `scripts/tasks-to-plan.py`, `docs/specs/version-demo-gate.md`) after this PRD was frozen. The following amendments fold into the chunk specs so FD-1…FD-4 harmonize with that work instead of colliding with it. All amendments expand scope by <10% total; none change the approval surface.

1. **FD-2 schema — add optional `demo_gate` field on Version.** Pydantic `DemoGate` sub-model with required `url: str` + `walkthrough: list[str]`. Shape validation only at this chunk; runner-side consumption is deferred to the follow-up chunk specced in `docs/specs/version-demo-gate.md`. Seeded on V2 from the spec's example. Adding now is zero-cost; retrofitting later forces a migration. Lint rejects missing `url` / empty `walkthrough`.

2. **FD-4 must preserve `post-chunk.sh` Step 3.5 byte-identical.** The existing smoke-probe block (lines 62–76) is the V2 autonomous build's slice-regression safety net. Chunk 4 surgically inserts a new `# --- 3.b Frontend build + restart` block INSIDE Step 3, AFTER the backend restart and BEFORE Step 3.5. A diff test locks this down. Frontend build failures log-and-continue; they do NOT block chunk DONE — the smoke probe is the authoritative gate.

3. **FD-1 adds a 5th check type: `smoke_list`.** New `ChunkCheckType.smoke_list` in the schema. Evaluator shells to `scripts/smoke-probe.sh` with `SMOKE_QUIET=1`, parses summary, returns aggregate ok/fail plus per-URL detail. Implicitly `slow: true` (always opt-in). Separate 60s result cache (curl probes are expensive). Plus: `/heartbeat` endpoint gains three extra fields — `last_smoke_run_at`, `last_smoke_result`, `last_smoke_summary` — sourced from `orchestrator/logs/*.smoke.log` mtime + trailer line.

4. **FD-2 adds `scripts/plan-to-roadmap.py` writer companion to the lint.** Takes `--chunk Cxx --version Vy`, appends a skeleton `- id: Cxx\n  plan_ref: true` under the target version's `chunks:` list. Idempotent; refuses cross-version conflicts. Uses `ruamel.yaml` for round-trip YAML so existing comments and formatting survive. Wires into `scripts/tasks-to-plan.py` via a new `--auto-roadmap` flag so the forge-build Phase 2 → orchestrator pipeline ends with both `plan.yaml` AND `roadmap.yaml` updated in one step. Without this, "walk away and let the orchestrator run V2" requires hand-editing YAML after every Phase 2.

5. **FD-3 heartbeat strip grows from 5 chips to 6 — adds "Last smoke".** Reads the three new `/heartbeat` fields from Amendment 3. Displays e.g. `"Smoke · 3/3 green · 12m ago"`. Amber >1h, red >6h OR any hard fail regardless of age. This is the "ATLAS is actually coming to life" signal — catches the "chunks green, product dead" failure mode.

---

## 14. Approval gate

PRD is ready. This is where `/forge-build` Phase 1 ends and Phase 2 (chunk plan) begins. Conductor will pause here and ask for explicit user sign-off on:
- Problem framing
- Scope (§6) and non-goals (§3)
- API contract shape (§7)
- Security posture (§9)
- Open-question defaults (§11)

Once approved, Conductor proceeds to Phase 2.1: break PRD into chunks, write `chunk-plan.md` + per-chunk specs + `tasks.json`.
