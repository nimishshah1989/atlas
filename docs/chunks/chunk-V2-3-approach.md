---
chunk: V2-3
project: atlas
date: 2026-04-14
title: MF computations — RS momentum + quadrant + manager alpha
---

# Approach: V2-3 MF Computations

## Actual data scale

- `de_rs_scores` total rows: 14,779,545
- `de_rs_scores` MF rows only: 3,009,018
- Distinct MF entity_ids: 841
- Date range: 2016-04-18 to 2026-04-09
- Scale category: 100K–1M MF rows → SQL aggregation required, not Python loop

## Chosen approach

**Batch SQL CTE (RS_MOMENTUM_SQL)** for the computation, not per-fund Python loop.

With 841 funds and 3M+ rows in de_rs_scores, an N+1 approach (one query per fund)
would require 841 round-trips. The batch CTE uses two DISTINCT ON sub-selects
(latest + 28-day-ago) and a single LEFT JOIN, returning one row per fund.
This runs in ~1s on the DB instead of potentially 10+ seconds for N+1.

The `compute_rs_momentum_28d` function operates on pre-loaded RS history rows
(already fetched by JIP client), so it is pure Python Decimal arithmetic —
no additional DB calls.

## Wiki patterns checked

- `pure-computation-agent.md` — agent reads via service, all Decimal, no LLM
- `decimal-not-float.md` — always str→Decimal conversion, never float
- `sql-window-computation.md` — use DISTINCT ON pattern (already in codebase)

## Existing code being reused

- `backend/clients/sql_fragments.py:safe_decimal()` — Decimal conversion at boundary
- `backend/models/schemas.py:Quadrant` — canonical enum (NOT rs_analyzer.Quadrant)
- `backend/clients/jip_mf_service.py:_decimalize()` — row→dict with Decimal fields
- DISTINCT ON pattern from FUND_DETAIL_SQL and UNIVERSE_SQL — same pattern for RS batch

## Edge cases

- NULL rs_composite in de_rs_scores: `safe_decimal` returns None; functions return None
- Fund with <28 days RS history: past CTE LEFT JOIN returns NULL → None momentum
- Fund with no RS scores at all: LEFT JOIN returns NULL → None for both fields
- Boundary: rs_composite == 0 treated as negative (spec §4.2 uses strict >)
- Empty universe: `compute_universe_metrics` returns empty list gracefully

## Expected runtime on t3.large

- RS_MOMENTUM_SQL batch query: ~500–800ms (3M rows, indexed on entity_id+date)
- Pure Python `enrich_fund_with_computations` per fund: <1ms (trivial arithmetic)
- Full 841-fund enrichment: ~1s total (batch SQL + trivial Python)

## Files to modify

1. `backend/services/mf_compute.py` — NEW computation module
2. `backend/clients/jip_mf_sql.py` — EDIT: add RS_MOMENTUM_SQL + decimal fields
3. `backend/clients/jip_mf_service.py` — EDIT: add get_mf_rs_momentum_batch()
4. `tests/services/test_mf_compute.py` — NEW tests (50 fund fixture, 10 exact Decimal)
</content>
</invoke>