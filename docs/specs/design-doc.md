# ATLAS Forge Dashboard — Design Doc

**Author:** Forge Conductor
**Date:** 2026-04-13
**Status:** DRAFT (awaiting CEO review → PRD)
**Spec target:** rebuild `atlas.jslwealth.in/forge` as a real PM view of ATLAS

---

## 1. The pain (what we're actually solving)

The user opened this with: *"none of the project chunks are getting updated here. i asked for a simple thing — a frontend where i can understand whats happening with the entire project."*

Two problems compound into one bad experience:

1. **The pipeline is broken or flaky.** Even though `state.db` and `.quality/report.json` are being written correctly post-chunk, what's actually rendered at `atlas.jslwealth.in/forge` is not reliably fresh. Root cause candidates:
   - Frontend runs via `next dev` (per `scripts/post-chunk.sh:54`) — a long-lived dev process that can wedge.
   - The existing `/forge` route reads files via Node `fs` from paths like `orchestrator/state.db` and `.quality/report.json`. In a Next dev server started from an earlier working directory, or behind a reverse proxy whose cwd differs, these relative paths silently point at stale/absent files.
   - No backend API endpoint serves this data — the frontend is talking directly to the filesystem, which couples the dashboard's correctness to how Next.js was launched.

2. **The view doesn't match the user's mental model.** The user thinks in terms of `V1 → V10` vertical slices (from `CLAUDE.md` Build Order section). The dashboard shows a flat `C1–C11` list from `orchestrator/plan.yaml`, which is the V1.5 *retrofit* plan — not the product roadmap. No roadmap tree, no per-version rollup, no sense of "what's the overall arc."

   Equally: punch_lists exist in `plan.yaml` as static YAML, but there's no mechanism that turns them into live ✓/✗ on the dashboard. So per-chunk granularity is invisible.

   And: freshness signals (MEMORY.md mtime, wiki mtime, last chunk completion time) exist in a side panel but aren't the first thing your eye lands on — so even when data IS fresh, it doesn't FEEL fresh.

**Scope confirmed by user in office-hours:** fix BOTH the pipeline AND the view. Don't pick one.

---

## 2. Who this is for

- **Primary:** the user (solo builder / product owner of ATLAS). Every morning they want to open one URL and know "what did the overnight build do, what's next, is anything red."
- **Secondary:** occasional stakeholders — an advisor, investor, or collaborator the user might share the link with every few weeks.

Implications:
- Basic polish required (it will be shown to others sometimes), but not a public status page.
- A shared-link token on the `/forge` route is enough — no user auth system.
- Read-only. No write actions from the dashboard. This matches the `project_c8_build_dashboard.md` memory.

---

## 3. What "done" looks like

A single page at `atlas.jslwealth.in/forge` where, within 3 seconds of loading, the user can answer:

1. **Is the dashboard alive?** (heartbeat strip — MEMORY.md, wiki, state.db, backend uptime, last quality run — all with "Xm ago" and amber/red thresholds).
2. **Where are we on the roadmap?** (V1–V10 tree. Each V is a card with rollup: `V1 · 11/11 chunks · 100%`; `V2 · 0/4 chunks · PLANNED`; `V3 · —`. Click to expand chunks. Click a chunk to see its punch_list with live ✓/✗.)
3. **What's the quality of what we just shipped?** (Architecture / Code / Security as the three primary tiles, with "as of Xm ago" so stale ≠ broken.)
4. **What just happened?** (Log tail from the most recent orchestrator run.)

If any of these answers is missing, the dashboard has failed its job.

---

## 4. The "live roadmap" principle (user-specified)

The user was explicit: **"we will be making chunks each from v2 to v10; so whenever the chunk plan is written for a V; it should be automatically be updated as a card to the frontend; anytime a chunk is added or edited; it should get updated on the dash."**

This is the single most important design constraint and it shapes everything downstream:

- The roadmap tree is **not** a hand-maintained JSON or a component with hardcoded version cards. It is **derived** from a single file — `orchestrator/roadmap.yaml` — on every request.
- Adding a chunk to `V3` = editing `roadmap.yaml` and committing. Next page load shows it. No code change. No deploy.
- Chunk status inside the tree is joined live from `orchestrator/state.db` (the authoritative orchestrator source). The roadmap file carries structure + display metadata; the state DB carries status. They are never allowed to duplicate each other.
- `V` status is a rollup, computed: `DONE` if all chunks DONE, `IN_PROGRESS` if any non-DONE chunk has attempts > 0, `PLANNED` if chunks exist but none started, `EMPTY` if no chunks yet. Never hand-set.
- A lint script (`scripts/roadmap-lint.py`) runs in CI and refuses commits where `roadmap.yaml` references a chunk ID that doesn't exist in `plan.yaml` (unless marked `future: true`), OR where `plan.yaml` has a chunk not claimed by any V in `roadmap.yaml`. Drift is impossible.

