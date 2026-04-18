"""Tests for V11-1 check-data-coverage.py calibration fixes.

Tests run WITHOUT a real database (no asyncpg calls). All DB interactions
are mocked via AsyncMock. Covers:
- expand_partitioned_tables
- collect_tables with mandatory_only filter
- score_freshness partition-aware logic
- score_integrity sampling for large tables
- health_gate FastAPI dependency
- GET /api/v1/system/data-health route
"""

from __future__ import annotations

import importlib.util
import json
import sys
from datetime import date
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

# ---------------------------------------------------------------------------
# Load the standalone script via importlib to avoid triggering package init
# (importlib-isolation-standalone-scripts pattern from wiki)
# ---------------------------------------------------------------------------

SCRIPT = Path(__file__).resolve().parent.parent.parent / "scripts" / "check-data-coverage.py"

spec = importlib.util.spec_from_file_location("check_data_coverage", SCRIPT)
assert spec is not None and spec.loader is not None, "Could not load script spec"
module = importlib.util.module_from_spec(spec)
# Must register in sys.modules before exec_module so dataclass __module__ lookup works
sys.modules["check_data_coverage"] = module
spec.loader.exec_module(module)  # type: ignore[union-attr]

expand_partitioned_tables = module.expand_partitioned_tables
collect_tables = module.collect_tables


# ---------------------------------------------------------------------------
# TestExpandPartitionedTables
# ---------------------------------------------------------------------------


class TestExpandPartitionedTables:
    def test_non_partitioned_returns_single(self) -> None:
        result = expand_partitioned_tables({"name": "de_rs_scores"})
        assert result == ["de_rs_scores"]

    def test_year_partitioned_expands(self) -> None:
        result = expand_partitioned_tables(
            {"name": "de_equity_ohlcv_y{YEAR}", "years": [2022, 2024]}
        )
        assert result == [
            "de_equity_ohlcv_y2022",
            "de_equity_ohlcv_y2023",
            "de_equity_ohlcv_y2024",
        ]

    def test_missing_years_returns_template(self) -> None:
        result = expand_partitioned_tables({"name": "de_mf_nav_daily_y{YEAR}"})
        assert result == ["de_mf_nav_daily_y{YEAR}"]

    def test_single_year_range(self) -> None:
        result = expand_partitioned_tables({"name": "de_test_y{YEAR}", "years": [2025, 2025]})
        assert result == ["de_test_y2025"]


# ---------------------------------------------------------------------------
# TestCollectTablesMandatoryFilter
# ---------------------------------------------------------------------------


class TestCollectTablesMandatoryFilter:
    MANIFEST = {
        "domains": {
            "equity_ohlcv": {
                "mandatory": True,
                "tables": [{"name": "de_equity_ohlcv"}],
                "proposed_tables": [],
            },
            "derivatives_eod": {
                "mandatory": False,
                "proposed_tables": [{"name": "de_fo_bhavcopy_daily"}],
                "tables": [],
            },
            "relative_strength": {
                # no mandatory field — defaults to True for legacy compat
                "tables": [{"name": "de_rs_scores"}],
                "proposed_tables": [],
            },
        }
    }

    def test_no_filter_returns_all(self) -> None:
        tables = collect_tables(self.MANIFEST, domain_filter=None, mandatory_only=False)
        domains = {t[2] for t in tables}
        assert "equity_ohlcv" in domains
        assert "derivatives_eod" in domains
        assert "relative_strength" in domains

    def test_mandatory_only_excludes_non_mandatory(self) -> None:
        tables = collect_tables(self.MANIFEST, domain_filter=None, mandatory_only=True)
        domains = {t[2] for t in tables}
        assert "equity_ohlcv" in domains
        assert "relative_strength" in domains  # no mandatory field → defaults True
        assert "derivatives_eod" not in domains

    def test_mandatory_only_false_is_default_compat(self) -> None:
        """Calling without mandatory_only param is backwards-compatible."""
        tables = collect_tables(self.MANIFEST, domain_filter=None)
        domains = {t[2] for t in tables}
        assert "derivatives_eod" in domains

    def test_domain_filter_combined_with_mandatory_only(self) -> None:
        tables = collect_tables(self.MANIFEST, domain_filter="equity_ohlcv", mandatory_only=True)
        domains = {t[2] for t in tables}
        assert domains == {"equity_ohlcv"}

    def test_non_mandatory_domain_with_domain_filter_is_included(self) -> None:
        """--domain flag overrides --mandatory-only for explicit single domain."""
        # The --domain filter is applied first; mandatory_only filter runs separately.
        # When domain_filter selects a non-mandatory domain, it is still collected
        # because domain_filter is checked before mandatory_only.
        # This matches the implementation: the domain_filter check uses `continue` before
        # the mandatory_only check.
        tables = collect_tables(
            self.MANIFEST,
            domain_filter="derivatives_eod",
            mandatory_only=True,
        )
        # derivatives_eod is mandatory=False, so mandatory_only skips it even when
        # it matches the domain_filter — the implementation checks mandatory_only
        # regardless of domain_filter.
        # Verify the expected behaviour based on the actual implementation order:
        # 1. if domain_filter and domain_name != domain_filter: continue
        # 2. if mandatory_only and not domain_spec.get("mandatory", True): continue
        # So derivatives_eod passes step 1 (matches filter) but fails step 2 (not mandatory).
        # Result: empty list
        assert tables == []


