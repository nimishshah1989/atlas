"""S1 — dimension registry shared types + registration."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _load_dimensions_pkg():
    """Load .quality/dimensions/__init__.py (dir name starts with a dot, can't `import`)."""
    if "quality_dimensions" in sys.modules:
        return sys.modules["quality_dimensions"]
    spec = importlib.util.spec_from_file_location(
        "quality_dimensions",
        ROOT / ".quality" / "dimensions" / "__init__.py",
    )
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["quality_dimensions"] = mod
    spec.loader.exec_module(mod)
    return mod


def test_dimension_result_score_is_passed_over_eligible():
    dims = _load_dimensions_pkg()
    dim = dims.DimensionResult(
        "x",
        [
            dims.CheckResult("a", "A", 5, 10, "", "", "", "info"),
            dims.CheckResult("b", "B", 10, 10, "", "", "", "info"),
        ],
    )
    assert dim.passed == 15
    assert dim.eligible == 20
    assert dim.score == 75


def test_dimension_result_skipped_checks_excluded_from_eligible():
    dims = _load_dimensions_pkg()
    dim = dims.DimensionResult(
        "x",
        [
            dims.CheckResult("a", "A", 10, 10, "", "", "", "info", status="RUN"),
            dims.CheckResult("b", "B", 0, 10, "", "", "", "info", status="SKIP"),
        ],
    )
    # SKIP rows must not drag the score — only RUN rows count toward eligible.
    assert dim.passed == 10
    assert dim.eligible == 10
    assert dim.score == 100


def test_dimension_result_zero_eligible_returns_100():
    dims = _load_dimensions_pkg()
    dim = dims.DimensionResult("x", [])
    assert dim.score == 100
    assert dim.eligible == 0


def test_register_records_gating_flag():
    dims = _load_dimensions_pkg()
    dims.REGISTRY.clear()
    dims.GATING.clear()
    dims.register("foo", lambda: dims.DimensionResult("foo", []), gating=True)
    dims.register("bar", lambda: dims.DimensionResult("bar", []), gating=False)
    assert dims.GATING["foo"] is True
    assert dims.GATING["bar"] is False
    result = dims.run_dimension("bar")
    assert result.gating is False


def test_to_dict_shape_matches_s1_report():
    dims = _load_dimensions_pkg()
    dim = dims.DimensionResult(
        "code",
        [dims.CheckResult("c1", "x", 5, 10, "ev", "pe", "fix", "info")],
        gating=True,
    )
    out = dim.to_dict()
    assert set(out.keys()) == {
        "dimension",
        "score",
        "gating",
        "passed",
        "eligible",
        "checks",
    }
    assert out["dimension"] == "code"
    assert out["gating"] is True
    assert out["score"] == 50
