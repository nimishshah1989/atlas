# ATLAS V1 Gap Analysis

**Date:** 2026-04-13
**Method:** Spec extraction (ATLAS-DEFINITIVE-SPEC.md §4, §11, §23, §24.2, §24.3) vs live code inventory vs live endpoint probes vs quality gates (ruff/mypy/pytest) vs deployed backend on :8010.
**Verdict:** V1 is **~75% built**. Vertical slice is navigable end-to-end, latency budgets are met, but several spec-level deliverables are missing or drifted. V1 is **NOT** 100% complete.

---

## 1. Live quality gates

| Gate | Result | Notes |
|---|---|---|
| Backend service | PASS | `atlas-backend.service` active on :8010, git_sha b14b4212 |
| `ruff check backend/ --select E,F,W` | **FAIL — 27 errors** | Mostly E501 line length, incl. docstring at `backend/core/computations.py:43` that still says "4 conviction pillars" (code only builds 3 — see §4) |
| `mypy backend/ --ignore-missing-imports` | **FAIL — 1 error** | `backend/main.py:48` — slowapi `RateLimitExceeded` handler signature mismatch |
| `pytest tests/ -q` | **FAIL — 3/145 failing** | All 3 in `tests/test_orchestrator.py` (plan validation, dry-run, boot-context). Not V1-functional, but gates the release. |
| V1 endpoint latency (universe) | PASS | 204 ms vs 2000 ms budget |
| V1 endpoint latency (deep-dive) | PASS | 158 ms vs 500 ms budget |
| No `float(` in `backend/core/` or `backend/routes/` | PASS | All monetary values `Decimal(str(...))` |

---

## 2. V1 spec deliverables → build status

Legend: ✅ done · 🟡 partial / drifted · ❌ missing

### 2.1 API endpoints (spec §11, §24.2)

| Endpoint | Spec | Built | Live | Gap |
|---|---|---|---|---|
| `GET /api/v1/stocks/universe` | ✅ | ✅ | 200 / 204 ms | none |
| `GET /api/v1/stocks/sectors` | ✅ | ✅ | 200 / 186 ms | 31 sectors, 23 keys — OK |
| `GET /api/v1/stocks/breadth` | ✅ | ✅ | 200 / 20 ms | none |
| `GET /api/v1/stocks/{symbol}` | ✅ | ✅ | 200 / 158 ms | conviction pillars drifted (§4) |
| `GET /api/v1/stocks/{symbol}/rs-history` | ✅ | ✅ | 200 / 26 ms | none |
| `GET /api/v1/stocks/{symbol}/mf-holders` | ✅ | 🟡 | **404** | Route not registered. `JIPDataService.get_mf_holders()` exists but is not wired into `backend/routes/stocks.py`. |
| `POST /api/v1/query` (UQL) | ✅ | 🟡 | **422** | Contract drift: route expects filter key `op`, spec + client-facing contract uses `operator`. Rename in `backend/models/schemas.py` UQLFilter or accept both. |
| `GET /api/v1/status` | ✅ | 🟡 | 200 / 22 ms / 268 B | Too thin. Spec §16.5 requires `equity_ohlcv_as_of`, `rs_scores_as_of`, `breadth_as_of`, `regime_as_of`, `pipeline_last_run`, `anomaly_count`. Verify fields present. |
| `GET /api/v1/decisions` + `PUT /api/v1/decisions/{id}/action` | ✅ | ✅ | 200 (empty list) | endpoint fine; **no decision generation pipeline** — see §2.4 |

### 2.2 Contracts (spec §0, §15)

- ❌ **No `contracts/` package.** Spec mandates contracts-first in a top-level `contracts/` directory (CLAUDE.md key file locations). Everything lives in `backend/models/schemas.py`. This blocks the "frontend imports from contracts" workflow and is a structural V1 miss.
- 🟡 **UQLFilter field name** drifted (`op` vs `operator`).
- 🟡 **StockUniverseResponse `_meta`** — verify provenance `_meta` block (sources, formula, data_as_of, staleness) is attached per spec §16.3.

