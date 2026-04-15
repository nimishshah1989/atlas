"""Unit tests for V5 criteria YAML and validate-v5.py importability.

Tests:
- v5-criteria.yaml loads and validates against expected structure
- Each criterion has required fields (id, title, check)
- All 12 criteria IDs (v5-01..v5-12) are present
- Every python_callable dotted_path is importable and callable
- The YAML is valid and has version/slice/source/criteria keys
- validate-v5.py is importable (module-level sanity)
- quality_product_checks_v5 is importable and has expected functions
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
CRITERIA_PATH = ROOT / "docs" / "specs" / "v5-criteria.yaml"
VALIDATE_SCRIPT = ROOT / "scripts" / "validate-v5.py"
CHECKS_MODULE = ROOT / ".quality" / "quality_product_checks_v5.py"

EXPECTED_CRITERIA_IDS = [f"v5-{i:02d}" for i in range(1, 13)]

REQUIRED_CRITERION_FIELDS = ["id", "title", "check"]
REQUIRED_CHECK_FIELDS = ["type"]


class TestV5CriteriaYAML:
    """v5-criteria.yaml structure and content tests."""

    @pytest.fixture(scope="class")
    def criteria_data(self):
        pytest.importorskip("yaml", reason="pyyaml required")
        import yaml

        assert CRITERIA_PATH.exists(), f"{CRITERIA_PATH} not found"
        data = yaml.safe_load(CRITERIA_PATH.read_text())
        assert data is not None
        return data

    def test_top_level_keys_present(self, criteria_data):
        for key in ("version", "slice", "source", "criteria"):
            assert key in criteria_data, f"missing top-level key: {key}"

    def test_slice_is_v5(self, criteria_data):
        assert criteria_data["slice"] == "V5"

    def test_version_is_1(self, criteria_data):
        assert criteria_data["version"] == "1"

    def test_has_twelve_criteria(self, criteria_data):
        criteria = criteria_data["criteria"]
        assert len(criteria) == 12, f"expected 12 criteria, got {len(criteria)}"

    def test_each_criterion_has_required_fields(self, criteria_data):
        for c in criteria_data["criteria"]:
            for field in REQUIRED_CRITERION_FIELDS:
                assert field in c, f"criterion {c.get('id', '?')} missing {field!r}"

    def test_each_check_has_type(self, criteria_data):
        for c in criteria_data["criteria"]:
            check = c["check"]
            assert "type" in check, f"criterion {c['id']} check missing 'type'"

    def test_check_types_are_known(self, criteria_data):
        known_types = {"http_contract", "sql_count", "python_callable", "file_exists"}
        for c in criteria_data["criteria"]:
            ct = c["check"]["type"]
            assert ct in known_types, f"criterion {c['id']} uses unknown check type: {ct!r}"

    def test_criterion_ids_are_sequential(self, criteria_data):
        ids = [c["id"] for c in criteria_data["criteria"]]
        expected = EXPECTED_CRITERIA_IDS
        assert ids == expected, f"IDs not sequential: {ids}"

    def test_all_criteria_have_severity(self, criteria_data):
        valid = {"critical", "high", "medium", "low"}
        for c in criteria_data["criteria"]:
            sev = c.get("severity")
            assert sev in valid, f"criterion {c['id']} has invalid severity: {sev!r}"

    def test_python_callable_dotted_paths_have_module(self, criteria_data):
        for c in criteria_data["criteria"]:
            check = c["check"]
            if check["type"] == "python_callable":
                dp = check.get("dotted_path", "")
                assert "." in dp, f"criterion {c['id']} dotted_path lacks module: {dp!r}"
                module, _, func = dp.rpartition(".")
                assert module, f"criterion {c['id']} dotted_path has empty module"
                assert func, f"criterion {c['id']} dotted_path has empty function"

    def test_sql_count_has_query_and_min(self, criteria_data):
        for c in criteria_data["criteria"]:
            check = c["check"]
            if check["type"] == "sql_count":
                assert "query" in check, f"criterion {c['id']} sql_count missing query"
                assert "min" in check, f"criterion {c['id']} sql_count missing min"
                assert isinstance(check["min"], int), (
                    f"criterion {c['id']} sql_count min must be int"
                )

    def test_all_twelve_ids_present(self, criteria_data):
        ids = [c["id"] for c in criteria_data["criteria"]]
        for expected_id in EXPECTED_CRITERIA_IDS:
            assert expected_id in ids, f"Expected criterion ID {expected_id} not found"


class TestValidateV5Script:
    """validate-v5.py importability and structure."""

    def test_script_exists(self):
        assert VALIDATE_SCRIPT.exists(), f"{VALIDATE_SCRIPT} not found"

    def test_script_has_main_guard(self):
        content = VALIDATE_SCRIPT.read_text()
        assert '__name__ == "__main__"' in content, "missing __name__ guard"

    def test_script_references_v5_criteria(self):
        content = VALIDATE_SCRIPT.read_text()
        assert "v5-criteria.yaml" in content, "script should reference v5-criteria.yaml"

    def test_script_importable_via_spec(self):
        """Load validate-v5.py as a module without executing main()."""
        spec = importlib.util.spec_from_file_location("validate_v5", VALIDATE_SCRIPT)
        assert spec is not None
        assert spec.loader is not None
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        assert hasattr(mod, "main"), "validate-v5.py must have a main() function"

    def test_script_main_is_callable(self):
        spec = importlib.util.spec_from_file_location("validate_v5_callable", VALIDATE_SCRIPT)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        assert callable(mod.main)


class TestQualityProductChecksV5:
    """quality_product_checks_v5.py importability and function presence."""

    @pytest.fixture(scope="class")
    def checks_module(self):
        assert CHECKS_MODULE.exists(), f"{CHECKS_MODULE} not found"
        quality_dir = str(ROOT / ".quality")
        if quality_dir not in sys.path:
            sys.path.insert(0, quality_dir)
        import quality_product_checks_v5 as m

        return m

    def test_module_importable(self, checks_module):
        assert checks_module is not None

    def test_check_intelligence_findings_exists(self, checks_module):
        assert hasattr(checks_module, "check_intelligence_findings_endpoint")
        assert callable(checks_module.check_intelligence_findings_endpoint)

    def test_check_intelligence_search_exists(self, checks_module):
        assert hasattr(checks_module, "check_intelligence_search_endpoint")
        assert callable(checks_module.check_intelligence_search_endpoint)

    def test_check_global_briefing_exists(self, checks_module):
        assert hasattr(checks_module, "check_global_briefing_endpoint")
        assert callable(checks_module.check_global_briefing_endpoint)

    def test_check_global_regime_exists(self, checks_module):
        assert hasattr(checks_module, "check_global_regime_endpoint")
        assert callable(checks_module.check_global_regime_endpoint)

    def test_check_global_rs_heatmap_exists(self, checks_module):
        assert hasattr(checks_module, "check_global_rs_heatmap_endpoint")
        assert callable(checks_module.check_global_rs_heatmap_endpoint)

    def test_check_v5_no_float_exists(self, checks_module):
        assert hasattr(checks_module, "check_v5_no_float")
        assert callable(checks_module.check_v5_no_float)

    def test_check_v5_no_print_exists(self, checks_module):
        assert hasattr(checks_module, "check_v5_no_print")
        assert callable(checks_module.check_v5_no_print)

    def test_check_cost_ledger_budget_exists(self, checks_module):
        assert hasattr(checks_module, "check_cost_ledger_budget")
        assert callable(checks_module.check_cost_ledger_budget)

    def test_check_v5_no_float_returns_tuple(self, checks_module):
        """check_v5_no_float does not need a live backend — test it directly."""
        result = checks_module.check_v5_no_float()
        assert isinstance(result, tuple), "must return tuple"
        assert len(result) == 2, "must return (bool, str)"
        passed, evidence = result
        assert isinstance(passed, bool)
        assert isinstance(evidence, str)

    def test_check_v5_no_float_passes_for_v5_files(self, checks_module):
        """V5 backend files should not contain ': float' annotations."""
        passed, evidence = checks_module.check_v5_no_float()
        assert passed, f"float detected in V5 files: {evidence}"

    def test_check_v5_no_print_returns_tuple(self, checks_module):
        """check_v5_no_print does not need a live backend — test it directly."""
        result = checks_module.check_v5_no_print()
        assert isinstance(result, tuple), "must return tuple"
        assert len(result) == 2, "must return (bool, str)"
        passed, evidence = result
        assert isinstance(passed, bool)
        assert isinstance(evidence, str)

    def test_check_v5_no_print_passes_for_v5_files(self, checks_module):
        """V5 backend files should not contain print() calls."""
        passed, evidence = checks_module.check_v5_no_print()
        assert passed, f"print() detected in V5 files: {evidence}"

    def test_check_cost_ledger_budget_returns_tuple(self, checks_module):
        result = checks_module.check_cost_ledger_budget()
        assert isinstance(result, tuple), "must return tuple"
        assert len(result) == 2, "must return (bool, str)"
        passed, evidence = result
        assert isinstance(passed, bool)
        assert isinstance(evidence, str)

    def test_check_cost_ledger_budget_passes(self, checks_module):
        """cost_ledger.py must have DAILY_BUDGET_USD and BudgetExhaustedError."""
        passed, evidence = checks_module.check_cost_ledger_budget()
        assert passed, f"cost ledger budget gate missing: {evidence}"

    def test_all_python_callables_importable(self, checks_module):
        """Every function referenced by v5-criteria.yaml python_callable checks must be callable."""
        import yaml

        criteria_path = ROOT / "docs" / "specs" / "v5-criteria.yaml"
        data = yaml.safe_load(criteria_path.read_text())
        for c in data["criteria"]:
            check = c["check"]
            if check["type"] == "python_callable":
                dp = check["dotted_path"]
                _, _, func_name = dp.rpartition(".")
                assert hasattr(checks_module, func_name), (
                    f"criterion {c['id']}: function {func_name!r} not found in module"
                )
                fn = getattr(checks_module, func_name)
                assert callable(fn), f"criterion {c['id']}: {func_name!r} is not callable"


class TestProductDimV5Integration:
    """product.py loads v5-criteria.yaml when it exists."""

    def test_v5_criteria_path_constant_exists(self):
        quality_dir = str(ROOT / ".quality")
        if quality_dir not in sys.path:
            sys.path.insert(0, quality_dir)
        import importlib

        import dimensions.product as prod

        importlib.reload(prod)
        assert hasattr(prod, "V5_CRITERIA_PATH"), (
            "V5_CRITERIA_PATH constant missing from product.py"
        )

    def test_v5_criteria_path_points_to_existing_file(self):
        quality_dir = str(ROOT / ".quality")
        if quality_dir not in sys.path:
            sys.path.insert(0, quality_dir)
        import importlib

        import dimensions.product as prod

        importlib.reload(prod)
        assert prod.V5_CRITERIA_PATH.exists(), f"V5_CRITERIA_PATH {prod.V5_CRITERIA_PATH} not found"
