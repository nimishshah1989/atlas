# S1-11: QA sweep — Playwright baselines + full-gate pass + design review

**Slice:** V1-Frontend-Stage1
**Depends on:** S1-0..S1-10 all DONE
**Blocks:** V1-Frontend-Stage1 ship
**Complexity:** M (6 hours)
**Inherits:** docs/specs/chunks/s1-common.md
**Quality targets:** code: 90, architecture: 90, frontend: 95, security: 90

## Step 0 — Boot context

Same as s1-common.md, plus:
- `cat docs/design/frontend-inner-loop.md` — three-reviewer pipeline
- `cat .forge/frontend-report.json` — last S1-10 gate output
- Every page chunk's Points-of-Success list, verified individually

## Page-specific goal

No new pages. Ship three things:
1. Baseline Playwright screenshots for every page at 1440 / 1200 / 960 /
   640 / 360 viewports → checked into `frontend/mockups/.baselines/`
2. a11y sweep — axe-core against every page, zero serious/critical
   violations
3. Full-harness green: `scripts/check-frontend-criteria.py --criteria
   docs/specs/frontend-v1-criteria.yaml` exits 0 with zero critical
   failures across **all** 113 criteria

Also: wire `.quality/checks.py` to require this green state before V1
frontend ships.

## Files

### New
- `frontend/mockups/.baselines/*.png` — 5 viewports × 10 pages = 50 files
- `scripts/capture-fe-baselines.py` — one-shot baseline generator
- `scripts/check-fe-a11y.py` — wraps Playwright+axe-core
- `tests/e2e/fe_pages/test_all_pages_a11y.py`
- `tests/e2e/fe_pages/test_all_pages_screenshot_baseline.py`

### Modified
- `.quality/checks.py` — frontend dimension: require
  `.forge/frontend-report.json.totals.critical_fail_count == 0`
- `orchestrator/plan.yaml` — Stage-1 rows flip to DONE **only** after
  this chunk DONE-stamps

## Tests (≥ 12)

1..10. Per-page a11y: zero serious/critical violations at 1440px
11. Every baseline file ≥ 20kB (guards empty screenshots)
12. Full-harness rerun exits 0; report shows 113/113 pass (or only
    `high`/`medium` fails with explicit ADR exemption)

## Points of success (all required for DONE)

1. `python scripts/check-frontend-criteria.py` exits 0
2. `python scripts/check-fe-a11y.py` exits 0
3. `pytest tests/e2e/fe_pages/ -v` green
4. All 50 baseline screenshots committed, bit-exact on rerun (determinism)
5. Design-reviewer agent pass (per frontend-inner-loop.md) — no Sev-1/Sev-2
6. Code-reviewer agent pass — no Sev-1
7. `.quality/checks.py` full-gate shows frontend dim ≥ 95
8. Smoke probe: `curl -sf https://atlas.jslwealth.in/mockups/index.html | grep -q "ATLAS"` — green

## Post-chunk sync invariant

`scripts/post-chunk.sh S1-11` green. MEMORY.md entry
`project_v1_frontend_stage1_ship.md` capturing: 10 pages, 113 checks,
all green, baseline screenshots, a11y pass, date shipped.

This is the chunk that ends V1-Frontend-Stage1.
