# Chunk Plan — Forge Dashboard v2

**Source PRD:** `docs/specs/prd.md`
**Date:** 2026-04-13
**Total chunks:** 4
**Estimated wall-clock:** 2.5–4 hours of orchestrated build time

---

## Build order and dependencies

```
CHUNK-1 (backend data plane)  ──┐
                                 ├──►  CHUNK-3 (frontend redesign) ──► CHUNK-4 (deployment pipeline)
CHUNK-2 (roadmap yaml + lint) ──┘
```

- **CHUNK-1** and **CHUNK-2** are independent and can run in either order.
- **CHUNK-3** requires both (needs the backend endpoints live AND `roadmap.yaml` populated so the roadmap response isn't empty).
- **CHUNK-4** is last — it installs `atlas-frontend.service` and wires post-chunk hook, which means the frontend must build cleanly first.

Supervised (Option B) build runs them sequentially. Autonomous (Option A / ralph) can parallelize chunks 1+2 in worktrees if desired.

---

## Chunk summary

| # | Name | Files touched | Blocks | Complexity |
|---|------|---------------|--------|------------|
| 1 | Backend data plane | `backend/routes/system.py`, `backend/core/roadmap_checks.py` (new, incl. `smoke_list` check type), `roadmap_loader.py`, tests | C3 | M |
| 2 | Roadmap spine + lint | `orchestrator/roadmap.yaml` (new, with `demo_gate` schema), `scripts/roadmap-lint.py` (new), `scripts/plan-to-roadmap.py` (new), pre-commit | C3 | S+ |
| 3 | Frontend redesign | `frontend/src/components/forge/*` (6-chip heartbeat strip incl. smoke), `frontend/src/app/forge/*`, middleware | C4 | L |
| 4 | Deployment pipeline | `backend/systemd/atlas-frontend.service` (new), `scripts/post-chunk.sh` (Step 3.b added inside Step 3, Step 3.5 preserved byte-identical) | — | S |

Complexity scale: S = <1h, M = 1–2h, L = 2–4h.

---

## Risk matrix (from /plan-eng-review pass)

| Risk | Affected chunk | Pre-build mitigation | Post-build check |
|------|---------------|----------------------|------------------|
| `command:` check evaluator executes user-provided shell | C1 | Subprocess sandbox: `shell=False`, `cwd=repo_root`, timeout=5s, `PATH`-only env | Unit test that asserts commands cannot escape repo_root |
| `roadmap.yaml` drift from `plan.yaml` | C2 | Lint script runs in pre-commit + CI | Integration test: deliberate drift → lint exits non-zero |
| `/roadmap` endpoint hangs waiting on slow checks | C1 | Whole-endpoint timeout 15s; `slow: true` steps opt-in only | Contract test: endpoint P95 < 500ms with synthetic roadmap |
| Frontend `next build` fails in post-chunk hook → stale frontend keeps serving | C4 | Hook catches build failure, logs, does NOT restart service | Manual test: break a TSX file, run hook, verify old build still serves |
| Backend endpoint contracts drift from frontend expectations | C1↔C3 | Contracts frozen in PRD §7, Pydantic models shared | Contract test in tests/routes/test_system.py matches frontend types |
| `atlas-frontend.service` wrong user/path/permissions | C4 | Test on staging EC2 first, keep `next dev` fallback 24h | systemd unit has `Restart=on-failure` + journal logging |
| Middleware token check blocks legitimate dev access | C3 | Token absent from env = open mode (dev). Only production EC2 gets the env var | Integration test: no env → 200; wrong token → 401; right token → 200 |
| Clobbering Step 3.5 smoke probe in `post-chunk.sh` | C4 | Surgical insertion of Step 3.b INSIDE Step 3; Step 3.5 stays byte-identical | Diff test: Step 3.5 block pre- vs post-edit must be empty |
| `smoke_list` check recurses / triggers curl storm | C1 | `smoke_list` is implicitly `slow: true` (not run per page load), 60s result cache, only `scripts/smoke-endpoints.txt` allowed | Unit test: hitting `/roadmap` 10× in 2s triggers one probe, not ten |
| `demo_gate` field unused in v1, rots before follow-up chunk lands | C2 | Schema-only validation now; lint enforces shape; follow-up `version-demo-gate.md` chunk already specced | Contract test: V2 seed parses; unknown fields rejected |
| `plan-to-roadmap.py` corrupts comments/formatting when editing YAML | C2 | Use `ruamel.yaml` (round-trip YAML) not `pyyaml` for the writer only | Round-trip test: write skeleton entry, diff should be strictly additive |

---

## Architecture diagram (data flow)

```
                                  ┌──────────────────────────┐
User browser ─► atlas.jslwealth.in┤ next start (systemd)     │
                                  │ /forge route             │
                                  │ /forge/api/route.ts      │──┐
                                  └──────────────────────────┘  │
                                                                │ HTTP (localhost:8010)
                                                                ▼
                                  ┌──────────────────────────────────────┐
                                  │ FastAPI (systemd)                    │
                                  │ backend/routes/system.py             │
                                  │  ├─ GET /heartbeat  ─── reads mtimes │
                                  │  ├─ GET /roadmap    ─── parses YAML, │
                                  │  │                      joins state, │
                                  │  │                      runs checks  │
                                  │  ├─ GET /quality    ─── report.json  │
                                  │  └─ GET /logs/tail  ─── log files    │
                                  └────────┬─────────────────────────────┘
                                           │
                    ┌──────────────────────┼──────────────────────┬──────────────────────┐
                    ▼                      ▼                      ▼                      ▼
          orchestrator/            orchestrator/          .quality/              ~/.claude/.../
          roadmap.yaml             state.db               report.json            memory/MEMORY.md
                                                                                 ~/.forge/knowledge/
                                                                                 wiki/index.md
```

All filesystem access happens in the backend process. Frontend only talks HTTP.

---

## Test matrix

| Layer | Chunk | Test type | Coverage target |
|-------|-------|-----------|-----------------|
| Backend route handlers | C1 | pytest + httpx AsyncClient | 90% of new code |
| Check evaluator (4 types) | C1 | pytest unit | 100% of type branches |
| Sandbox escape attempts | C1 | pytest — 5 malicious command payloads | Must all fail closed |
| Roadmap lint | C2 | pytest + test fixture with 3 drift cases | 3/3 caught |
| Roadmap YAML schema | C2 | pydantic model validation | Invalid YAML rejected |
| Frontend components | C3 | React Testing Library (if configured) or Playwright | Smoke only |
| Middleware token | C3 | Playwright: 3 cases (no env, wrong token, right token) | 3/3 pass |
| Post-chunk hook | C4 | Shell test: deliberate `next build` failure | Old build still serves |
| End-to-end | all | Phase 4 QA browser walk-through | US-1 through US-6 |

---

## Out-of-chunk work

- **Phase 4 QA** — runs /qa against live dashboard after all chunks ship. Browser walk-through of US-1 through US-6. Generates regression tests.
- **Phase 4 /cso** — OWASP Top 10 + STRIDE pass focused on the `command:` check sandbox, the middleware token, and the Next.js proxy.
- **Phase 5 /retro + wiki harvest** — standard.

---

## Per-chunk specs

See:
- `docs/specs/chunks/chunk-1.md` — Backend data plane
- `docs/specs/chunks/chunk-2.md` — Roadmap spine + lint
- `docs/specs/chunks/chunk-3.md` — Frontend redesign
- `docs/specs/chunks/chunk-4.md` — Deployment pipeline

And `docs/specs/tasks.json` for the orchestrator-consumable task list.