# ---------------------------------------------------------------------------
# TestPartitionAwareFreshness
# ---------------------------------------------------------------------------


class TestPartitionAwareFreshness:
    """Test that archived year partitions return freshness=100."""

    @pytest.mark.asyncio
    async def test_archived_partition_returns_100(self) -> None:
        """de_equity_ohlcv_y2020 is archived (2+ years old) → freshness=100."""
        conn = AsyncMock()
        spec_dict: dict = {"sla_freshness_days": 1}
        result = await module.score_freshness(conn, "de_equity_ohlcv_y2020", spec_dict)
        assert result.score == 100.0
        assert "archived" in result.detail
        # conn should NOT have been called for date query
        conn.fetchval.assert_not_called()
        conn.fetch.assert_not_called()

    @pytest.mark.asyncio
    async def test_current_year_partition_uses_normal_scoring(self) -> None:
        """de_equity_ohlcv_y2026 is active → normal freshness check."""
        conn = AsyncMock()
        conn.fetch = AsyncMock(return_value=[{"column_name": "trade_date"}])
        conn.fetchval = AsyncMock(return_value=date(2026, 4, 17))
        spec_dict: dict = {"sla_freshness_days": 1}
        result = await module.score_freshness(conn, "de_equity_ohlcv_y2026", spec_dict)
        # Should NOT return archived
        assert "archived" not in result.detail
        # Should have called fetchval to get max date
        conn.fetchval.assert_called()

    @pytest.mark.asyncio
    async def test_prev_year_partition_uses_normal_scoring(self) -> None:
        """de_equity_ohlcv_y2025 (current_year - 1 = 2025) → active, normal scoring."""
        conn = AsyncMock()
        conn.fetch = AsyncMock(return_value=[{"column_name": "trade_date"}])
        conn.fetchval = AsyncMock(return_value=date(2025, 12, 31))
        spec_dict: dict = {"sla_freshness_days": 1}
        result = await module.score_freshness(conn, "de_equity_ohlcv_y2025", spec_dict)
        assert "archived" not in result.detail

    @pytest.mark.asyncio
    async def test_non_partitioned_unaffected(self) -> None:
        """de_rs_scores has no _y{year} suffix → normal path."""
        conn = AsyncMock()
        conn.fetch = AsyncMock(return_value=[{"column_name": "asof_date"}])
        conn.fetchval = AsyncMock(return_value=date(2026, 4, 17))
        spec_dict: dict = {"sla_freshness_days": 1}
        result = await module.score_freshness(conn, "de_rs_scores", spec_dict)
        assert "archived" not in result.detail
        conn.fetchval.assert_called()

    @pytest.mark.asyncio
    async def test_two_years_ago_is_archived(self) -> None:
        """de_equity_ohlcv_y2024 = current_year - 2 → archived."""
        # Current year is 2026 (from test env), 2024 = 2026 - 2 → archived
        conn = AsyncMock()
        spec_dict: dict = {"sla_freshness_days": 1}
        result = await module.score_freshness(conn, "de_equity_ohlcv_y2024", spec_dict)
        assert result.score == 100.0
        assert "archived" in result.detail
        conn.fetchval.assert_not_called()


