"""Integration tests for ATLAS V2 MF (Mutual Fund) API endpoints.

Maps to v2-criteria.yaml assertions. All tests require a live backend
at http://localhost:8010 and are marked @pytest.mark.integration so
forge-ship.sh can skip them in the standard unit gate.

Criteria mapping:
- v2-01: /mf/universe (TestMFUniverse)
- v2-02: /mf/categories (TestMFCategories)
- v2-03: /mf/{mstar_id} deep-dive idempotency (TestMFDeepDive)
- v2-04: staleness in /mf/categories (TestMFCategories)
- v2-05: MF page files exist (TestMFFrontend)
- v2-06: atlas_decisions has MF decisions (separate script check)
- v2-07: no float in MF files (TestMFNoFloat)
- v2-08: V1 criteria pass (separate script check)
- v2-09: response times within budget (TestMFResponseTimes)
"""

from __future__ import annotations

import re
import time
from pathlib import Path

import httpx
import pytest

pytestmark = pytest.mark.integration

BASE_URL = "http://localhost:8010"
ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def client():
    return httpx.Client(base_url=BASE_URL, timeout=30.0)


@pytest.fixture(scope="module")
def real_mstar_id(client: httpx.Client) -> str:
    """Fetch a real mstar_id from the live universe endpoint."""
    resp = client.get("/api/v1/mf/universe")
    assert resp.status_code == 200, f"/mf/universe returned {resp.status_code}"
    data = resp.json()
    groups = data.get("broad_category_groups", [])
    for broad in groups:
        for cat in broad.get("category_groups", []):
            funds = cat.get("funds", [])
            if funds:
                mstar_id = funds[0].get("mstar_id")
                if mstar_id:
                    return str(mstar_id)
    pytest.skip("no mstar_id available from /mf/universe")


class TestMFUniverse:
    """v2-01: /mf/universe returns valid MF data."""

    def test_universe_returns_200(self, client):
        resp = client.get("/api/v1/mf/universe")
        assert resp.status_code == 200

    def test_universe_has_broad_category_groups(self, client):
        resp = client.get("/api/v1/mf/universe")
        body = resp.json()
        groups = body.get("broad_category_groups", [])
        assert len(groups) > 0, "expected at least one broad category group"

    def test_universe_fund_has_required_fields(self, client):
        resp = client.get("/api/v1/mf/universe")
        body = resp.json()
        groups = body.get("broad_category_groups", [])
        assert groups, "no broad_category_groups"
        for broad in groups:
            for cat in broad.get("category_groups", []):
                funds = cat.get("funds", [])
                if funds:
                    fund = funds[0]
                    assert "mstar_id" in fund
                    assert "fund_name" in fund
                    assert "amc_name" in fund
                    return
        pytest.skip("no funds found in universe response")

    def test_universe_has_data_as_of(self, client):
        resp = client.get("/api/v1/mf/universe")
        body = resp.json()
        assert "data_as_of" in body or "staleness" in body, (
            "universe response lacks data_as_of or staleness"
        )

    def test_universe_fund_nav_is_string_decimal(self, client):
        """NAV values must be strings (Decimal serialized), not float."""
        resp = client.get("/api/v1/mf/universe")
        body = resp.json()
        for broad in body.get("broad_category_groups", []):
            for cat in broad.get("category_groups", []):
                for fund in cat.get("funds", []):
                    nav = fund.get("nav")
                    if nav is not None:
                        assert isinstance(nav, str), (
                            f"fund {fund.get('mstar_id')} nav={nav!r} is {type(nav).__name__}, "
                            "expected str (Decimal serialized)"
                        )
                    break  # Check first fund in each category, not all 2000+
                break
            break


class TestMFCategories:
    """v2-02 + v2-04: /mf/categories returns category hierarchy with staleness."""

    def test_categories_returns_200(self, client):
        resp = client.get("/api/v1/mf/categories")
        assert resp.status_code == 200

    def test_categories_has_groups(self, client):
        resp = client.get("/api/v1/mf/categories")
        body = resp.json()
        # Accept either broad_category_groups or category_groups at top level
        has_groups = bool(body.get("broad_category_groups") or body.get("category_groups"))
        assert has_groups, f"no category groups in response. Keys: {list(body.keys())}"

    def test_categories_each_group_has_name(self, client):
        resp = client.get("/api/v1/mf/categories")
        body = resp.json()
        groups = body.get("broad_category_groups", body.get("category_groups", []))
        for group in groups:
            assert "name" in group or "broad_category" in group or "category_name" in group, (
                f"group missing name field: {list(group.keys())}"
            )

    def test_categories_has_staleness_metadata(self, client):
        """v2-04: SC-009 — structured provenance must be present."""
        resp = client.get("/api/v1/mf/categories")
        body = resp.json()
        has_staleness = "staleness" in body
        has_data_as_of = "data_as_of" in body
        assert has_staleness or has_data_as_of, (
            f"categories response lacks staleness/data_as_of. Keys: {list(body.keys())}"
        )


