"""Unit tests for scripts/check-data-coverage.py.

Tests cover pure-Python logic only — no asyncpg, no database required.
Follows the Importlib Isolation pattern (wiki) to load the standalone
script without triggering the backend package init chain.

Tested functions:
  - expand_partitioned_tables
  - collect_tables (including skip_gaps logic)
  - compute_overall
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Load the standalone script via importlib (importlib-isolation-standalone-scripts)
# ---------------------------------------------------------------------------

_SCRIPT = Path(__file__).resolve().parent.parent.parent / "scripts" / "check-data-coverage.py"

_spec = importlib.util.spec_from_file_location("check_data_coverage_v11_10", _SCRIPT)
assert _spec is not None and _spec.loader is not None, "Could not load script spec"
_mod = importlib.util.module_from_spec(_spec)
sys.modules["check_data_coverage_v11_10"] = _mod
_spec.loader.exec_module(_mod)  # type: ignore[union-attr]

expand_partitioned_tables = _mod.expand_partitioned_tables
collect_tables = _mod.collect_tables
compute_overall = _mod.compute_overall
TableHealth = _mod.TableHealth
DimensionScore = _mod.DimensionScore

# ---------------------------------------------------------------------------
# Shared test manifest
# ---------------------------------------------------------------------------

MINI_MANIFEST: dict[str, Any] = {
    "version": 1,
    "rubric": {
        "scoring": {
            "pass_threshold": 80,
            "overall_threshold": 85,
            "weights": {
                "coverage": 25,
                "freshness": 25,
                "completeness": 15,
                "continuity": 15,
                "integrity": 10,
                "provenance": 10,
            },
        }
    },
    "domains": {
        "good_domain": {
            "mandatory": True,
            "tables": [{"name": "de_good_table"}],
        },
        "gap_domain": {
            "mandatory": True,
            "status": "gap",
            "tables": [{"name": "de_gap_domain_table"}],
        },
        "mixed_domain": {
            "mandatory": True,
            "tables": [
                {"name": "de_good_table_2"},
                {"name": "de_gap_table", "status": "gap"},
            ],
        },
        "optional_domain": {
            "mandatory": False,
            "tables": [{"name": "de_optional_table"}],
        },
        "partitioned_domain": {
            "mandatory": True,
            "tables": [{"name": "de_part_y{YEAR}", "years": [2024, 2026]}],
        },
    },
}

# ─── TestExpandPartitionedTables ─────────────────────────────────────────


class TestExpandPartitionedTables:
    """Tests for expand_partitioned_tables()."""

    def test_non_partitioned_returns_single_element(self) -> None:
        """A table name without {YEAR} returns exactly itself."""
        result = expand_partitioned_tables({"name": "de_rs_scores"})
        assert result == ["de_rs_scores"]

    def test_year_range_expands_all_years(self) -> None:
        """years: [2024, 2026] → 3 tables (inclusive)."""
        result = expand_partitioned_tables({"name": "de_part_y{YEAR}", "years": [2024, 2026]})
        assert result == ["de_part_y2024", "de_part_y2025", "de_part_y2026"]

    def test_year_range_single_year(self) -> None:
        """years: [2025, 2025] → exactly 1 table."""
        result = expand_partitioned_tables({"name": "de_part_y{YEAR}", "years": [2025, 2025]})
        assert result == ["de_part_y2025"]

    def test_missing_years_key_returns_template(self) -> None:
        """No years key → return template name unchanged."""
        result = expand_partitioned_tables({"name": "de_mf_nav_y{YEAR}"})
        assert result == ["de_mf_nav_y{YEAR}"]

    def test_empty_years_list_returns_template(self) -> None:
        """Empty years list → return template name unchanged."""
        result = expand_partitioned_tables({"name": "de_mf_nav_y{YEAR}", "years": []})
        assert result == ["de_mf_nav_y{YEAR}"]

    def test_wrong_years_length_returns_template(self) -> None:
        """years with length != 2 → return template name unchanged."""
        result = expand_partitioned_tables(
            {"name": "de_mf_nav_y{YEAR}", "years": [2024, 2025, 2026]}
        )
        assert result == ["de_mf_nav_y{YEAR}"]

    def test_year_names_contain_correct_suffix(self) -> None:
        """Each resolved name ends with the year string."""
        result = expand_partitioned_tables(
            {"name": "de_equity_ohlcv_y{YEAR}", "years": [2022, 2024]}
        )
        assert result == [
            "de_equity_ohlcv_y2022",
            "de_equity_ohlcv_y2023",
            "de_equity_ohlcv_y2024",
        ]


# ─── TestCollectTables ───────────────────────────────────────────────────


class TestCollectTables:
    """Tests for collect_tables() — filtering and skip_gaps logic."""

    def test_no_filter_includes_all_domains(self) -> None:
        """Without any filters, all domains are included."""
        tables = collect_tables(MINI_MANIFEST, domain_filter=None, mandatory_only=False)
        domain_names = {t[2] for t in tables}
        assert "good_domain" in domain_names
        assert "gap_domain" in domain_names
        assert "mixed_domain" in domain_names
        assert "optional_domain" in domain_names
        assert "partitioned_domain" in domain_names

    def test_mandatory_only_excludes_non_mandatory_domains(self) -> None:
        """mandatory_only=True skips domains with mandatory=False."""
        tables = collect_tables(MINI_MANIFEST, domain_filter=None, mandatory_only=True)
        domain_names = {t[2] for t in tables}
        assert "optional_domain" not in domain_names
        assert "good_domain" in domain_names

    def test_mandatory_only_keeps_gap_domains_by_default(self) -> None:
        """mandatory_only=True without skip_gaps still includes gap domains."""
        tables = collect_tables(
            MINI_MANIFEST, domain_filter=None, mandatory_only=True, skip_gaps=False
        )
        domain_names = {t[2] for t in tables}
        # gap_domain has mandatory=True, so it's included when skip_gaps=False
        assert "gap_domain" in domain_names

    def test_skip_gaps_excludes_gap_domains(self) -> None:
        """skip_gaps=True removes entire domains with status='gap'."""
        tables = collect_tables(
            MINI_MANIFEST, domain_filter=None, mandatory_only=True, skip_gaps=True
        )
        domain_names = {t[2] for t in tables}
        # gap_domain has domain-level status='gap' → excluded
        assert "gap_domain" not in domain_names
        assert "good_domain" in domain_names

    def test_skip_gaps_removes_gap_tables_within_mandatory_domain(self) -> None:
        """skip_gaps=True removes gap-status tables inside a mandatory domain."""
        tables = collect_tables(
            MINI_MANIFEST, domain_filter=None, mandatory_only=True, skip_gaps=True
        )
        table_names = {t[0] for t in tables}
        # mixed_domain has one good and one gap table
        assert "de_good_table_2" in table_names
        assert "de_gap_table" not in table_names

    def test_skip_gaps_false_includes_gap_tables_in_mandatory_domain(self) -> None:
        """skip_gaps=False keeps gap-status tables in mandatory domains."""
        tables = collect_tables(
            MINI_MANIFEST, domain_filter=None, mandatory_only=True, skip_gaps=False
        )
        table_names = {t[0] for t in tables}
        assert "de_gap_table" in table_names
        assert "de_good_table_2" in table_names

    def test_domain_filter_limits_to_single_domain(self) -> None:
        """domain_filter='good_domain' returns only tables from that domain."""
        tables = collect_tables(MINI_MANIFEST, domain_filter="good_domain")
        domain_names = {t[2] for t in tables}
        assert domain_names == {"good_domain"}
        table_names = {t[0] for t in tables}
        assert table_names == {"de_good_table"}

    def test_partitioned_domain_expands_all_years(self) -> None:
        """Partitioned tables in mandatory domain expand to all years."""
        tables = collect_tables(
            MINI_MANIFEST, domain_filter="partitioned_domain", mandatory_only=True
        )
        table_names = {t[0] for t in tables}
        assert "de_part_y2024" in table_names
        assert "de_part_y2025" in table_names
        assert "de_part_y2026" in table_names

    def test_mandatory_only_default_includes_domain_without_mandatory_field(self) -> None:
        """Domain without explicit mandatory field defaults to True (legacy compat)."""
        manifest: dict[str, Any] = {
            "domains": {
                "legacy_domain": {
                    # no 'mandatory' key → defaults to True
                    "tables": [{"name": "de_legacy"}],
                }
            }
        }
        tables = collect_tables(manifest, domain_filter=None, mandatory_only=True)
        domain_names = {t[2] for t in tables}
        assert "legacy_domain" in domain_names


# ─── TestComputeOverall ──────────────────────────────────────────────────


class TestComputeOverall:
    """Tests for compute_overall() — scoring and pass/fail logic."""

    WEIGHTS = {
        "coverage": 25,
        "freshness": 25,
        "completeness": 15,
        "continuity": 15,
        "integrity": 10,
        "provenance": 10,
    }

    def _make_health(self, score: float, names: list[str] | None = None) -> TableHealth:
        """Create a TableHealth with all dims at the given score."""
        dim_names = names or list(self.WEIGHTS.keys())
        dims = [DimensionScore(name=n, score=score, detail="", raw={}) for n in dim_names]
        return TableHealth(
            table="test_table",
            domain="test_domain",
            overall_score=0.0,
            pass_=False,
            dimensions=dims,
        )

    def test_all_dims_at_90_passes(self) -> None:
        """All dims at 90 → overall=90.0, pass_=True."""
        health = self._make_health(90.0)
        compute_overall(health, self.WEIGHTS, pass_floor=80.0, overall_floor=85.0)
        assert health.overall_score == 90.0
        assert health.pass_ is True

    def test_one_dim_below_floor_fails(self) -> None:
        """One dim at 70 → per-dim check fails, pass_=False even if overall ≥ 85."""
        dims = [
            DimensionScore(name="coverage", score=90.0, detail="", raw={}),
            DimensionScore(name="freshness", score=70.0, detail="", raw={}),  # below floor
            DimensionScore(name="completeness", score=90.0, detail="", raw={}),
            DimensionScore(name="continuity", score=90.0, detail="", raw={}),
            DimensionScore(name="integrity", score=90.0, detail="", raw={}),
            DimensionScore(name="provenance", score=90.0, detail="", raw={}),
        ]
        health = TableHealth(table="t", domain="d", overall_score=0.0, pass_=False, dimensions=dims)
        compute_overall(health, self.WEIGHTS, pass_floor=80.0, overall_floor=85.0)
        # overall = (90*25 + 70*25 + 90*15 + 90*15 + 90*10 + 90*10) / 100
        #         = (2250 + 1750 + 1350 + 1350 + 900 + 900) / 100 = 8500/100 = 85.0
        assert health.overall_score == 85.0
        assert health.pass_ is False  # one dim below floor

    def test_overall_below_threshold_fails(self) -> None:
        """overall < 85 → pass_=False even if all dims above per-dim floor."""
        health = self._make_health(82.0)
        compute_overall(health, self.WEIGHTS, pass_floor=80.0, overall_floor=85.0)
        # overall = 82.0, which is < 85.0 → fail
        assert health.pass_ is False
        assert health.overall_score == 82.0

    def test_overall_at_threshold_passes(self) -> None:
        """overall == 85.0 (exactly at threshold) and all dims ≥ 80 → pass_=True."""
        # Mix: coverage=85, freshness=85, rest=85 → weighted avg = 85
        health = self._make_health(85.0)
        compute_overall(health, self.WEIGHTS, pass_floor=80.0, overall_floor=85.0)
        assert health.overall_score == 85.0
        assert health.pass_ is True

    def test_empty_dimensions_gives_zero_score(self) -> None:
        """No dimensions → overall=0.0, pass_=True (vacuously — no dims failed)."""
        health = TableHealth(table="t", domain="d", overall_score=0.0, pass_=False, dimensions=[])
        compute_overall(health, self.WEIGHTS, pass_floor=80.0, overall_floor=85.0)
        assert health.overall_score == 0.0
        # all() of empty is True, but overall=0 < 85 → pass_=False
        assert health.pass_ is False

    def test_compute_overall_mutates_in_place(self) -> None:
        """compute_overall modifies the TableHealth object in place."""
        health = self._make_health(95.0)
        assert health.overall_score == 0.0
        assert health.pass_ is False
        compute_overall(health, self.WEIGHTS, pass_floor=80.0, overall_floor=85.0)
        assert health.overall_score == 95.0
        assert health.pass_ is True

    def test_zero_weight_dim_does_not_affect_score(self) -> None:
        """A dim with weight=0 contributes nothing to overall score."""
        weights_no_provenance = {k: v for k, v in self.WEIGHTS.items() if k != "provenance"}
        weights_no_provenance["provenance"] = 0
        dims = [
            DimensionScore(name="coverage", score=100.0, detail="", raw={}),
            DimensionScore(name="freshness", score=100.0, detail="", raw={}),
            DimensionScore(name="completeness", score=100.0, detail="", raw={}),
            DimensionScore(name="continuity", score=100.0, detail="", raw={}),
            DimensionScore(name="integrity", score=100.0, detail="", raw={}),
            DimensionScore(name="provenance", score=0.0, detail="", raw={}),  # weight=0
        ]
        health = TableHealth(table="t", domain="d", overall_score=0.0, pass_=False, dimensions=dims)
        compute_overall(health, weights_no_provenance, pass_floor=80.0, overall_floor=85.0)
        # provenance dim score=0 but weight=0, so overall = 100
        # BUT per_dim_pass checks all dims including provenance score < 80 → fail
        assert health.overall_score == 100.0
        assert health.pass_ is False  # provenance score 0 < floor 80


# ─── Integration: collect_tables + real manifest ─────────────────────────


class TestCollectTablesWithRealManifest:
    """Smoke tests against the real data-coverage.yaml manifest."""

    def _load_real_manifest(self) -> dict[str, Any]:
        import yaml

        manifest_path = (
            Path(__file__).resolve().parent.parent.parent / "docs" / "specs" / "data-coverage.yaml"
        )
        return yaml.safe_load(manifest_path.read_text())  # type: ignore[no-any-return]

    def test_mandatory_only_skip_gaps_excludes_known_gap_domains(self) -> None:
        """gold_lens + institutional_flows domains are gaps → excluded in CI mode."""
        manifest = self._load_real_manifest()
        tables = collect_tables(manifest, domain_filter=None, mandatory_only=True, skip_gaps=True)
        domain_names = {t[2] for t in tables}
        # gold_lens has domain-level status='gap'
        assert "gold_lens" not in domain_names
        # institutional_flows has domain-level status='gap'
        assert "institutional_flows" not in domain_names

    def test_mandatory_only_skip_gaps_excludes_de_adjustment_factors_daily(self) -> None:
        """de_adjustment_factors_daily has table-level status='gap' → excluded."""
        manifest = self._load_real_manifest()
        tables = collect_tables(manifest, domain_filter=None, mandatory_only=True, skip_gaps=True)
        table_names = {t[0] for t in tables}
        assert "de_adjustment_factors_daily" not in table_names

    def test_mandatory_only_skip_gaps_includes_de_corporate_actions(self) -> None:
        """de_corporate_actions (no gap status) must still be included."""
        manifest = self._load_real_manifest()
        tables = collect_tables(manifest, domain_filter=None, mandatory_only=True, skip_gaps=True)
        table_names = {t[0] for t in tables}
        assert "de_corporate_actions" in table_names

    def test_no_skip_gaps_includes_gap_tables(self) -> None:
        """With skip_gaps=False, gap tables like de_institutional_flows ARE included."""
        manifest = self._load_real_manifest()
        tables = collect_tables(manifest, domain_filter=None, mandatory_only=True, skip_gaps=False)
        table_names = {t[0] for t in tables}
        assert "de_institutional_flows" in table_names
        assert "de_adjustment_factors_daily" in table_names
