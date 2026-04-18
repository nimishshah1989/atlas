# Chunk V11-10 Approach — Coverage Close-out

## Summary

Pure tooling/gate chunk. No DB writes, no route changes, no schema changes.

## Problem statement

`scripts/check-data-coverage.py --strict --mandatory-only` exits non-zero because
mandatory domains contain tables with `status: gap`. These are known intentional gaps
(empty tables, not bugs). The checker faithfully scores them as 0 and exits 1.

Affected known-gap tables inside mandatory domains:
- `de_adjustment_factors_daily` in `corporate_actions` domain — `status: gap`, 0 rows
- `de_institutional_flows` in `institutional_flows` domain — `status: gap`, ~5 rows
- `atlas_gold_rs_cache` in `gold_lens` domain — domain `status: gap`, 0 rows

## Scale check

Not applicable. This chunk does not touch DB tables. Script is pure Python.

## Chosen approach

1. **Add `skip_gaps` parameter to `collect_tables()`** — when `mandatory_only=True`,
   default `skip_gaps=True` so gap-status tables and gap-status domains are excluded.
   Add `--no-skip-gaps` CLI flag to override. This is semantically clean:
   "mandatory and expected to be healthy".

2. **Add `status: gap` at domain level for `institutional_flows`** — currently only on
   the table. Domain-level status enables one-check skipping of the whole domain.

3. **Add sort for deterministic output** — `results.sort(key=lambda h: (h.domain, h.table))`
   before JSON write ensures three consecutive runs produce identical scores.

4. **Write 15+ unit tests in `tests/unit/test_data_coverage_checker.py`** — pure Python,
   no DB, covering skip_gaps behavior and compute_overall.

5. **Update CI** — replace conditional `if [ -n ... ]` with cleaner warning pattern.

## Wiki patterns checked

- **Importlib Isolation** — already used in existing `test_check_data_coverage_v11_1.py`.
  Will reuse same pattern for new test file.
- **No-Op DONE Guard** — spec requires explicit file-existence check before shipping.

## Existing code being reused

- `tests/unit/test_check_data_coverage_v11_1.py` — existing test file uses importlib
  pattern correctly. New test file follows same structure.
- `collect_tables()`, `compute_overall()`, `expand_partitioned_tables()` — synchronous
  functions already in the script, safe to import and test directly.

## Edge cases

- `gold_lens` domain has `status: gap` at domain level — skip whole domain when
  `skip_gaps=True`.
- `corporate_actions` domain has mixed tables: `de_corporate_actions` (healthy) and
  `de_adjustment_factors_daily` (gap). When `skip_gaps=True`, only the gap table is skipped;
  the healthy table continues to be checked.
- `institutional_flows` domain: currently only `status: gap` on the table, not domain.
  Add domain-level status too for belt-and-suspenders.
- `global_rates` domain has no `tables:` key — `collect_tables()` returns nothing for it.
  No change needed.
- Sort before JSON write: ensures idempotency across runs.

## Expected runtime

- Tests: <5s (no DB, pure computation)
- Full `--strict --mandatory-only` run with DB: ~30s on t3.large (was failing before)

## Files modified

- `scripts/check-data-coverage.py` — add `skip_gaps` parameter, sort results
- `docs/specs/data-coverage.yaml` — add `status: gap` to `institutional_flows` domain
- `tests/unit/test_data_coverage_checker.py` — NEW, 15+ tests
- `.github/workflows/ci.yml` — cleaner DATABASE_URL guard
