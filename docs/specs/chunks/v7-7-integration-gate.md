# V7-7: Integration gate — check-api-standard + 7-dim gate + no-mocks + final sync

**Slice:** V7
**Depends on:** V7-2, V7-3 (backend-only slice — frontend V7-4/5/6 deferred)
**Blocks:** (closes the slice)
**Complexity:** S (2–3 hours)
**Quality targets:** all 7 dims ≥ 80

---

## Step 0 — Boot context

1. `cat CLAUDE.md`
2. Memory: `project_v15_chunk_status.md`
3. Read `specs/014-v7-etf-global-goldrs/spec.md §SC-001..010`, `checklists/constitution.md`
4. Review `scripts/check-api-standard.py` and `.quality/checks.py`

## Goal

Close the V7 slice. No new features — only integration tests + gate enforcement + final sync.

## Files

### New
- `tests/integration/test_v7_end_to_end.py` ≥ 8 tests — hits all 7 new routes against real DB snapshot, no mocks.

### Modified (light touch)
- `scripts/check-api-standard.py` — extend allowlist if needed
- `.quality/checks.py` — extend coverage scope if needed

## Punch list

1. `python scripts/check-api-standard.py` exits 0 across all 7 new routes (`/api/etf/universe`, `/api/etf/{t}`, `/api/etf/{t}/chart-data`, `/api/etf/{t}/rs-history`, `/api/global/ratios`, `/api/global/rs-heatmap`, `/api/global/indices`).
2. `pytest tests/integration/test_v7_end_to_end.py -v` — all tests green.
3. `python .quality/checks.py` — 7-dim gate ≥ 80 for security / code / architecture / api / backend / product. `frontend` dim: n/a pass (backend-only slice; frontend chunks V7-4/5/6 deferred to a later run).
4. `grep -rn "float(" backend/services/gold_rs_service.py backend/services/etf_service.py backend/services/global_service.py` returns empty (Decimal only).
5. Backend portion of SC-001..SC-010 success criteria measurable and met (SC-008 frontend page render is deferred).

## Integration tests (≥8)

1. `test_etf_universe_end_to_end` — real JIP data, ≥100 rows, Decimal types, no duplicates.
2. `test_etf_detail_with_gold_rs_opt_in` — `include=gold_rs` produces full block.
3. `test_etf_chart_data_1y_window`.
4. `test_etf_rs_history_12m`.
5. `test_global_ratios_nine_series_live`.
6. `test_global_rs_heatmap_131_instruments_live`.
7. `test_global_indices_four_bench_verdict_end_to_end`.
8. `test_gold_rs_cache_hit_path` — first call computes + upserts, second call hits Redis, assertions on cache_status log field.

## Post-chunk sync (final)

`scripts/post-chunk.sh V7-7` — final sync closes the V7 slice:
- commit+push via forge-ship.sh
- restart atlas-backend.service
- smoke probe on all 7 routes
- /forge-compile knowledge wiki
- MEMORY.md append with "V7 slice COMPLETE"

Update `~/.claude/projects/-home-ubuntu-atlas/memory/project_v15_chunk_status.md` with V7 DONE status.
