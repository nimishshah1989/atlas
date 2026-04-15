"""Unit-level API shape tests for V5-5 Intelligence Memory read-only routes.

Verifies that the three GET intelligence endpoints return the §20.4 standard
envelope shape: {data, _meta}. Uses dependency overrides + service-level mocks.
No real DB or embedding service required.

Pattern note (FastAPI Dependency Patch Gotcha): get_db must be overridden via
app.dependency_overrides even when the service is fully mocked, because FastAPI
resolves all Depends() eagerly before the handler runs.
"""

from __future__ import annotations

import datetime
import uuid
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from backend.db.session import get_db
from backend.main import app
from backend.models.intelligence import FindingSummary

# Patch targets — kept as constants so lines stay under 100 chars
_LIST_FINDINGS = "backend.routes.intelligence.list_findings"
_GET_RELEVANT = "backend.routes.intelligence.get_relevant_intelligence"
_GET_BY_ID = "backend.routes.intelligence.get_finding_by_id"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_finding_summary(
    finding_id: uuid.UUID | None = None,
    entity: str = "RELIANCE",
    finding_type: str = "momentum",
) -> FindingSummary:
    now = datetime.datetime(2026, 4, 15, 10, 0, 0, tzinfo=datetime.timezone.utc)
    return FindingSummary(
        id=finding_id or uuid.uuid4(),
        agent_id="test-agent",
        agent_type="equity_analyst",
        entity=entity,
        entity_type="equity",
        finding_type=finding_type,
        title="Test finding",
        content="Test content for the finding.",
        confidence=Decimal("0.85"),
        evidence={"source": "test"},
        tags=["momentum", "buy"],
        data_as_of=now,
        expires_at=now + datetime.timedelta(hours=168),
        is_validated=False,
        created_at=now,
        updated_at=now,
    )


def _make_orm_row(
    finding_id: uuid.UUID | None = None,
    entity: str = "RELIANCE",
    finding_type: str = "momentum",
) -> MagicMock:
    """Return a MagicMock that looks like an AtlasIntelligence ORM row."""
    now = datetime.datetime(2026, 4, 15, 10, 0, 0, tzinfo=datetime.timezone.utc)
    row = MagicMock()
    row.id = finding_id or uuid.uuid4()
    row.agent_id = "test-agent"
    row.agent_type = "equity_analyst"
    row.entity = entity
    row.entity_type = "equity"
    row.finding_type = finding_type
    row.title = "Test finding"
    row.content = "Test content for the finding."
    row.confidence = Decimal("0.85")
    row.evidence = {"source": "test"}
    row.tags = ["momentum", "buy"]
    row.data_as_of = now
    row.expires_at = now + datetime.timedelta(hours=168)
    row.is_validated = False
    row.created_at = now
    row.updated_at = now
    return row


def _override_db(mock_session: Any) -> Any:
    async def _get_db() -> Any:  # type: ignore[misc]
        yield mock_session

    return _get_db


# ---------------------------------------------------------------------------
# GET /api/v1/intelligence/findings (list)
# ---------------------------------------------------------------------------