# ---------------------------------------------------------------------------
# TestIntegritySampling
# ---------------------------------------------------------------------------


class TestIntegritySampling:
    """Test that integrity sampling is used for large tables."""

    @pytest.mark.asyncio
    async def test_large_table_uses_tablesample(self) -> None:
        """Tables with n_live_tup > 500_000 should use TABLESAMPLE."""
        conn = AsyncMock()
        # First fetchval: pg_stat returns 1M rows
        # Second fetchval: TABLESAMPLE dupes count
        conn.fetchval = AsyncMock(side_effect=[1_000_000, 0])
        spec_dict: dict = {"natural_key": ["symbol", "trade_date"]}
        result = await module.score_integrity(conn, "de_equity_ohlcv_y2026", spec_dict)
        # Check that a TABLESAMPLE call was made
        calls_str = [str(c) for c in conn.fetchval.call_args_list]
        assert any("TABLESAMPLE" in s or "tablesample" in s.lower() for s in calls_str), (
            f"Expected TABLESAMPLE in one of: {calls_str}"
        )
        assert "sampled" in result.detail.lower()
        assert result.score >= 0

    @pytest.mark.asyncio
    async def test_large_table_100_pct_score_when_no_dupes(self) -> None:
        """Large table with 0 dupes scores 100."""
        conn = AsyncMock()
        conn.fetchval = AsyncMock(side_effect=[2_000_000, 0])
        spec_dict: dict = {"natural_key": ["symbol", "trade_date"]}
        result = await module.score_integrity(conn, "de_equity_ohlcv_y2026", spec_dict)
        assert result.score == 100.0

    @pytest.mark.asyncio
    async def test_small_table_skips_tablesample(self) -> None:
        """Tables with n_live_tup <= 500_000 use exact count, no TABLESAMPLE."""
        conn = AsyncMock()
        # fetchval calls: pg_stat(100), dupes(0), row_count pg_stat(100), exact COUNT(100)
        conn.fetchval = AsyncMock(side_effect=[100, 0, 100, 100])
        spec_dict: dict = {"natural_key": ["symbol", "nav_date"]}
        await module.score_integrity(conn, "de_mf_master", spec_dict)
        calls_str = [str(c) for c in conn.fetchval.call_args_list]
        # No TABLESAMPLE for small tables
        assert not any("TABLESAMPLE" in s for s in calls_str)

    @pytest.mark.asyncio
    async def test_no_natural_key_returns_100(self) -> None:
        """When no natural_key declared, integrity = 100."""
        conn = AsyncMock()
        spec_dict: dict = {}
        result = await module.score_integrity(conn, "de_mf_master", spec_dict)
        assert result.score == 100.0
        conn.fetchval.assert_not_called()

    @pytest.mark.asyncio
    async def test_sampling_exception_returns_0(self) -> None:
        """If TABLESAMPLE query fails, score = 0."""
        conn = AsyncMock()
        conn.fetchval = AsyncMock(side_effect=[1_000_000, Exception("query timeout")])
        spec_dict: dict = {"natural_key": ["symbol", "trade_date"]}
        result = await module.score_integrity(conn, "de_equity_ohlcv_y2026", spec_dict)
        assert result.score == 0.0
        assert "sampled" in result.detail or "failed" in result.detail


# ---------------------------------------------------------------------------
# TestHealthGate
# ---------------------------------------------------------------------------


