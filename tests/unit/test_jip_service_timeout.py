"""Unit tests for JIPDataService.execute_sql_plan timeout enforcement (V2-UQL-AGG-7).

Covers:
  1. Normal queries flow through unchanged: count_sql + data_sql both run,
     SET LOCAL statement_timeout = 2000 is the first statement, and the
     transaction commits.
  2. A simulated long-running query (the optimizer plan wraps a
     ``pg_sleep(5)`` clause; the fake session raises
     ``asyncpg.exceptions.QueryCanceledError`` to model PostgreSQL's
     statement_timeout cancel) is translated into an HTTP 504
     ``QUERY_TIMEOUT`` UQLError within 2.5 seconds wall-clock — the
     timeout never blocks the test loop because the fake session raises
     immediately. We still measure wall-clock to enforce the contract.
  3. count_sql=None falls back to ``len(rows)`` for ``total``.
  4. Non-timeout DBAPIErrors propagate untouched (no false 504).
"""

from __future__ import annotations

import time
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import asyncpg.exceptions
import pytest
from sqlalchemy.exc import DBAPIError

from backend.clients.jip_data_service import (
    STATEMENT_TIMEOUT_MS,
    JIPDataService,
)
from backend.services.uql import errors as uql_errors
from backend.services.uql.optimizer import SQLPlan


class _FakeMappings:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = rows

    def all(self) -> list[dict[str, Any]]:
        return list(self._rows)


class _FakeResult:
    def __init__(
        self,
        rows: list[dict[str, Any]] | None = None,
        scalar_value: Any = None,
    ) -> None:
        self._rows = rows or []
        self._scalar = scalar_value

    def mappings(self) -> _FakeMappings:
        return _FakeMappings(self._rows)

    def scalar(self) -> Any:
        return self._scalar


class _FakeSession:
    """Minimal AsyncSession stand-in: records every execute call.

    ``execute_responses`` is a queue of (predicate, response_or_exc)
    tuples consumed in order. The predicate inspects the rendered SQL
    text so a test can wire one response for ``SET LOCAL ...`` and
    another for the actual query.
    """

    def __init__(self, plan: list[Any]) -> None:
        self._plan = list(plan)
        self.executed_sql: list[str] = []
        self.executed_params: list[dict[str, Any]] = []
        self.committed = False
        self.rolled_back = False

    async def execute(self, sql_clause: Any, params: dict[str, Any] | None = None):
        rendered = str(sql_clause)
        self.executed_sql.append(rendered)
        self.executed_params.append(dict(params or {}))
        if not self._plan:
            raise AssertionError(f"Unexpected execute({rendered!r})")
        response = self._plan.pop(0)
        if isinstance(response, BaseException):
            raise response
        return response

    def begin(self) -> "_FakeTransaction":
        return _FakeTransaction(self)

    async def __aenter__(self) -> "_FakeSession":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None


class _FakeTransaction:
    def __init__(self, session: _FakeSession) -> None:
        self._session = session

    async def __aenter__(self) -> "_FakeTransaction":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        if exc_type is None:
            self._session.committed = True
        else:
            self._session.rolled_back = True
        return None


def _make_factory(session: _FakeSession):
    def _factory() -> _FakeSession:
        return session

    return _factory


def _make_service(session: _FakeSession) -> JIPDataService:
    # JIPDataService still wants an AsyncSession for its sub-services,
    # but execute_sql_plan never touches them — a MagicMock is enough.
    return JIPDataService(MagicMock(), session_factory=_make_factory(session))


@pytest.mark.asyncio
async def test_execute_sql_plan_normal_query_returns_rows_and_total():
    rows = [{"symbol": "HDFCBANK", "rs": 12.5}, {"symbol": "TCS", "rs": 9.1}]
    session = _FakeSession(
        plan=[
            _FakeResult(),  # SET LOCAL statement_timeout
            _FakeResult(scalar_value=42),  # count_sql
            _FakeResult(rows=rows),  # data_sql
        ]
    )
    svc = _make_service(session)
    plan = SQLPlan(
        sql="SELECT current_symbol AS symbol, rs_composite AS rs FROM x",
        params={},
        count_sql="SELECT COUNT(*) FROM x",
        count_params={},
    )

    result_rows, total = await svc.execute_sql_plan(plan)

    assert result_rows == rows
    assert total == 42
    assert session.committed is True
    # First statement must be the timeout cap.
    assert session.executed_sql[0] == f"SET LOCAL statement_timeout = {STATEMENT_TIMEOUT_MS}"
    assert STATEMENT_TIMEOUT_MS == 2000