class TestListIntelligenceFindings:
    """Verify GET /intelligence/findings returns standard envelope."""

    def test_list_returns_200(self) -> None:
        mock_session = AsyncMock()
        rows = [_make_orm_row(), _make_orm_row()]

        app.dependency_overrides[get_db] = _override_db(mock_session)
        try:
            with patch(_LIST_FINDINGS, new_callable=AsyncMock) as mock_list:
                mock_list.return_value = rows
                client = TestClient(app)
                resp = client.get("/api/v1/intelligence/findings")
        finally:
            app.dependency_overrides.pop(get_db, None)

        assert resp.status_code == 200

    def test_list_has_data_key(self) -> None:
        mock_session = AsyncMock()
        rows = [_make_orm_row()]

        app.dependency_overrides[get_db] = _override_db(mock_session)
        try:
            with patch(_LIST_FINDINGS, new_callable=AsyncMock) as mock_list:
                mock_list.return_value = rows
                client = TestClient(app)
                resp = client.get("/api/v1/intelligence/findings")
        finally:
            app.dependency_overrides.pop(get_db, None)

        body = resp.json()
        assert "data" in body, f"missing 'data' key in response: {list(body.keys())}"
        assert isinstance(body["data"], list)

    def test_list_has_meta_key(self) -> None:
        mock_session = AsyncMock()

        app.dependency_overrides[get_db] = _override_db(mock_session)
        try:
            with patch(_LIST_FINDINGS, new_callable=AsyncMock) as mock_list:
                mock_list.return_value = []
                client = TestClient(app)
                resp = client.get("/api/v1/intelligence/findings")
        finally:
            app.dependency_overrides.pop(get_db, None)

        body = resp.json()
        assert "_meta" in body, f"missing '_meta' key in response: {list(body.keys())}"

    def test_list_has_findings_compat_key(self) -> None:
        """V1 compat key 'findings' must still be present."""
        mock_session = AsyncMock()

        app.dependency_overrides[get_db] = _override_db(mock_session)
        try:
            with patch(_LIST_FINDINGS, new_callable=AsyncMock) as mock_list:
                mock_list.return_value = []
                client = TestClient(app)
                resp = client.get("/api/v1/intelligence/findings")
        finally:
            app.dependency_overrides.pop(get_db, None)

        body = resp.json()
        assert "findings" in body

    def test_list_empty_data(self) -> None:
        mock_session = AsyncMock()

        app.dependency_overrides[get_db] = _override_db(mock_session)
        try:
            with patch(_LIST_FINDINGS, new_callable=AsyncMock) as mock_list:
                mock_list.return_value = []
                client = TestClient(app)
                resp = client.get("/api/v1/intelligence/findings")
        finally:
            app.dependency_overrides.pop(get_db, None)

        body = resp.json()
        assert body["data"] == []
        assert body["_meta"]["record_count"] == 0

    def test_list_with_entity_filter_passes_param(self) -> None:
        mock_session = AsyncMock()

        app.dependency_overrides[get_db] = _override_db(mock_session)
        try:
            with patch(_LIST_FINDINGS, new_callable=AsyncMock) as mock_list:
                mock_list.return_value = []
                client = TestClient(app)
                resp = client.get("/api/v1/intelligence/findings?entity=RELIANCE")
        finally:
            app.dependency_overrides.pop(get_db, None)

        assert resp.status_code == 200
        mock_list.assert_called_once()
        call_kwargs = mock_list.call_args.kwargs
        assert call_kwargs.get("entity") == "RELIANCE"

    def test_list_with_finding_type_filter(self) -> None:
        mock_session = AsyncMock()
        row = _make_orm_row(finding_type="buy_signal")

        app.dependency_overrides[get_db] = _override_db(mock_session)
        try:
            with patch(_LIST_FINDINGS, new_callable=AsyncMock) as mock_list:
                mock_list.return_value = [row]
                client = TestClient(app)
                resp = client.get("/api/v1/intelligence/findings?finding_type=buy_signal")
        finally:
            app.dependency_overrides.pop(get_db, None)

        assert resp.status_code == 200
        body = resp.json()
        assert len(body["data"]) == 1
        assert body["data"][0]["finding_type"] == "buy_signal"

    def test_list_meta_record_count(self) -> None:
        mock_session = AsyncMock()
        rows = [_make_orm_row(), _make_orm_row(), _make_orm_row()]

        app.dependency_overrides[get_db] = _override_db(mock_session)
        try:
            with patch(_LIST_FINDINGS, new_callable=AsyncMock) as mock_list:
                mock_list.return_value = rows
                client = TestClient(app)
                resp = client.get("/api/v1/intelligence/findings")
        finally:
            app.dependency_overrides.pop(get_db, None)

        body = resp.json()
        assert body["_meta"]["record_count"] == 3


