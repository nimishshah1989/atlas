# Chunk V5-6 Approach — LLM Cost Ledger Budget Enforcement

## Data Scale
- `atlas_cost_ledger`: append-only, probably <1K rows in dev. Rolling 24h window query: simple SUM with WHERE clause — well within SQL territory.
- `atlas_alerts`: new table, 0 rows initially.

## Chosen Approach
- SQL for rolling window SUM: `SELECT COALESCE(SUM(cost_usd), 0) FROM atlas_cost_ledger WHERE created_at >= NOW() - INTERVAL '24 hours' AND is_deleted = FALSE`
- Python computes Decimal arithmetic for remaining budget
- `BudgetStatus` as a dataclass (NamedTuple-style but mutable)
- Budget check inserted at top of `record_llm_call` — before any DB write
- Alert write is a fire-and-separate-flush operation

## Wiki Patterns Checked
- `Budget-Aware API Integration`: Two-layer gate — hard check at entry, this aligns perfectly
- `AsyncMock Context Manager Pattern`: Used for mock DB `execute().scalar_one_or_none()` — need `execute_result = MagicMock(); execute_result.scalar_one_or_none.return_value = X; db.execute = AsyncMock(return_value=execute_result)`
- `Decimal Not Float`: All financial values Decimal, never float
- `Alembic Mypy attr-defined`: `# type: ignore[attr-defined]` on alembic op/context imports

## Existing Code Reused
- `backend/db/models.py`: `AtlasCostLedger` pattern (BigInteger PK, Numeric(20,4) for money)
- `alembic/versions/a8b9c0d1e2f3_v5_10a_cost_ledger.py`: existing migration pattern for down_revision
- `tests/services/test_intelligence.py`: mock DB pattern for SQLAlchemy async

## Edge Cases
- NULL cost_usd SUM when no rows in window → COALESCE to 0
- Zero-value total cost → `Decimal("0")` not falsy check
- Budget exactly at $2.00 → "at" status, NEXT call raises (not this one)
- Concurrent writes → alert is best-effort (no lock needed; budget check is advisory)
- `atlas_alerts` write failure → log but don't mask the BudgetExhaustedError

## Files Modified
1. `backend/db/models.py` — add `AtlasAlert` class (BIGSERIAL PK, per spec DDL)
2. `alembic/versions/b1c2d3e4f5g6_v5_6_atlas_alerts.py` — new migration, down_revision = "a8b9c0d1e2f3"
3. `backend/services/cost_ledger.py` — add budget constants, `BudgetStatus`, `BudgetExhaustedError`, `get_rolling_window_cost`, `check_budget`, `_write_budget_alert`; modify `record_llm_call`
4. `tests/services/test_cost_ledger.py` — 5 test scenarios with mocked DB

## Expected Runtime
- Rolling window query: <5ms on indexed `created_at` column (note: needs index added in migration)
- Python budget check: microseconds
- Overall overhead per LLM call: negligible

## Migration filename note
Spec says `b1c2d3e4f5g6` — using exact string per spec. This is a non-standard alembic revision ID but matches spec convention.