**Consequence for punch lists:** Each step in `roadmap.yaml` carries a declarative `check:` spec (`file_exists`, `command`, `http_ok`, `db_query`). When the dashboard renders a chunk's expansion, the backend evaluates each check on the fly and returns live ✓/✗. This is what turns punch_lists from "static YAML docs" into "live acceptance tests." It's the whole game.

---

## 5. Quality score cadence (decided)

User chose **post-chunk only**. No polling, no on-demand button.

- `.quality/report.json` is written by `orchestrator/runner.py` after every `QUALITY_GATE` phase. That stays unchanged.
- Dashboard reads the file fresh on each page load, shows scores + an "as of Xm ago" timestamp derived from the file's mtime.
- Staleness is visible: if the last chunk was 3 days ago, the header shows "Quality · 97/100 · 3d ago" in amber.
- No extra CPU. No timer. Simplest thing that works.

This also keeps the dashboard read-only — no "trigger a check run" button means no auth surface to worry about.

---

## 6. Pipeline fix (the "it's not updating" half)

Three targeted fixes, in order of likely impact:

### 6.1 Move frontend off `next dev`
`next dev` is a long-running Node process that can wedge without notice. In production on EC2 this is the wrong runtime. Build once, serve with `next start` under a systemd unit:
- New unit file: `backend/systemd/atlas-frontend.service` (mirrors the existing `atlas-backend.service`).
- `scripts/post-chunk.sh` currently restarts `atlas-backend.service` only (line 55). Extend to also restart `atlas-frontend.service` when it exists.
- Frontend build step added to post-chunk sync: `npm run build` before the restart.
- **Estimated impact:** this alone probably fixes 80% of "nothing updating" complaints.

### 6.2 Stop reading files directly from the Next.js route
The current `/forge/api/route.ts` reads `state.db`, `report.json`, and memory files via Node `fs`. This binds the dashboard's correctness to the cwd Next was started in and the user the systemd unit runs as. Replace with HTTP calls to the backend:
- Backend owns all filesystem access (it already runs from `/home/ubuntu/atlas` via its own systemd unit, so paths are correct).
- Frontend becomes a thin proxy / direct fetch. No `fs` calls in the Next.js layer.
- New backend endpoints (section 7) are the single source of dashboard data.

### 6.3 Add the heartbeat strip
The user should SEE staleness, not be surprised by it. The heartbeat strip at the top of `/forge` shows five chips with mtimes + thresholds. If MEMORY.md hasn't been touched in 6h during a build, it goes red — immediate visual signal that something upstream is broken, before we have to debug why numbers look wrong.

---

## 7. Backend API surface (new, read-only)

All three endpoints extend `backend/routes/system.py` (already modified for C11 live quality). No new router file.

### `GET /api/v1/system/heartbeat`
Returns one JSON object with everything the heartbeat strip needs:
```json
{
  "memory_md_mtime": "2026-04-13T09:14:22+05:30",
  "wiki_index_mtime": "2026-04-13T07:01:11+05:30",
  "state_db_mtime": "2026-04-13T09:18:44+05:30",
  "last_chunk_done_at": "2026-04-13T09:18:44+05:30",
  "last_chunk_id": "C11",
  "last_quality_run_at": "2026-04-13T09:19:02+05:30",
  "last_quality_score": 97,
  "backend_uptime_seconds": 14321
}
```
In-process cache: 10s. One request = whole header.

### `GET /api/v1/system/roadmap`
Parses `orchestrator/roadmap.yaml`, joins `state.db` chunk status, evaluates every step's `check:` spec, returns the full V1–V10 tree. Cache: 10s in-process.

Structure of response:
```json
{
  "as_of": "2026-04-13T09:20:00+05:30",
  "versions": [
    {
      "id": "V1",
      "title": "Market → Sector → Stock → Decision",
      "status": "IN_PROGRESS",
      "rollup": { "done": 11, "total": 11, "pct": 100 },
      "chunks": [
        {
          "id": "C11",
          "title": "Live API quality checks against running backend",
          "status": "DONE",
          "attempts": 1,
          "updated_at": "2026-04-13T09:18:44+05:30",
          "steps": [
            { "id": "C11.1", "text": "/api/v1/system/health returns 200", "check": "ok", "detail": "" },
            { "id": "C11.2", "text": "Pydantic contract validation on stocks/universe", "check": "ok", "detail": "" }
          ]
        }
      ]
    }
  ]
}
```