@pytest.mark.asyncio
async def test_execute_sql_plan_pg_sleep_raises_query_timeout_within_2_5s():
    # Model what PostgreSQL does on statement_timeout: cancels the
    # statement, asyncpg raises QueryCanceledError, SQLAlchemy wraps it
    # in DBAPIError(orig=...).
    canceled = asyncpg.exceptions.QueryCanceledError("canceling statement due to statement timeout")
    wrapped = DBAPIError.instance(
        statement="SELECT pg_sleep(5)",
        params={},
        orig=canceled,
        dbapi_base_err=Exception,
        hide_parameters=False,
    )
    session = _FakeSession(
        plan=[
            _FakeResult(),  # SET LOCAL statement_timeout
            wrapped,  # data query is canceled
        ]
    )
    svc = _make_service(session)
    plan = SQLPlan(sql="SELECT pg_sleep(5)", params={})

    start = time.monotonic()
    with pytest.raises(uql_errors.UQLError) as excinfo:
        await svc.execute_sql_plan(plan)
    elapsed = time.monotonic() - start

    assert excinfo.value.code == uql_errors.QUERY_TIMEOUT
    assert excinfo.value.http_status == 504
    assert "2000ms" in excinfo.value.message
    # Wall-clock budget per the chunk punch list.
    assert elapsed < 2.5, f"timeout path took {elapsed:.3f}s, must be < 2.5s"
    assert session.rolled_back is True


@pytest.mark.asyncio
async def test_execute_sql_plan_without_count_sql_uses_row_count():
    rows = [{"x": 1}, {"x": 2}, {"x": 3}]
    session = _FakeSession(
        plan=[
            _FakeResult(),  # SET LOCAL
            _FakeResult(rows=rows),  # data
        ]
    )
    svc = _make_service(session)
    plan = SQLPlan(sql="SELECT 1", params={})

    result_rows, total = await svc.execute_sql_plan(plan)

    assert result_rows == rows
    assert total == 3


@pytest.mark.asyncio
async def test_execute_sql_plan_non_timeout_dbapi_error_propagates():
    # A constraint violation is *not* a timeout — it must surface to the
    # caller untouched, never as a 504. Otherwise we would mask real
    # bugs as transient timeouts.
    other = RuntimeError("oops")
    wrapped = DBAPIError.instance(
        statement="SELECT 1",
        params={},
        orig=other,
        dbapi_base_err=Exception,
        hide_parameters=False,
    )
    session = _FakeSession(
        plan=[
            _FakeResult(),  # SET LOCAL
            wrapped,
        ]
    )
    svc = _make_service(session)
    plan = SQLPlan(sql="SELECT 1", params={})

    with pytest.raises(DBAPIError):
        await svc.execute_sql_plan(plan)


@pytest.mark.asyncio
async def test_execute_sql_plan_query_canceled_via_cause_chain():
    # Some asyncpg versions chain the cancel via __cause__ instead of
    # ``orig``; the walker must catch both.
    canceled = asyncpg.exceptions.QueryCanceledError("timeout")
    wrapper: Exception
    try:
        raise RuntimeError("driver wrapper") from canceled
    except RuntimeError as exc:
        wrapper = exc
    wrapped = DBAPIError.instance(
        statement="SELECT pg_sleep(5)",
        params={},
        orig=wrapper,
        dbapi_base_err=Exception,
        hide_parameters=False,
    )
    session = _FakeSession(
        plan=[
            _FakeResult(),
            wrapped,
        ]
    )
    svc = _make_service(session)
    plan = SQLPlan(sql="SELECT pg_sleep(5)", params={})

    with pytest.raises(uql_errors.UQLError) as excinfo:
        await svc.execute_sql_plan(plan)
    assert excinfo.value.code == uql_errors.QUERY_TIMEOUT


@pytest.mark.asyncio
async def test_execute_sql_plan_unused_async_mock_smoke():
    # Sanity: AsyncMock is importable and usable for callers that wire
    # heavier doubles. Keeps the import surface honest.
    m = AsyncMock(return_value=None)
    await m()
    m.assert_awaited_once()
