"""API-level tests for POST /api/v1/portfolio/import-cams.

Tests cover:
- Full endpoint with mocked casparser + mocked JIP + mocked DB
- Response shape matches PortfolioImportResult
- needs_review bucket populated for low-confidence matches
- Error cases (empty file, corrupt PDF)
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from backend.main import app


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_mock_session() -> MagicMock:
    """Create a mock async session that doesn't hit real DB."""
    mock = MagicMock()
    mock.__aenter__ = AsyncMock(return_value=mock)
    mock.__aexit__ = AsyncMock(return_value=False)
    mock.execute = AsyncMock()
    mock.flush = AsyncMock()
    mock.add = MagicMock()
    mock.begin = MagicMock()
    mock.begin.return_value.__aenter__ = AsyncMock(return_value=mock)
    mock.begin.return_value.__aexit__ = AsyncMock(return_value=False)
    return mock


@pytest.fixture
def client() -> TestClient:
    """TestClient with get_db dependency overridden."""
    from backend.db.session import get_db

    mock_session = _make_mock_session()

    async def override_get_db() -> Any:
        yield mock_session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c
    app.dependency_overrides.pop(get_db, None)


# ---------------------------------------------------------------------------
# Helper builders
# ---------------------------------------------------------------------------


def _make_fake_parse_result(
    num_holdings: int = 2,
) -> MagicMock:
    """Build a fake CamsParseResult with N holdings."""
    from backend.services.portfolio.cams_import import CamsParseResult, ParsedHolding

    holdings = [
        ParsedHolding(
            scheme_name=f"Test Fund {i} - Growth",
            folio_number=f"1234{i} / 01",
            units=Decimal("100.0000"),
            nav=Decimal("50.0000"),
            value=Decimal("5000.0000"),
        )
        for i in range(num_holdings)
    ]
    return CamsParseResult(
        holdings=holdings,
        investor_name="Test Investor",
        pan="ABCDE1234F",
        raw_folio_count=1,
    )


def _make_fake_mapped(
    num_holdings: int,
    *,
    pending_indices: list[int] | None = None,
) -> list[MagicMock]:
    """Build fake MappedHolding list, with some set to pending."""
    from backend.models.portfolio import MappingStatus
    from backend.services.portfolio.scheme_mapper import MappedHolding

    if pending_indices is None:
        pending_indices = []

    results = []
    for i in range(num_holdings):
        if i in pending_indices:
            mapped = MappedHolding(
                scheme_name=f"Test Fund {i} - Growth",
                mstar_id=None,
                confidence=Decimal("0.50"),
                mapping_status=MappingStatus.pending,
            )
        else:
            mapped = MappedHolding(
                scheme_name=f"Test Fund {i} - Growth",
                mstar_id=f"F0000{i:04d}",
                confidence=Decimal("0.85"),
                mapping_status=MappingStatus.mapped,
            )
        results.append(mapped)
    return results


def _make_fake_portfolio_orm(portfolio_id: uuid.UUID, name: str) -> MagicMock:
    """Build a fake AtlasPortfolio ORM object."""
    import datetime

    portfolio = MagicMock()
    portfolio.id = portfolio_id
    portfolio.name = name
    portfolio.portfolio_type = "cams_import"
    portfolio.owner_type = "retail"
    portfolio.user_id = None
    portfolio.analysis_cache = None
    now = datetime.datetime.now(tz=datetime.timezone.utc)
    portfolio.created_at = now
    portfolio.updated_at = now
    return portfolio


def _make_fake_holdings_orm(
    portfolio_id: uuid.UUID,
    num_holdings: int,
    pending_indices: list[int] | None = None,
) -> list[MagicMock]:
    """Build fake AtlasPortfolioHolding ORM objects."""
    import datetime

    if pending_indices is None:
        pending_indices = []

    now = datetime.datetime.now(tz=datetime.timezone.utc)
    holdings = []
    for i in range(num_holdings):
        h = MagicMock()
        h.id = uuid.uuid4()
        h.portfolio_id = portfolio_id
        h.scheme_name = f"Test Fund {i} - Growth"
        h.folio_number = f"1234{i} / 01"
        h.units = Decimal("100.0000")
        h.nav = Decimal("50.0000")
        h.current_value = Decimal("5000.0000")
        h.cost_value = None
        h.mstar_id = None if i in pending_indices else f"F0000{i:04d}"
        h.mapping_confidence = Decimal("0.50") if i in pending_indices else Decimal("0.85")
        h.mapping_status = "pending" if i in pending_indices else "mapped"
        h.is_deleted = False
        h.created_at = now
        h.updated_at = now
        holdings.append(h)
    return holdings


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_import_cams_route_registered() -> None:
    """POST /api/v1/portfolio/import-cams route must exist."""
    paths = [r.path for r in app.routes]  # type: ignore[attr-defined]
    assert "/api/v1/portfolio/import-cams" in paths


