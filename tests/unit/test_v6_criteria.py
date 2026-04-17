"""Unit tests for V6 criteria YAML and validate-v6.py importability.

Tests:
- v6-criteria.yaml loads and validates against expected structure
- Each criterion has required fields (id, title, check)
- All 20 criteria IDs (v6-01..v6-20) are present
- Every python_callable dotted_path is importable and callable
- The YAML is valid and has version/slice/source/criteria keys
- validate-v6.py is importable (module-level sanity)
- quality_product_checks_v6 is importable and has expected functions
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
CRITERIA_PATH = ROOT / "docs" / "specs" / "v6-criteria.yaml"
VALIDATE_SCRIPT = ROOT / "scripts" / "validate-v6.py"
CHECKS_MODULE = ROOT / ".quality" / "quality_product_checks_v6.py"

EXPECTED_CRITERIA_IDS = [f"v6-{i:02d}" for i in range(1, 21)]  # v6-01..v6-20

REQUIRED_CRITERION_FIELDS = ["id", "title", "check"]
REQUIRED_CHECK_FIELDS = ["type"]


class TestV6CriteriaYAML:
    """v6-criteria.yaml structure and content tests."""

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

    def test_slice_is_v6(self, criteria_data):
        assert criteria_data["slice"] == "V6"

    def test_version_is_1(self, criteria_data):
        assert criteria_data["version"] == "1"

    def test_has_twenty_criteria(self, criteria_data):
        criteria = criteria_data["criteria"]
        assert len(criteria) >= 15, f"expected at least 15 criteria, got {len(criteria)}"

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

    def test_criterion_ids_are_unique(self, criteria_data):
        ids = [c["id"] for c in criteria_data["criteria"]]
        assert len(ids) == len(set(ids)), f"duplicate criterion IDs found: {ids}"

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

    def test_all_twenty_ids_present(self, criteria_data):
        ids = [c["id"] for c in criteria_data["criteria"]]
        for expected_id in EXPECTED_CRITERIA_IDS:
            assert expected_id in ids, f"Expected criterion ID {expected_id} not found"


class TestValidateV6Script:
    """validate-v6.py importability and structure."""

    def test_script_exists(self):
        assert VALIDATE_SCRIPT.exists(), f"{VALIDATE_SCRIPT} not found"

    def test_script_has_main_guard(self):
        content = VALIDATE_SCRIPT.read_text()
        assert '__name__ == "__main__"' in content, "missing __name__ guard"

    def test_script_references_v6_criteria(self):
        content = VALIDATE_SCRIPT.read_text()
        assert "v6-criteria.yaml" in content, "script should reference v6-criteria.yaml"

    def test_script_importable_via_spec(self):
        """Load validate-v6.py as a module without executing main()."""
        spec = importlib.util.spec_from_file_location("validate_v6", VALIDATE_SCRIPT)
        assert spec is not None
        assert spec.loader is not None
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        assert hasattr(mod, "main"), "validate-v6.py must have a main() function"

    def test_script_main_is_callable(self):
        spec = importlib.util.spec_from_file_location("validate_v6_callable", VALIDATE_SCRIPT)
        assert spec is not None
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        assert callable(mod.main)


class TestQualityProductChecksV6:
    """quality_product_checks_v6.py importability and function presence."""

    @pytest.fixture(scope="class")
    def checks_module(self):
        assert CHECKS_MODULE.exists(), f"{CHECKS_MODULE} not found"
        quality_dir = str(ROOT / ".quality")
        if quality_dir not in sys.path:
            sys.path.insert(0, quality_dir)
        import quality_product_checks_v6 as m

        return m

    def test_module_importable(self, checks_module):
        assert checks_module is not None

    def test_check_tv_ta_endpoint_exists(self, checks_module):
        assert hasattr(checks_module, "check_tv_ta_endpoint")
        assert callable(checks_module.check_tv_ta_endpoint)

    def test_check_tv_screener_endpoint_exists(self, checks_module):
        assert hasattr(checks_module, "check_tv_screener_endpoint")
        assert callable(checks_module.check_tv_screener_endpoint)

    def test_check_tv_fundamentals_endpoint_exists(self, checks_module):
        assert hasattr(checks_module, "check_tv_fundamentals_endpoint")
        assert callable(checks_module.check_tv_fundamentals_endpoint)

    def test_check_tv_ta_bulk_endpoint_exists(self, checks_module):
        assert hasattr(checks_module, "check_tv_ta_bulk_endpoint")
        assert callable(checks_module.check_tv_ta_bulk_endpoint)

    def test_check_tv_webhook_requires_secret_exists(self, checks_module):
        assert hasattr(checks_module, "check_tv_webhook_requires_secret")
        assert callable(checks_module.check_tv_webhook_requires_secret)

    def test_check_sync_tv_is_404_exists(self, checks_module):
        assert hasattr(checks_module, "check_sync_tv_is_404")
        assert callable(checks_module.check_sync_tv_is_404)

    def test_check_watchlists_list_endpoint_exists(self, checks_module):
        assert hasattr(checks_module, "check_watchlists_list_endpoint")
        assert callable(checks_module.check_watchlists_list_endpoint)

    def test_check_alerts_list_endpoint_exists(self, checks_module):
        assert hasattr(checks_module, "check_alerts_list_endpoint")
        assert callable(checks_module.check_alerts_list_endpoint)

    def test_check_bridge_no_httpx_exists(self, checks_module):
        assert hasattr(checks_module, "check_bridge_no_httpx")
        assert callable(checks_module.check_bridge_no_httpx)

    def test_check_tradingview_screener_pinned_exists(self, checks_module):
        assert hasattr(checks_module, "check_tradingview_screener_pinned")
        assert callable(checks_module.check_tradingview_screener_pinned)

    def test_check_v6_no_float_exists(self, checks_module):
        assert hasattr(checks_module, "check_v6_no_float")
        assert callable(checks_module.check_v6_no_float)

    def test_check_v6_no_print_exists(self, checks_module):
        assert hasattr(checks_module, "check_v6_no_print")
        assert callable(checks_module.check_v6_no_print)

    def test_check_v6_no_float_returns_tuple(self, checks_module):
        """check_v6_no_float does not need a live backend -- test it directly."""
        result = checks_module.check_v6_no_float()
        assert isinstance(result, tuple), "must return tuple"
        assert len(result) == 2, "must return (bool, str)"
        passed, evidence = result
        assert isinstance(passed, bool)
        assert isinstance(evidence, str)

    def test_check_v6_no_float_passes_for_v6_files(self, checks_module):
        """V6 backend files should not contain ': float' annotations."""
        passed, evidence = checks_module.check_v6_no_float()
        assert passed, f"float detected in V6 files: {evidence}"

    def test_check_v6_no_print_returns_tuple(self, checks_module):
        """check_v6_no_print does not need a live backend -- test it directly."""
        result = checks_module.check_v6_no_print()
        assert isinstance(result, tuple), "must return tuple"
        assert len(result) == 2, "must return (bool, str)"
        passed, evidence = result
        assert isinstance(passed, bool)
        assert isinstance(evidence, str)

    def test_check_v6_no_print_passes_for_v6_files(self, checks_module):
        """V6 backend files should not contain print() calls."""
        passed, evidence = checks_module.check_v6_no_print()
        assert passed, f"print() detected in V6 files: {evidence}"

    def test_check_bridge_no_httpx_returns_tuple(self, checks_module):
        result = checks_module.check_bridge_no_httpx()
        assert isinstance(result, tuple), "must return tuple"
        assert len(result) == 2, "must return (bool, str)"
        passed, evidence = result
        assert isinstance(passed, bool)
        assert isinstance(evidence, str)

    def test_check_bridge_no_httpx_passes(self, checks_module):
        """bridge.py must not import httpx after V6T-2 migration."""
        passed, evidence = checks_module.check_bridge_no_httpx()
        assert passed, f"httpx found in bridge.py: {evidence}"

    def test_check_tradingview_screener_pinned_returns_tuple(self, checks_module):
        result = checks_module.check_tradingview_screener_pinned()
        assert isinstance(result, tuple), "must return tuple"
        assert len(result) == 2, "must return (bool, str)"
        passed, evidence = result
        assert isinstance(passed, bool)
        assert isinstance(evidence, str)

    def test_check_tradingview_screener_pinned_passes(self, checks_module):
        """tradingview-screener must be pinned in requirements.txt."""
        passed, evidence = checks_module.check_tradingview_screener_pinned()
        assert passed, f"tradingview-screener not pinned: {evidence}"

    def test_all_python_callables_importable(self, checks_module):
        """Every function referenced by v6-criteria.yaml python_callable checks must be callable."""
        pytest.importorskip("yaml", reason="pyyaml required")
        import yaml

        criteria_path = ROOT / "docs" / "specs" / "v6-criteria.yaml"
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


class TestProductDimV6Integration:
    """product.py loads v6-criteria.yaml when it exists."""

    def test_v6_criteria_path_constant_exists(self):
        quality_dir = str(ROOT / ".quality")
        if quality_dir not in sys.path:
            sys.path.insert(0, quality_dir)
        import importlib

        import dimensions.product as prod

        importlib.reload(prod)
        assert hasattr(prod, "V6_CRITERIA_PATH"), (
            "V6_CRITERIA_PATH constant missing from product.py"
        )

    def test_v6_criteria_path_points_to_existing_file(self):
        quality_dir = str(ROOT / ".quality")
        if quality_dir not in sys.path:
            sys.path.insert(0, quality_dir)
        import importlib

        import dimensions.product as prod

        importlib.reload(prod)
        assert prod.V6_CRITERIA_PATH.exists(), f"V6_CRITERIA_PATH {prod.V6_CRITERIA_PATH} not found"
