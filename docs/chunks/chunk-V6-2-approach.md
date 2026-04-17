# Chunk V6-2 Approach: TV MCP Bridge Service Wrapper

## Data scale
No database writes. This chunk is pure HTTP client wrapper — no DB reads.
The bridge calls a local Node.js sidecar running at 127.0.0.1:7100.

## Chosen approach
Simple `httpx.AsyncClient` wrapper class with three async methods. Timeout/connect
errors caught and re-raised as `TVBridgeUnavailableError`. No financial computation
(bridge just passes through dicts), so Decimal constraint is N/A here.

## Wiki patterns checked
- `AsyncMock Context Manager Pattern` — httpx.AsyncClient is an async context manager;
  tests must use `AsyncMock` with `__aenter__`/`__aexit__`. However, the bridge itself
  uses the client as a module-level or per-call context manager.
- `httpx ConnectError Requires request= Kwarg` — when constructing `httpx.ConnectError`
  in tests, must pass `request=httpx.Request(...)` kwarg.

## Existing code being reused
- Pattern: `backend/services/cost_ledger.py` for service structure (structlog, BudgetExhaustedError pattern)
- `backend/models/tv.py` — existing Pydantic models (TvDataType constants)

## Implementation plan

### Files
1. `backend/services/tv/__init__.py` — empty
2. `backend/services/tv/bridge.py` — TVBridgeClient + TVBridgeUnavailableError
3. `tests/unit/tv/__init__.py` — empty
4. `tests/unit/tv/test_bridge_timeout.py` — 5 tests

### bridge.py design
- `TVBridgeUnavailableError(Exception)` defined at top
- `TVBridgeClient` class with `base_url` and `timeout` constructor params
- Three async methods use `async with httpx.AsyncClient(timeout=self.timeout) as client:`
- Catch `httpx.TimeoutException | httpx.ConnectError` → raise `TVBridgeUnavailableError`
- structlog logger, no print()

### Test design
- Use `unittest.mock.patch` on `httpx.AsyncClient` (respx not in requirements)
- Mock `__aenter__` and `__aexit__` as AsyncMock (per AsyncMock Context Manager Pattern)
- Mock `client.get.return_value` for success / `.get` side_effect for exceptions
- Use `httpx.ConnectError("msg", request=httpx.Request("GET", "http://x"))` (per staging pattern)
- `@pytest.mark.asyncio` on each test

## Edge cases
- `httpx.TimeoutException` is abstract base; construct `httpx.ReadTimeout` or catch the
  base class. The bridge catches both `TimeoutException` and `ConnectError`.
- Empty dict response: passed through as-is (no financial parsing)
- sidecar offline at startup: ConnectError path

## Expected runtime
Trivial — pure mocking, no real network calls. Tests run < 1 second.
