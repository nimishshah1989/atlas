"""Unit tests for V3 product quality checks and criteria.

Tests:
- check_simulation_no_float() returns (True, ...) — V3-1..V3-8 enforce no float
- check_simulation_no_print() returns (True, ...) — structlog only in services
- v3-criteria.yaml loads and has 5 criteria with required fields
- _extra_criteria_checks() returns [] gracefully for a missing file
- scripts/validate-v3.py exists
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]

# Ensure .quality/ is on sys.path for direct imports
_QUALITY_DIR = str(ROOT / ".quality")
if _QUALITY_DIR not in sys.path:
    sys.path.insert(0, _QUALITY_DIR)

from quality_product_checks_v3 import (  # noqa: E402
    check_simulation_no_float,
    check_simulation_no_print,
)
from dimensions.product import _extra_criteria_checks  # noqa: E402

V3_CRITERIA_PATH = ROOT / "docs" / "specs" / "v3-criteria.yaml"
VALIDATE_V3_SCRIPT = ROOT / "scripts" / "validate-v3.py"


class TestSimulationNoFloat:
    """check_simulation_no_float() correctness."""

    def test_check_simulation_no_float_returns_tuple(self) -> None:
        result = check_simulation_no_float()
        assert isinstance(result, tuple), "must return tuple"
        assert len(result) == 2, "must return (bool, str)"
        passed, evidence = result
        assert isinstance(passed, bool)
        assert isinstance(evidence, str)

    def test_check_simulation_no_float_passes(self) -> None:
        """V3-1..V3-8 enforce no float — scan must find zero violations."""
        passed, evidence = check_simulation_no_float()
        assert passed, f"float annotation found in simulation code: {evidence}"

    def test_check_simulation_no_float_evidence_non_empty(self) -> None:
        _, evidence = check_simulation_no_float()
        assert evidence, "evidence string must be non-empty"


class TestSimulationNoPrint:
    """check_simulation_no_print() correctness."""

    def test_check_simulation_no_print_returns_tuple(self) -> None:
        result = check_simulation_no_print()
        assert isinstance(result, tuple), "must return tuple"
        assert len(result) == 2, "must return (bool, str)"
        passed, evidence = result
        assert isinstance(passed, bool)
        assert isinstance(evidence, str)

    def test_check_simulation_no_print_passes(self) -> None:
        """Simulation services must use structlog — zero print() calls."""
        passed, evidence = check_simulation_no_print()
        assert passed, f"print() call found in simulation services: {evidence}"

    def test_check_simulation_no_print_evidence_non_empty(self) -> None:
        _, evidence = check_simulation_no_print()
        assert evidence, "evidence string must be non-empty"


class TestV3CriteriaYAML:
    """v3-criteria.yaml structure and content tests."""

    @pytest.fixture(scope="class")
    def criteria_data(self):
        pytest.importorskip("yaml", reason="pyyaml required")
        import yaml

        assert V3_CRITERIA_PATH.exists(), f"{V3_CRITERIA_PATH} not found"
        data = yaml.safe_load(V3_CRITERIA_PATH.read_text())
        assert data is not None
        return data

    def test_v3_criteria_loads(self, criteria_data) -> None:
        """File must load cleanly from YAML."""
        assert isinstance(criteria_data, dict)

    def test_v3_criteria_has_five_criteria(self, criteria_data) -> None:
        criteria = criteria_data.get("criteria", [])
        assert len(criteria) == 5, f"expected 5 criteria, got {len(criteria)}"

    def test_each_criterion_has_required_fields(self, criteria_data) -> None:
        for c in criteria_data["criteria"]:
            for field in ("id", "title", "check"):
                assert field in c, f"criterion {c.get('id', '?')} missing {field!r}"

    def test_each_check_has_type(self, criteria_data) -> None:
        for c in criteria_data["criteria"]:
            assert "type" in c["check"], f"criterion {c['id']} check missing 'type'"

    def test_criterion_ids_start_with_v3(self, criteria_data) -> None:
        for c in criteria_data["criteria"]:
            assert c["id"].startswith("v3-"), f"criterion id {c['id']!r} should start with 'v3-'"


class TestExtraCriteriaChecks:
    """_extra_criteria_checks() behaviour for edge cases."""

    def test_extra_criteria_checks_missing_file_returns_empty(self) -> None:
        result = _extra_criteria_checks(Path("/nonexistent/path/v99-criteria.yaml"))
        assert result == [], f"expected [], got {result}"

    def test_extra_criteria_checks_returns_list(self) -> None:
        result = _extra_criteria_checks(V3_CRITERIA_PATH)
        assert isinstance(result, list)

    def test_extra_criteria_checks_v3_count(self) -> None:
        """Should return one CheckResult per criterion in v3-criteria.yaml."""
        result = _extra_criteria_checks(V3_CRITERIA_PATH)
        assert len(result) == 5, f"expected 5 CheckResults, got {len(result)}"

    def test_extra_criteria_checks_each_has_check_id(self) -> None:
        result = _extra_criteria_checks(V3_CRITERIA_PATH)
        for check in result:
            assert check.check_id, f"CheckResult missing check_id: {check}"


class TestValidateV3Script:
    """scripts/validate-v3.py existence and structure."""

    def test_validate_v3_script_exists(self) -> None:
        assert VALIDATE_V3_SCRIPT.exists(), f"{VALIDATE_V3_SCRIPT} not found"

    def test_validate_v3_script_has_shebang(self) -> None:
        content = VALIDATE_V3_SCRIPT.read_text()
        assert content.startswith("#!/usr/bin/env python3"), "missing shebang"

    def test_validate_v3_script_has_main_guard(self) -> None:
        content = VALIDATE_V3_SCRIPT.read_text()
        assert '__name__ == "__main__"' in content, "missing __name__ guard"

    def test_validate_v3_script_references_v3_criteria(self) -> None:
        content = VALIDATE_V3_SCRIPT.read_text()
        assert "v3-criteria.yaml" in content
