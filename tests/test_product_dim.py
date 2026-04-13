"""Tests for the S3 product dimension + check-type handlers.

The product dim is wired to docs/specs/v1-criteria.yaml. These tests
exercise the dispatcher and each check type in isolation so regressions
in the declarative layer surface before they reach the forge dashboard.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
QUALITY_DIR = REPO_ROOT / ".quality"
if str(QUALITY_DIR) not in sys.path:
    sys.path.insert(0, str(QUALITY_DIR))

from dimensions import product  # type: ignore[import-not-found]  # noqa: E402
from dimensions.check_types import dispatch  # type: ignore[import-not-found]  # noqa: E402


def test_file_exists_handler_pass_and_fail() -> None:
    # Use a real repo file the handler can stat under ROOT.
    ok, ev = dispatch(
        {"type": "file_exists", "path": "README.md", "min_size_bytes": 100}
    )
    assert ok is True
    assert "README.md" in ev

    ok2, ev2 = dispatch({"type": "file_exists", "path": "does-not-exist.xyz"})
    assert ok2 is False
    assert "missing" in ev2


def test_dispatch_unknown_type() -> None:
    ok, ev = dispatch({"type": "totally_made_up"})
    assert ok is False
    assert "unknown check type" in ev


def test_sql_count_bad_query_returns_false_cleanly() -> None:
    # Invalid SQL against any DB — handler must catch, not raise.
    ok, ev = dispatch(
        {
            "type": "sql_count",
            "query": "SELECT * FROM definitely_not_a_table_xyz_atlas",
            "min": 1,
        }
    )
    assert ok is False
    assert any(
        s in ev for s in ("DATABASE_URL", "psycopg2", "query failed", "does not exist")
    )


def test_dim_product_loads_yaml_and_returns_checks() -> None:
    result = product.dim_product()
    assert result.dimension == "product"
    assert result.gating is False
    # The YAML ships with 15 criteria. If S3 is wired, we should see them.
    v1_ids = [c.check_id for c in result.checks if c.check_id.startswith("v1-")]
    assert len(v1_ids) == 15, f"expected 15 v1-XX criteria, got {len(v1_ids)}"
    # And no p0 stub when the YAML loads cleanly.
    assert not any(c.check_id == "p0" for c in result.checks)


def test_dim_product_skip_when_yaml_missing(monkeypatch) -> None:
    fake_missing = REPO_ROOT / "docs" / "specs" / "does-not-exist.yaml"
    monkeypatch.setattr(product, "CRITERIA_PATH", fake_missing)
    result = product.dim_product()
    assert result.checks and result.checks[0].check_id == "p0"
    assert result.checks[0].status == "SKIP"
    assert result.gating is False