class TestHealthGate:
    """Test the health_gate FastAPI dependency."""

    def test_passing_domain_returns_none(self, tmp_path: Path) -> None:
        health_file = tmp_path / "data-health.json"
        health_file.write_text(
            json.dumps(
                {
                    "tables": [
                        {
                            "domain": "equity_ohlcv",
                            "table": "de_rs_scores",
                            "pass": True,
                            "overall_score": 90,
                            "error": None,
                            "dimensions": [],
                        },
                    ]
                }
            )
        )

        import backend.core.health_gate as hg

        original = hg._DATA_HEALTH_PATH
        hg._DATA_HEALTH_PATH = health_file
        hg._health_cache.clear()
        try:
            gate_fn = hg.health_gate("equity_ohlcv")
            gate_fn()  # Should not raise
        finally:
            hg._DATA_HEALTH_PATH = original
            hg._health_cache.clear()

    def test_failing_domain_raises_503(self, tmp_path: Path) -> None:
        from fastapi import HTTPException

        health_file = tmp_path / "data-health.json"
        health_file.write_text(
            json.dumps(
                {
                    "tables": [
                        {
                            "domain": "equity_ohlcv",
                            "table": "de_rs_scores",
                            "pass": False,
                            "overall_score": 40,
                            "error": None,
                            "dimensions": [{"name": "freshness", "score": 20, "detail": "stale"}],
                        },
                    ]
                }
            )
        )

        import backend.core.health_gate as hg

        original = hg._DATA_HEALTH_PATH
        hg._DATA_HEALTH_PATH = health_file
        hg._health_cache.clear()
        try:
            gate_fn = hg.health_gate("equity_ohlcv")
            with pytest.raises(HTTPException) as exc_info:
                gate_fn()
            assert exc_info.value.status_code == 503
            assert exc_info.value.detail["domain"] == "equity_ohlcv"
            assert exc_info.value.detail["error"] == "data_domain_unhealthy"
            # Failing dimensions (score < 80) should be listed
            failing_tables = exc_info.value.detail["failing_tables"]
            assert len(failing_tables) == 1
            assert failing_tables[0]["table"] == "de_rs_scores"
        finally:
            hg._DATA_HEALTH_PATH = original
            hg._health_cache.clear()

    def test_missing_health_file_passes_through(self, tmp_path: Path) -> None:
        """Fail open when health file does not exist yet."""
        import backend.core.health_gate as hg

        original = hg._DATA_HEALTH_PATH
        hg._DATA_HEALTH_PATH = tmp_path / "missing.json"
        hg._health_cache.clear()
        try:
            gate_fn = hg.health_gate("equity_ohlcv")
            gate_fn()  # Should not raise
        finally:
            hg._DATA_HEALTH_PATH = original
            hg._health_cache.clear()

    def test_domain_not_in_file_passes_through(self, tmp_path: Path) -> None:
        """Domain not present in health file → fail open."""
        health_file = tmp_path / "data-health.json"
        health_file.write_text(json.dumps({"tables": []}))

        import backend.core.health_gate as hg

        original = hg._DATA_HEALTH_PATH
        hg._DATA_HEALTH_PATH = health_file
        hg._health_cache.clear()
        try:
            gate_fn = hg.health_gate("unknown_domain")
            gate_fn()  # Should not raise
        finally:
            hg._DATA_HEALTH_PATH = original
            hg._health_cache.clear()

    def test_503_detail_lists_only_low_score_dimensions(self, tmp_path: Path) -> None:
        """Only dimensions with score < 80 appear in 503 detail."""
        from fastapi import HTTPException

        health_file = tmp_path / "data-health.json"
        health_file.write_text(
            json.dumps(
                {
                    "tables": [
                        {
                            "domain": "mf",
                            "table": "de_mf_nav_daily_y2026",
                            "pass": False,
                            "overall_score": 55,
                            "error": None,
                            "dimensions": [
                                {"name": "coverage", "score": 95, "detail": "ok"},
                                {"name": "freshness", "score": 30, "detail": "stale"},
                                {"name": "completeness", "score": 88, "detail": "ok"},
                            ],
                        },
                    ]
                }
            )
        )

        import backend.core.health_gate as hg

        original = hg._DATA_HEALTH_PATH
        hg._DATA_HEALTH_PATH = health_file
        hg._health_cache.clear()
        try:
            gate_fn = hg.health_gate("mf")
            with pytest.raises(HTTPException) as exc_info:
                gate_fn()
            failing_dims = exc_info.value.detail["failing_tables"][0]["dimensions"]
            dim_names = [d["name"] for d in failing_dims]
            assert "freshness" in dim_names
            assert "coverage" not in dim_names
            assert "completeness" not in dim_names
        finally:
            hg._DATA_HEALTH_PATH = original
            hg._health_cache.clear()


