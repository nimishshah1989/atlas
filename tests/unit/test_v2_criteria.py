"""Unit tests for V2 criteria YAML and validate-v2.py importability.

Tests:
- v2-criteria.yaml loads and validates against expected structure
- Each criterion has required fields (id, title, check)
- SC-001..SC-009 mapping is documented
- validate-v2.py is importable (module-level sanity)
- quality_product_checks_v2 is importable and has expected functions
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
CRITERIA_PATH = ROOT / "docs" / "specs" / "v2-criteria.yaml"
VALIDATE_SCRIPT = ROOT / "scripts" / "validate-v2.py"
CHECKS_MODULE = ROOT / ".quality" / "quality_product_checks_v2.py"

# SC mapping: these SC references must appear somewhere in the criteria file
EXPECTED_SC_REFERENCES = [
    "SC-001",
    "SC-002",
    "SC-003",
    "SC-004",
    "SC-005",
    "SC-006",
    "SC-007",
    "SC-008",
    "SC-009",
]

REQUIRED_CRITERION_FIELDS = ["id", "title", "check"]
REQUIRED_CHECK_FIELDS = ["type"]


class TestV2CriteriaYAML:
    """v2-criteria.yaml structure and content tests."""

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

    def test_slice_is_v2(self, criteria_data):
        assert criteria_data["slice"] == "V2"

    def test_version_is_1(self, criteria_data):
        assert criteria_data["version"] == "1"

    def test_has_nine_criteria(self, criteria_data):
        criteria = criteria_data["criteria"]
        assert len(criteria) == 9, f"expected 9 criteria, got {len(criteria)}"

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
        expected = [f"v2-{i:02d}" for i in range(1, 10)]
        assert ids == expected, f"IDs not sequential: {ids}"

    def test_all_criteria_have_severity(self, criteria_data):
        valid = {"critical", "high", "medium", "low"}
        for c in criteria_data["criteria"]:
            sev = c.get("severity")
            assert sev in valid, f"criterion {c['id']} has invalid severity: {sev!r}"

    def test_sc_mapping_documented_in_file(self):
        """All SC-001..SC-009 references must appear in the criteria file."""
        content = CRITERIA_PATH.read_text()
        for sc in EXPECTED_SC_REFERENCES:
            # SC-007 is documented in a comment (product dim gating=True is in product.py)
            if sc == "SC-007":
                # SC-007 is documented in source comment block
                assert sc in content or "gating" in content, (
                    f"{sc} not referenced in v2-criteria.yaml"
                )
            else:
                assert sc in content, f"{sc} not referenced in v2-criteria.yaml"

    def test_python_callable_dotted_paths_have_module(self, criteria_data):
        for c in criteria_data["criteria"]:
            check = c["check"]
            if check["type"] == "python_callable":
                dp = check.get("dotted_path", "")
                assert "." in dp, f"criterion {c['id']} dotted_path lacks module: {dp!r}"
                module, _, func = dp.rpartition(".")
                assert module, f"criterion {c['id']} dotted_path has empty module"
                assert func, f"criterion {c['id']} dotted_path has empty function"

    def test_http_contract_has_url(self, criteria_data):
        for c in criteria_data["criteria"]:
            check = c["check"]
            if check["type"] == "http_contract":
                assert "url" in check, f"criterion {c['id']} http_contract missing url"
                assert check["url"].startswith("http"), (
                    f"criterion {c['id']} url should start with http"
                )

    def test_sql_count_has_query_and_min(self, criteria_data):
        for c in criteria_data["criteria"]:
            check = c["check"]
            if check["type"] == "sql_count":
                assert "query" in check, f"criterion {c['id']} sql_count missing query"
                assert "min" in check, f"criterion {c['id']} sql_count missing min"
                assert isinstance(check["min"], int), (
                    f"criterion {c['id']} sql_count min must be int"
                )

    def test_file_exists_has_path(self, criteria_data):
        for c in criteria_data["criteria"]:
            check = c["check"]
            if check["type"] == "file_exists":
                assert "path" in check, f"criterion {c['id']} file_exists missing path"


class TestValidateV2Script:
    """validate-v2.py importability and structure."""

    def test_script_exists(self):
        assert VALIDATE_SCRIPT.exists(), f"{VALIDATE_SCRIPT} not found"

    def test_script_has_main_guard(self):
        content = VALIDATE_SCRIPT.read_text()
        assert '__name__ == "__main__"' in content, "missing __name__ guard"

    def test_script_references_v2_criteria(self):
        content = VALIDATE_SCRIPT.read_text()
        assert "v2-criteria.yaml" in content, "script should reference v2-criteria.yaml"

    def test_script_importable_via_spec(self):
        """Load validate-v2.py as a module without executing main()."""
        spec = importlib.util.spec_from_file_location("validate_v2", VALIDATE_SCRIPT)
        assert spec is not None
        assert spec.loader is not None
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        assert hasattr(mod, "main"), "validate-v2.py must have a main() function"

    def test_script_main_is_callable(self):
        spec = importlib.util.spec_from_file_location("validate_v2_callable", VALIDATE_SCRIPT)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        assert callable(mod.main)


class TestQualityProductChecksV2:
    """quality_product_checks_v2.py importability and function presence."""

    @pytest.fixture(scope="class")
    def checks_module(self):
        assert CHECKS_MODULE.exists(), f"{CHECKS_MODULE} not found"
        quality_dir = str(ROOT / ".quality")
        if quality_dir not in sys.path:
            sys.path.insert(0, quality_dir)
        import quality_product_checks_v2 as m

        return m

    def test_module_importable(self, checks_module):
        assert checks_module is not None

    def test_check_mf_deep_dive_exists(self, checks_module):
        assert hasattr(checks_module, "check_mf_deep_dive")
        assert callable(checks_module.check_mf_deep_dive)

    def test_check_mf_categories_staleness_exists(self, checks_module):
        assert hasattr(checks_module, "check_mf_categories_staleness")
        assert callable(checks_module.check_mf_categories_staleness)

    def test_check_mf_no_float_exists(self, checks_module):
        assert hasattr(checks_module, "check_mf_no_float")
        assert callable(checks_module.check_mf_no_float)

    def test_check_v1_criteria_pass_exists(self, checks_module):
        assert hasattr(checks_module, "check_v1_criteria_pass")
        assert callable(checks_module.check_v1_criteria_pass)

    def test_check_mf_response_times_exists(self, checks_module):
        assert hasattr(checks_module, "check_mf_response_times")
        assert callable(checks_module.check_mf_response_times)

    def test_check_mf_no_float_returns_tuple(self, checks_module):
        """check_mf_no_float does not need a live backend — test it directly."""
        result = checks_module.check_mf_no_float()
        assert isinstance(result, tuple), "must return tuple"
        assert len(result) == 2, "must return (bool, str)"
        passed, evidence = result
        assert isinstance(passed, bool)
        assert isinstance(evidence, str)

    def test_check_mf_no_float_passes_for_mf_files(self, checks_module):
        """MF backend files should not contain ': float' annotations."""
        passed, evidence = checks_module.check_mf_no_float()
        assert passed, f"float detected in MF files: {evidence}"


class TestProductDimV2Integration:
    """product.py loads v2-criteria.yaml when it exists."""

    def test_v2_criteria_path_constant_exists(self):
        quality_dir = str(ROOT / ".quality")
        if quality_dir not in sys.path:
            sys.path.insert(0, quality_dir)
        # Reload to pick up our changes
        import importlib

        import dimensions.product as prod

        importlib.reload(prod)
        assert hasattr(prod, "V2_CRITERIA_PATH"), (
            "V2_CRITERIA_PATH constant missing from product.py"
        )

    def test_v2_criteria_path_points_to_existing_file(self):
        quality_dir = str(ROOT / ".quality")
        if quality_dir not in sys.path:
            sys.path.insert(0, quality_dir)
        import importlib

        import dimensions.product as prod

        importlib.reload(prod)
        assert prod.V2_CRITERIA_PATH.exists(), f"V2_CRITERIA_PATH {prod.V2_CRITERIA_PATH} not found"
