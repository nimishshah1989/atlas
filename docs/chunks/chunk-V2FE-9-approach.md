---
chunk: V2FE-9
project: atlas
date: 2026-04-19
status: in-progress
---

## Objective

Integration gate for the entire V2FE slice. Author Python-based E2E tests,
add a V2FE sub-check to `.quality/checks.py`, create a Lighthouse scaffold,
and ensure `scripts/check-spec-coverage.py` remains green.

## Data scale check

No new data tables. This chunk is test/gate only.

## Approach

### E2E test files

All tests go in `tests/e2e/` alongside `tests/e2e/fe_pages/`.
Use `.py` extension (pytest-playwright, not TypeScript).
Pattern from `tests/e2e/fe_pages/test_mockup_pages.py`:
- `playwright.sync_api` for page E2E tests (file:// URL)
- `requests` for backend API smoke tests with SKIP-on-ConnectionError
- All tests SKIP gracefully when backend/browser unreachable

Files to create:
1. `tests/e2e/v2fe_backend.spec.py` — 9 backend smoke checks + deterministic replay
2. `tests/e2e/v2fe_today.spec.py` — Pulse page E2E
3. `tests/e2e/v2fe_explore_country.spec.py` — Country page E2E
4. `tests/e2e/v2fe_breadth.spec.py` — Breadth Terminal E2E
5. `tests/e2e/v2fe_stock_detail.spec.py` — Stock Detail E2E
6. `tests/e2e/v2fe_mf_detail.spec.py` — MF Detail E2E
7. `tests/e2e/v2fe_mf_rank.spec.py` — MF Rank E2E
8. `tests/e2e/v2fe_lighthouse.py` — Lighthouse budget scaffold

### .quality/checks.py update

Add check `5.11` under `dim_frontend()` that runs `scripts/check-frontend-v2.py`
and reads the resulting `.forge/frontend-v2-report.json`. Weight: 30 pts max
(same as 5.10 frontend criteria gate approach but V2-specific).

### Lighthouse scaffold

Create `.forge/v2fe-lighthouse-report.json` with LCP/CLS budget thresholds.
Since Lighthouse can't run in this environment, create a static scaffold
with `not_measured` status and budget thresholds documented.

### spec-coverage

`scripts/check-spec-coverage.py` already PASSES (§11, §17, §18, §20, §24 covered).
The spec says §15 needs a cross-link to `frontend-v2-criteria.yaml`.
The `frontend-v2-criteria.yaml` currently has no `source_spec_section` fields.
The mandatory set doesn't include §15 — so this is informational only.
Adding `source_spec_section: "§15"` to one criterion in `frontend-v2-criteria.yaml`
would link it, but §15 is not mandatory, so the gate already passes.
We will add the cross-link anyway per spec requirement.

## Wiki patterns checked

- `static-html-mockup-react-spec` (12x) — V2FE binding contract
- `runner-report-json-contract` (3x) — runner writes `.forge/<slice>-report.json`
- `void-sentinel-regex-parser-dom` (16x) — page E2E uses file:// tests
- `sys-executable-vs-bare-python3-subprocess` — use sys.executable not python3

## Existing code being reused

- `tests/e2e/fe_pages/conftest.py` — `browser`, `page`, `mockup_dir` fixtures
  (already available via conftest.py in tests/e2e/fe_pages/)
- `scripts/check-frontend-v2.py` — runner that produces frontend-v2-report.json
- Pattern: `.quality/checks.py` dim_frontend() with sub-checks

## Edge cases

- Backend unreachable: all backend tests SKIP (not FAIL)
- Playwright not installed: page tests SKIP
- file:// XHR blocked: page tests assert DOM structure, not data-state=ready
  (data-state transition requires live backend fetch which file:// cannot do)
- Pre-existing V1FE failures in check-frontend-criteria.py: these are known;
  the V2FE quality gate sub-check uses check-frontend-v2.py (not V1FE)

## Expected runtime

< 30 seconds on t3.large (2 vCPU, 8GB RAM) with all tests skipping.
With backend live: < 60 seconds total.