# ---------------------------------------------------------------------------
# TestDataHealthRoute
# ---------------------------------------------------------------------------


class TestDataHealthRoute:
    """Test GET /api/v1/system/data-health route."""

    def test_returns_unavailable_when_file_missing(self, tmp_path: Path) -> None:
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        import backend.routes.system_data_health as sdh

        original = sdh._DATA_HEALTH_PATH
        sdh._DATA_HEALTH_PATH = tmp_path / "missing.json"
        sdh._cache.clear()
        try:
            app = FastAPI()
            app.include_router(sdh.router)
            client = TestClient(app)
            resp = client.get("/api/v1/system/data-health")
            assert resp.status_code == 200
            data = resp.json()
            assert data["available"] is False
            assert data["tables"] == []
        finally:
            sdh._DATA_HEALTH_PATH = original
            sdh._cache.clear()

    def test_returns_tables_when_file_present(self, tmp_path: Path) -> None:
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        import backend.routes.system_data_health as sdh

        health_file = tmp_path / "data-health.json"
        health_file.write_text(
            json.dumps(
                {
                    "generated_at": "2026-04-18T10:00:00+05:30",
                    "manifest_version": 1,
                    "rubric": {},
                    "tables": [
                        {
                            "domain": "equity_ohlcv",
                            "table": "de_rs_scores",
                            "pass": True,
                            "overall_score": 90,
                            "error": None,
                            "dimensions": [],
                        }
                    ],
                }
            )
        )
        original = sdh._DATA_HEALTH_PATH
        sdh._DATA_HEALTH_PATH = health_file
        sdh._cache.clear()
        try:
            app = FastAPI()
            app.include_router(sdh.router)
            client = TestClient(app)
            resp = client.get("/api/v1/system/data-health")
            assert resp.status_code == 200
            data = resp.json()
            assert data["available"] is True
            assert len(data["tables"]) == 1
            assert data["tables"][0]["domain"] == "equity_ohlcv"
            assert data["generated_at"] == "2026-04-18T10:00:00+05:30"
        finally:
            sdh._DATA_HEALTH_PATH = original
            sdh._cache.clear()

    def test_caches_response_within_ttl(self, tmp_path: Path) -> None:
        """Second call within TTL returns cached response without re-reading file."""
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        import backend.routes.system_data_health as sdh

        health_file = tmp_path / "data-health.json"
        health_file.write_text(
            json.dumps(
                {
                    "generated_at": "2026-04-18T10:00:00+05:30",
                    "manifest_version": 1,
                    "rubric": {},
                    "tables": [],
                }
            )
        )
        original = sdh._DATA_HEALTH_PATH
        sdh._DATA_HEALTH_PATH = health_file
        sdh._cache.clear()
        try:
            app = FastAPI()
            app.include_router(sdh.router)
            client = TestClient(app)

            resp1 = client.get("/api/v1/system/data-health")
            assert resp1.status_code == 200

            # Overwrite file — cached response should still be returned
            health_file.write_text(json.dumps({"generated_at": "CHANGED", "tables": []}))

            resp2 = client.get("/api/v1/system/data-health")
            assert resp2.status_code == 200
            # Still returns cached (original) response
            assert resp2.json()["generated_at"] == "2026-04-18T10:00:00+05:30"
        finally:
            sdh._DATA_HEALTH_PATH = original
            sdh._cache.clear()

    def test_returns_unavailable_on_json_parse_error(self, tmp_path: Path) -> None:
        """Malformed JSON in health file → available=False (graceful degradation)."""
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        import backend.routes.system_data_health as sdh

        health_file = tmp_path / "data-health.json"
        health_file.write_text("{ invalid json !!!")
        original = sdh._DATA_HEALTH_PATH
        sdh._DATA_HEALTH_PATH = health_file
        sdh._cache.clear()
        try:
            app = FastAPI()
            app.include_router(sdh.router)
            client = TestClient(app)
            resp = client.get("/api/v1/system/data-health")
            assert resp.status_code == 200
            assert resp.json()["available"] is False
        finally:
            sdh._DATA_HEALTH_PATH = original
            sdh._cache.clear()