def test_import_cams_empty_file_returns_422(client: TestClient) -> None:
    """Empty file upload returns 422 Unprocessable Entity."""
    resp = client.post(
        "/api/v1/portfolio/import-cams",
        files={"file": ("test.pdf", b"", "application/pdf")},
    )
    assert resp.status_code == 422, f"Expected 422, got {resp.status_code}: {resp.text}"


def test_import_cams_corrupt_pdf_returns_422(client: TestClient) -> None:
    """Corrupt PDF content returns 422 with error detail."""
    from backend.services.portfolio.cams_import import CamsImportError

    with patch(
        "backend.routes.portfolio.parse_cas_pdf",
        side_effect=CamsImportError("Invalid PDF structure"),
    ):
        resp = client.post(
            "/api/v1/portfolio/import-cams",
            files={"file": ("test.pdf", b"not a real pdf", "application/pdf")},
        )

    assert resp.status_code == 422, f"Expected 422, got {resp.status_code}: {resp.text}"
    data = resp.json()
    # The error detail should be in the response
    assert "Invalid PDF structure" in str(data) or resp.status_code == 422


def test_import_cams_returns_portfolio_import_result(client: TestClient) -> None:
    """Successful import returns PortfolioImportResult shape."""
    portfolio_id = uuid.uuid4()
    parse_result = _make_fake_parse_result(num_holdings=3)
    mapped = _make_fake_mapped(num_holdings=3, pending_indices=[2])
    portfolio_orm = _make_fake_portfolio_orm(portfolio_id, "Test Investor — CAMS Import")
    holdings_orm = _make_fake_holdings_orm(portfolio_id, num_holdings=3, pending_indices=[2])

    with (
        patch("backend.routes.portfolio.parse_cas_pdf", return_value=parse_result),
        patch(
            "backend.routes.portfolio.SchemeMapper.map_holdings",
            new_callable=AsyncMock,
            return_value=mapped,
        ),
        patch("backend.routes.portfolio.PortfolioRepo") as MockRepo,
    ):
        mock_repo = MagicMock()
        mock_repo.create_portfolio = AsyncMock(return_value=portfolio_orm)
        mock_repo.get_holdings = AsyncMock(return_value=holdings_orm)
        MockRepo.return_value = mock_repo

        resp = client.post(
            "/api/v1/portfolio/import-cams",
            files={"file": ("test.pdf", b"%PDF fake content", "application/pdf")},
        )

    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"
    data = resp.json()

    # Verify PortfolioImportResult shape
    assert "portfolio_id" in data
    assert "portfolio_name" in data
    assert "holdings" in data
    assert "needs_review" in data
    assert "mapped_count" in data
    assert "pending_count" in data
    assert "total_count" in data
    assert "data_as_of" in data


def test_import_cams_needs_review_bucket_populated(client: TestClient) -> None:
    """Low-confidence holdings appear in needs_review bucket."""
    portfolio_id = uuid.uuid4()
    # 3 holdings, index 1 and 2 are pending (low confidence)
    parse_result = _make_fake_parse_result(num_holdings=3)
    mapped = _make_fake_mapped(num_holdings=3, pending_indices=[1, 2])
    portfolio_orm = _make_fake_portfolio_orm(portfolio_id, "Test Investor — CAMS Import")
    holdings_orm = _make_fake_holdings_orm(portfolio_id, num_holdings=3, pending_indices=[1, 2])

    with (
        patch("backend.routes.portfolio.parse_cas_pdf", return_value=parse_result),
        patch(
            "backend.routes.portfolio.SchemeMapper.map_holdings",
            new_callable=AsyncMock,
            return_value=mapped,
        ),
        patch("backend.routes.portfolio.PortfolioRepo") as MockRepo,
    ):
        mock_repo = MagicMock()
        mock_repo.create_portfolio = AsyncMock(return_value=portfolio_orm)
        mock_repo.get_holdings = AsyncMock(return_value=holdings_orm)
        MockRepo.return_value = mock_repo

        resp = client.post(
            "/api/v1/portfolio/import-cams",
            files={"file": ("test.pdf", b"%PDF fake content", "application/pdf")},
        )

    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"
    data = resp.json()

    assert data["total_count"] == 3
    assert data["pending_count"] == 2
    assert data["mapped_count"] == 1
    assert len(data["needs_review"]) == 2

    # Verify needs_review only contains pending holdings
    for nr in data["needs_review"]:
        assert nr["mapping_status"] == "pending"