### `GET /api/v1/system/quality`
Returns the current `.quality/report.json` verbatim, plus an `as_of` derived from the file's mtime. No computation. No side effects. If the file is missing, returns `{"as_of": null, "scores": null}` — never 500.

### `GET /api/v1/system/logs/tail?lines=200`
Returns the last N lines of the most recent file in `orchestrator/logs/`. Streams from disk, no buffering. Used by the log-tail panel.

---

## 8. Frontend structure

Directory: `frontend/src/app/forge/` + `frontend/src/components/forge/`.

Layout (top to bottom):
1. **Heartbeat strip** (`HeartbeatStrip.tsx`, new) — five chips, full-width, sticky on scroll.
2. **Roadmap tree** (`RoadmapTree.tsx`, new) — replaces `ChunkTable.tsx` as primary. Collapsible V1–V10 cards. `ChunkTable.tsx` kept as a secondary "flat view" tab for power users.
3. **Quality scores** (`QualityScores.tsx`, existing, repointed to `/api/v1/system/quality`) — three primary tiles (Architecture / Code / Security), four secondary tiles below.
4. **Context files** (`ContextFiles.tsx`, existing, demoted) — still available for drilling into specific memory/wiki files.
5. **Log tail** (`LogTail.tsx`, existing, repointed to `/api/v1/system/logs/tail`) — unchanged in shape.

Route (`frontend/src/app/forge/page.tsx`) stays `force-dynamic`. The API route (`frontend/src/app/forge/api/route.ts`) is rewritten to proxy the three new backend endpoints, NOT to read files directly. Reuses hooks in `frontend/src/lib/forgeContext.ts` where possible.

Polish target: the visual quality of a serious internal tool (Linear / Vercel dashboard). Teal accent (#1D9E75 per frontend rules), white background, data-dense. No generic Bootstrap.

---

## 9. Success metrics (how we know we shipped the right thing)

1. **Freshness.** 100% of page loads during an active build show MEMORY.md mtime within last 30 minutes.
2. **Honesty.** If the next dev / next start process dies, the heartbeat strip turns red within 60s of the next user visit — no silent stale data.
3. **Roadmap liveness.** Adding a new chunk to `roadmap.yaml` + committing = the chunk card appears on the next page load with no code change, no deploy. (This is testable with a temporary fake chunk in a feature branch.)
4. **Drift prevention.** `scripts/roadmap-lint.py` in CI catches 100% of `roadmap.yaml` ↔ `plan.yaml` mismatches. We seed with 3 deliberate mismatches in a test fixture and verify it catches all 3.
5. **Time-to-confidence.** From URL hit to "I know what's up" is ≤3 seconds for the user, measured by asking them after a week of use. (Qualitative, but the primary metric.)

---

## 10. Explicit non-goals

- **No write actions from the dashboard.** No "trigger a run" button, no "mark chunk done" button, no auth system. Read-only.
- **No polling quality scores on a timer.** Decided in office-hours: post-chunk only.
- **No rewrite of `orchestrator/runner.py` or the state machine.** The orchestrator stays authoritative for chunk status. We only ADD a roadmap view over it.
- **No changes to `plan.yaml` chunk definitions.** `roadmap.yaml` is additive. `plan.yaml` remains the executable spine for whatever the orchestrator is currently running (today: the V1.5 retrofit; tomorrow: V2 chunks).
- **No V-level punch_lists.** Steps exist at the chunk level only. Versions are rollups.
- **No historical time-series / sparklines.** (Tempting, but not in scope. If wanted later, the backend already has the data in `state.db`.)
- **No multi-tenant dashboard / RBAC.** Single user + occasional shared link.

---

## 11. Open questions to resolve in PRD

1. Shared-link token: simple env-var-based query param (`?token=...`), or Cloudflare Access, or just rely on an obscure domain path? (Suggest: env var on `atlas-frontend.service`, checked in middleware.)
2. V2–V10 initial content: seed `roadmap.yaml` with V-level goals from `CLAUDE.md` Build Order section today, and let chunks populate as they're planned? Or leave V2–V10 empty entirely? (Suggest: seed with V-level goals, empty chunks arrays — matches the user's "auto-appears" requirement.)
3. Log tail source: latest file in `orchestrator/logs/`, or tail of `journalctl -u atlas-backend`? (Suggest: orchestrator log — it's the build log, which is what the user cares about here.)
4. Check types to support in `roadmap.yaml`: `file_exists`, `command`, `http_ok`, `db_query` — is that enough? Any check that takes >2s must be marked `slow: true` and only evaluated on explicit expand.

These questions carry forward to `/plan-ceo-review`.
