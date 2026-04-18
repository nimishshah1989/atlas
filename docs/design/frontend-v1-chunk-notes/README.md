# V1-Frontend-Stage1 chunk notes — REFERENCE ONLY

**Status:** reference design material, NOT the source of truth.
**Authored:** 18 Apr 2026 (pre-chunkmaster run), author hand-written.
**Successor artefact:** whatever `/chunkmaster V1FE --spec
docs/design/frontend-v1-spec.md` produces under `specs/<NNN-v1fe>/`.

---

## Why this directory exists

These 15 files were drafted by hand before `/chunkmaster` was run for
the V1-Frontend-Stage1 slice. They encode the design thinking that
went into *how* the slice should be partitioned into chunks —
pre-chunks (check runner + component library), page chunks (one per
mockup), and a QA-sweep tail chunk.

They are NOT the orchestrator ledger. `/chunkmaster` writes the
canonical ledger to `specs/<NNN-v1fe>/` via the Spec Kit pipeline
(specify → clarify → plan → checklist → tasks → analyze). Only the
chunkmaster-generated `tasks.json` feeds `scripts/tasks-to-plan.py`
and populates `orchestrator/plan.yaml`.

## How to use these notes

**Don't:**
- Treat any file here as authoritative
- Reference these file paths from orchestrator/plan.yaml
- Copy-paste "Points of success" lists from here into chunk DONE
  acceptance — chunkmaster will generate its own via /speckit-tasks

**Do:**
- Let `/chunkmaster`'s slice-extraction step (Case B, SKILL.md lines
  ~104-126) read this directory when `SPEC_PATH =
  docs/design/frontend-v1-spec.md` — the contents here are
  pre-chewed design intent that informs the SLICE_BRIEF
- Use these notes as a prompt for `/speckit-clarify` — if chunkmaster
  asks a clarification question whose answer is already captured
  here, cite the relevant file instead of escalating
- After chunkmaster ships and the V1FE chunks complete, these files
  can be deleted or archived — they're a staging artefact, not
  long-term documentation

## Directory contents

| File | Purpose |
|---|---|
| `s1-common.md` | Hard invariants shared across every page chunk |
| `s1-pre-0-check-runner.md` | Gate: `scripts/check-frontend-criteria.py` implementing the 28 check types declared in `docs/specs/frontend-v1-criteria.yaml` |
| `s1-pre-1-component-library.md` | `components.html` + `tokens.css` v1.1 additions + 2 new fixtures (mf_rank_universe, sector_rrg) |
| `s1-0-index-landing.md` | `index.html` landing page + link audit |
| `s1-1-today.md` | `today.html` — Pulse page (regime banner + 4-decision grid + universal benchmarks) |
| `s1-2-explore-global.md` | Global market regimes + universal benchmarks |
| `s1-3-explore-country.md` | India market view + instrument-row grid with 7 chips |
| `s1-4-explore-sector.md` | Sector RRG chart + rotation table |
| `s1-5-stock-detail.md` | Stock hub-spoke (richest page) |
| `s1-6-mf-detail.md` | MF hub-spoke with weighted-technicals |
| `s1-7-mf-rank.md` | 4-factor composite ranking (dimensional-fix formula v1.1) |
| `s1-8-breadth.md` | Breadth terminal (read surface; Lab is the interactive twin) |
| `s1-9-portfolios.md` | Watchlist + portfolio overview |
| `s1-10-lab.md` | Signal Playback simulator (14-param v1.1) |
| `s1-11-qa-sweep.md` | Playwright baselines + a11y sweep + full gate pass |

## Relationship to companion artefacts

- Source of truth for the slice: `docs/design/frontend-v1-spec.md` (v1.1, 1475 lines)
- Machine-readable acceptance: `docs/specs/frontend-v1-criteria.yaml` (113 checks)
- DP mappings: `docs/design/design-principles.md` (referenced throughout)
- Mobile rules: `docs/design/frontend-v1-mobile.md`
- States catalogue: `docs/design/frontend-v1-states.md`
- Inner-loop / CONDUCTOR: `docs/design/frontend-inner-loop.md`
- Fixture schemas: `frontend/mockups/fixtures/schemas/*.json` (8 schemas, Draft-07)

## When to delete this directory

After V1-Frontend-Stage1 ships (S1-11 DONE + atlas.jslwealth.in
verified), this directory should be deleted in a single commit
with message "archive: remove V1FE pre-chunkmaster notes (ship done)".
The knowledge is by then captured in:
- The chunkmaster output `specs/<NNN-v1fe>/` (permanent)
- The wiki article produced by `/forge-compile` post-S1-11
- The actual shipped mockups under `frontend/mockups/`