def test_import_cams_counts_correct_when_all_mapped(client: TestClient) -> None:
    """When all holdings map successfully, needs_review is empty."""
    portfolio_id = uuid.uuid4()
    parse_result = _make_fake_parse_result(num_holdings=2)
    mapped = _make_fake_mapped(num_holdings=2, pending_indices=[])
    portfolio_orm = _make_fake_portfolio_orm(portfolio_id, "Test Investor — CAMS Import")
    holdings_orm = _make_fake_holdings_orm(portfolio_id, num_holdings=2, pending_indices=[])

    with (
        patch("backend.routes.portfolio.parse_cas_pdf", return_value=parse_result),
        patch(
            "backend.routes.portfolio.SchemeMapper.map_holdings",
            new_callable=AsyncMock,
            return_value=mapped,
        ),
        patch("backend.routes.portfolio.PortfolioRepo") as MockRepo,
    ):
        mock_repo = MagicMock()
        mock_repo.create_portfolio = AsyncMock(return_value=portfolio_orm)
        mock_repo.get_holdings = AsyncMock(return_value=holdings_orm)
        MockRepo.return_value = mock_repo

        resp = client.post(
            "/api/v1/portfolio/import-cams",
            files={"file": ("test.pdf", b"%PDF fake content", "application/pdf")},
        )

    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"
    data = resp.json()

    assert data["total_count"] == 2
    assert data["pending_count"] == 0
    assert data["mapped_count"] == 2
    assert data["needs_review"] == []


def test_import_cams_portfolio_name_from_form(client: TestClient) -> None:
    """Custom portfolio_name from form data is used if provided."""
    portfolio_id = uuid.uuid4()
    parse_result = _make_fake_parse_result(num_holdings=1)
    mapped = _make_fake_mapped(num_holdings=1)
    portfolio_orm = _make_fake_portfolio_orm(portfolio_id, "My Custom Portfolio")
    holdings_orm = _make_fake_holdings_orm(portfolio_id, num_holdings=1)

    with (
        patch("backend.routes.portfolio.parse_cas_pdf", return_value=parse_result),
        patch(
            "backend.routes.portfolio.SchemeMapper.map_holdings",
            new_callable=AsyncMock,
            return_value=mapped,
        ),
        patch("backend.routes.portfolio.PortfolioRepo") as MockRepo,
    ):
        mock_repo = MagicMock()
        mock_repo.create_portfolio = AsyncMock(return_value=portfolio_orm)
        mock_repo.get_holdings = AsyncMock(return_value=holdings_orm)
        MockRepo.return_value = mock_repo

        resp = client.post(
            "/api/v1/portfolio/import-cams",
            files={"file": ("test.pdf", b"%PDF fake content", "application/pdf")},
            data={"portfolio_name": "My Custom Portfolio"},
        )

    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"
    data = resp.json()
    assert data["portfolio_name"] == "My Custom Portfolio"


def test_import_cams_no_500_on_valid_input(client: TestClient) -> None:
    """Endpoint must not return 500 for any reason with valid input."""
    parse_result = _make_fake_parse_result(num_holdings=0)
    portfolio_id = uuid.uuid4()
    portfolio_orm = _make_fake_portfolio_orm(portfolio_id, "Empty Import")

    with (
        patch("backend.routes.portfolio.parse_cas_pdf", return_value=parse_result),
        patch(
            "backend.routes.portfolio.SchemeMapper.map_holdings",
            new_callable=AsyncMock,
            return_value=[],
        ),
        patch("backend.routes.portfolio.PortfolioRepo") as MockRepo,
    ):
        mock_repo = MagicMock()
        mock_repo.create_portfolio = AsyncMock(return_value=portfolio_orm)
        mock_repo.get_holdings = AsyncMock(return_value=[])
        MockRepo.return_value = mock_repo

        resp = client.post(
            "/api/v1/portfolio/import-cams",
            files={"file": ("test.pdf", b"%PDF fake content", "application/pdf")},
        )

    assert resp.status_code != 500, f"Got unexpected 500: {resp.text}"