# ---------------------------------------------------------------------------
# GET /api/v1/intelligence/search
# ---------------------------------------------------------------------------


class TestSearchIntelligence:
    """Verify GET /intelligence/search returns standard envelope."""

    def test_search_returns_200(self) -> None:
        mock_session = AsyncMock()
        rows = [_make_orm_row()]

        app.dependency_overrides[get_db] = _override_db(mock_session)
        try:
            with patch(_GET_RELEVANT, new_callable=AsyncMock) as mock_search:
                mock_search.return_value = rows
                client = TestClient(app)
                resp = client.get("/api/v1/intelligence/search?q=momentum+signals")
        finally:
            app.dependency_overrides.pop(get_db, None)

        assert resp.status_code == 200

    def test_search_has_data_key(self) -> None:
        mock_session = AsyncMock()
        rows = [_make_orm_row()]

        app.dependency_overrides[get_db] = _override_db(mock_session)
        try:
            with patch(_GET_RELEVANT, new_callable=AsyncMock) as mock_search:
                mock_search.return_value = rows
                client = TestClient(app)
                resp = client.get("/api/v1/intelligence/search?q=test")
        finally:
            app.dependency_overrides.pop(get_db, None)

        body = resp.json()
        assert "data" in body, f"missing 'data' key: {list(body.keys())}"
        assert isinstance(body["data"], list)

    def test_search_has_meta_key(self) -> None:
        mock_session = AsyncMock()

        app.dependency_overrides[get_db] = _override_db(mock_session)
        try:
            with patch(_GET_RELEVANT, new_callable=AsyncMock) as mock_search:
                mock_search.return_value = []
                client = TestClient(app)
                resp = client.get("/api/v1/intelligence/search?q=test")
        finally:
            app.dependency_overrides.pop(get_db, None)

        body = resp.json()
        assert "_meta" in body, f"missing '_meta' key: {list(body.keys())}"

    def test_search_missing_q_returns_error(self) -> None:
        mock_session = AsyncMock()

        app.dependency_overrides[get_db] = _override_db(mock_session)
        try:
            client = TestClient(app)
            resp = client.get("/api/v1/intelligence/search")
        finally:
            app.dependency_overrides.pop(get_db, None)

        # q is required — expect 400 (validation error handler shapes 422→400)
        assert resp.status_code in (400, 422)

    def test_search_passes_filters_to_service(self) -> None:
        mock_session = AsyncMock()

        app.dependency_overrides[get_db] = _override_db(mock_session)
        try:
            with patch(_GET_RELEVANT, new_callable=AsyncMock) as mock_search:
                mock_search.return_value = []
                client = TestClient(app)
                resp = client.get("/api/v1/intelligence/search?q=growth&entity=RELIANCE&top_k=5")
        finally:
            app.dependency_overrides.pop(get_db, None)

        assert resp.status_code == 200
        mock_search.assert_called_once()
        call_kwargs = mock_search.call_args.kwargs
        assert call_kwargs.get("entity") == "RELIANCE"
        assert call_kwargs.get("top_k") == 5

    def test_search_compat_findings_key(self) -> None:
        """V1 compat: 'findings' key must still be present."""
        mock_session = AsyncMock()

        app.dependency_overrides[get_db] = _override_db(mock_session)
        try:
            with patch(_GET_RELEVANT, new_callable=AsyncMock) as mock_search:
                mock_search.return_value = []
                client = TestClient(app)
                resp = client.get("/api/v1/intelligence/search?q=test")
        finally:
            app.dependency_overrides.pop(get_db, None)

        body = resp.json()
        assert "findings" in body


# ---------------------------------------------------------------------------
# GET /api/v1/intelligence/findings/{finding_id}
# ---------------------------------------------------------------------------


