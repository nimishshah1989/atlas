---
id: V2FE-1c
title: "Backend: UQL templates + conviction_series include extension"
status: PENDING
estimated_hours: 3
depends_on: [V2FE-1b]
gate_criteria:
  code: 80
  test: 80
---

## Objective

Add the UQL query templates consumed by stock-detail, mf-detail, and mf-rank pages, plus the
`conviction_series` include extension for MF weighted-technicals.

## Punch list

- [ ] Register UQL templates in the shared UQL service (wherever existing templates live):
  - `stock_peers` — finds stocks in same sector+industry with similar market cap band; params: `symbol`, `limit` (default 10)
  - `mf_rank_composite` — 4-factor MF rank (Returns/Risk/Resilience/Consistency); params: `category`, `period` (1y/3y/5y), `limit` (default 50)
  - `sector_breadth_template` — % stocks above 50MA and 200MA per sector; params: `universe` (default nifty500)
  - Read existing template registration pattern first — match it exactly. Do NOT create new route handlers; templates go through the shared `POST /query/template` route.
- [ ] Add `include=conviction_series` to `GET /api/v1/mf/{id}/weighted-technicals`
  - `conviction_series`: last 12 months of weekly conviction score (0–100) as time series
  - Only loaded when `include=conviction_series` is in query string
  - Reads from existing `atlas_gold_rs_cache` or `atlas_conviction_scores` if available; returns `[]` if not yet populated
  - Follow spec §18 include system pattern exactly
- [ ] Tests:
  - `tests/api/test_uql_templates.py` — test each template: valid params → 200, missing required param → 422, unknown template → 404
  - `tests/api/test_mf_weighted_technicals_include.py` — test `include=conviction_series` adds the field; test without include omits it
- [ ] Run `check-api-standard.py` — must pass

## Exit criteria

- `POST /query/template` with `{"template": "stock_peers", "params": {"symbol": "RELIANCE"}}` returns 200 with data array
- `POST /query/template` with `{"template": "mf_rank_composite", "params": {"category": "Large Cap"}}` returns 200
- `POST /query/template` with `{"template": "sector_breadth_template", "params": {}}` returns 200
- `GET /api/v1/mf/123/weighted-technicals?include=conviction_series` includes `conviction_series` key in response
- All tests pass. `check-api-standard.py` passes.

## Domain constraints

- UQL templates MUST go through shared `POST /query/template` — never new route handlers (spec §17)
- `include=` system: spec §18 pattern — loaded only when requested, never by default
- `Decimal` not `float` for all computed values
- Fault-tolerant: templates return `data: []` if JIP source is empty, never 500
