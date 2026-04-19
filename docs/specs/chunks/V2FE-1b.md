---
id: V2FE-1b
title: "Backend: global events + flows endpoints + atlas_key_events migration"
status: PENDING
estimated_hours: 3
depends_on: [V2FE-1a]
gate_criteria:
  code: 80
  test: 80
---

## Objective

Add global events feed and FII/DII flows endpoints, plus the `atlas_key_events` table.

## Punch list

- [ ] Create Alembic migration: `atlas_key_events` table
  - Columns: `id UUID PK`, `event_date DATE NOT NULL`, `event_type VARCHAR(50)`, `title VARCHAR(255)`, `description TEXT`, `source VARCHAR(100)`, `created_at TIMESTAMPTZ`, `updated_at TIMESTAMPTZ`
  - Index on `event_date`. No FK to `de_*` tables.
  - Run `alembic upgrade head` to verify migration applies cleanly.
- [ ] Create `backend/services/event_marker_service.py`
  - `get_events(start_date: date, end_date: date) -> list[KeyEvent]`
  - Reads from `atlas_key_events` (own table). Reads from `de_corporate_actions` via JIP for earnings/dividends.
  - Returns merged, sorted list with `source` field on each event.
- [ ] Create `backend/services/flows_service.py`
  - `get_fii_dii_flows(lookback_days: int = 90) -> FlowsSummary`
  - Reads `de_fii_dii_activity` via JIP client.
  - Returns: daily series + 30d/90d cumulative totals. All values `Decimal` (crore).
- [ ] Add `backend/routes/global_.py` (new file — note underscore to avoid `global` keyword)
  - `GET /api/v1/global/events` — params: `start_date`, `end_date` (ISO date strings, Optional)
  - `GET /api/v1/global/flows` — params: `lookback_days: Optional[int] = 90`
  - Both: `_meta` envelope with `data_as_of`, `staleness_seconds`, `source`
  - Register router in `backend/main.py`
  - Read spec §17 + §18 + §20 before writing routes. Run `check-api-standard.py`.
- [ ] Tests: `tests/api/test_global_events.py`, `tests/api/test_global_flows.py`
  - Test empty atlas_key_events → returns `data: []` not error
  - Test sparse FII/DII data → `insufficient_data: true` in `_meta`

## Exit criteria

- `GET /api/v1/global/events` returns 200 with `data` array + `_meta`
- `GET /api/v1/global/flows` returns 200 with cumulative totals + daily series + `_meta`
- Alembic migration applies cleanly: `alembic upgrade head` exits 0
- `pytest tests/api/test_global_events.py tests/api/test_global_flows.py` all pass
- `check-api-standard.py` passes
- No `float` in any financial value

## Domain constraints

- Indian formatting: flows in ₹ crore (not million). `Decimal(precision=20, scale=4)`.
- `de_fii_dii_activity` may be sparse — always soft-degrade, never error.
- `atlas_key_events` is owned by ATLAS — read/write allowed.
- `de_*` tables: read-only via JIP client only.
- All datetimes IST-aware.