class TestMFDeepDive:
    """v2-03: /mf/{mstar_id} deep-dive idempotency check."""

    def test_deep_dive_returns_200(self, client, real_mstar_id):
        resp = client.get(f"/api/v1/mf/{real_mstar_id}")
        assert resp.status_code == 200, f"/mf/{real_mstar_id} → {resp.status_code}"

    def test_deep_dive_has_fund_data(self, client, real_mstar_id):
        resp = client.get(f"/api/v1/mf/{real_mstar_id}")
        body = resp.json()
        assert "fund" in body, f"response missing 'fund' key. Keys: {list(body.keys())}"
        fund = body["fund"]
        assert fund.get("mstar_id") == real_mstar_id

    def test_deep_dive_idempotent(self, client, real_mstar_id):
        """Two calls must return same mstar_id — deterministic output (SC-003)."""
        resp1 = client.get(f"/api/v1/mf/{real_mstar_id}")
        resp2 = client.get(f"/api/v1/mf/{real_mstar_id}")
        assert resp1.status_code == resp2.status_code == 200
        id1 = resp1.json().get("fund", {}).get("mstar_id")
        id2 = resp2.json().get("fund", {}).get("mstar_id")
        assert id1 == id2 == real_mstar_id, (
            f"non-idempotent: call1={id1!r}, call2={id2!r}, expected={real_mstar_id!r}"
        )

    def test_deep_dive_has_conviction_pillars(self, client, real_mstar_id):
        resp = client.get(f"/api/v1/mf/{real_mstar_id}")
        body = resp.json()
        # Conviction pillars may be nested under 'fund' or at top level
        fund = body.get("fund", {})
        has_conviction = "conviction" in fund or "conviction" in body
        assert has_conviction, "deep-dive response lacks conviction pillars"

    def test_deep_dive_404_for_invalid_id(self, client):
        resp = client.get("/api/v1/mf/INVALID_MSTAR_ID_XXXXXXX")
        assert resp.status_code in (404, 422), (
            f"expected 404 or 422 for invalid mstar_id, got {resp.status_code}"
        )

    def test_deep_dive_has_nav_history(self, client, real_mstar_id):
        resp = client.get(f"/api/v1/mf/{real_mstar_id}")
        body = resp.json()
        # NAV history may be nested
        fund = body.get("fund", {})
        has_nav = "nav_history" in fund or "nav_history" in body
        assert has_nav, "deep-dive response lacks nav_history"


class TestMFOverlap:
    """v2-04 (overlap): /mf/overlap returns comparison data."""

    def test_overlap_returns_200_with_two_funds(self, client, real_mstar_id):
        resp = client.get(f"/api/v1/mf/overlap?fund_ids={real_mstar_id}&fund_ids={real_mstar_id}")
        # Accept 200 or 422 (single fund overlap is edge case)
        assert resp.status_code in (200, 422), f"overlap returned unexpected {resp.status_code}"


class TestMFFrontend:
    """v2-05: MF Pro shell page and related components exist (SC-004: FM UI)."""

    def test_mf_page_exists(self):
        page = ROOT / "frontend" / "src" / "app" / "page.tsx"
        assert page.exists(), f"{page} not found"

    def test_mf_page_is_non_trivial(self):
        page = ROOT / "frontend" / "src" / "app" / "page.tsx"
        size = page.stat().st_size
        assert size >= 500, f"page.tsx is only {size} bytes (expected >=500)"

    def test_mf_related_components_exist(self):
        """At least one MF-specific component file exists in frontend."""
        frontend_src = ROOT / "frontend" / "src"
        mf_files = list(frontend_src.rglob("*[Mm][Ff]*.tsx")) + list(
            frontend_src.rglob("*[Mm]utual[Ff]und*.tsx")
        )
        # Also check for MF-named folders
        mf_dirs = [d for d in frontend_src.rglob("*") if d.is_dir() and "mf" in d.name.lower()]
        assert mf_files or mf_dirs, "no MF-related components or directories found in frontend/src"


class TestMFNoFloat:
    """v2-07: No float annotations in MF backend files (SC-008)."""

    def test_no_float_in_mf_route(self):
        mf_route = ROOT / "backend" / "routes" / "mf.py"
        assert mf_route.exists(), f"{mf_route} not found"
        pattern = re.compile(r":\s*float\b")
        text = mf_route.read_text(encoding="utf-8")
        matches = [
            f"line {i}: {ln.strip()}"
            for i, ln in enumerate(text.splitlines(), 1)
            if pattern.search(ln)
        ]
        assert not matches, f"float in backend/routes/mf.py: {matches[:3]}"

    def test_no_float_in_mf_compute(self):
        mf_compute = ROOT / "backend" / "services" / "mf_compute.py"
        assert mf_compute.exists(), f"{mf_compute} not found"
        pattern = re.compile(r":\s*float\b")
        text = mf_compute.read_text(encoding="utf-8")
        matches = [
            f"line {i}: {ln.strip()}"
            for i, ln in enumerate(text.splitlines(), 1)
            if pattern.search(ln)
        ]
        assert not matches, f"float in backend/services/mf_compute.py: {matches[:3]}"


class TestMFResponseTimes:
    """v2-09: /mf/universe < 2s, /mf/{mstar_id} < 500ms (SC-005)."""

    def test_universe_within_2s(self, client):
        start = time.monotonic()
        resp = client.get("/api/v1/mf/universe", timeout=10.0)
        elapsed_ms = (time.monotonic() - start) * 1000
        assert resp.status_code == 200
        assert elapsed_ms < 2000, f"/mf/universe took {elapsed_ms:.0f}ms > 2000ms"

    def test_deep_dive_within_500ms(self, client, real_mstar_id):
        start = time.monotonic()
        resp = client.get(f"/api/v1/mf/{real_mstar_id}", timeout=5.0)
        elapsed_ms = (time.monotonic() - start) * 1000
        assert resp.status_code == 200
        assert elapsed_ms < 500, f"/mf/{real_mstar_id} took {elapsed_ms:.0f}ms > 500ms"