### 2.3 Computations (spec §4)

| Computation | Spec | Built | Gap |
|---|---|---|---|
| RS momentum (T − T-28d) | ✅ | ✅ | `backend/core/computations.py` |
| Quadrant (LEADING/IMPROVING/WEAKENING/LAGGING) | ✅ | ✅ | `compute_quadrant()` — sign-based, matches spec §4.2 |
| Sector rollup | 22 metrics | 23 fields | Field count matches (close enough). **Verify `stock_count` sum** — live sums to **2,431**, spec target "~2,700". BUILD_STATUS explains: 312 stocks have no sector mapping. This is a **data-quality gap**, not a compute bug. Needs explicit "unmapped" bucket or JIP-side fix. |
| Conviction pillars | **4 pillars** (RS, Technical, External/Macro, Institutional) | **3 pillars** (RS, Technical, Institutional) | ❌ **External/Macro pillar missing.** Spec §4.8 requires macro context pillar (regime, breadth, global RS). Code comment at `backend/core/computations.py:43` still claims "4 pillars" — lying docstring. |
| MF holder count | ✅ | 🟡 | Computation in service layer, endpoint 404. |
| Index breadth (equal-weighted) | ✅ | ❓ | Not surfaced in any V1 route. Verify whether breadth endpoint pulls from JIP or computes. |

### 2.4 Decision system (spec §23, §24.3 criterion "≥5 decisions per pipeline run")

- ✅ `atlas_decisions` table exists (baseline migration).
- ✅ `GET /decisions` + `PUT /decisions/{id}/action` endpoints work.
- ❌ **No decision-generation pipeline.** Live `/decisions` returns `[]`. Spec §23 + §24.3 requires decisions auto-generated from quadrant transitions and rotation signals, ≥5 per pipeline run. There is no cron, no pipeline runner, no `generate_decisions()` call chain. **This is the single biggest V1 gap.**
- ❌ **No invalidation lifecycle.** Spec §23.2–23.5 requires decisions to transition to `invalidated` when invalidation_conditions are met. Not implemented.

### 2.5 Database tables (spec Appendix A)

| Table | Spec | Built | Gap |
|---|---|---|---|
| `atlas_decisions` | ✅ | ✅ | schema matches |
| `atlas_intelligence` (pgvector) | ✅ | ✅ | table exists; **no findings being written** — spec §24.3 requires ≥10 findings after first pipeline run |
| `atlas_watchlists` | ✅ | ✅ | |
| `atlas_alerts` | ✅ | ❌ | not in migration |
| `atlas_tv_cache` | ✅ (structure only in V1) | ❌ | not in migration |
| `atlas_agent_scores` | ✅ (structure only) | ❌ | not in migration |
| `atlas_agent_weights` | ✅ (structure only) | ❌ | not in migration |

### 2.6 Architecture — JIP isolation (spec §3, CLAUDE.md "ATLAS NEVER queries de_* tables directly")

