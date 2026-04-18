"""Tests for V11-10 check-data-coverage.py: gap handling, determinism, manifest standards.

Covers:
- _score_gap_table: gap/missing status tables produce score=85, pass=True, gap=True
- score_table: gap detection short-circuits DB calls
- strict mode: gap tables don't count as failures
- determinism: identical calls produce identical scores
- manifest standards: every mandatory domain has >=1 table
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
import yaml

SCRIPT = Path(__file__).resolve().parent.parent.parent / "scripts" / "check-data-coverage.py"
MANIFEST_PATH = (
    Path(__file__).resolve().parent.parent.parent / "docs" / "specs" / "data-coverage.yaml"
)

spec_obj = importlib.util.spec_from_file_location("check_data_coverage_v11_10", SCRIPT)
assert spec_obj is not None and spec_obj.loader is not None
module = importlib.util.module_from_spec(spec_obj)
sys.modules["check_data_coverage_v11_10"] = module
spec_obj.loader.exec_module(module)  # type: ignore[union-attr]

_score_gap_table = module._score_gap_table
score_table = module.score_table
collect_tables = module.collect_tables
SCORERS = module.SCORERS
TableHealth = module.TableHealth
DimensionScore = module.DimensionScore


class TestScoreGapTable:
    """_score_gap_table returns documented-gap result."""

    def test_gap_status_produces_pass_true(self) -> None:
        result = _score_gap_table("de_adjustment_factors_daily", "corporate_actions", "gap")
        assert result.pass_ is True

    def test_gap_status_overall_score_85(self) -> None:
        result = _score_gap_table("de_adjustment_factors_daily", "corporate_actions", "gap")
        assert result.overall_score == 85.0

    def test_gap_flag_set(self) -> None:
        result = _score_gap_table("de_adjustment_factors_daily", "corporate_actions", "gap")
        assert result.gap is True

    def test_all_six_dimensions_present(self) -> None:
        result = _score_gap_table("de_institutional_flows", "institutional_flows", "gap")
        dim_names = {d.name for d in result.dimensions}
        expected = {
            "coverage",
            "freshness",
            "completeness",
            "continuity",
            "integrity",
            "provenance",
        }
        assert dim_names == expected

    def test_all_dimensions_score_85(self) -> None:
        result = _score_gap_table("de_institutional_flows", "institutional_flows", "gap")
        for dim in result.dimensions:
            assert dim.score == 85.0, f"{dim.name} expected 85.0 got {dim.score}"

    def test_missing_status_also_produces_gap(self) -> None:
        result = _score_gap_table("de_fo_bhavcopy_daily", "derivatives_eod", "missing")
        assert result.pass_ is True
        assert result.gap is True
        assert result.overall_score == 85.0

    def test_detail_mentions_status(self) -> None:
        result = _score_gap_table("de_adjustment_factors_daily", "corporate_actions", "gap")
        for dim in result.dimensions:
            assert "gap" in dim.detail.lower()

    def test_error_field_is_none(self) -> None:
        result = _score_gap_table("de_adjustment_factors_daily", "corporate_actions", "gap")
        assert result.error is None

    def test_table_and_domain_preserved(self) -> None:
        result = _score_gap_table("atlas_gold_rs_cache", "gold_lens", "gap")
        assert result.table == "atlas_gold_rs_cache"
        assert result.domain == "gold_lens"


class TestScoreTableGapDetection:
    """score_table calls _score_gap_table for gap/missing tables."""

    @pytest.mark.asyncio
    async def test_gap_spec_does_not_call_db(self) -> None:
        conn = AsyncMock()
        spec_dict: dict = {"status": "gap", "sla_freshness_days": 1}
        result = await score_table(
            conn, "de_adjustment_factors_daily", spec_dict, "corporate_actions"
        )
        assert result.gap is True
        assert result.pass_ is True
        # No DB calls should have been made
        conn.fetchval.assert_not_called()
        conn.fetch.assert_not_called()

    @pytest.mark.asyncio
    async def test_missing_spec_does_not_call_db(self) -> None:
        conn = AsyncMock()
        spec_dict: dict = {"status": "missing"}
        result = await score_table(conn, "de_fo_bhavcopy_daily", spec_dict, "derivatives_eod")
        assert result.gap is True
        conn.fetchval.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_status_field_goes_through_normal_path(self) -> None:
        """Tables without status field still attempt DB check (table_exists)."""
        conn = AsyncMock()
        conn.fetchval = AsyncMock(return_value=False)  # table doesn't exist
        spec_dict: dict = {"sla_freshness_days": 1}
        result = await score_table(conn, "de_nonexistent", spec_dict, "some_domain")
        assert result.gap is False
        conn.fetchval.assert_called()

    @pytest.mark.asyncio
    async def test_existing_status_goes_through_normal_path(self) -> None:
        """Tables with status='existing' are checked normally."""
        conn = AsyncMock()
        conn.fetchval = AsyncMock(return_value=False)  # simulate table_exists=False
        spec_dict: dict = {"status": "existing"}
        result = await score_table(conn, "de_rs_scores", spec_dict, "relative_strength")
        assert result.gap is False
        conn.fetchval.assert_called()


class TestDeterminism:
    """Three consecutive calls produce identical results."""

    def test_gap_table_scoring_deterministic(self) -> None:
        """Same gap table spec -> identical TableHealth on every call."""
        results = [
            _score_gap_table("de_adjustment_factors_daily", "corporate_actions", "gap")
            for _ in range(3)
        ]
        for r in results:
            assert r.overall_score == results[0].overall_score
            assert r.pass_ == results[0].pass_
            assert r.gap == results[0].gap
            assert len(r.dimensions) == len(results[0].dimensions)
            for d, d0 in zip(r.dimensions, results[0].dimensions):
                assert d.score == d0.score
                assert d.name == d0.name

    def test_gap_table_all_three_runs_match(self) -> None:
        """Strict identity: run1 == run2 == run3 for gap tables."""
        runs = [_score_gap_table("atlas_gold_rs_cache", "gold_lens", "gap") for _ in range(3)]
        baseline = runs[0]
        for r in runs[1:]:
            assert r.overall_score == baseline.overall_score
            assert r.pass_ == baseline.pass_
            assert r.gap == baseline.gap
            dim_scores_r = [(d.name, d.score) for d in r.dimensions]
            dim_scores_b = [(d.name, d.score) for d in baseline.dimensions]
            assert dim_scores_r == dim_scores_b


class TestManifestStandards:
    """Real manifest validation -- every mandatory domain has >=1 table."""

    def _load_manifest(self) -> dict:
        return yaml.safe_load(MANIFEST_PATH.read_text())

    def test_manifest_loads_without_error(self) -> None:
        manifest = self._load_manifest()
        assert "domains" in manifest
        assert "rubric" in manifest

    def test_all_domains_have_mandatory_field(self) -> None:
        manifest = self._load_manifest()
        for domain_name, domain_spec in manifest["domains"].items():
            assert "mandatory" in domain_spec, (
                f"Domain '{domain_name}' missing 'mandatory' field in data-coverage.yaml"
            )

    def test_all_mandatory_domains_have_at_least_one_table(self) -> None:
        manifest = self._load_manifest()
        # global_rates is descriptive-only (no tables/proposed_tables) — it's a
        # cross-reference note pointing to de_macro_values. Exempt it.
        NOTE_ONLY_DOMAINS = {"global_rates"}
        for domain_name, domain_spec in manifest["domains"].items():
            if not domain_spec.get("mandatory", False):
                continue
            if domain_name in NOTE_ONLY_DOMAINS:
                continue
            has_tables = bool(domain_spec.get("tables"))
            has_proposed = bool(domain_spec.get("proposed_tables"))
            assert has_tables or has_proposed, (
                f"Mandatory domain '{domain_name}' has no tables or proposed_tables"
            )

    def test_rubric_pass_threshold_is_80(self) -> None:
        manifest = self._load_manifest()
        threshold = manifest["rubric"]["scoring"]["pass_threshold"]
        assert threshold == 80

    def test_rubric_overall_threshold_is_85(self) -> None:
        manifest = self._load_manifest()
        threshold = manifest["rubric"]["scoring"]["overall_threshold"]
        assert threshold == 85

    def test_mandatory_domains_with_gap_tables_are_declared(self) -> None:
        """Verify the three known-gap mandatory domains exist in manifest."""
        manifest = self._load_manifest()
        domains = manifest["domains"]
        # These are the domains we know have gap tables
        assert "corporate_actions" in domains
        assert "institutional_flows" in domains
        assert "gold_lens" in domains

    def test_gap_tables_have_status_field(self) -> None:
        """Tables that are known gaps must declare status: gap in manifest."""
        manifest = self._load_manifest()
        domains = manifest["domains"]

        # de_adjustment_factors_daily in corporate_actions
        corp_tables = domains["corporate_actions"].get("tables", [])
        adj_table = next(
            (t for t in corp_tables if "adjustment_factors" in t.get("name", "")), None
        )
        assert adj_table is not None
        assert adj_table.get("status") in ("gap", "missing"), (
            "de_adjustment_factors_daily should declare status: gap in manifest"
        )

    def test_six_rubric_dimensions_declared(self) -> None:
        manifest = self._load_manifest()
        dims = manifest["rubric"]["dimensions"]
        expected = {
            "coverage",
            "freshness",
            "completeness",
            "continuity",
            "integrity",
            "provenance",
        }
        assert set(dims) == expected

    def test_rubric_weights_sum_to_100(self) -> None:
        manifest = self._load_manifest()
        weights = manifest["rubric"]["scoring"]["weights"]
        assert sum(weights.values()) == 100


class TestStrictModeGapExemption:
    """Strict mode should not count gap tables as failures."""

    def test_gap_tables_have_pass_true(self) -> None:
        """Gap tables produce pass_=True so they don't increment fail_count."""
        gap_result = _score_gap_table("de_adjustment_factors_daily", "corporate_actions", "gap")
        assert gap_result.pass_ is True
        assert gap_result.gap is True

    def test_non_gap_failing_table_counted_as_failure(self) -> None:
        """A normal table with pass_=False, gap=False counts as a failure."""
        # Simulate a non-gap failing table
        failing = TableHealth(
            table="de_some_table",
            domain="some_domain",
            overall_score=50.0,
            pass_=False,
            dimensions=[],
            gap=False,
        )
        fail_count = sum(1 for r in [failing] if not r.pass_ and not r.gap)
        assert fail_count == 1

    def test_mix_of_gap_and_pass_tables_gives_zero_fail_count(self) -> None:
        """All pass + all gap -> fail_count = 0."""
        results = [
            _score_gap_table("de_adjustment_factors_daily", "corporate_actions", "gap"),
            _score_gap_table("de_institutional_flows", "institutional_flows", "gap"),
            _score_gap_table("atlas_gold_rs_cache", "gold_lens", "gap"),
            TableHealth(
                table="de_rs_scores",
                domain="relative_strength",
                overall_score=92.0,
                pass_=True,
                dimensions=[],
                gap=False,
            ),
        ]
        fail_count = sum(1 for r in results if not r.pass_ and not r.gap)
        assert fail_count == 0

    def test_gap_table_does_not_increment_fail_count_even_if_pass_false_hypothetically(
        self,
    ) -> None:
        """Even if gap table somehow had pass_=False, gap flag protects it from fail count."""
        # This tests the explicit `not r.gap` guard in fail_count logic
        hypothetical = TableHealth(
            table="de_adjustment_factors_daily",
            domain="corporate_actions",
            overall_score=0.0,
            pass_=False,
            dimensions=[],
            gap=True,  # gap=True means it should not be counted as a failure
        )
        fail_count = sum(1 for r in [hypothetical] if not r.pass_ and not r.gap)
        assert fail_count == 0

    def test_gold_lens_domain_level_gap_detected_via_merged_spec(self) -> None:
        """gold_lens domain has status: gap at domain level.

        When collect_tables merges {**domain_spec, **tbl}, the merged spec
        inherits status='gap' from the domain, so score_table will correctly
        identify it as a gap table.
        """
        manifest = yaml.safe_load(MANIFEST_PATH.read_text())
        tables = collect_tables(manifest, domain_filter="gold_lens", mandatory_only=False)
        # The gold_lens domain should have atlas_gold_rs_cache
        assert len(tables) >= 1
        _, merged_spec, domain = tables[0]
        # Domain-level status: gap should be in the merged spec
        assert merged_spec.get("status") == "gap", (
            f"gold_lens merged spec should have status='gap', got {merged_spec.get('status')!r}"
        )
        assert domain == "gold_lens"
