---
id: V2FE-1a
title: "Backend: zone-events + breadth divergences endpoints"
status: PENDING
estimated_hours: 3
depends_on: []
gate_criteria:
  code: 80
  test: 80
---

## Objective

Add two missing breadth endpoints consumed by `breadth.html` and `explore-country.html`.

## Punch list

- [ ] Create `backend/services/breadth_zone_detector.py`
  - `detect_zone_events(symbol: str, lookback_days: int = 365) -> list[ZoneEvent]`
  - Reads `de_bhavcopy_eq` for price data via JIP client. Never direct SQL.
  - Returns: date, zone (ABOVE_20/BELOW_20/ABOVE_200/BELOW_200/CROSS_UP/CROSS_DOWN), close, ma_value
  - All price values `Decimal`. Dates IST-aware.
- [ ] Create `backend/services/breadth_divergence_detector.py`
  - `detect_divergences(universe: str = "nifty500", lookback_days: int = 180) -> list[DivergenceEvent]`
  - Price divergence: index new high but breadth (% above 50MA) declining
  - Returns: date, type (BULLISH/BEARISH), index_change_pct (Decimal), breadth_change_pct (Decimal)
- [ ] Add route `GET /api/v1/stocks/breadth/zone-events` in `backend/routes/stocks.py`
  - Query params: `symbol: Optional[str] = "NIFTY"`, `lookback_days: Optional[int] = 365`
  - Response: `{"data": [...], "_meta": {"data_as_of": ..., "staleness_seconds": ..., "source": "de_bhavcopy_eq"}}`
  - Conforms to spec §17 (UQL), §18 (include), §20 (principles) — read these before writing route
- [ ] Add route `GET /api/v1/stocks/breadth/divergences` in `backend/routes/stocks.py`
  - Query params: `universe: Optional[str] = "nifty500"`, `lookback_days: Optional[int] = 180`
  - Same `_meta` envelope
- [ ] Write tests: `tests/api/test_breadth_zone_events.py`, `tests/api/test_breadth_divergences.py`
  - Use httpx AsyncClient. Test request schema AND response schema.
  - Test empty-state when JIP data sparse (mock JIP returning []).
- [ ] Run `python scripts/check-api-standard.py` — must pass before ship

## Exit criteria

- `GET /api/v1/stocks/breadth/zone-events` returns 200 with `data` array and `_meta` envelope
- `GET /api/v1/stocks/breadth/divergences` returns 200 with same shape
- Both return empty `data: []` (not error) when JIP source is sparse
- `pytest tests/api/test_breadth_zone_events.py tests/api/test_breadth_divergences.py` all pass
- `check-api-standard.py` passes
- No `float` in any financial value — `Decimal` only

## Domain constraints

- JIP `de_bhavcopy_eq` is read-only via `backend/clients/jip_data_service.py`. Never direct SQL.
- `de_fo_bhavcopy` = 0 rows — do not use it. Use `de_bhavcopy_eq` only.
- All price/return values: `Decimal`, never `float`
- Dates: IST timezone-aware (`Arrow` or `pendulum`)
- Fault-tolerant: if JIP returns partial data, return what we have with `insufficient_data: true` in `_meta`