- ❌ **Hard architecture violation.** `JIPDataService` (`backend/clients/jip_data_service.py`) queries `de_*` tables via direct SQL. Spec + CLAUDE.md require ATLAS to go through JIP `/internal/*` HTTP API so schema changes are absorbed by an abstraction layer. The facade class name pretends to be a client but is actually a repository.
- Impact: any JIP schema change (and we've already had spec-v2-was-wrong incidents) ripples straight into ATLAS.
- Fix path: either stand up the JIP `/internal/*` service on the JIP EC2 and rewrite `JIPDataService` as an HTTP client, or formally amend CLAUDE.md to accept the facade as the abstraction boundary. **Decision needed from user.**

### 2.7 Frontend — Pro shell (spec §12, §24.2)

- ✅ `frontend/src/app/page.tsx` Market → Sector → Stock → Deep-dive navigation works, breadcrumbs present.
- ✅ Components: MarketOverview, SectorTable, StockTable, DeepDivePanel, DecisionPanel.
- 🟡 **DeepDivePanel shows 3 pillars** (since backend returns 3). Missing External/Macro pillar UI.
- ❓ **Not browser-verified in this audit.** Per Four Laws ("See what you build"), a QA pass via `/qa` is required before calling V1 done.
- ❓ `/pro/status` page — unverified.

### 2.8 Tests (spec §15, §24.3 "integration tests ALL passing")

- ✅ `tests/integration/test_v1_endpoints.py` exists, covers health/status/breadth/sectors/universe.
- ❌ **No test for `/stocks/{symbol}` deep-dive response shape.**
- ❌ **No test for `/stocks/{symbol}/mf-holders`** (and it's 404 in prod, so a test would catch this).
- ❌ **No test for `/query` UQL** (and it's 422 in prod).
- ❌ **No test for decision generation.**
- ❌ **No Playwright / frontend test** per spec §15 line 2125-2136 `test_frontend.py`.
- ❌ 3 orchestrator tests failing — unrelated to V1 product, but blocks "ALL passing" criterion.

---

## 3. V1 completion criteria scorecard (spec §24.3)

| # | Criterion | Status | Evidence |
|---|---|---|---|
| 1 | `/stocks/universe` returns valid data matching contract | ✅ | 200 / 204 ms / 224 KB |
| 2 | `/stocks/sectors` returns 31 sectors × 22 metrics | ✅ | 31 sectors, 23 keys |
| 3 | `/stocks/{symbol}` returns deep-dive | 🟡 | works, but only 3/4 pillars |
| 4 | `/query` handles basic equity queries | ❌ | 422 contract drift |
| 5 | FM navigates Market → Sector → Stock | 🟡 | present, not browser-verified |
| 6 | Deep-dive shows all conviction pillars | ❌ | 3/4 |
| 7 | ≥5 decisions per pipeline run | ❌ | no pipeline, table empty |
| 8 | FM accept/ignore/override decisions | ✅ | endpoint wired |
| 9 | Sector `stock_count` sums to ~2,700 | 🟡 | sums to 2,431 (312 unmapped) |
| 10 | RS momentum matches manual calc | ❓ | no verification test on record |
| 11 | `pct_above_200dma` matches raw SQL | ❓ | no verification test on record |
| 12 | Intelligence engine ≥10 findings stored | ❌ | no findings pipeline |
| 13 | Integration tests all passing | ❌ | 3 failing + missing coverage |
| 14 | No float in financial calcs | ✅ | clean grep |
| 15 | Response times: universe <2 s, deep-dive <500 ms | ✅ | 204 ms / 158 ms |

**Score: 6 ✅ · 4 🟡 · 5 ❌  →  ~60% of spec criteria strictly met, ~75% if partials count as half.**

---

## 4. Gap remediation — chunks to run before V2

Proposed forge-build chunks, in dependency order:

**G1 — Contract hygiene & quality gates green** *(smallest, unblocks everything)*
- Fix 27 ruff E501 violations (`backend/core/computations.py`, `backend/routes/query.py`, etc.)
- Fix mypy slowapi handler typing in `backend/main.py:48`
- Fix 3 orchestrator test failures OR mark them out of V1 scope
- Acceptance: `ruff`, `mypy`, `pytest tests/` all green in CI

**G2 — UQL contract drift**
- Rename `UQLFilter.op` → `operator` (or accept alias) so POST `/query` matches spec contract
- Add integration test for POST `/query` happy path + 2 filter combos
- Acceptance: live 200 response with real filtered rows

**G3 — MF holders endpoint**
- Wire `JIPDataService.get_mf_holders()` into `backend/routes/stocks.py`
- Response schema + integration test
- Acceptance: `/stocks/TCS/mf-holders` returns 200 with MF list

**G4 — 4th conviction pillar (External/Macro)**
- Add `PillarMacro` model: regime confidence, breadth pct_above_200dma, global RS context
- Update `build_conviction_pillars()` in `backend/core/computations.py` to emit 4 pillars
- Update `DeepDivePanel.tsx` to render new pillar
- Fix the lying docstring on line 43
- Acceptance: `/stocks/{symbol}` returns 4 pillars, frontend renders all 4

**G5 — Decision generation pipeline** *(biggest chunk)*
- `backend/core/decision_engine.py`: detect quadrant transitions (today vs yesterday), rotation signals, emit `DecisionObject` rows
- Runner: scheduled job (cron or on-demand endpoint) that populates `atlas_decisions`
- Invalidation lifecycle: compare current market state vs `invalidation_conditions`, flip status
- Acceptance: one pipeline run produces ≥5 decisions; `/decisions` returns non-empty; aging test flips one to `invalidated`

**G6 — Intelligence findings seed**
- At least one agent (sector-analyst or rs-analyzer) writing to `atlas_intelligence` with embeddings
- Acceptance: ≥10 findings after one pipeline run (spec §24.3 #12)

**G7 — `/status` freshness fields**
- Populate `equity_ohlcv_as_of`, `rs_scores_as_of`, `breadth_as_of`, `regime_as_of`, `pipeline_last_run`, `anomaly_count`
- Add `_meta` provenance block to universe + deep-dive responses (spec §16.3)
- Acceptance: status response contains all 6 fields with live timestamps

**G8 — Missing atlas_* tables**
- Alembic migration adding empty-structure `atlas_alerts`, `atlas_tv_cache`, `atlas_agent_scores`, `atlas_agent_weights` (V1 doesn't use them but spec requires schemas in place for V2–V5)
- Acceptance: migration applied, tables present

**G9 — Test coverage to hit "ALL passing"**
- Integration tests for `/stocks/{symbol}`, `/stocks/{symbol}/mf-holders`, `/query`
- Unit tests: RS momentum vs manual SQL (spec §24.3 #10), pct_above_200dma vs raw SQL (#11)
- Playwright smoke test for Pro shell navigation (spec test_frontend.py)
- Acceptance: `pytest tests/ -v` green, coverage ≥80% on new code

**G10 — Browser QA via `/qa`**
- Run `/qa` against localhost:3000 frontend + :8010 backend
- Fix any bugs found with atomic commits + regression tests
- Acceptance: Four Laws "See what you build" satisfied

**G11 — Sector `stock_count` gap** *(decide-then-build)*
- Either add "Unmapped" sector bucket so sum hits ~2,743, OR document the 312-stock gap and accept 2,431 as the real V1 universe
- Needs user decision before implementation

**G-ARCH — JIP `/internal/*` architecture decision** *(block or accept)*
- User call: either build the JIP `/internal/*` HTTP layer and rewrite `JIPDataService` as an HTTP client (large, multi-day), OR amend CLAUDE.md to make `JIPDataService` the blessed abstraction boundary
- **Do not start V2 without resolving this** — V2 (MF slice) will double down on whichever side wins

---

## 5. Recommended order of operations

1. **User decisions first:** G-ARCH (JIP API yes/no), G11 (unmapped stocks).
2. **Quick wins in one session:** G1 + G2 + G3 + G7 (all small, unblock tests and the "valid contract" criteria).
3. **Spec-correctness session:** G4 (4th pillar).
4. **Big chunk:** G5 (decision pipeline) + G6 (intelligence findings) — these together satisfy criteria #7 and #12.
5. **Schema hygiene:** G8.
6. **Gate close:** G9 (tests) + G10 (browser QA).
7. Only after all above green → open V2 (MF slice).

**Estimated effort:** G1–G4, G7, G8 are ~1 chunk each. G5+G6 is ~2–3 chunks. G9+G10 is ~1 chunk. Total ≈ **8–10 chunks** before V2 is safe to start.
