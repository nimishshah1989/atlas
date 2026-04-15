"""Smoke test for /pro/intelligence page data requirements.

Verifies:
1. Semantic search returns findings with confidence, evidence, agent_id, agent_type, created_at
2. Empty state: min_confidence=0.99 returns zero findings with proper empty response
3. top_k parameter is respected and passed through to the service
"""

import datetime
import uuid
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from backend.db.session import get_db
from backend.main import app

_GET_RELEVANT = "backend.routes.intelligence.get_relevant_intelligence"


def _make_orm_row(**overrides):  # type: ignore[no-untyped-def]
    """Return MagicMock that looks like AtlasIntelligence ORM row."""
    now = datetime.datetime(2026, 4, 15, 10, 0, 0, tzinfo=datetime.timezone.utc)
    row = MagicMock()
    row.id = overrides.get("id", uuid.uuid4())
    row.agent_id = overrides.get("agent_id", "rs-analyzer")
    row.agent_type = overrides.get("agent_type", "equity_analyst")
    row.entity = overrides.get("entity", "RELIANCE")
    row.entity_type = overrides.get("entity_type", "equity")
    row.finding_type = overrides.get("finding_type", "rs_analysis")
    row.title = overrides.get("title", "RS momentum turning positive")
    row.content = overrides.get("content", "RELIANCE relative strength has crossed above zero.")
    row.confidence = overrides.get("confidence", Decimal("0.85"))
    row.evidence = overrides.get("evidence", {"rs_score": "1.23", "period": "21d"})
    row.tags = overrides.get("tags", ["momentum", "equity"])
    row.data_as_of = overrides.get("data_as_of", now)
    row.expires_at = overrides.get("expires_at", now + datetime.timedelta(hours=168))
    row.is_validated = overrides.get("is_validated", False)
    row.created_at = overrides.get("created_at", now)
    row.updated_at = overrides.get("updated_at", now)
    return row


def _override_db(mock_session: AsyncMock):  # type: ignore[no-untyped-def]
    async def _get_db():  # type: ignore[return]
        yield mock_session

    return _get_db


class TestProIntelligenceSmoke:
    """Smoke tests for /pro/intelligence page data contract."""

    def test_search_findings_have_required_fields(self) -> None:
        """Top-k findings must include confidence, evidence, agent, timestamp."""
        mock_session = AsyncMock()
        rows = [
            _make_orm_row(
                agent_id="rs-analyzer",
                confidence=Decimal("0.85"),
                evidence={"rs_score": "1.23"},
                agent_type="equity_analyst",
            ),
            _make_orm_row(
                agent_id="sector-analyst",
                confidence=Decimal("0.72"),
                evidence={"breadth": "declining"},
                agent_type="sector_analyst",
            ),
        ]

        app.dependency_overrides[get_db] = _override_db(mock_session)
        try:
            with patch(_GET_RELEVANT, new_callable=AsyncMock) as mock_search:
                mock_search.return_value = rows
                client = TestClient(app)
                resp = client.get("/api/v1/intelligence/search?q=momentum+signals&top_k=10")
        finally:
            app.dependency_overrides.pop(get_db, None)

        assert resp.status_code == 200
        body = resp.json()
        findings = body["data"]
        assert len(findings) == 2

        for f in findings:
            # confidence present and numeric string
            assert f["confidence"] is not None
            assert float(f["confidence"]) > 0

            # evidence present and non-empty
            assert f["evidence"] is not None
            assert isinstance(f["evidence"], dict)
            assert len(f["evidence"]) > 0

            # agent fields present
            assert f["agent_id"]
            assert f["agent_type"]

            # timestamp present
            assert f["created_at"]

    def test_search_empty_state_high_min_confidence(self) -> None:
        """min_confidence=0.99 with no matches returns empty data array."""
        mock_session = AsyncMock()

        app.dependency_overrides[get_db] = _override_db(mock_session)
        try:
            with patch(_GET_RELEVANT, new_callable=AsyncMock) as mock_search:
                mock_search.return_value = []
                client = TestClient(app)
                resp = client.get("/api/v1/intelligence/search?q=any+query&min_confidence=0.99")
        finally:
            app.dependency_overrides.pop(get_db, None)

        assert resp.status_code == 200
        body = resp.json()
        assert body["data"] == []
        assert body["_meta"]["record_count"] == 0

        # Verify min_confidence was passed through to service
        call_kwargs = mock_search.call_args.kwargs
        assert call_kwargs["min_confidence"] == Decimal("0.99")

    def test_search_findings_top_k_respected(self) -> None:
        """top_k parameter limits number of returned findings."""
        mock_session = AsyncMock()
        rows = [_make_orm_row() for _ in range(3)]

        app.dependency_overrides[get_db] = _override_db(mock_session)
        try:
            with patch(_GET_RELEVANT, new_callable=AsyncMock) as mock_search:
                mock_search.return_value = rows
                client = TestClient(app)
                resp = client.get("/api/v1/intelligence/search?q=test&top_k=3")
        finally:
            app.dependency_overrides.pop(get_db, None)

        assert resp.status_code == 200
        body = resp.json()
        assert len(body["data"]) == 3
        assert body["_meta"]["record_count"] == 3

        # Verify top_k passed to service
        call_kwargs = mock_search.call_args.kwargs
        assert call_kwargs["top_k"] == 3
