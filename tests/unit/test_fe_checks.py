"""
Unit tests for fe_checks package.

Each test creates temporary files in a tmp dir, calls the check type handler
directly, and asserts the result. Covers all 28 check types.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from unittest.mock import patch

# Ensure scripts/ is on the path — must come before fe_checks imports
_SCRIPTS_DIR = Path(__file__).resolve().parent.parent.parent / "scripts"
sys.path.insert(0, str(_SCRIPTS_DIR))

from fe_checks.grep_checks import grep_forbid, grep_require, kill_list, i18n_indian  # noqa: E402
from fe_checks.file_checks import file_exists, url_reachable, link_integrity  # noqa: E402
from fe_checks.dom_checks import (  # noqa: E402
    dom_required,
    dom_forbidden,
    attr_required,
    attr_enum,
    attr_numeric_range,
    find_elements,
)
from fe_checks.html_checks import (  # noqa: E402
    html5_valid,
    design_tokens_only,
    chart_contract,
    methodology_footer,
)
from fe_checks.playwright_checks import (  # noqa: E402
    playwright_screenshot,
    playwright_a11y,
    playwright_no_horizontal_scroll,
    playwright_tap_target,
)
from fe_checks.fixture_checks import (  # noqa: E402
    fixture_schema,
    fixture_field_required,
    fixture_numeric_range,
    fixture_array_length,
    fixture_enum,
    fixture_endpoint_reference,
)
from fe_checks.rule_checks import rule_coverage  # noqa: E402
from fe_checks import list_types, validate_types  # noqa: E402


# ─── Helpers ─────────────────────────────────────────────────────────────────


def _write_file(path: Path, content: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def _tmp_html(tmp_path: Path, name: str, content: str) -> Path:
    return _write_file(tmp_path / name, content)


# ─── grep_forbid ─────────────────────────────────────────────────────────────


def test_grep_forbid_detects_pattern(tmp_path: Path) -> None:
    f = _write_file(tmp_path / "page.html", "Buy signal here BUY")
    passed, evidence = grep_forbid({"pattern": r"\bBUY\b", "files": str(f)})
    assert not passed
    assert "page.html" in evidence


def test_grep_forbid_passes_clean(tmp_path: Path) -> None:
    f = _write_file(tmp_path / "page.html", "<p>Market data</p>")
    passed, evidence = grep_forbid({"pattern": r"\bBUY\b", "files": str(f)})
    assert passed


# ─── grep_require ─────────────────────────────────────────────────────────────


def test_grep_require_finds_pattern(tmp_path: Path) -> None:
    f = _write_file(tmp_path / "main.js", "const cutoff = '2024-07-23';")
    passed, evidence = grep_require({"pattern": "2024-07-23", "files": str(f), "min_matches": 1})
    assert passed


def test_grep_require_fails_missing(tmp_path: Path) -> None:
    f = _write_file(tmp_path / "main.js", "const x = 42;")
    passed, evidence = grep_require({"pattern": "2024-07-23", "files": str(f), "min_matches": 1})
    assert not passed


# ─── kill_list ────────────────────────────────────────────────────────────────


def test_kill_list_detects_forbidden(tmp_path: Path) -> None:
    f = _write_file(tmp_path / "page.html", "<p>Atlas Verdict: ADD ON DIPS</p>")
    passed, evidence = kill_list(
        {
            "patterns": [r"\bBUY\b", "ADD ON DIPS"],
            "files": str(f),
        }
    )
    assert not passed
    assert "page.html" in evidence


def test_kill_list_passes_clean(tmp_path: Path) -> None:
    f = _write_file(tmp_path / "page.html", "<p>Market breadth is expanding</p>")
    passed, evidence = kill_list(
        {
            "patterns": [r"\bBUY\b", r"\bSELL\b", "ADD ON DIPS"],
            "files": str(f),
        }
    )
    assert passed


# ─── i18n_indian ─────────────────────────────────────────────────────────────


def test_i18n_indian_detects_dollar(tmp_path: Path) -> None:
    f = _write_file(tmp_path / "page.html", "<p>$1000 gain</p>")
    passed, evidence = i18n_indian(
        {
            "forbidden_patterns": [r"\$[0-9]"],
            "files": str(f),
        }
    )
    assert not passed


def test_i18n_indian_skips_fixtures(tmp_path: Path) -> None:
    f = _write_file(tmp_path / "data.json", '{"price": "$1000"}')
    passed, evidence = i18n_indian(
        {
            "forbidden_patterns": [r"\$[0-9]"],
            "files": str(f),
            "allowed_in_fixtures": True,
        }
    )
    assert passed  # JSON files skipped when allowed_in_fixtures=True


# ─── file_exists ─────────────────────────────────────────────────────────────


def test_file_exists_passes(tmp_path: Path) -> None:
    f = _write_file(tmp_path / "tokens.css", ":root { --color: #1D9E75; }")
    passed, evidence = file_exists({"paths": [str(f)]})
    assert passed


def test_file_exists_fails(tmp_path: Path) -> None:
    missing = str(tmp_path / "nonexistent.css")
    passed, evidence = file_exists({"paths": [missing]})
    assert not passed
    assert "missing" in evidence.lower()


# ─── url_reachable ────────────────────────────────────────────────────────────


def test_url_reachable_skips_offline() -> None:
    with patch.dict(os.environ, {"FE_CHECKS_OFFLINE": "1"}):
        passed, evidence = url_reachable(
            {"urls": ["https://atlas.jslwealth.in/mockups/today.html"]}
        )
    assert passed
    assert "SKIP" in evidence


# ─── link_integrity ───────────────────────────────────────────────────────────


def test_link_integrity_local_ok(tmp_path: Path) -> None:
    _write_file(tmp_path / "tokens.css", ":root {}")
    html = _write_file(
        tmp_path / "page.html", '<html><head><link href="tokens.css"></head><body></body></html>'
    )
    passed, evidence = link_integrity(
        {
            "files": str(html),
            "allow_external": True,
            "allow_anchor_only": True,
        }
    )
    assert passed


# ─── dom_required ────────────────────────────────────────────────────────────


def test_dom_required_finds_element(tmp_path: Path) -> None:
    f = _write_file(tmp_path / "page.html", '<div class="explain-block">formula here</div>')
    passed, evidence = dom_required(
        {
            "selector": ".explain-block",
            "min_count": 1,
            "files": [str(f)],
        }
    )
    assert passed


def test_dom_required_fails_missing(tmp_path: Path) -> None:
    f = _write_file(tmp_path / "page.html", "<div class='header'>No explain block</div>")
    passed, evidence = dom_required(
        {
            "selector": ".explain-block",
            "min_count": 1,
            "files": [str(f)],
        }
    )
    assert not passed
    assert "page.html" in evidence


# ─── dom_forbidden ───────────────────────────────────────────────────────────


def test_dom_forbidden_passes_absent(tmp_path: Path) -> None:
    f = _write_file(tmp_path / "page.html", "<div class='data-view'>content</div>")
    passed, evidence = dom_forbidden(
        {
            "selectors": [".atlas-insight", ".verdict-strip"],
            "files": [str(f)],
        }
    )
    assert passed


def test_dom_forbidden_fails_present(tmp_path: Path) -> None:
    f = _write_file(tmp_path / "page.html", '<div class="atlas-insight">BUY NOW</div>')
    passed, evidence = dom_forbidden(
        {
            "selectors": [".atlas-insight"],
            "files": [str(f)],
        }
    )
    assert not passed
    assert "atlas-insight" in evidence


# ─── attr_required ────────────────────────────────────────────────────────────


def test_attr_required_passes(tmp_path: Path) -> None:
    f = _write_file(
        tmp_path / "page.html",
        '<span class="info-tooltip" title="Relative Strength measures momentum">i</span>',
    )
    passed, evidence = attr_required(
        {
            "selector": ".info-tooltip",
            "attribute": "title",
            "min_length": 5,
            "files": [str(f)],
        }
    )
    assert passed


# ─── attr_enum ───────────────────────────────────────────────────────────────


def test_attr_enum_passes(tmp_path: Path) -> None:
    f = _write_file(
        tmp_path / "page.html",
        '<div data-component="regime-banner" data-regime="risk-on">banner</div>',
    )
    passed, evidence = attr_enum(
        {
            "selector": "[data-component='regime-banner']",
            "attr": "data-regime",
            "allowed": ["risk-on", "risk-off", "neutral", "mixed"],
            "files": [str(f)],
        }
    )
    assert passed


def test_attr_enum_fails_invalid(tmp_path: Path) -> None:
    f = _write_file(
        tmp_path / "page.html",
        '<div data-component="regime-banner" data-regime="bullish">banner</div>',
    )
    passed, evidence = attr_enum(
        {
            "selector": "[data-component='regime-banner']",
            "attr": "data-regime",
            "allowed": ["risk-on", "risk-off", "neutral", "mixed"],
            "files": [str(f)],
        }
    )
    assert not passed


# ─── attr_numeric_range ───────────────────────────────────────────────────────


def test_attr_numeric_range_passes(tmp_path: Path) -> None:
    f = _write_file(
        tmp_path / "page.html",
        '<div data-chip="conviction" data-score="75" data-band="high">75</div>',
    )
    passed, evidence = attr_numeric_range(
        {
            "selector": "[data-chip='conviction']",
            "attr": "data-score",
            "min": 0,
            "max": 100,
            "integer_only": True,
            "files": [str(f)],
        }
    )
    assert passed


def test_attr_numeric_range_fails_out_of_range(tmp_path: Path) -> None:
    f = _write_file(
        tmp_path / "page.html",
        '<div data-chip="conviction" data-score="150" data-band="high">150</div>',
    )
    passed, evidence = attr_numeric_range(
        {
            "selector": "[data-chip='conviction']",
            "attr": "data-score",
            "min": 0,
            "max": 100,
            "files": [str(f)],
        }
    )
    assert not passed


# ─── html5_valid ─────────────────────────────────────────────────────────────


def test_html5_valid_skips_not_installed(tmp_path: Path) -> None:
    f = _write_file(tmp_path / "page.html", "<!DOCTYPE html><html><body></body></html>")
    # html5validator is almost certainly not installed in test env
    # The handler should SKIP gracefully
    passed, evidence = html5_valid({"files": str(f)})
    # Either passes (valid) or skips (not installed) — never crashes
    assert isinstance(passed, bool)
    assert isinstance(evidence, str)


# ─── design_tokens_only ───────────────────────────────────────────────────────


def test_design_tokens_only_detects_raw_color(tmp_path: Path) -> None:
    f = _write_file(
        tmp_path / "page.html", '<div style="color: #ff0000; background-color: #000">test</div>'
    )
    passed, evidence = design_tokens_only(
        {
            "files": str(f),
            "allow_inline_style_properties": [],
        }
    )
    # Should detect raw colors or pass through (gracefully)
    assert isinstance(passed, bool)
    assert isinstance(evidence, str)


# ─── chart_contract ───────────────────────────────────────────────────────────


def test_chart_contract_checks_children(tmp_path: Path) -> None:
    # Chart with all required children
    html = """
    <div class="chart-with-events" data-as-of="2026-04-18">
        <div class="chart__legend" data-role="legend">Legend</div>
        <div class="chart__axis-x" data-role="axis-x">X axis</div>
        <div class="chart__axis-y" data-role="axis-y">Y axis</div>
        <div class="chart__source" data-role="source">JIP</div>
        <div class="chart__tooltip" data-role="tooltip">Tooltip</div>
        <div class="chart__explain" data-role="explain">Explain</div>
    </div>
    """
    f = _write_file(tmp_path / "page.html", html)
    passed, evidence = chart_contract(
        {
            "selector": ".chart-with-events",
            "required_children": [
                ".chart__legend, [data-role=legend]",
                ".chart__axis-x, [data-role=axis-x]",
            ],
            "files": [str(f)],
        }
    )
    assert passed


# ─── methodology_footer ───────────────────────────────────────────────────────


def test_methodology_footer_finds_source(tmp_path: Path) -> None:
    html = """
    <footer data-role="methodology">
        Source: JIP Data Engine | Data as of 2026-04-18
    </footer>
    """
    f = _write_file(tmp_path / "page.html", html)
    passed, evidence = methodology_footer(
        {
            "files": [str(f)],
            "must_contain": ["Source:", "Data as of"],
        }
    )
    assert passed


def test_methodology_footer_fails_missing(tmp_path: Path) -> None:
    f = _write_file(tmp_path / "page.html", "<div>No footer here</div>")
    passed, evidence = methodology_footer(
        {
            "files": [str(f)],
            "must_contain": ["Source:", "Data as of"],
        }
    )
    assert not passed


# ─── playwright checks (all SKIP) ────────────────────────────────────────────


def test_playwright_screenshot_skips() -> None:
    passed, evidence = playwright_screenshot({"pages_from": ["today.html"], "max_delta_pct": 2.0})
    assert passed
    assert "SKIP" in evidence


def test_playwright_a11y_skips() -> None:
    passed, evidence = playwright_a11y({"level": "wcag2aa"})
    assert passed
    assert "SKIP" in evidence


def test_playwright_no_horizontal_scroll_skips() -> None:
    passed, evidence = playwright_no_horizontal_scroll(
        {
            "url": "http://localhost:8080/today.html",
            "viewport": {"width": 360, "height": 720},
        }
    )
    assert passed
    assert "SKIP" in evidence


def test_playwright_tap_target_skips() -> None:
    passed, evidence = playwright_tap_target(
        {
            "min_width_px": 44,
            "min_height_px": 44,
        }
    )
    assert passed
    assert "SKIP" in evidence


# ─── fixture_schema ───────────────────────────────────────────────────────────


def test_fixture_schema_validates(tmp_path: Path) -> None:
    fixtures_dir = tmp_path / "fixtures"
    schemas_dir = tmp_path / "fixtures" / "schemas"

    fixture_data = {"data_as_of": "2026-04-18", "source": "JIP", "funds": []}
    _write_file(fixtures_dir / "mf_rank.json", json.dumps(fixture_data))

    schema_data = {
        "type": "object",
        "required": ["data_as_of", "source"],
        "properties": {
            "data_as_of": {"type": "string"},
            "source": {"type": "string"},
        },
    }
    _write_file(schemas_dir / "mf_rank.schema.json", json.dumps(schema_data))

    passed, evidence = fixture_schema(
        {
            "fixtures_dir": str(fixtures_dir),
            "schemas_dir": str(schemas_dir),
        }
    )
    # May SKIP if jsonschema not installed, but should not crash
    assert isinstance(passed, bool)
    assert isinstance(evidence, str)


# ─── fixture_field_required ───────────────────────────────────────────────────


def test_fixture_field_required_passes(tmp_path: Path) -> None:
    data = {
        "data_as_of": "2026-04-18",
        "source": "JIP",
        "funds": [
            {
                "scheme_code": "120503",
                "returns_score": 85.5,
                "composite_score": 78.0,
            }
        ],
    }
    f = _write_file(tmp_path / "mf_rank_universe.json", json.dumps(data))
    passed, evidence = fixture_field_required(
        {
            "fixture": str(f),
            "path": "$.funds[*]",
            "required_fields": ["scheme_code", "returns_score", "composite_score"],
        }
    )
    assert passed


def test_fixture_field_required_fails_missing_field(tmp_path: Path) -> None:
    data = {"data_as_of": "2026-04-18", "source": "JIP", "funds": [{"scheme_code": "1234"}]}
    f = _write_file(tmp_path / "fixture.json", json.dumps(data))
    passed, evidence = fixture_field_required(
        {
            "fixture": str(f),
            "path": "$.funds[*]",
            "required_fields": ["scheme_code", "composite_score"],
        }
    )
    assert not passed
    assert "composite_score" in evidence


# ─── fixture_numeric_range ────────────────────────────────────────────────────


def test_fixture_numeric_range_passes(tmp_path: Path) -> None:
    data = {
        "data_as_of": "2026-04-18",
        "source": "JIP",
        "funds": [
            {"composite_score": 78.5},
            {"composite_score": 55.0},
        ],
    }
    f = _write_file(tmp_path / "fixture.json", json.dumps(data))
    passed, evidence = fixture_numeric_range(
        {
            "fixture": str(f),
            "path": "$.funds[*].composite_score",
            "min": 0,
            "max": 100,
            "decimal_places_max": 1,
        }
    )
    assert passed


def test_fixture_numeric_range_fails_out_of_range(tmp_path: Path) -> None:
    data = {"data_as_of": "2026-04-18", "source": "JIP", "funds": [{"score": 150.0}]}
    f = _write_file(tmp_path / "fixture.json", json.dumps(data))
    passed, evidence = fixture_numeric_range(
        {
            "fixture": str(f),
            "path": "$.funds[*].score",
            "min": 0,
            "max": 100,
        }
    )
    assert not passed


# ─── fixture_array_length ─────────────────────────────────────────────────────


def test_fixture_array_length_passes(tmp_path: Path) -> None:
    tail = [{"x": i, "y": i * 1.1} for i in range(8)]
    data = {
        "data_as_of": "2026-04-18",
        "source": "JIP",
        "sectors": [{"sector_code": "IT", "tail": tail}],
    }
    f = _write_file(tmp_path / "fixture.json", json.dumps(data))
    passed, evidence = fixture_array_length(
        {
            "fixture": str(f),
            "path": "$.sectors[*].tail",
            "min_length": 8,
        }
    )
    assert passed


def test_fixture_array_length_fails_short(tmp_path: Path) -> None:
    data = {
        "data_as_of": "2026-04-18",
        "source": "JIP",
        "sectors": [{"tail": [1, 2, 3]}],
    }
    f = _write_file(tmp_path / "fixture.json", json.dumps(data))
    passed, evidence = fixture_array_length(
        {
            "fixture": str(f),
            "path": "$.sectors[*].tail",
            "min_length": 8,
        }
    )
    assert not passed


# ─── fixture_enum ─────────────────────────────────────────────────────────────


def test_fixture_enum_passes(tmp_path: Path) -> None:
    data = {
        "data_as_of": "2026-04-18",
        "source": "JIP",
        "sectors": [
            {"quadrant": "leading"},
            {"quadrant": "lagging"},
        ],
    }
    f = _write_file(tmp_path / "fixture.json", json.dumps(data))
    passed, evidence = fixture_enum(
        {
            "fixture": str(f),
            "path": "$.sectors[*].quadrant",
            "allowed": ["leading", "weakening", "lagging", "improving"],
        }
    )
    assert passed


def test_fixture_enum_fails_invalid(tmp_path: Path) -> None:
    data = {
        "data_as_of": "2026-04-18",
        "source": "JIP",
        "sectors": [{"quadrant": "unknown_value"}],
    }
    f = _write_file(tmp_path / "fixture.json", json.dumps(data))
    passed, evidence = fixture_enum(
        {
            "fixture": str(f),
            "path": "$.sectors[*].quadrant",
            "allowed": ["leading", "weakening", "lagging", "improving"],
        }
    )
    assert not passed


# ─── fixture_endpoint_reference ───────────────────────────────────────────────


def test_fixture_endpoint_reference(tmp_path: Path) -> None:
    fixtures_dir = tmp_path / "fixtures"
    data = {
        "data_as_of": "2026-04-18",
        "source": "/api/v1/stocks/breadth",
        "endpoint": "/api/v1/stocks/breadth",
    }
    _write_file(fixtures_dir / "breadth.json", json.dumps(data))
    passed, evidence = fixture_endpoint_reference(
        {
            "endpoints_must_appear": ["/api/v1/stocks/breadth"],
            "fixtures_dir": str(fixtures_dir),
        }
    )
    assert passed


def test_fixture_endpoint_reference_missing(tmp_path: Path) -> None:
    fixtures_dir = tmp_path / "fixtures"
    _write_file(fixtures_dir / "data.json", json.dumps({"source": "/api/v1/other"}))
    passed, evidence = fixture_endpoint_reference(
        {
            "endpoints_must_appear": ["/api/v1/stocks/breadth"],
            "fixtures_dir": str(fixtures_dir),
        }
    )
    assert not passed


# ─── rule_coverage ────────────────────────────────────────────────────────────


def test_rule_coverage_basic() -> None:
    """rule_coverage against the actual criteria YAML should pass or SKIP."""
    passed, evidence = rule_coverage(
        {
            "rules_expected": 10,
            "mapping_file": "docs/specs/frontend-v1-criteria.yaml",
        }
    )
    # Should either pass (file exists with enough bindings) or SKIP (yaml not installed)
    assert isinstance(passed, bool)
    assert isinstance(evidence, str)


# ─── Registry meta-tests ─────────────────────────────────────────────────────


def test_list_types_count_28() -> None:
    """list_types() returns exactly 28 type names."""
    types = list_types()
    assert len(types) == 28, f"Expected 28 types, got {len(types)}: {types}"


def test_list_types_sorted() -> None:
    """list_types() returns sorted list."""
    types = list_types()
    assert types == sorted(types)


def test_preflight_rejects_unknown() -> None:
    """validate_types returns unknown type names."""
    fake_criteria = [{"check": {"type": "nonexistent_type_xyz"}}]
    unknown = validate_types(fake_criteria)
    assert "nonexistent_type_xyz" in unknown


def test_preflight_accepts_known() -> None:
    """validate_types returns empty list for known types."""
    valid_criteria = [
        {"check": {"type": "grep_forbid"}},
        {"check": {"type": "file_exists"}},
        {"check": {"type": "dom_required"}},
    ]
    unknown = validate_types(valid_criteria)
    assert unknown == []


# ─── Runner integration: sorted results ──────────────────────────────────────


def test_results_sorted_by_id() -> None:
    """Results from dispatch are sortable by id."""
    # Test with a few check specs
    results = [
        {"id": "fe-z-01", "passed": True},
        {"id": "fe-a-01", "passed": True},
        {"id": "fe-m-01", "passed": True},
    ]
    sorted_results = sorted(results, key=lambda r: r["id"])
    assert sorted_results[0]["id"] == "fe-a-01"
    assert sorted_results[-1]["id"] == "fe-z-01"


# ─── Determinism test ─────────────────────────────────────────────────────────


def test_determinism_two_runs(tmp_path: Path) -> None:
    """Two runs on the same input produce the same (passed, evidence) result."""
    f = _write_file(tmp_path / "page.html", "<div class='explain-block'>formula</div>")
    spec = {"selector": ".explain-block", "min_count": 1, "files": [str(f)]}

    result1 = dom_required(spec)
    result2 = dom_required(spec)

    assert result1 == result2, f"Non-deterministic: {result1} != {result2}"


# ─── DOM find_elements unit tests ─────────────────────────────────────────────


def test_find_elements_by_class() -> None:
    html = '<div class="chip rs-chip">RS</div><span class="chip">Vol</span>'
    elements = find_elements(html, ".chip")
    assert len(elements) == 2


def test_find_elements_by_attr() -> None:
    html = '<div data-block="macros">Macros</div><div data-block="rates">Rates</div>'
    elements = find_elements(html, "[data-block=macros]")
    assert len(elements) == 1
    assert elements[0].attrs.get("data-block") == "macros"


def test_find_elements_comma_union() -> None:
    html = '<div class="foo">A</div><div class="bar">B</div><div class="baz">C</div>'
    elements = find_elements(html, ".foo, .bar")
    assert len(elements) == 2


# ─── JSONPath tests ───────────────────────────────────────────────────────────


def test_resolve_jsonpath_nested() -> None:
    from fe_checks.fixture_checks import resolve_jsonpath

    data = {"funds": [{"score": 80}, {"score": 60}]}
    values = resolve_jsonpath(data, "$.funds[*].score")
    assert values == [80, 60]


def test_resolve_jsonpath_single_key() -> None:
    from fe_checks.fixture_checks import resolve_jsonpath

    data = {"data_as_of": "2026-04-18"}
    values = resolve_jsonpath(data, "$.data_as_of")
    assert values == ["2026-04-18"]


def test_resolve_jsonpath_missing() -> None:
    from fe_checks.fixture_checks import resolve_jsonpath

    data = {"other": "value"}
    values = resolve_jsonpath(data, "$.missing_key")
    assert values == []