class TestGetFinding:
    """Verify GET /intelligence/findings/{finding_id} returns standard envelope."""

    def test_get_finding_returns_200(self) -> None:
        mock_session = AsyncMock()
        fid = uuid.uuid4()
        row = _make_orm_row(finding_id=fid)

        app.dependency_overrides[get_db] = _override_db(mock_session)
        try:
            with patch(_GET_BY_ID, new_callable=AsyncMock) as mock_get:
                mock_get.return_value = row
                client = TestClient(app)
                resp = client.get(f"/api/v1/intelligence/findings/{fid}")
        finally:
            app.dependency_overrides.pop(get_db, None)

        assert resp.status_code == 200

    def test_get_finding_has_data_key(self) -> None:
        mock_session = AsyncMock()
        fid = uuid.uuid4()
        row = _make_orm_row(finding_id=fid)

        app.dependency_overrides[get_db] = _override_db(mock_session)
        try:
            with patch(_GET_BY_ID, new_callable=AsyncMock) as mock_get:
                mock_get.return_value = row
                client = TestClient(app)
                resp = client.get(f"/api/v1/intelligence/findings/{fid}")
        finally:
            app.dependency_overrides.pop(get_db, None)

        body = resp.json()
        assert "data" in body, f"missing 'data' key: {list(body.keys())}"
        assert isinstance(body["data"], dict)

    def test_get_finding_has_meta_key(self) -> None:
        mock_session = AsyncMock()
        fid = uuid.uuid4()
        row = _make_orm_row(finding_id=fid)

        app.dependency_overrides[get_db] = _override_db(mock_session)
        try:
            with patch(_GET_BY_ID, new_callable=AsyncMock) as mock_get:
                mock_get.return_value = row
                client = TestClient(app)
                resp = client.get(f"/api/v1/intelligence/findings/{fid}")
        finally:
            app.dependency_overrides.pop(get_db, None)

        body = resp.json()
        assert "_meta" in body, f"missing '_meta' key: {list(body.keys())}"

    def test_get_finding_meta_record_count_is_one(self) -> None:
        mock_session = AsyncMock()
        fid = uuid.uuid4()
        row = _make_orm_row(finding_id=fid)

        app.dependency_overrides[get_db] = _override_db(mock_session)
        try:
            with patch(_GET_BY_ID, new_callable=AsyncMock) as mock_get:
                mock_get.return_value = row
                client = TestClient(app)
                resp = client.get(f"/api/v1/intelligence/findings/{fid}")
        finally:
            app.dependency_overrides.pop(get_db, None)

        body = resp.json()
        assert body["_meta"]["record_count"] == 1

    def test_get_finding_data_has_correct_id(self) -> None:
        mock_session = AsyncMock()
        fid = uuid.uuid4()
        row = _make_orm_row(finding_id=fid)

        app.dependency_overrides[get_db] = _override_db(mock_session)
        try:
            with patch(_GET_BY_ID, new_callable=AsyncMock) as mock_get:
                mock_get.return_value = row
                client = TestClient(app)
                resp = client.get(f"/api/v1/intelligence/findings/{fid}")
        finally:
            app.dependency_overrides.pop(get_db, None)

        body = resp.json()
        assert body["data"]["id"] == str(fid)

    def test_get_finding_not_found_returns_404(self) -> None:
        mock_session = AsyncMock()
        fid = uuid.uuid4()

        app.dependency_overrides[get_db] = _override_db(mock_session)
        try:
            with patch(_GET_BY_ID, new_callable=AsyncMock) as mock_get:
                mock_get.return_value = None
                client = TestClient(app)
                resp = client.get(f"/api/v1/intelligence/findings/{fid}")
        finally:
            app.dependency_overrides.pop(get_db, None)

        assert resp.status_code == 404

    def test_get_finding_invalid_uuid_returns_error(self) -> None:
        mock_session = AsyncMock()

        app.dependency_overrides[get_db] = _override_db(mock_session)
        try:
            client = TestClient(app)
            resp = client.get("/api/v1/intelligence/findings/not-a-uuid")
        finally:
            app.dependency_overrides.pop(get_db, None)

        # FastAPI validates UUID path param — expects 4xx
        assert resp.status_code in (400, 422)
