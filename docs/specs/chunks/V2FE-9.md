---
id: V2FE-9
title: "Integration gate: Playwright E2E + Lighthouse regression + API-standard + spec-coverage"
status: PENDING
estimated_hours: 3
deps: [V2FE-8]
gate_criteria:
  - tests/e2e/v2fe_*.spec.ts all pass (6 page specs + 1 backend spec)
  - Lighthouse LCP < 2.5s and CLS < 0.1 on all 6 pages (no regression vs V1 budget)
  - scripts/check-api-standard.py exits 0 (UQL + include + error shape compliance)
  - scripts/check-spec-coverage.py exits 0 (V2 criteria YAML registered + linked)
  - scripts/check-frontend-criteria.py exits 0 with critical_fail_count==0 (all V1 criteria preserved)
  - scripts/check-frontend-v2.py exits 0 with all 9 backend checks and all 6 page binding checks passing
  - Deterministic replay: two consecutive loads with same data_as_of return byte-identical _meta
---

## Objective

Run the complete V2FE integration gate. This chunk authors the Playwright E2E test suite in `tests/e2e/`, updates the `.quality/checks.py` frontend dimension to include V2 gate awareness, and verifies that all acceptance criteria from §8.1 through §8.5 pass in a live-backend smoke run. This is the DONE gate for the entire V2FE slice.

## Punch list

1. [ ] Author `tests/e2e/v2fe_backend.spec.ts` — backend API smoke tests (§8.1, 9 checks):
   - `zone-events` returns 200 + parses schema.
   - `global/events` returns 200.
   - `breadth/divergences` returns 200 + shape per §4.2.3.
   - `global/flows` returns 200 or empty + `insufficient_data:true`.
   - `query/template sector_rotation` returns ≥11 rows with `{sector_id, rs, rs_gold, conviction}`.
   - `query/template top_rs_gainers limit:10` returns exactly 10 rows ordered desc.
   - `query/template fund_1d_movers limit:5` returns 5 rows with `rs_composite + gold_rs_state`.
   - `query/template mf_rank_composite` parses against `mf_rank_universe.schema.json`.
   - Every V2 response carries `_meta` superset of `{data_as_of, source, staleness_seconds, includes_loaded}`.

2. [ ] Author `tests/e2e/v2fe_today.spec.ts` — Pulse page E2E:
   - Open `today.html` against live backend.
   - Wait for all `[data-endpoint]` blocks to reach `data-state=ready|stale` (timeout 15s).
   - Assert no `[data-state=error]` blocks (exempt `data-sparse=true` blocks from this assertion).
   - Assert `[data-role=sector-board]` has ≥11 rows.

3. [ ] Author `tests/e2e/v2fe_explore_country.spec.ts` — Country page E2E.
4. [ ] Author `tests/e2e/v2fe_breadth.spec.ts` — Breadth Terminal E2E; assert `[data-block=signal-history]` resolves to `ready|stale`.
5. [ ] Author `tests/e2e/v2fe_stock_detail.spec.ts` — Stock Detail E2E; assert hero block resolves for `HDFCBANK`.
6. [ ] Author `tests/e2e/v2fe_mf_detail.spec.ts` — MF Detail E2E; assert returns block resolves.
7. [ ] Author `tests/e2e/v2fe_mf_rank.spec.ts` — MF Rank E2E; assert rank-table resolves and has ≥10 rows.

8. [ ] **Lighthouse budget check** — add a Playwright Lighthouse step (using `playwright-lighthouse` or `@lhci/cli`) for each page:
   - LCP < 2.5s (pass/warn threshold).
   - CLS < 0.1.
   - Document results in `.forge/v2fe-lighthouse-report.json`.
   - The V2 loader MUST NOT regress Lighthouse by >200ms vs V1 baseline.

9. [ ] **Deterministic replay test** — add test that: (a) calls the same breadth endpoint twice within 1s, (b) asserts `_meta.data_as_of` is identical, (c) asserts `records` array is byte-identical (modulo `cache_hit` field). This verifies §2.5.

10. [ ] **Update `.quality/checks.py`** — add a V2FE sub-check under the `frontend` dimension that runs `scripts/check-frontend-v2.py` and contributes to the frontend dim score. Weight: same as a V1FE sub-check.

11. [ ] Run `scripts/check-api-standard.py` — must exit 0. If any V2FE-1 route missed the UQL/include/error standard, fix before declaring DONE.

12. [ ] Run `scripts/check-spec-coverage.py` — must exit 0. `frontend-v2-criteria.yaml` must be registered in the spec coverage map pointing to `ATLAS-DEFINITIVE-SPEC.md §15`.

13. [ ] Run full V1 gate: `scripts/check-frontend-criteria.py` across all 6 target pages + all other pages — must exit 0 with `critical_fail_count==0`.

14. [ ] Run `scripts/check-frontend-v2.py` — must exit 0 with all checks passing.

## Exit criteria

- `npx playwright test tests/e2e/v2fe_*.spec.ts` exits 0 (all E2E tests pass).
- `.forge/v2fe-lighthouse-report.json` exists; LCP < 2.5s and CLS < 0.1 on all 6 pages.
- `scripts/check-api-standard.py` exits 0.
- `scripts/check-spec-coverage.py` exits 0.
- `scripts/check-frontend-criteria.py` exits 0 with `critical_fail_count==0`.
- `scripts/check-frontend-v2.py` exits 0.
- `python .quality/checks.py` frontend dim ≥ 95 (V1FE target maintained).
- Deterministic replay test passes: two consecutive loads return identical `_meta.data_as_of` and `records`.

## Domain constraints

- Playwright E2E tests go in `tests/e2e/` (directory already scaffolded per git status `?? tests/e2e/`).
- E2E tests must run against the live backend (`http://localhost:8000` for local, `https://atlas.jslwealth.in` for CI). Provide `BASE_URL` environment variable.
- `data-sparse=true` blocks are exempt from `no [data-state=error]` assertion — they are expected to render empty-state.
- Rec-slots (`data-v2-deferred="true"`) and client-derived blocks (`data-v2-derived="true"`) are exempt from `data-state=ready` wait.
- The Lighthouse budget is from §8.4: LCP <2.5s, CLS <0.1. The loader cannot regress more than 200ms on any page — document delta vs V1 baseline.
- `scripts/check-spec-coverage.py` green requires `ATLAS-DEFINITIVE-SPEC.md §15` to have a cross-link to `frontend-v2-criteria.yaml`. Add the cross-link to the spec if missing (this is a doc edit, not a code change).
- No new backend services in this chunk. If a route is 404, that is a V2FE-1 defect — file a note and fix in V2FE-1 before declaring this chunk DONE.
